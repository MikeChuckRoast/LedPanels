#!/usr/bin/env python3
"""
animation_display.py

Play a looping animation — a GIF or a video clip — on the LED panels.

The clip is decoded once at startup into panel-sized frames (see
animation_loader.py), then blitted in a wall-clock-driven loop. Frames are
dropped rather than queued when the panel cannot keep up, so a 30fps source
plays at the correct speed on hardware that can only push 7fps instead of
running in slow motion.

Usage:
    python animation_display.py --config-dir ./config --file logo.gif
"""

import argparse
import bisect
import logging
import signal
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

from animation_loader import (DEFAULT_MAX_FRAMES, FIT_MODES, AnimationError,
                              load_animation)
from config_loader import ConfigError, load_mode_config, load_settings
from event_parser import parse_hex_color
from matrix_backend import get_matrix_backend

# Animations uploaded through the web UI live here, under the config directory.
ANIMATIONS_DIRNAME = "animations"

# Floor on a frame's on-screen time. Guards against a zero-duration frame
# collapsing the schedule and spinning the playback loop.
MIN_FRAME_DURATION = 0.001

# Longest single sleep in the playback loop. Bounds how long shutdown and
# source-change detection wait, without busy-looping between frames.
MAX_SLEEP = 0.25

# Floor on every pass through the playback loop, which guarantees progress.
#
# Frame boundaries are accumulated floats and elapsed time is a difference of
# two large monotonic readings, so the two routinely land within rounding error
# of each other — sometimes exactly equal. Sleeping only when there is strictly
# positive time left then spins the loop hot against the clock. A 1ms floor
# bounds that at 1000 iterations a second and is invisible next to a panel
# write measured in tens or hundreds of milliseconds.
MIN_SLEEP = 0.001

# How often the playback loop stats the source file to notice a re-upload.
SOURCE_CHECK_INTERVAL = 2.0


class FrameScheduler:
    """Maps elapsed wall-clock time onto frame indices.

    Playback asks "what should be on screen *now*" rather than stepping frame
    by frame. If a panel write overruns its frame budget the next lookup simply
    returns a later index, so the clip keeps correct time by dropping frames.
    """

    def __init__(self, durations: List[float], loop: bool = True):
        self.loop = loop
        self._boundaries: List[float] = []
        total = 0.0
        for duration in durations:
            total += max(float(duration), MIN_FRAME_DURATION)
            self._boundaries.append(total)
        self.total = total

    def __len__(self) -> int:
        return len(self._boundaries)

    def frame_at(self, elapsed: float) -> Optional[int]:
        """Index of the frame due at *elapsed* seconds, or None once finished."""
        if not self._boundaries:
            return None
        elapsed = max(0.0, elapsed)
        if self.loop:
            elapsed %= self.total
        elif elapsed >= self.total:
            return None
        # Boundaries hold each frame's end time, so frame i spans
        # [boundaries[i-1], boundaries[i]). min() guards the float edge case
        # where elapsed lands a hair past the last boundary.
        return min(bisect.bisect_right(self._boundaries, elapsed), len(self._boundaries) - 1)

    def next_boundary(self, elapsed: float) -> Optional[float]:
        """Elapsed time at which the on-screen frame next changes, or None."""
        if not self._boundaries:
            return None
        elapsed = max(0.0, elapsed)
        if not self.loop:
            if elapsed >= self.total:
                return None
            index = self.frame_at(elapsed)
            return self._boundaries[index]
        completed, position = divmod(elapsed, self.total)
        index = min(bisect.bisect_right(self._boundaries, position),
                    len(self._boundaries) - 1)
        return completed * self.total + self._boundaries[index]


def resolve_animation_path(config_dir: str, file_setting: str) -> Path:
    """Resolve a configured animation filename to a path.

    Bare filenames resolve inside <config_dir>/animations/, which is where the
    web UI puts uploads. Absolute paths are taken as given so a clip can live
    anywhere.
    """
    if not file_setting or not file_setting.strip():
        raise AnimationError(
            "No animation file configured. Set [mode.animation_display].file "
            "in settings.toml, or upload one from the web UI."
        )

    candidate = Path(file_setting.strip()).expanduser()
    if candidate.is_absolute():
        return candidate

    animations_dir = Path(config_dir) / ANIMATIONS_DIRNAME
    # A bare name belongs in animations/; anything with a separator is treated
    # as relative to the config directory.
    if candidate.parent == Path("."):
        return animations_dir / candidate
    return Path(config_dir) / candidate


def _source_fingerprint(path: Path):
    """Return (mtime, size), or None if the file is gone."""
    try:
        stat = path.stat()
        return stat.st_mtime, stat.st_size
    except OSError:
        return None


