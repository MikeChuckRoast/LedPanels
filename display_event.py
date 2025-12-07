"""
display_event.py

Display an event (from `lynx.evt`) on an RGB LED matrix (real or emulator).

Features:
- Uses `rgbmatrix` if available, otherwise attempts to use an `RGBMatrixEmulator`
  module (importable as `RGBMatrixEmulator`, `rgbmatrix_emulator` or `rgbmatrix_emulator`).
- Parses `lynx.evt` CSV file and extracts events and athlete rows.
- CLI options to select event/round/heat, panel configuration, font and interval.
- Renders a header line (white background, black text) and athlete lines
  (black background, white text). Each line is `line_height` pixels tall
  (default 16). The header consumes one line; the remaining lines are used
  for athletes. If there are more athletes than fit on a page, pages rotate
  every `--interval` seconds.

Design notes:
- The code is structured into small functions (parsing, pagination, rendering)
  to make it easy to extend.

"""

import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Import from local modules
from config_loader import (ConfigError, ensure_config_directory,
                           load_current_event, load_settings)
from event_parser import (extract_relay_suffix, fill_lanes_with_empty_rows,
                          format_athlete_line, is_relay_event,
                          load_affiliation_colors, paginate_items,
                          parse_lynx_file)
from file_watcher import start_file_watcher
from matrix_backend import get_matrix_backend

# Try to import keyboard handling library
KEYBOARD_AVAILABLE = False
keyboard_backend = None

try:
    # First try evdev (works on Linux without X server)
    import evdev
    from evdev import InputDevice, categorize, ecodes
    keyboard_backend = 'evdev'
    KEYBOARD_AVAILABLE = True
except ImportError:
    try:
        # Fall back to pynput (requires X server)
        from pynput import keyboard
        keyboard_backend = 'pynput'
        KEYBOARD_AVAILABLE = True
    except ImportError:
        logging.warning("No keyboard library available (tried evdev, pynput). Keyboard navigation disabled.")

# Global state for keyboard navigation
heat_change_lock = threading.Lock()
heat_change_request = None  # None, 'next', 'prev', or 'reset'

# Global state for file reload monitoring
file_reload_lock = threading.Lock()
file_reload_requested = False


# Note: Parsing and formatting functions moved to event_parser.py
# Matrix backend functions moved to matrix_backend.py and fpp_output.py


