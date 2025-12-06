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
from typing import Dict, List, Optional, Tuple

# Import from local modules
from event_parser import (
    parse_lynx_file,
    load_affiliation_colors,
    is_relay_event,
    extract_relay_suffix,
    format_athlete_line,
    fill_lanes_with_empty_rows,
    paginate_items,
)
from matrix_backend import get_matrix_backend

try:
    from pynput import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False
    logging.warning("pynput not available. Keyboard navigation disabled.")

# Default configuration
DEFAULT_WIDTH = 64
DEFAULT_HEIGHT = 32
DEFAULT_LINE_HEIGHT = 16  # pixels per text line (half a 32px panel)
#DEFAULT_FONT_PATH = "/home/mike/u8g2/tools/font/bdf/helvB12.bdf"
DEFAULT_FONT_PATH = "/Users/mike/Documents/Code Projects/u8g2/tools/font/bdf/helvB12.bdf"
DEFAULT_INTERVAL = 2.0
FONT_SHIFT = 7

# FPP configuration
FPP_DEFAULT_HOST = "127.0.0.1"
FPP_DEFAULT_PORT = 4048

# Global state for keyboard navigation
heat_change_lock = threading.Lock()
heat_change_request = None  # None, 'next', 'prev', or 'reset'


# Note: Parsing and formatting functions moved to event_parser.py
# Matrix backend functions moved to matrix_backend.py and fpp_output.py