def play(matrix, canvas, animation, scheduler: FrameScheduler,
         stop_event: threading.Event, source: Optional[Path] = None,
         clock=time.monotonic):
    """Run the playback loop.

    Returns (outcome, canvas), where outcome is 'finished' when a non-looping
    clip ran out, 'reload' when the source file changed on disk, or 'stopped'
    on shutdown. The canvas comes back because a real rgbmatrix hands out the
    other half of its double buffer on every swap.

    *clock* is injectable so tests can drive playback deterministically rather
    than sleeping through it.
    """
    start = clock()
    last_index = None
    rendered = 0
    reported = False
    fingerprint = _source_fingerprint(source) if source else None
    next_source_check = start + SOURCE_CHECK_INTERVAL

    def report_first_pass(elapsed):
        """Log achieved vs source frame rate once a full pass has elapsed.

        Checked before the end-of-clip return so a one-shot clip reports too,
        not just a looping one.
        """
        logging.info(
            "First pass: rendered %d of %d frames (%.1f fps achieved, %.1f fps in source)",
            rendered, len(animation), rendered / elapsed, len(animation) / scheduler.total)
        if rendered < len(animation) * 0.9:
            logging.info(
                "Dropping frames to hold real-time speed — the panel write "
                "is the limit. See [network].colorlight_row_delay_ms.")

    while not stop_event.is_set():
        now = clock()
        elapsed = now - start

        # One pass through the clip is enough to tell whether the backend can
        # keep up. Worth saying out loud — a low number here is the panel's
        # write path, not the decode.
        if not reported and elapsed >= scheduler.total > 0:
            reported = True
            report_first_pass(elapsed)

        index = scheduler.frame_at(elapsed)
        if index is None:
            return "finished", canvas

        if index != last_index:
            canvas.SetImage(animation.frames[index])
            try:
                canvas = matrix.SwapOnVSync(canvas)
            except Exception as exc:
                logging.exception("SwapOnVSync failed: %s", exc)
            last_index = index
            rendered += 1

        if source is not None and now >= next_source_check:
            next_source_check = now + SOURCE_CHECK_INTERVAL
            current = _source_fingerprint(source)
            if current is not None and current != fingerprint:
                logging.info("Animation source changed on disk — reloading")
                return "reload", canvas

        boundary = scheduler.next_boundary(clock() - start)
        if boundary is None:
            return "finished", canvas
        # Unconditional: a negative delay means the panel is running behind and
        # the next frame is already due, but the loop must still yield or it
        # will spin. See MIN_SLEEP.
        delay = boundary - (clock() - start)
        stop_event.wait(min(max(delay, MIN_SLEEP), MAX_SLEEP))

    return "stopped", canvas


