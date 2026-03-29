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
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Import from local modules
from config_loader import (ConfigError, ensure_config_directory,
                           load_current_event, load_settings)
from display_utils import (calculate_text_baseline, draw_centered_text,
                           fill_rectangle, load_font_metadata,
                           load_font_with_fallback, measure_text_width,
                           truncate_text_to_width, wrap_text_lines)
from event_parser import (extract_relay_suffix, fill_lanes_with_empty_rows,
                          format_athlete_line, get_duplicate_relay_teams,
                          is_relay_event, load_affiliation_colors,
                          paginate_items, parse_lynx_file)
from file_watcher import start_file_watcher
from matrix_backend import get_matrix_backend
from schedule_parser import (find_nearest_schedule_index, find_schedule_index,
                             get_schedule_position_text, parse_schedule,
                             validate_schedule_entries)
from web_server import start_web_server

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

# Global state for display power (on/off)
display_power_lock = threading.Lock()
display_power_on = True

# Global state for network connectivity
network_status_lock = threading.Lock()
network_connected = True


# Note: Parsing and formatting functions moved to event_parser.py
# Matrix backend functions moved to matrix_backend.py and fpp_output.py


def get_default_gateway():
    """Discover the default gateway IP address.

    Returns:
        Gateway IP string, or None if it cannot be determined.
    """
    try:
        if platform.system() == 'Windows':
            result = subprocess.run(
                ['route', 'print', '0.0.0.0'],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[0] == '0.0.0.0':
                    return parts[2]
        else:
            # Linux/macOS
            route_file = Path('/proc/net/route')
            if route_file.exists():
                for line in route_file.read_text().splitlines()[1:]:
                    fields = line.split()
                    if len(fields) >= 3 and fields[1] == '00000000':
                        # Gateway is in hex, little-endian
                        gw_hex = fields[2]
                        gw_bytes = bytes.fromhex(gw_hex)
                        return f'{gw_bytes[3]}.{gw_bytes[2]}.{gw_bytes[1]}.{gw_bytes[0]}'
            else:
                # macOS fallback
                result = subprocess.run(
                    ['route', '-n', 'get', 'default'],
                    capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.splitlines():
                    if 'gateway:' in line:
                        return line.split('gateway:')[1].strip()
    except Exception as e:
        logging.debug("Failed to discover default gateway: %s", e)
    return None


def check_network_connectivity(gateway):
    """Ping the gateway to check network connectivity.

    Args:
        gateway: IP address to ping

    Returns:
        True if reachable, False otherwise
    """
    try:
        if platform.system() == 'Windows':
            cmd = ['ping', '-n', '1', '-w', '1000', gateway]
        else:
            cmd = ['ping', '-c', '1', '-W', '1', gateway]
        result = subprocess.run(cmd, capture_output=True, timeout=3)
        return result.returncode == 0
    except Exception:
        return False


def network_monitor_loop(interval=10):
    """Background thread that monitors network connectivity.

    Pings the default gateway periodically and updates the global
    network_connected flag.

    Args:
        interval: Seconds between checks (default 10)
    """
    global network_connected
    gateway = get_default_gateway()
    if gateway is None:
        logging.warning("Could not determine default gateway - network monitoring disabled")
        return
    logging.info("Network monitoring started (gateway: %s, interval: %ds)", gateway, interval)
    was_connected = True

    while True:
        reachable = check_network_connectivity(gateway)

        with network_status_lock:
            network_connected = reachable

        # Log state transitions
        if reachable and not was_connected:
            logging.info("Network connectivity restored (gateway %s reachable)", gateway)
        elif not reachable and was_connected:
            logging.warning("Network connectivity lost (gateway %s unreachable)", gateway)

        was_connected = reachable

        # On failure, re-discover gateway in case it changed
        if not reachable:
            new_gw = get_default_gateway()
            if new_gw and new_gw != gateway:
                logging.info("Default gateway changed: %s -> %s", gateway, new_gw)
                gateway = new_gw

        time.sleep(interval)


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

    # For relay events, determine which teams appear multiple times (case-insensitive)
    duplicate_teams = set()
    if is_relay:
        duplicate_teams = get_duplicate_relay_teams(athletes)

    # Colors
    white = graphics.Color(255, 255, 255)
    black = graphics.Color(0, 0, 0)

    # Load font
    font = load_font_with_fallback(graphics, font_path)

    # Load font metadata for portable rendering
    font_metadata = load_font_metadata(font_path)

    # Compute a lane column width (based on all athletes in the event) so we can
    # align names into a consistent column. Add a small padding gap.
    lane_col_width = 0
    for a in athletes:
        lane_txt = (a.get("lane") or "").strip()
        w = measure_text_width(font, lane_txt)
        if w > lane_col_width:
            lane_col_width = w
    lane_col_width = max(lane_col_width, measure_text_width(font, "88"))  # at least space for two-digit lane
    lane_x = 1
    name_x = lane_x + lane_col_width + 3

    def render_page(page_index: int):
        nonlocal canvas
        page = athlete_pages[page_index]
        canvas.Clear()

        # Draw header background (white) for the header_rows
        header_height = header_rows * header_line_height
        fill_rectangle(canvas, graphics, 0, 0, canvas_width - 1, header_height - 1, white)

        # Wrap header text into multiple lines if needed
        available_header_width = canvas_width - 2  # Leave 1px margin on each side
        header_lines = wrap_text_lines(font, header, available_header_width)

        # Truncate to header_rows if we have too many lines
        if len(header_lines) > header_rows:
            header_lines = header_lines[:header_rows]
            # Truncate last line if needed
            header_lines[-1] = truncate_text_to_width(font, header_lines[-1], available_header_width)

        # Draw each header line, centered within its row
        for line_idx, line_text in enumerate(header_lines):
            draw_centered_text(canvas, graphics, font, font_metadata,
                               line_idx * header_line_height,
                               header_line_height,
                               canvas_width,
                               line_text,
                               black,
                               font_shift)
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
            fill_rectangle(canvas, graphics, 0, y0, canvas_width - 1, y1, bg_color)

            # Draw lane and name in columns
            lane_txt = (athlete.get("lane") or "").strip()
            # Baseline for this row
            y_txt = calculate_text_baseline(y0, line_height, font_metadata, font_shift)
            # Draw lane (left column)
            graphics.DrawText(canvas, font, lane_x, y_txt, text_color, lane_txt)

            # Only draw athlete info if there's an athlete in this lane
            if has_athlete:
                if is_relay:
                    # For relay: draw team name, with suffix only if team has duplicates
                    # Use display_name from colors.csv if available, otherwise use last name
                    team_name = display_name if display_name else (athlete.get("last") or "").strip()

                    # Check if this team appears multiple times (case-insensitive)
                    # Use the original 'last' field for duplicate detection, not display_name
                    original_team_name = (athlete.get("last") or "").strip().lower()
                    has_duplicate = original_team_name in duplicate_teams

                    if has_duplicate:
                        # Team has duplicates - show suffix in right column
                        suffix = extract_relay_suffix((athlete.get("affiliation") or "").strip())
                        # Reserve space for suffix
                        suffix_col_width = measure_text_width(font, "W") + 2  # Use 'W' as widest letter
                        suffix_x = canvas_width - suffix_col_width - 1
                        # Calculate available width for team name (between name_x and suffix column)
                        available_width = suffix_x - name_x - 3  # Leave 3px gap before suffix
                    else:
                        # Team is unique - no suffix, use full width
                        suffix = ""
                        available_width = canvas_width - name_x - 1

                    # Truncate team name if needed to fit available space
                    team_name = truncate_text_to_width(font, team_name, available_width)

                    # Draw team name in middle column
                    graphics.DrawText(canvas, font, name_x, y_txt, text_color, team_name)

                    # Draw suffix in right column only if team has duplicates
                    if has_duplicate and suffix:
                        graphics.DrawText(canvas, font, suffix_x, y_txt, text_color, suffix)
                else:
                    # For individual: draw name normally
                    name_txt = format_athlete_line(athlete, is_relay=False)
                    graphics.DrawText(canvas, font, name_x, y_txt, text_color, name_txt)

            # Draw network status indicator (red bottom row when disconnected)
            net_ok = True
            with network_status_lock:
                net_ok = network_connected
            if not net_ok:
                red = graphics.Color(255, 0, 0)
                fill_rectangle(canvas, graphics, 0, canvas_height - 1, canvas_width - 1, canvas_height - 1, red)

        # Push to matrix
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

                # Check for display power off
                power_is_on = True
                with display_power_lock:
                    power_is_on = display_power_on
                if not power_is_on:
                    matrix.Clear()
                    canvas = matrix.SwapOnVSync(canvas)
                    # Stay in sleep loop but don't advance pages
                    while True:
                        time.sleep(check_interval)
                        with display_power_lock:
                            if display_power_on:
                                break
                        with heat_change_lock:
                            if heat_change_request is not None:
                                matrix.Clear()
                                return False
                        with file_reload_lock:
                            if file_reload_requested:
                                matrix.Clear()
                                return False
                    # Power back on — re-render current page
                    render_page(page_idx)
                    elapsed = 0.0
                    continue

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


def handle_file_reload(config_dir, events, affiliation_colors, disp, schedule,
                       args_file, args_font, args_colors_csv,
                       displayed_event, displayed_round, displayed_heat,
                       current_schedule_index, starting_schedule_index,
                       original_event, original_round, original_heat):
    """Handle file reload: re-read data files and conditionally jump forward.

    Args:
        config_dir: Path to config directory
        events: Current events dict
        affiliation_colors: Current color mappings
        disp: Current display settings dict
        schedule: Current schedule list
        args_file: Path to lynx.evt file
        args_font: Current font path
        args_colors_csv: Path to colors.csv file
        displayed_event: Event number currently displayed
        displayed_round: Round number currently displayed
        displayed_heat: Heat number currently displayed
        current_schedule_index: Index of currently displayed event in schedule
        starting_schedule_index: Index of reference event in schedule (keyboard floor)
        original_event: Reference event number (keyboard floor)
        original_round: Reference round number (keyboard floor)
        original_heat: Reference heat number (keyboard floor)

    Returns:
        Dict with updated state keys: events, affiliation_colors, disp, font,
        event, round, heat, schedule, starting_schedule_index,
        current_schedule_index, original_event, original_round, original_heat
    """
    logging.info("Reloading event data from files...")

    # Phase 1: Capture currently displayed state before reload
    displayed_event_tuple = (displayed_event, displayed_round, displayed_heat)

    # Track whether current_event.json changed
    current_event_changed = False
    incoming_event = displayed_event
    incoming_round = displayed_round
    incoming_heat = displayed_heat

    # Reload lynx.evt with retry logic
    new_events = load_file_with_retry(
        lambda: parse_lynx_file(args_file),
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
        # Store incoming values - don't update display yet (conditional jump later)
        incoming_event = new_current_event['event']
        incoming_round = new_current_event['round']
        incoming_heat = new_current_event['heat']
        current_event_changed = True
        # Always update the reference floor (keyboard can't go before this)
        original_event = incoming_event
        original_round = incoming_round
        original_heat = incoming_heat
        logging.info(f"Reference updated to Event={incoming_event}, Round={incoming_round}, Heat={incoming_heat}")
    else:
        logging.warning("Could not reload current_event.json - continuing with current event selection")

    # Reload colors.csv with retry logic
    new_colors = load_file_with_retry(
        lambda: load_affiliation_colors(args_colors_csv),
        "colors.csv"
    )
    if new_colors is not None:
        affiliation_colors = new_colors
    else:
        logging.warning("Could not reload colors.csv - continuing with current colors")

    # Reload settings.toml so display settings (font_shift, line_height, etc.) update live
    new_settings = load_file_with_retry(
        lambda: load_settings(config_dir),
        "settings.toml"
    )
    font = args_font
    if new_settings is not None:
        disp = new_settings['display']
        new_fonts = new_settings['fonts']
        new_font_path = os.path.join(new_fonts['font_path'], new_fonts['font_name'])
        if new_font_path != args_font:
            font = new_font_path
            logging.info(f"Font updated: {font}")
        logging.info("Display settings reloaded from settings.toml")
    else:
        logging.warning("Could not reload settings.toml - continuing with current display settings")

    # Reload schedule (lynx.sch) if it exists
    schedule_path = os.path.join(config_dir, "lynx.sch")
    if os.path.exists(schedule_path):
        new_schedule = load_file_with_retry(
            lambda: parse_schedule(schedule_path),
            "lynx.sch"
        )
        if new_schedule is not None:
            # Validate against reloaded events
            validated_schedule = validate_schedule_entries(new_schedule, events)
            if validated_schedule:
                schedule = validated_schedule

                # Calculate starting_schedule_index (reference floor) from incoming event
                starting_schedule_index = find_schedule_index(schedule, incoming_event, incoming_round, incoming_heat)
                if starting_schedule_index == -1:
                    starting_schedule_index = find_nearest_schedule_index(
                        schedule, incoming_event, incoming_round, incoming_heat
                    )
                    if starting_schedule_index == -1:
                        logging.warning("Reference event is past all scheduled events - disabling schedule navigation")
                        schedule = []
                    else:
                        # Update incoming to the nearest valid schedule entry
                        incoming_event, incoming_round, incoming_heat = schedule[starting_schedule_index]
                        original_event = incoming_event
                        original_round = incoming_round
                        original_heat = incoming_heat
                        position_text = get_schedule_position_text(schedule, incoming_event, incoming_round, incoming_heat)
                        logging.info(f"Reference event not in schedule - nearest: {position_text}")

                # Recalculate current_schedule_index for the displayed event in the new schedule
                if schedule:
                    displayed_schedule_index = find_schedule_index(
                        schedule, displayed_event_tuple[0], displayed_event_tuple[1], displayed_event_tuple[2]
                    )
                    if displayed_schedule_index == -1:
                        displayed_schedule_index = find_nearest_schedule_index(
                            schedule, displayed_event_tuple[0], displayed_event_tuple[1], displayed_event_tuple[2]
                        )
                        if displayed_schedule_index is None:
                            displayed_schedule_index = len(schedule) - 1
                    current_schedule_index = displayed_schedule_index
            else:
                logging.warning("No valid schedule entries after reload - disabling schedule navigation")
                schedule = []
        else:
            logging.warning("Could not reload lynx.sch - continuing with current schedule")
    else:
        # Schedule file was deleted - disable schedule navigation
        if schedule:
            logging.info("Schedule file removed - switching to heat increment mode")
            schedule = []

    # Phase 4: Conditional jump - only jump display forward
    result_event = displayed_event
    result_round = displayed_round
    result_heat = displayed_heat

    if current_event_changed:
        if schedule:
            # Schedule mode: compare schedule positions
            if current_schedule_index < starting_schedule_index:
                # Display is behind reference - jump forward
                current_schedule_index = starting_schedule_index
                result_event, result_round, result_heat = schedule[current_schedule_index]
                position_text = get_schedule_position_text(schedule, result_event, result_round, result_heat)
                logging.info(f"Display behind reference - jumping forward to: {position_text}")
            else:
                logging.info(f"Display at or ahead of reference (pos {current_schedule_index + 1} >= ref {starting_schedule_index + 1}) - staying put")
        else:
            # No schedule: lexicographic tuple comparison
            incoming_tuple = (incoming_event, incoming_round, incoming_heat)
            if displayed_event_tuple < incoming_tuple:
                # Display is behind reference - jump forward
                result_event = incoming_event
                result_round = incoming_round
                result_heat = incoming_heat
                logging.info(f"Display behind reference - jumping forward to Event={result_event}, Round={result_round}, Heat={result_heat}")
            else:
                logging.info(f"Display at or ahead of reference {incoming_tuple} - staying put at {displayed_event_tuple}")

    logging.info("Reload complete - resuming display")

    return {
        'events': events,
        'affiliation_colors': affiliation_colors,
        'disp': disp,
        'font': font,
        'event': result_event,
        'round': result_round,
        'heat': result_heat,
        'schedule': schedule,
        'starting_schedule_index': starting_schedule_index,
        'current_schedule_index': current_schedule_index,
        'original_event': original_event,
        'original_round': original_round,
        'original_heat': original_heat,
    }


def handle_heat_change(request, schedule, current_schedule_index, starting_schedule_index,
                       current_event, current_round, current_heat,
                       original_event, original_round, original_heat, events):
    """Handle a keyboard heat change request.

    Args:
        request: One of 'next', 'prev', or 'reset'
        schedule: Current schedule list (empty if no schedule)
        current_schedule_index: Index in schedule of currently displayed event
        starting_schedule_index: Index in schedule of reference event (keyboard floor)
        current_event: Currently displayed event number
        current_round: Currently displayed round number
        current_heat: Currently displayed heat number
        original_event: Reference event number (keyboard floor)
        original_round: Reference round number (keyboard floor)
        original_heat: Reference heat number (keyboard floor)
        events: Events dict for checking existence of next/prev heats

    Returns:
        Tuple of (event, round, heat, schedule_index) with updated values
    """
    if schedule:
        # Schedule-based navigation
        if request == 'next':
            if current_schedule_index < len(schedule) - 1:
                current_schedule_index += 1
                current_event, current_round, current_heat = schedule[current_schedule_index]
                position_text = get_schedule_position_text(schedule, current_event, current_round, current_heat)
                logging.info("Moving to next event: %s", position_text)
            else:
                logging.info("Already at last event in schedule (position %d of %d)",
                           current_schedule_index + 1, len(schedule))
        elif request == 'prev':
            if current_schedule_index > starting_schedule_index:
                current_schedule_index -= 1
                current_event, current_round, current_heat = schedule[current_schedule_index]
                position_text = get_schedule_position_text(schedule, current_event, current_round, current_heat)
                logging.info("Moving to previous event: %s", position_text)
            else:
                logging.info("Cannot go before starting event (position %d of %d)",
                           starting_schedule_index + 1, len(schedule))
        elif request == 'reset':
            if current_schedule_index != starting_schedule_index:
                current_schedule_index = starting_schedule_index
                current_event, current_round, current_heat = schedule[current_schedule_index]
                position_text = get_schedule_position_text(schedule, current_event, current_round, current_heat)
                logging.info("Resetting to starting event: %s", position_text)
            else:
                position_text = get_schedule_position_text(schedule, current_event, current_round, current_heat)
                logging.info("Already at starting event: %s", position_text)
    else:
        # Heat increment mode (fallback when no schedule)
        if request == 'next':
            # Try next heat
            next_heat = current_heat + 1
            if (current_event, current_round, next_heat) in events:
                current_heat = next_heat
                logging.info("Switching to heat %d", current_heat)
            else:
                logging.info("No heat %d found, staying on heat %d", next_heat, current_heat)
        elif request == 'prev':
            # Try previous heat (minimum original_heat)
            prev_heat = max(original_heat, current_heat - 1)
            if prev_heat != current_heat and (current_event, current_round, prev_heat) in events:
                current_heat = prev_heat
                logging.info("Switching to heat %d", current_heat)
            else:
                logging.info("Cannot go to heat %d, staying on heat %d", prev_heat, current_heat)
        elif request == 'reset':
            # Reset to reference event (latest current_event.json)
            if current_event != original_event or current_round != original_round or current_heat != original_heat:
                current_event = original_event
                current_round = original_round
                current_heat = original_heat
                logging.info("Resetting to reference Event=%d, Round=%d, Heat=%d", current_event, current_round, current_heat)
            else:
                logging.info("Already at reference Event=%d, Round=%d, Heat=%d", current_event, current_round, current_heat)

    return current_event, current_round, current_heat, current_schedule_index


def setup_peripherals(settings, config_dir, args_keyboard_device):
    """Start background services: web server, file watcher, network monitor, keyboard listener.

    Args:
        settings: Full settings dict
        config_dir: Path to config directory
        args_keyboard_device: Keyboard device path from CLI args (or None)

    Returns:
        Tuple of (web_server, file_watcher, keyboard_listener, request_file_reload, get_display_power, set_display_power)
    """
    # File reload callback for file watcher
    def request_file_reload():
        global file_reload_requested
        with file_reload_lock:
            file_reload_requested = True

    # Display power callbacks for web server
    def get_display_power():
        global display_power_on
        with display_power_lock:
            return display_power_on

    def set_display_power(state):
        global display_power_on
        with display_power_lock:
            display_power_on = state
        logging.info(f"Display power set to {'on' if state else 'off'}")

    # Start web server if enabled
    web_server = None
    if settings.get('web', {}).get('web_enabled', False):
        web_host = settings.get('web', {}).get('web_host', '0.0.0.0')
        web_port = settings.get('web', {}).get('web_port', 5000)
        web_server = start_web_server(config_dir, web_host, web_port,
                                      get_display_power=get_display_power,
                                      set_display_power=set_display_power)
        if web_server:
            logging.info(f"Web interface available at http://{web_host}:{web_port}")
        else:
            logging.warning("Web server could not be started")

    # Start file watcher
    file_watcher = start_file_watcher(config_dir, request_file_reload)
    if file_watcher:
        logging.info("File monitoring enabled for auto-reload")
    else:
        logging.warning("File monitoring could not be started - manual restart required for file changes")

    # Start network monitor thread
    network_thread = threading.Thread(target=network_monitor_loop, daemon=True)
    network_thread.start()

    # Start keyboard listener if available
    keyboard_listener = None
    if KEYBOARD_AVAILABLE:
        if keyboard_backend == 'evdev':
            # Start evdev listener in a separate thread
            keyboard_thread = threading.Thread(
                target=evdev_keyboard_listener,
                args=(args_keyboard_device,),
                daemon=True
            )
            keyboard_thread.start()
            logging.info("Keyboard navigation enabled (evdev): Page Down (next heat), Page Up (prev heat), Period (reset)")
        elif keyboard_backend == 'pynput':
            keyboard_listener = keyboard.Listener(on_press=on_key_press_pynput)
            keyboard_listener.start()
            logging.info("Keyboard navigation enabled (pynput): Page Down (next heat), Page Up (prev heat), Period (reset)")

    return web_server, file_watcher, keyboard_listener


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
    # Combine font_path and font_name for the full font path
    default_font_full_path = os.path.join(fonts['font_path'], fonts['font_name'])
    parser.add_argument('--font', default=default_font_full_path, help='Path to BDF font for rgbmatrix')
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

    # Start peripheral services
    web_server, file_watcher, keyboard_listener = setup_peripherals(
        settings, config_dir, args.keyboard_device)

    # Load schedule file if available
    schedule_path = os.path.join(config_dir, "lynx.sch")
    schedule = parse_schedule(schedule_path)
    if schedule:
        # Validate schedule entries against loaded events
        schedule = validate_schedule_entries(schedule, events)
        if schedule:
            # Find starting position in schedule
            starting_schedule_index = find_schedule_index(schedule, args.event, args.round, args.heat)
            if starting_schedule_index < 0:
                # Current event not in schedule - find nearest
                starting_schedule_index = find_nearest_schedule_index(schedule, args.event, args.round, args.heat)
                if starting_schedule_index is None:
                    logging.warning("Current event is past all scheduled events - using heat increment mode")
                    schedule = []  # Disable schedule navigation
                    starting_schedule_index = -1
                else:
                    # Switch to the nearest event
                    evt, rnd, ht = schedule[starting_schedule_index]
                    args.event = evt
                    args.round = rnd
                    args.heat = ht
                    position_text = get_schedule_position_text(schedule, evt, rnd, ht)
                    logging.info(f"Initial event not in schedule - switched to nearest: {position_text}")
            if schedule:
                logging.info(f"Schedule navigation enabled - starting at position {starting_schedule_index + 1} of {len(schedule)}")
                logging.info(get_schedule_position_text(schedule, args.event, args.round, args.heat))
        else:
            logging.warning("No valid entries in schedule - using heat increment mode")
            starting_schedule_index = -1
    else:
        logging.info("No schedule file - using heat increment mode for keyboard navigation")
        starting_schedule_index = -1

    # Store original event/round/heat and current position
    original_event = args.event
    original_round = args.round
    original_heat = args.heat
    current_heat = args.heat
    current_schedule_index = starting_schedule_index if schedule else -1

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
                result = handle_file_reload(
                    config_dir, events, affiliation_colors, disp, schedule,
                    args.file, args.font, args.colors_csv,
                    args.event, args.round, current_heat,
                    current_schedule_index, starting_schedule_index,
                    original_event, original_round, original_heat)
                events = result['events']
                affiliation_colors = result['affiliation_colors']
                disp = result['disp']
                args.font = result['font']
                args.event = result['event']
                args.round = result['round']
                current_heat = result['heat']
                schedule = result['schedule']
                starting_schedule_index = result['starting_schedule_index']
                current_schedule_index = result['current_schedule_index']
                original_event = result['original_event']
                original_round = result['original_round']
                original_heat = result['original_heat']
                continue

            # Handle heat change request
            with heat_change_lock:
                args.event, args.round, current_heat, current_schedule_index = handle_heat_change(
                    heat_change_request, schedule, current_schedule_index, starting_schedule_index,
                    args.event, args.round, current_heat,
                    original_event, original_round, original_heat, events)
                heat_change_request = None  # Clear the request
    except Exception as e:
        logging.exception("Failed to render event: %s", e)
        sys.exit(5)
    finally:
        if keyboard_listener:
            keyboard_listener.stop()


if __name__ == '__main__':
    main()