def draw_event_on_matrix(event: Dict, matrix_classes, font_path: str, width: int, height: int,
                         line_height: int = DEFAULT_LINE_HEIGHT, interval: float = DEFAULT_INTERVAL,
                         chain: int = 2, parallel: int = 1, gpio_slowdown: int = 3, once: bool = False,
                         affiliation_colors: Optional[Dict[str, Tuple[Tuple[int, int, int], Tuple[int, int, int]]]] = None,
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

    # Calculate how many athlete lines fit per page: total lines minus header_rows
    total_lines = canvas_height // line_height
    athlete_lines_per_page = max(0, total_lines - header_rows)
    if athlete_lines_per_page <= 0:
        raise RuntimeError("Display height too small for required line height and header rows")

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
        header_height = header_rows * line_height
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
            y_pos = (line_idx * line_height) + (line_height + font.height) // 2 - FONT_SHIFT
            graphics.DrawText(canvas, font, x_pos, y_pos, black, line_text)

        # Draw athlete lines
        for idx, athlete in enumerate(page):
            # Row index on screen (header takes header_rows, so athletes start after that)
            row = idx + header_rows
            y0 = row * line_height
            y1 = y0 + line_height - 1

            # Check if this is an empty lane (only has lane number, no athlete data)
            has_athlete = bool((athlete.get("last") or "").strip() or (athlete.get("first") or "").strip())

            # Look up colors - for relay events, use last name (team name) for color lookup
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
                bg_rgb, text_rgb = affiliation_colors[color_key]
                bg_color = graphics.Color(bg_rgb[0], bg_rgb[1], bg_rgb[2])
                text_color = graphics.Color(text_rgb[0], text_rgb[1], text_rgb[2])

            # Fill background for this line
            for y in range(y0, y1 + 1):
                graphics.DrawLine(canvas, 0, y, canvas_width - 1, y, bg_color)

            # Draw lane and name in columns
            lane_txt = (athlete.get("lane") or "").strip()
            # Baseline for this row
            y_txt = y0 + (line_height + font.height) // 2 - FONT_SHIFT
            # Draw lane (left column)
            graphics.DrawText(canvas, font, lane_x, y_txt, text_color, lane_txt)

            # Only draw athlete info if there's an athlete in this lane
            if has_athlete:
                if is_relay:
                    # For relay: draw team name in middle, suffix on far right
                    team_name = (athlete.get("last") or "").strip()
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

            # Sleep in small increments to check for heat changes more frequently
            elapsed = 0.0
            check_interval = 0.1  # Check every 100ms for better responsiveness
            while elapsed < interval:
                # Check for heat change request
                global heat_change_request
                with heat_change_lock:
                    if heat_change_request is not None:
                        matrix.Clear()
                        return False  # Signal to reload

                time.sleep(check_interval)
                elapsed += check_interval

            page_idx = (page_idx + 1) % page_count
    except KeyboardInterrupt:
        matrix.Clear()
        return True


def on_key_press(key):
    """Handle keyboard events for heat navigation."""
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


def main():
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
    parser = argparse.ArgumentParser(description="Display an event from lynx.evt on LED matrix")
    parser.add_argument('--file', '-f', default='lynx.evt', help='Path to lynx.evt file')
    parser.add_argument('--colors-csv', default='colors.csv', help='Path to colors CSV file (affiliation,bgcolor,text)')
    parser.add_argument('--event', type=int, required=True, help='Event number')
    parser.add_argument('--round', type=int, required=True, help='Round number')
    parser.add_argument('--heat', type=int, required=True, help='Heat number')
    parser.add_argument('--font', default=DEFAULT_FONT_PATH, help='Path to BDF font for rgbmatrix')
    parser.add_argument('--width', type=int, default=DEFAULT_WIDTH, help='Display width in pixels')
    parser.add_argument('--height', type=int, default=DEFAULT_HEIGHT, help='Display height in pixels')
    parser.add_argument('--line-height', type=int, default=DEFAULT_LINE_HEIGHT, help='Pixels per text line')
    parser.add_argument('--header-rows', type=int, default=1, help='Number of rows for header (allows text wrapping)')
    parser.add_argument('--interval', type=float, default=DEFAULT_INTERVAL, help='Seconds per page when paging')
    parser.add_argument('--once', action='store_true', help='Render once then exit')
    parser.add_argument('--chain', type=int, default=2, help='Panels chained horizontally')
    parser.add_argument('--parallel', type=int, default=1, help='Panels stacked vertically')
    parser.add_argument('--gpio-slowdown', type=int, default=3, help='GPIO slowdown for RGBMatrixOptions')
    parser.add_argument('--fpp', action='store_true', help='Use FPP output instead of direct matrix control')
    parser.add_argument('--fpp-host', default=FPP_DEFAULT_HOST, help='FPP host IP address')
    parser.add_argument('--fpp-port', type=int, default=FPP_DEFAULT_PORT, help='FPP DDP port')
    args = parser.parse_args()

    try:
        events = parse_lynx_file(args.file)
    except Exception as e:
        logging.error("Failed to parse lynx file: %s", e)
        sys.exit(2)

    # Load affiliation colors
    affiliation_colors = load_affiliation_colors(args.colors_csv)

    # Start keyboard listener if available
    keyboard_listener = None
    if KEYBOARD_AVAILABLE:
        keyboard_listener = keyboard.Listener(on_press=on_key_press)
        keyboard_listener.start()
        logging.info("Keyboard navigation enabled: Page Down (next heat), Page Up (prev heat), Period (reset)")

    # Store original heat number
    original_heat = args.heat
    current_heat = args.heat

    # Get appropriate matrix backend (direct, emulator, or FPP)
    matrix_classes = get_matrix_backend(
        use_fpp=args.fpp,
        fpp_host=args.fpp_host,
        fpp_port=args.fpp_port,
        width=args.width,
        height=args.height
    )
    if matrix_classes[0] is None:
        if args.fpp:
            logging.error("Failed to initialize FPP output")
        else:
            logging.error("No rgbmatrix backend available: install 'rgbmatrix' or an emulator module named 'RGBMatrixEmulator' or 'rgbmatrix_emulator', or use --fpp for network output")
        sys.exit(4)

    # Main loop - allows reloading when heat changes
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
                                 line_height=args.line_height, interval=args.interval,
                                 chain=args.chain, parallel=args.parallel, gpio_slowdown=args.gpio_slowdown,
                                 once=args.once, affiliation_colors=affiliation_colors,
                                 header_rows=args.header_rows)

            if should_continue or args.once:
                break

            # Handle heat change request
            global heat_change_request
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
                    # Try previous heat (minimum 1)
                    prev_heat = max(1, current_heat - 1)
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