def main():
    # force=True because importing colorlight_output warns at module scope on
    # any platform without AF_PACKET (Windows), which installs a root handler
    # and makes a plain basicConfig() a no-op — swallowing every INFO line,
    # including the achieved-frame-rate report.
    logging.basicConfig(level=logging.INFO, force=True,
                        format='[%(asctime)s] %(levelname)s: %(message)s')

    # Pre-parse config-dir so settings can seed the real parser's defaults.
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument('--config-dir', default='./config')
    pre_args, _ = pre_parser.parse_known_args()
    config_dir = pre_args.config_dir

    try:
        settings = load_settings(config_dir)
        hw = settings.get('hardware', {})
        net = settings.get('network', {})
    except ConfigError as exc:
        logging.warning("Could not load config: %s. Using defaults.", exc)
        hw = {}
        net = {}

    try:
        mode_cfg = load_mode_config(config_dir, 'animation_display')
    except ConfigError:
        mode_cfg = {}

    parser = argparse.ArgumentParser(description="Play an animation on the LED panels")
    parser.add_argument('--config-dir', default='./config',
                        help='Path to configuration directory (default: ./config)')
    parser.add_argument('--file', default=mode_cfg.get('file', ''),
                        help='Animation file; a bare name resolves inside config/animations/')
    parser.add_argument('--fit', choices=FIT_MODES, default=mode_cfg.get('fit', 'contain'),
                        help='How to scale the clip onto the panel (default: contain)')
    parser.add_argument('--fps', type=float, default=mode_cfg.get('fps', 0),
                        help='Override source frame rate; 0 keeps the source timing')
    parser.add_argument('--background', default=mode_cfg.get('background', '#000000'),
                        help='Hex fill behind letterboxing and transparency')
    parser.add_argument('--max-frames', type=int,
                        default=mode_cfg.get('max_frames', DEFAULT_MAX_FRAMES),
                        help=f'Cap on decoded frames (default: {DEFAULT_MAX_FRAMES})')
    parser.add_argument('--no-loop', dest='loop', action='store_false',
                        default=mode_cfg.get('loop', True),
                        help='Play once and exit instead of looping')
    # SUPPRESS so this alias does not clobber --no-loop's default, which is
    # where the configured value arrives.
    parser.add_argument('--once', dest='loop', action='store_false',
                        default=argparse.SUPPRESS,
                        help='Alias for --no-loop, matching the other modes')
    parser.add_argument('--ffmpeg', default=mode_cfg.get('ffmpeg', ''),
                        help='Path to the ffmpeg binary (default: search PATH)')
    parser.add_argument('--width', type=int, default=hw.get('width', 64),
                        help='Single panel width in pixels')
    parser.add_argument('--height', type=int, default=hw.get('height', 32),
                        help='Single panel height in pixels')
    parser.add_argument('--chain', type=int, default=hw.get('chain', 2),
                        help='Panels chained horizontally')
    parser.add_argument('--parallel', type=int, default=hw.get('parallel', 4),
                        help='Panels stacked vertically')
    parser.add_argument('--gpio-slowdown', type=int, default=hw.get('gpio_slowdown', 3),
                        help='GPIO slowdown for RGBMatrixOptions')
    parser.add_argument('--fpp', action='store_true', default=net.get('fpp_enabled', False),
                        help='Use FPP output instead of direct matrix control')
    parser.add_argument('--fpp-host', default=net.get('fpp_host', '127.0.0.1'),
                        help='FPP host IP address')
    parser.add_argument('--fpp-port', type=int, default=net.get('fpp_port', 4048),
                        help='FPP DDP port')
    parser.add_argument('--colorlight', action='store_true',
                        default=net.get('colorlight_enabled', False),
                        help='Send frames to ColorLight 5A-75B via raw Ethernet')
    parser.add_argument('--colorlight-interface', default=net.get('colorlight_interface', 'eth0'),
                        help='Network interface for ColorLight (e.g., eth0)')
    parser.add_argument('--colorlight-row-delay-ms', type=float,
                        default=net.get('colorlight_row_delay_ms', 1.0),
                        help='Per-row pacing delay for ColorLight; lower is faster but '
                             'too low tears frames')
    args = parser.parse_args()

    try:
        background = parse_hex_color(args.background)
    except ValueError as exc:
        logging.error("Invalid --background: %s", exc)
        sys.exit(1)

    try:
        source = resolve_animation_path(args.config_dir, args.file)
    except AnimationError as exc:
        logging.error("%s", exc)
        sys.exit(1)

    canvas_width = args.width * args.chain
    canvas_height = args.height * args.parallel

    matrix_classes = get_matrix_backend(
        use_fpp=args.fpp,
        fpp_host=args.fpp_host,
        fpp_port=args.fpp_port,
        use_colorlight=args.colorlight,
        colorlight_interface=args.colorlight_interface,
        colorlight_row_delay_ms=args.colorlight_row_delay_ms,
        width=args.width,
        height=args.height,
    )
    RGBMatrix, RGBMatrixOptions, _graphics = matrix_classes
    if RGBMatrix is None:
        logging.error("No rgbmatrix backend available")
        sys.exit(1)

    options = RGBMatrixOptions()
    options.rows = args.height
    options.cols = args.width
    options.chain_length = args.chain
    options.parallel = args.parallel
    options.gpio_slowdown = args.gpio_slowdown

    # The backend constructor is where a wrong or unavailable output shows up —
    # ColorLight on Windows, a down interface, missing privileges. Report it as
    # one line; the manager restarts on a loop, and a traceback per attempt
    # buries the journal without saying anything the message does not.
    try:
        matrix = RGBMatrix(options=options)
        canvas = matrix.CreateFrameCanvas()
    except Exception as exc:
        logging.error("Could not initialise the matrix backend: %s", exc)
        sys.exit(1)

    # A backend built before SetImage existed would fall back to a per-pixel
    # loop, which cannot sustain animation. Fail loudly rather than crawl.
    if not hasattr(canvas, 'SetImage'):
        logging.error("The active matrix backend has no SetImage(); cannot play animation")
        sys.exit(1)

    stop_event = threading.Event()

    def _handle_signal(sig, _frame):
        logging.info("Received signal %s, stopping playback…", sig)
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logging.info("Panel %dx%d, source %s, fit=%s, loop=%s",
                 canvas_width, canvas_height, source, args.fit, args.loop)

    exit_code = 0
    try:
        while not stop_event.is_set():
            try:
                animation = load_animation(
                    source,
                    canvas_width,
                    canvas_height,
                    fit=args.fit,
                    fps=max(0.0, args.fps),
                    background=background,
                    max_frames=max(1, args.max_frames),
                    ffmpeg_path=args.ffmpeg or None,
                )
            except AnimationError as exc:
                logging.error("%s", exc)
                exit_code = 1
                break

            scheduler = FrameScheduler(animation.durations, loop=args.loop)
            outcome, canvas = play(matrix, canvas, animation, scheduler, stop_event, source)
            if outcome == 'finished':
                logging.info("Playback finished")
                break
            if outcome == 'stopped':
                break
            # 'reload' — fall through and decode the new file
    finally:
        # Clear the canvas rather than the matrix: on a real rgbmatrix the two
        # are different objects, and swapping in an uncleared canvas after
        # matrix.Clear() would put the last frame straight back up.
        try:
            canvas.Clear()
            matrix.SwapOnVSync(canvas)
        except Exception as exc:
            logging.debug("Could not blank panel on exit: %s", exc)
        logging.info("Animation display stopped")

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
