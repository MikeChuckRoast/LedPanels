"""
Animation decoding for the animation_display mode.

Turns a GIF or a video file into a list of panel-sized RGB frames plus the
duration each one should be held for. Two decoders sit behind one entry point:

  - GIF / APNG / animated WebP via Pillow, which is already a dependency
  - MP4 / MOV / WebM / MKV via a pipe to the system ffmpeg binary

Everything is decoded once, up front, and scaled to the panel while it is
decoded. Playback then costs nothing but a blit, which matters because the
panel write itself is the bottleneck (see colorlight_output.DEFAULT_ROW_DELAY_MS).
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageSequence

# Decoded by Pillow.
IMAGE_EXTENSIONS = {".gif", ".webp", ".png", ".apng"}
# Decoded by piping through ffmpeg.
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi"}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

FIT_MODES = ("contain", "cover", "stretch")

# Frames beyond this are dropped, with a warning. A 128x128 RGB frame is 48KB,
# so this bounds a clip at roughly 30MB of resident memory.
DEFAULT_MAX_FRAMES = 600

# Rate at which video is decoded when no explicit fps is configured.
#
# Deliberately low: ffmpeg's fps filter resamples in time, so decoding a 30fps
# source at 15fps plays at the same speed with half the frames — the same
# frame-dropping the scheduler would do at playback, but done once and more
# cheaply. 15 is comfortably above what any supported backend can push.
DEFAULT_VIDEO_FPS = 15.0

# A GIF frame delay at or below this is treated as "unspecified" and replaced
# with FALLBACK_FRAME_DURATION, which is what browsers do. Authoring tools
# routinely emit 0 for "as fast as possible".
MIN_MEANINGFUL_DELAY_SEC = 0.01
FALLBACK_FRAME_DURATION = 0.1


class AnimationError(Exception):
    """Raised when an animation file cannot be read or decoded."""


@dataclass
class Animation:
    """A decoded, panel-sized animation ready to blit."""

    frames: List[Image.Image] = field(repr=False)
    durations: List[float]
    width: int
    height: int
    source: str = ""
    truncated: bool = False

    def __len__(self) -> int:
        return len(self.frames)

    @property
    def total_duration(self) -> float:
        return sum(self.durations)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def scaled_size(src_w: int, src_h: int, width: int, height: int, fit: str) -> Tuple[int, int]:
    """Return the size *fit* scales a src_w x src_h source to.

    'contain' fits inside the panel (letterboxed), 'cover' fills it (cropped),
    'stretch' ignores aspect ratio. Kept separate from fit_frame so the ffmpeg
    filter graph and the Pillow path can be checked against the same maths.
    """
    if fit not in FIT_MODES:
        raise AnimationError(f"Unknown fit mode '{fit}'. Valid: {', '.join(FIT_MODES)}")
    if src_w <= 0 or src_h <= 0:
        raise AnimationError(f"Invalid source dimensions: {src_w}x{src_h}")

    if fit == "stretch":
        return width, height

    scale = min(width / src_w, height / src_h) if fit == "contain" \
        else max(width / src_w, height / src_h)
    # Round up so 'cover' never leaves a sub-pixel gap at an edge.
    return max(1, round(src_w * scale)), max(1, round(src_h * scale))


def fit_frame(image: Image.Image, width: int, height: int, fit: str = "contain",
              background: Sequence[int] = (0, 0, 0)) -> Image.Image:
    """Scale *image* to exactly width x height under the given fit mode."""
    new_w, new_h = scaled_size(image.width, image.height, width, height, fit)
    resized = image.resize((new_w, new_h), Image.LANCZOS)

    if (new_w, new_h) == (width, height):
        return resized

    if fit == "cover":
        # Centre-crop the overflow.
        left = (new_w - width) // 2
        top = (new_h - height) // 2
        return resized.crop((left, top, left + width, top + height))

    # contain: centre on a background-filled canvas.
    canvas = Image.new("RGB", (width, height), tuple(background))
    canvas.paste(resized, ((width - new_w) // 2, (height - new_h) // 2))
    return canvas


# ---------------------------------------------------------------------------
# Pillow path — GIF, APNG, animated WebP
# ---------------------------------------------------------------------------

def _load_with_pillow(path: Path, width: int, height: int, fit: str, fps: float,
                      background: Sequence[int], max_frames: int) -> Animation:
    try:
        img = Image.open(path)
    except Exception as exc:
        raise AnimationError(f"Could not open image '{path.name}': {exc}") from exc

    frames: List[Image.Image] = []
    durations: List[float] = []
    truncated = False

    with img:
        for frame in ImageSequence.Iterator(img):
            if len(frames) >= max_frames:
                truncated = True
                break

            # The iterator hands back a fully composited frame at the image's
            # own size, with GIF disposal already applied. Transparency is not
            # resolved though, so flatten onto the background colour before the
            # resize — otherwise transparent pixels arrive as black regardless
            # of what the background is set to.
            rgba = frame.convert("RGBA")
            flat = Image.new("RGBA", rgba.size, tuple(background) + (255,))
            flat.alpha_composite(rgba)
            frames.append(fit_frame(flat.convert("RGB"), width, height, fit, background))

            delay = (frame.info.get("duration") or 0) / 1000.0
            durations.append(delay if delay > MIN_MEANINGFUL_DELAY_SEC
                             else FALLBACK_FRAME_DURATION)

    if not frames:
        raise AnimationError(f"No frames found in '{path.name}'")

    if fps > 0:
        durations = [1.0 / fps] * len(frames)

    if truncated:
        logging.warning("Animation '%s' truncated to %d frames", path.name, max_frames)

    return Animation(frames=frames, durations=durations, width=width, height=height,
                     source=str(path), truncated=truncated)


# ---------------------------------------------------------------------------
# ffmpeg path — MP4, MOV, WebM, MKV
# ---------------------------------------------------------------------------

def find_ffmpeg(explicit: Optional[str] = None) -> Optional[str]:
    """Locate the ffmpeg binary, or return None if it is not installed."""
    if explicit:
        return explicit if Path(explicit).exists() or shutil.which(explicit) else None
    return shutil.which("ffmpeg")


def build_ffmpeg_filter(width: int, height: int, fit: str, fps: float,
                        background: Sequence[int]) -> str:
    """Build the -vf filter chain that scales and paces a video for the panel.

    Doing this inside ffmpeg rather than in Pillow means frames arrive already
    panel-sized, so the pipe carries a few hundred KB/s instead of decoded
    full-resolution video.
    """
    if fit not in FIT_MODES:
        raise AnimationError(f"Unknown fit mode '{fit}'. Valid: {', '.join(FIT_MODES)}")

    stages = [f"fps={fps:g}"]
    if fit == "contain":
        colour = "0x{:02X}{:02X}{:02X}".format(*background)
        stages.append(f"scale={width}:{height}:force_original_aspect_ratio=decrease")
        stages.append(f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={colour}")
    elif fit == "cover":
        stages.append(f"scale={width}:{height}:force_original_aspect_ratio=increase")
        stages.append(f"crop={width}:{height}")
    else:
        stages.append(f"scale={width}:{height}")
    return ",".join(stages)


def _load_with_ffmpeg(path: Path, width: int, height: int, fit: str, fps: float,
                      background: Sequence[int], max_frames: int,
                      ffmpeg_path: Optional[str]) -> Animation:
    binary = find_ffmpeg(ffmpeg_path)
    if binary is None:
        raise AnimationError(
            f"Playing '{path.name}' needs ffmpeg, which was not found on PATH. "
            "Install it with 'sudo apt install ffmpeg', or convert the clip to "
            "a GIF, which needs no extra software."
        )

    rate = fps if fps > 0 else DEFAULT_VIDEO_FPS
    # Argument list, never a shell string — path is caller-supplied.
    #
    # -v error also matters for correctness, not just noise: stderr is not
    # drained until stdout is exhausted, so a chatty ffmpeg could fill that
    # pipe's buffer and deadlock. At this level it emits a line or two.
    cmd = [
        binary, "-v", "error", "-nostdin",
        "-i", str(path),
        "-vf", build_ffmpeg_filter(width, height, fit, rate, background),
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    logging.info("Decoding %s via ffmpeg at %.3g fps", path.name, rate)

    frame_bytes = width * height * 3
    frames: List[Image.Image] = []
    truncated = False

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        raise AnimationError(f"Could not run ffmpeg: {exc}") from exc

    try:
        while len(frames) < max_frames:
            raw = proc.stdout.read(frame_bytes)
            if not raw:
                break
            if len(raw) < frame_bytes:
                # A short read at EOF is a truncated final frame; discard it.
                logging.debug("Discarding %d trailing bytes from ffmpeg", len(raw))
                break
            frames.append(Image.frombytes("RGB", (width, height), raw))
        else:
            truncated = True
    finally:
        if proc.stdout:
            proc.stdout.close()
        stderr = proc.stderr.read() if proc.stderr else b""
        if proc.stderr:
            proc.stderr.close()
        # Decoding stops early on max_frames, so ffmpeg may still be writing
        # into a closed pipe. Terminate rather than wait for it to notice.
        if proc.poll() is None:
            proc.terminate()
        returncode = proc.wait()

    if not frames:
        detail = stderr.decode("utf-8", "replace").strip() or f"exit code {returncode}"
        raise AnimationError(f"ffmpeg produced no frames for '{path.name}': {detail}")

    if truncated:
        logging.warning("Animation '%s' truncated to %d frames", path.name, max_frames)

    return Animation(frames=frames, durations=[1.0 / rate] * len(frames),
                     width=width, height=height, source=str(path), truncated=truncated)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def load_animation(path, width: int, height: int, fit: str = "contain",
                   fps: float = 0.0, background: Sequence[int] = (0, 0, 0),
                   max_frames: int = DEFAULT_MAX_FRAMES,
                   ffmpeg_path: Optional[str] = None) -> Animation:
    """Decode *path* into panel-sized frames.

    Args:
        path: Animation file; extension selects the decoder
        width, height: Panel size in pixels
        fit: 'contain', 'cover' or 'stretch'
        fps: Override the source frame rate; 0 keeps the source's own timing
        background: RGB fill behind letterboxing and transparency
        max_frames: Hard cap on decoded frames
        ffmpeg_path: Explicit ffmpeg binary; None searches PATH

    Raises:
        AnimationError: on a missing file, unsupported type, or decode failure
    """
    path = Path(path)
    if not path.exists():
        raise AnimationError(f"Animation file not found: {path}")
    if not path.is_file():
        raise AnimationError(f"Not a file: {path}")

    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        animation = _load_with_pillow(path, width, height, fit, fps, background, max_frames)
    elif suffix in VIDEO_EXTENSIONS:
        animation = _load_with_ffmpeg(path, width, height, fit, fps, background,
                                      max_frames, ffmpeg_path)
    else:
        raise AnimationError(
            f"Unsupported file type '{suffix or path.name}'. Supported: "
            + ", ".join(sorted(SUPPORTED_EXTENSIONS))
        )

    logging.info("Loaded %s: %d frames, %.2fs, %dx%d",
                 path.name, len(animation), animation.total_duration, width, height)
    return animation