def draw_event_on_matrix(event: Dict, matrix_classes, font_path: str, width: int, height: int,
                         line_height: int, header_line_height: int,
                         interval: float, chain: int, parallel: int,
                         gpio_slowdown: int, once: bool, font_shift: int,
                         affiliation_colors: Optional[Dict[str, Tuple[Tuple[int, int, int], Tuple[int, int, int], str]]] = None,
                         header_rows: int = 1):
    """Render the given event repeatedly (paging) onto the RGB matrix.

    `matrix_classes` is the tuple returned by `try_import_rgbmatrix()`.
    Returns True if should continue running, False if should reload with different heat.
    """
    RGBMatrix, RGBMatrixOptions, graphics = matrix_classes
    if RGBMatrix is None:
        raise RuntimeError("No rgbmatrix backend available")

    # Configure options
    options = RGBMatrixOptions()
    options.rows = height
    options.cols = width
    options.chain_length = chain
    options.parallel = parallel
    options.gpio_slowdown = gpio_slowdown

    matrix = RGBMatrix(options=options)
    canvas = matrix.CreateFrameCanvas()

    canvas_width = canvas.width
    canvas_height = canvas.height

    # Calculate header height and remaining height for athletes
    header_height = header_rows * header_line_height
    remaining_height = canvas_height - header_height
    athlete_lines_per_page = max(0, remaining_height // line_height)
    if athlete_lines_per_page <= 0:
        raise RuntimeError("Display height too small for required line heights and header rows")

    # Prepare text elements
    header = event.get("name", "")
    athletes = event.get("athletes", [])

    # Fill in missing lanes with empty rows
    full_athlete_list = fill_lanes_with_empty_rows(athletes)

    # Use the full athlete list for pagination
    athlete_pages = list(paginate_items(full_athlete_list, athlete_lines_per_page)) or [[]]

    # Detect if this is a relay event (check original athletes list)
    is_relay = is_relay_event(athletes)

    # Colors
    white = graphics.Color(255, 255, 255)
    black = graphics.Color(0, 0, 0)

    # Load font
    font = graphics.Font()
    try:
        font.LoadFont(font_path)
        logging.info("Loaded font: %s", font_path)
    except Exception:
        # Try relative path
        alt = os.path.join(os.path.dirname(__file__), font_path)
        try:
            font.LoadFont(alt)
            logging.info("Loaded font (alt): %s", alt)
        except Exception:
            logging.warning("Failed to load font '%s' for rgbmatrix; drawing may be mis-sized", font_path)

    # Helper to measure text width using the rgbmatrix font API or a fallback
    def get_text_width(text: str) -> int:
        try:
            return sum(font.CharacterWidth(ord(c)) for c in text)
        except Exception:
            return max(1, len(text)) * 6

    # Compute a lane column width (based on all athletes in the event) so we can
    # align names into a consistent column. Add a small padding gap.
    lane_col_width = 0
    for a in athletes:
        lane_txt = (a.get("lane") or "").strip()
        w = get_text_width(lane_txt)
        if w > lane_col_width:
            lane_col_width = w
    lane_col_width = max(lane_col_width, get_text_width("88"))  # at least space for two-digit lane
    lane_x = 1
    name_x = lane_x + lane_col_width + 3

    # For relay events, reserve space on the right for suffix letter
    suffix_col_width = 0
    suffix_x = 0
    if is_relay:
        # Reserve space for suffix (e.g., "A", "B") plus padding
        suffix_col_width = get_text_width("W") + 2  # Use 'W' as widest letter
        suffix_x = canvas_width - suffix_col_width - 1

    def render_page(page_index: int):
        nonlocal canvas
        page = athlete_pages[page_index]
        canvas.Clear()

        # Draw header background (white) for the header_rows
        header_height = header_rows * header_line_height
        for y in range(0, header_height):
            graphics.DrawLine(canvas, 0, y, canvas_width - 1, y, white)

        # Wrap header text into multiple lines if needed
        available_header_width = canvas_width - 2  # Leave 1px margin on each side
        words = header.split()
        header_lines = []
        current_line = ""

        for word in words:
            test_line = (current_line + " " + word).strip()
            if get_text_width(test_line) <= available_header_width:
                current_line = test_line
            else:
                if current_line:
                    header_lines.append(current_line)
                current_line = word

        if current_line:
            header_lines.append(current_line)

        # Truncate to header_rows if we have too many lines
        if len(header_lines) > header_rows:
            header_lines = header_lines[:header_rows]
            # Truncate last line if needed
            last_line = header_lines[-1]
            while last_line and get_text_width(last_line) > available_header_width:
                last_line = last_line[:-1]
            header_lines[-1] = last_line

        # Draw each header line, centered within its row
        for line_idx, line_text in enumerate(header_lines):
            line_width = get_text_width(line_text)
            x_pos = max(1, (canvas_width - line_width) // 2)
            y_pos = (line_idx * header_line_height) + (header_line_height + font.height) // 2 - font_shift
            graphics.DrawText(canvas, font, x_pos, y_pos, black, line_text)

        # Draw athlete lines
        for idx, athlete in enumerate(page):
            # Y position starts after header
            y0 = header_height + (idx * line_height)
            y1 = y0 + line_height - 1

            # Check if this is an empty lane (only has lane number, no athlete data)
            has_athlete = bool((athlete.get("last") or "").strip() or (athlete.get("first") or "").strip())

            # Look up colors - for relay events, use last name (team name) for color lookup
            display_name = None
            if is_relay and has_athlete:
                # For relay events, last name contains the team name
                color_key = (athlete.get("last") or "").strip()
            elif has_athlete:
                # For individual events, use affiliation
                color_key = (athlete.get("affiliation") or "").strip()
            else:
                color_key = ""

            text_color = white
            bg_color = black

            if has_athlete and affiliation_colors and color_key in affiliation_colors:
                bg_rgb, text_rgb, display_name = affiliation_colors[color_key]
                bg_color = graphics.Color(bg_rgb[0], bg_rgb[1], bg_rgb[2])
                text_color = graphics.Color(text_rgb[0], text_rgb[1], text_rgb[2])

            # Fill background for this line
            for y in range(y0, y1 + 1):
                graphics.DrawLine(canvas, 0, y, canvas_width - 1, y, bg_color)

            # Draw lane and name in columns
            lane_txt = (athlete.get("lane") or "").strip()
            # Baseline for this row
            y_txt = y0 + (line_height + font.height) // 2 - font_shift
            # Draw lane (left column)
            graphics.DrawText(canvas, font, lane_x, y_txt, text_color, lane_txt)

            # Only draw athlete info if there's an athlete in this lane
            if has_athlete:
                if is_relay:
                    # For relay: draw team name in middle, suffix on far right
                    # Use display_name from colors.csv if available, otherwise use last name
                    team_name = display_name if display_name else (athlete.get("last") or "").strip()
                    suffix = extract_relay_suffix((athlete.get("affiliation") or "").strip())

                    # Calculate available width for team name (between name_x and suffix column)
                    available_width = suffix_x - name_x - 3  # Leave 3px gap before suffix

                    # Truncate team name if needed to fit available space
                    team_name_width = get_text_width(team_name)
                    if team_name_width > available_width:
                        # Truncate character by character until it fits
                        while team_name and get_text_width(team_name) > available_width:
                            team_name = team_name[:-1]

                    # Draw team name in middle column
                    graphics.DrawText(canvas, font, name_x, y_txt, text_color, team_name)

                    # Draw suffix in right column
                    graphics.DrawText(canvas, font, suffix_x, y_txt, text_color, suffix)
                else:
                    # For individual: draw name normally
                    name_txt = format_athlete_line(athlete, is_relay=False)
                    graphics.DrawText(canvas, font, name_x, y_txt, text_color, name_txt)        # Push to matrix
        try:
            canvas = matrix.SwapOnVSync(canvas)
        except Exception as ex:
            logging.exception("SwapOnVSync failed: %s", ex)

    # Loop pages
    page_count = len(athlete_pages)
    page_idx = 0
    try:
        if once:
            render_page(page_idx)
            return True
        while True:
            render_page(page_idx)

            # Sleep in small increments to check for heat changes and file reloads
            elapsed = 0.0
            check_interval = 0.1  # Check every 100ms for better responsiveness
            while elapsed < interval:
                # Check for heat change request
                global heat_change_request, file_reload_requested
                with heat_change_lock:
                    if heat_change_request is not None:
                        matrix.Clear()
                        return False  # Signal to reload

                # Check for file reload request
                with file_reload_lock:
                    if file_reload_requested:
                        matrix.Clear()
                        return False  # Signal to reload

                time.sleep(check_interval)
                elapsed += check_interval

            page_idx = (page_idx + 1) % page_count
    except KeyboardInterrupt:
        matrix.Clear()
        return True


def find_keyboard_device():
    """Find a keyboard input device using evdev.

    Prioritizes keyboards with Page Up/Down keys, then full keyboards, then any keyboard-like device.
    """
    try:
        all_devices = evdev.list_devices()
        logging.info("Scanning for keyboard devices... found %d input devices", len(all_devices))

        devices = [evdev.InputDevice(path) for path in all_devices]

        # Categorize candidates by priority
        best_candidates = []  # Has Page Up/Down
        good_candidates = []  # Full keyboard (has letters)
        basic_candidates = [] # Has Enter/Space

        for device in devices:
            # Skip devices with "hdmi" in the name (HDMI audio/CEC devices)
            if "hdmi" in device.name.lower():
                logging.info("Device: %s [%s] - SKIPPED (HDMI device)", device.name, device.path)
                continue

            # Look for devices with keyboard capabilities
            capabilities = device.capabilities(verbose=False)
            if ecodes.EV_KEY in capabilities:
                # Check if it has common keyboard keys
                keys = capabilities[ecodes.EV_KEY]
                has_enter = ecodes.KEY_ENTER in keys
                has_space = ecodes.KEY_SPACE in keys
                has_pageup = ecodes.KEY_PAGEUP in keys
                has_pagedown = ecodes.KEY_PAGEDOWN in keys
                has_letters = ecodes.KEY_A in keys and ecodes.KEY_Z in keys

                logging.info("Device: %s [%s] - ENTER:%s SPACE:%s PAGEUP:%s PAGEDOWN:%s LETTERS:%s",
                             device.name, device.path, has_enter, has_space,
                             has_pageup, has_pagedown, has_letters)

                # Prioritize keyboards with Page Up/Down since that's what we need
                if has_pageup and has_pagedown:
                    best_candidates.append(device)
                    logging.info("  -> BEST candidate (has Page Up/Down)")
                elif has_letters:
                    good_candidates.append(device)
                    logging.info("  -> GOOD candidate (full keyboard)")
                elif has_enter or has_space:
                    basic_candidates.append(device)
                    logging.info("  -> BASIC candidate (has Enter/Space)")

        # Select the best available device
        if best_candidates:
            device = best_candidates[0]
            logging.info("Selected BEST keyboard: %s at %s", device.name, device.path)
            return device
        elif good_candidates:
            device = good_candidates[0]
            logging.info("Selected GOOD keyboard: %s at %s", device.name, device.path)
            return device
        elif basic_candidates:
            device = basic_candidates[0]
            logging.info("Selected BASIC keyboard: %s at %s", device.name, device.path)
            return device

        logging.warning("No keyboard device found among %d input devices", len(devices))
        logging.warning("Try running with: sudo python3 test_keyboard.py to debug")
        logging.warning("Or specify device manually with: --keyboard-device /dev/input/eventX")
        return None
    except Exception as e:
        logging.error("Error finding keyboard device: %s", e)
        import traceback
        logging.error(traceback.format_exc())
        return None


def evdev_keyboard_listener(device_path=None):
    """Listen for keyboard events using evdev (runs in separate thread).

    Args:
        device_path: Optional path to specific input device (e.g., '/dev/input/event2')
    """
    global heat_change_request

    if device_path:
        try:
            device = evdev.InputDevice(device_path)
            logging.info("Using specified keyboard device: %s at %s", device.name, device.path)
        except Exception as e:
            logging.error("Failed to open specified device %s: %s", device_path, e)
            return
    else:
        device = find_keyboard_device()
        if not device:
            logging.warning("Could not start evdev keyboard listener - no device found")
            return

    logging.info("Keyboard listener started (evdev) - monitoring %s", device.path)
    logging.info("Waiting for key presses... (Page Up, Page Down, Period)")
    try:
        for event in device.read_loop():
            if event.type == ecodes.EV_KEY:
                key_event = categorize(event)
                # Only handle key down events (not key up)
                if key_event.keystate == 1:  # Key down
                    logging.info("Key event detected: %s", key_event.keycode)

                    if key_event.keycode == 'KEY_PAGEDOWN':
                        with heat_change_lock:
                            heat_change_request = 'next'
                        logging.info(">>> Page Down pressed - next heat requested")
                    elif key_event.keycode == 'KEY_PAGEUP':
                        with heat_change_lock:
                            heat_change_request = 'prev'
                        logging.info(">>> Page Up pressed - previous heat requested")
                    elif key_event.keycode == 'KEY_DOT':
                        with heat_change_lock:
                            heat_change_request = 'reset'
                        logging.info(">>> Period pressed - reset to original heat requested")
    except Exception as e:
        logging.error("Keyboard listener error: %s", e)
        import traceback
        logging.error(traceback.format_exc())


def on_key_press_pynput(key):
    """Handle keyboard events for heat navigation using pynput."""
    global heat_change_request

    # Debug: log all key presses
    logging.debug("Key pressed: %s", key)

    # Check for special keys first
    if hasattr(key, 'name'):
        # Special key (Page Up, Page Down, etc.)
        if key == keyboard.Key.page_down:
            with heat_change_lock:
                heat_change_request = 'next'
            logging.info("Page Down pressed - next heat")
            return
        elif key == keyboard.Key.page_up:
            with heat_change_lock:
                heat_change_request = 'prev'
            logging.info("Page Up pressed - previous heat")
            return

    # Check for character keys (like period)
    try:
        if hasattr(key, 'char') and key.char == '.':
            with heat_change_lock:
                heat_change_request = 'reset'
            logging.info("Period pressed - resetting to original heat")
            return
    except AttributeError:
        pass


def load_file_with_retry(load_func, file_description: str, max_retries: int = 3):
    """Load a file with retry logic to handle files being written.

    Args:
        load_func: Function to call to load the file (no arguments)
        file_description: Description of file for error messages
        max_retries: Maximum number of retry attempts

    Returns:
        Result from load_func, or None if all retries failed
    """
    for attempt in range(max_retries):
        try:
            return load_func()
        except (IOError, OSError, FileNotFoundError) as e:
            if attempt < max_retries - 1:
                delay = 0.1 * (attempt + 1)
                logging.warning(f"Failed to load {file_description} (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                logging.error(f"Failed to load {file_description} after {max_retries} attempts: {e}")
                return None
        except Exception as e:
            logging.error(f"Unexpected error loading {file_description}: {e}")
            return None
    return None


def main():
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

    # First parse to get config-dir
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument('--config-dir', default='./config')
    pre_args, _ = pre_parser.parse_known_args()
    config_dir = pre_args.config_dir

    # Ensure config directory exists and has default files
    try:
        ensure_config_directory(config_dir)
    except ConfigError as e:
        logging.error(f"Configuration error: {e}")
        sys.exit(1)

    # Load settings and current event
    try:
        settings = load_settings(config_dir)
        current_event = load_current_event(config_dir)
    except ConfigError as e:
        logging.error(f"Configuration error: {e}")
        sys.exit(1)

    # Extract settings for easier access
    hw = settings['hardware']
    disp = settings['display']
    fonts = settings['fonts']
    files = settings['files']
    net = settings['network']
    kbd = settings['keyboard']
    behavior = settings['behavior']

    # Resolve file paths relative to config directory
    config_path = Path(config_dir)
    lynx_file_path = str(config_path / files['lynx_file'])
    colors_file_path = str(config_path / files['colors_file'])

    # Now parse all arguments with defaults from config
    parser = argparse.ArgumentParser(description="Display an event from lynx.evt on LED matrix")
    parser.add_argument('--config-dir', default='./config', help='Path to configuration directory')
    parser.add_argument('--file', '-f', default=lynx_file_path, help='Path to lynx.evt file')
    parser.add_argument('--colors-csv', default=colors_file_path, help='Path to colors CSV file')
    parser.add_argument('--event', type=int, default=current_event['event'], help='Event number')
    parser.add_argument('--round', type=int, default=current_event['round'], help='Round number')
    parser.add_argument('--heat', type=int, default=current_event['heat'], help='Heat number')
    parser.add_argument('--font', default=fonts['font_path'], help='Path to BDF font for rgbmatrix')
    parser.add_argument('--width', type=int, default=hw['width'], help='Display width in pixels')
    parser.add_argument('--height', type=int, default=hw['height'], help='Display height in pixels')
    parser.add_argument('--line-height', type=int, default=disp['line_height'], help='Pixels per text line for athlete rows')
    parser.add_argument('--header-line-height', type=int, default=disp['header_line_height'], help='Pixels per text line for header rows')
    parser.add_argument('--header-rows', type=int, default=disp['header_rows'], help='Number of rows for header (allows text wrapping)')
    parser.add_argument('--interval', type=float, default=disp['interval'], help='Seconds per page when paging')
    parser.add_argument('--once', action='store_true', default=behavior['once'], help='Render once then exit')
    parser.add_argument('--chain', type=int, default=hw['chain'], help='Panels chained horizontally')
    parser.add_argument('--parallel', type=int, default=hw['parallel'], help='Panels stacked vertically')
    parser.add_argument('--gpio-slowdown', type=int, default=hw['gpio_slowdown'], help='GPIO slowdown for RGBMatrixOptions')
    parser.add_argument('--fpp', action='store_true', default=net['fpp_enabled'], help='Use FPP output instead of direct matrix control')
    parser.add_argument('--fpp-host', default=net['fpp_host'], help='FPP host IP address')
    parser.add_argument('--fpp-port', type=int, default=net['fpp_port'], help='FPP DDP port')
    parser.add_argument('--colorlight', action='store_true', default=net['colorlight_enabled'], help='Send frames directly to ColorLight 5A-75B via raw Ethernet (requires root/sudo)')
    parser.add_argument('--colorlight-interface', default=net['colorlight_interface'], help='Network interface name for ColorLight (e.g., eth0, enp0s3)')
    parser.add_argument('--keyboard-device', default=kbd['device_path'] or None, help='Path to keyboard input device for evdev (e.g., /dev/input/event2). Auto-detect if not specified.')
    args = parser.parse_args()

    try:
        events = parse_lynx_file(args.file)
    except Exception as e:
        logging.error("Failed to parse lynx file: %s", e)
        sys.exit(2)

    # Load affiliation colors
    affiliation_colors = load_affiliation_colors(args.colors_csv)

    # File reload callback for file watcher
    def request_file_reload():
        global file_reload_requested
        with file_reload_lock:
            file_reload_requested = True

    # Start file watcher
    file_watcher = None
    if not args.__dict__.get('no_file_watch', False):  # Check if flag exists
        file_watcher = start_file_watcher(config_dir, request_file_reload)
        if file_watcher:
            logging.info("File monitoring enabled for auto-reload")
        else:
            logging.warning("File monitoring could not be started - manual restart required for file changes")

    # Start keyboard listener if available
    keyboard_listener = None
    keyboard_thread = None
    if KEYBOARD_AVAILABLE:
        if keyboard_backend == 'evdev':
            # Start evdev listener in a separate thread
            keyboard_thread = threading.Thread(
                target=evdev_keyboard_listener,
                args=(args.keyboard_device,),
                daemon=True
            )
            keyboard_thread.start()
            logging.info("Keyboard navigation enabled (evdev): Page Down (next heat), Page Up (prev heat), Period (reset)")
        elif keyboard_backend == 'pynput':
            keyboard_listener = keyboard.Listener(on_press=on_key_press_pynput)
            keyboard_listener.start()
            logging.info("Keyboard navigation enabled (pynput): Page Down (next heat), Page Up (prev heat), Period (reset)")

    # Store original heat number
    original_heat = args.heat
    current_heat = args.heat

    # Get appropriate matrix backend (direct, emulator, FPP, or ColorLight)
    matrix_classes = get_matrix_backend(
        use_fpp=args.fpp,
        fpp_host=args.fpp_host,
        fpp_port=args.fpp_port,
        use_colorlight=args.colorlight,
        colorlight_interface=args.colorlight_interface,
        width=args.width,
        height=args.height
    )
    if matrix_classes[0] is None:
        if args.fpp:
            logging.error("Failed to initialize FPP output")
        else:
            logging.error("No rgbmatrix backend available: install 'rgbmatrix' or an emulator module named 'RGBMatrixEmulator' or 'rgbmatrix_emulator', or use --fpp for network output")
        sys.exit(4)

    # Main loop - allows reloading when heat changes or files change
    try:
        while True:
            key = (args.event, args.round, current_heat)
            if key not in events:
                logging.error("Requested event not found: %s", key)
                # Show available events briefly
                logging.info("Available events: %s", sorted(events.keys()))
                sys.exit(3)

            # Make a copy of the event to avoid modifying the original
            event = events[key].copy()
            event["athletes"] = events[key]["athletes"]  # Share the athletes list (no modification needed)

            # Check if there are multiple heats for this event/round combination
            heat_count = sum(1 for k in events.keys() if k[0] == args.event and k[1] == args.round)
            if heat_count > 1:
                # Prepend heat number to event name (on the copy)
                event["name"] = f"#{current_heat} {event['name']}"

            # Draw the event
            should_continue = draw_event_on_matrix(event, matrix_classes, args.font, args.width, args.height,
                                 line_height=args.line_height, header_line_height=args.header_line_height,
                                 interval=args.interval, chain=args.chain, parallel=args.parallel,
                                 gpio_slowdown=args.gpio_slowdown, once=args.once, font_shift=disp['font_shift'],
                                 affiliation_colors=affiliation_colors, header_rows=args.header_rows)

            if should_continue or args.once:
                break

            # Check what triggered the reload
            global heat_change_request, file_reload_requested
            is_file_reload = False
            with file_reload_lock:
                if file_reload_requested:
                    is_file_reload = True
                    file_reload_requested = False

            if is_file_reload:
                # File reload requested - reload all data files
                logging.info("Reloading event data from files...")

                # Reload lynx.evt with retry logic
                new_events = load_file_with_retry(
                    lambda: parse_lynx_file(args.file),
                    "lynx.evt"
                )
                if new_events is not None:
                    events = new_events
                else:
                    logging.warning("Could not reload lynx.evt - continuing with current data")

                # Reload current_event.json with retry logic
                new_current_event = load_file_with_retry(
                    lambda: load_current_event(config_dir),
                    "current_event.json"
                )
                if new_current_event is not None:
                    # Update current heat from reloaded file
                    args.event = new_current_event['event']
                    args.round = new_current_event['round']
                    current_heat = new_current_event['heat']
                    original_heat = current_heat
                    logging.info(f"Updated to Event={args.event}, Round={args.round}, Heat={current_heat}")
                else:
                    logging.warning("Could not reload current_event.json - continuing with current event selection")

                # Reload colors.csv with retry logic
                new_colors = load_file_with_retry(
                    lambda: load_affiliation_colors(args.colors_csv),
                    "colors.csv"
                )
                if new_colors is not None:
                    affiliation_colors = new_colors
                else:
                    logging.warning("Could not reload colors.csv - continuing with current colors")

                logging.info("Reload complete - resuming display")
                continue

            # Handle heat change request
            with heat_change_lock:
                if heat_change_request == 'next':
                    # Try next heat
                    next_heat = current_heat + 1
                    if (args.event, args.round, next_heat) in events:
                        current_heat = next_heat
                        logging.info("Switching to heat %d", current_heat)
                    else:
                        logging.info("No heat %d found, staying on heat %d", next_heat, current_heat)
                elif heat_change_request == 'prev':
                    # Try previous heat (minimum original_heat)
                    prev_heat = max(original_heat, current_heat - 1)
                    if prev_heat != current_heat and (args.event, args.round, prev_heat) in events:
                        current_heat = prev_heat
                        logging.info("Switching to heat %d", current_heat)
                    else:
                        logging.info("Cannot go to heat %d, staying on heat %d", prev_heat, current_heat)
                elif heat_change_request == 'reset':
                    # Reset to original heat
                    if current_heat != original_heat:
                        current_heat = original_heat
                        logging.info("Resetting to original heat %d", current_heat)
                    else:
                        logging.info("Already at original heat %d", current_heat)

                heat_change_request = None  # Clear the request
    except Exception as e:
        logging.exception("Failed to render event: %s", e)
        sys.exit(5)
    finally:
        if keyboard_listener:
            keyboard_listener.stop()


if __name__ == '__main__':
    main()
