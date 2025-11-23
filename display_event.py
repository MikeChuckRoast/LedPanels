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
import csv
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Default configuration
DEFAULT_WIDTH = 64
DEFAULT_HEIGHT = 32
DEFAULT_LINE_HEIGHT = 16  # pixels per text line (half a 32px panel)
#DEFAULT_FONT_PATH = "/home/mike/u8g2/tools/font/bdf/helvB12.bdf"
DEFAULT_FONT_PATH = "/Users/mike/Documents/Code Projects/u8g2/tools/font/bdf/helvB12.bdf"
DEFAULT_INTERVAL = 2.0
FONT_SHIFT = 7


def try_import_rgbmatrix():
    """Try to import a real rgbmatrix backend or an emulator.

    Returns a tuple (RGBMatrix, RGBMatrixOptions, graphics) or (None, None, None).
    """
    try:
        from rgbmatrix import (RGBMatrix, RGBMatrixOptions,  # type: ignore
                               graphics)
        return RGBMatrix, RGBMatrixOptions, graphics
    except Exception:
        # Try common emulator module names. The user's environment may provide
        # a module named `RGBMatrixEmulator` which exposes the same API.
        try:
            from RGBMatrixEmulator import RGBMatrix  # type: ignore
            from RGBMatrixEmulator import RGBMatrixOptions, graphics
            return RGBMatrix, RGBMatrixOptions, graphics
        except Exception:
            try:
                # Some emulators use lowercase package names
                from rgbmatrix_emulator import RGBMatrix  # type: ignore
                from rgbmatrix_emulator import RGBMatrixOptions, graphics
                return RGBMatrix, RGBMatrixOptions, graphics
            except Exception:
                return None, None, None


def load_affiliation_colors(csv_path: str) -> Dict[str, Tuple[Tuple[int, int, int], Tuple[int, int, int]]]:
    """Load affiliation color mappings from CSV file.

    CSV format: affiliation, bgcolor (hex), textcolor (hex)
    Returns: Dict mapping affiliation -> ((bg_r, bg_g, bg_b), (text_r, text_g, text_b))
    """
    colors = {}
    if not os.path.isfile(csv_path):
        logging.warning("Colors file not found: %s", csv_path)
        return colors

    try:
        with open(csv_path, "r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                affil = row.get("affiliation", "").strip()
                bg_hex = row.get("bgcolor", "").strip()
                text_hex = row.get("text", "").strip()

                if not affil or not bg_hex or not text_hex:
                    continue

                # Parse hex colors (format: #RRGGBB)
                try:
                    bg_hex = bg_hex.lstrip('#')
                    text_hex = text_hex.lstrip('#')
                    bg_rgb = tuple(int(bg_hex[i:i+2], 16) for i in (0, 2, 4))
                    text_rgb = tuple(int(text_hex[i:i+2], 16) for i in (0, 2, 4))
                    colors[affil] = (bg_rgb, text_rgb)
                except ValueError:
                    logging.warning("Invalid color format for %s: bg=%s, text=%s", affil, bg_hex, text_hex)
                    continue
    except Exception as e:
        logging.error("Failed to load colors from %s: %s", csv_path, e)

    logging.info("Loaded %d affiliation color mappings", len(colors))
    return colors


def parse_lynx_file(path: str) -> Dict[Tuple[int, int, int], Dict]:
    """Parse the lynx.evt CSV file into a mapping of (event, round, heat) -> event dict.

    Event header lines start with a number in the first column. Athlete lines
    have an empty first column (start with a comma).

    Event header format (we only care about the first 4 columns):
      event number, round number, heat number, event name, ...

    Athlete line format (we only care about the first 6 columns):
      '', athleteId, lane, last name, first name, affiliation, ...
    """
    events: Dict[Tuple[int, int, int], Dict] = {}

    if not os.path.isfile(path):
        raise FileNotFoundError(f"lynx file not found: {path}")

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        current_event_key: Optional[Tuple[int, int, int]] = None
        for raw in fh:
            line = raw.strip('\n')
            if not line:
                continue
            # Split CSV; use simple split because format is basic
            parts = [p.strip() for p in line.split(',')]
            if not parts:
                continue
            first = parts[0]
            # Event header if first column contains a number
            if first and first.isdigit():
                try:
                    ev = int(parts[0])
                    rd = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                    ht = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
                    name = parts[3] if len(parts) > 3 else ""
                except Exception:
                    # Malformed header; skip
                    current_event_key = None
                    continue
                key = (ev, rd, ht)
                events[key] = {"event": ev, "round": rd, "heat": ht, "name": name, "athletes": []}
                current_event_key = key
            else:
                # Athlete line if it starts with an empty first column
                if current_event_key is None:
                    # No current event; ignore
                    continue
                # athleteId, lane, last, first, affiliation
                # parts[0] is empty
                athlete = {}
                athlete["id"] = parts[1] if len(parts) > 1 else ""
                athlete["lane"] = parts[2] if len(parts) > 2 else ""
                athlete["last"] = parts[3] if len(parts) > 3 else ""
                athlete["first"] = parts[4] if len(parts) > 4 else ""
                athlete["affiliation"] = parts[5] if len(parts) > 5 else ""
                events[current_event_key]["athletes"].append(athlete)

    return events


def is_relay_event(athletes: List[Dict]) -> bool:
    """Detect if this is a relay event based on athlete data.

    Relay events have:
    - All first names empty
    - Last names matching pattern like 'Riverview' or 'Milan'
    - Affiliation matching pattern like 'RICO  A' or 'MILA  A'
    """
    if not athletes:
        return False

    import re
    for athlete in athletes:
        first = (athlete.get("first") or "").strip()
        last = (athlete.get("last") or "").strip()
        affil = (athlete.get("affiliation") or "").strip()

        # If any athlete has a first name, it's not a relay
        if first:
            return False

        # Check if affiliation matches relay pattern (3-4 letters, spaces, then a letter)
        if not re.match(r'^\w{3,4}\s+\w$', affil):
            return False

    return True


def extract_relay_suffix(affiliation: str) -> str:
    """Extract the relay suffix letter from affiliation (e.g., 'RICO  A' -> 'A')."""
    affil = affiliation.strip()
    if affil:
        # Get the last non-space character
        return affil.split()[-1] if affil.split() else ""
    return ""


def format_athlete_line(a: Dict, is_relay: bool = False) -> str:
    """Format athlete display string for the name column.

    For individual events: 'First L'
    For relay events: 'Team Name A' (team from last name, suffix from affiliation)

    NOTE: lane is displayed separately in its own column.
    """
    if is_relay:
        # For relay events, last name contains team name
        team_name = (a.get("last") or "").strip()
        affiliation = (a.get("affiliation") or "").strip()
        suffix = extract_relay_suffix(affiliation)
        return f"{team_name} {suffix}".strip()
    else:
        # For individual events
        first = (a.get("first") or "").strip()
        last = (a.get("last") or "").strip()
        last_initial = (last[0] + '.') if last else ""
        return f"{first} {last_initial}".strip()


def paginate_items(items: List[Dict], page_size: int):
    """Yield successive pages (lists) of items of size `page_size`."""
    for i in range(0, len(items), page_size):
        yield items[i:i + page_size]


def draw_event_on_matrix(event: Dict, matrix_classes, font_path: str, width: int, height: int,
                         line_height: int = DEFAULT_LINE_HEIGHT, interval: float = DEFAULT_INTERVAL,
                         chain: int = 2, parallel: int = 1, gpio_slowdown: int = 3, once: bool = False,
                         affiliation_colors: Optional[Dict[str, Tuple[Tuple[int, int, int], Tuple[int, int, int]]]] = None,
                         header_rows: int = 1):
    """Render the given event repeatedly (paging) onto the RGB matrix.

    `matrix_classes` is the tuple returned by `try_import_rgbmatrix()`.
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
    athlete_pages = list(paginate_items(athletes, athlete_lines_per_page)) or [[]]

    # Detect if this is a relay event
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

            # Look up colors - for relay events, use last name (team name) for color lookup
            if is_relay:
                # For relay events, last name contains the team name
                color_key = (athlete.get("last") or "").strip()
            else:
                # For individual events, use affiliation
                color_key = (athlete.get("affiliation") or "").strip()

            text_color = white
            bg_color = black

            if affiliation_colors and color_key in affiliation_colors:
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
            return
        while True:
            render_page(page_idx)
            time.sleep(interval)
            page_idx = (page_idx + 1) % page_count
    except KeyboardInterrupt:
        matrix.Clear()


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
    args = parser.parse_args()

    try:
        events = parse_lynx_file(args.file)
    except Exception as e:
        logging.error("Failed to parse lynx file: %s", e)
        sys.exit(2)

    # Load affiliation colors
    affiliation_colors = load_affiliation_colors(args.colors_csv)

    key = (args.event, args.round, args.heat)
    if key not in events:
        logging.error("Requested event not found: %s", key)
        # Show available events briefly
        logging.info("Available events: %s", sorted(events.keys()))
        sys.exit(3)

    event = events[key]

    # Check if there are multiple heats for this event/round combination
    heat_count = sum(1 for k in events.keys() if k[0] == args.event and k[1] == args.round)
    if heat_count > 1:
        # Prepend heat number to event name
        event["name"] = f"#{args.heat} {event['name']}"

    matrix_classes = try_import_rgbmatrix()
    if matrix_classes[0] is None:
        logging.error("No rgbmatrix backend available: install 'rgbmatrix' or an emulator module named 'RGBMatrixEmulator' or 'rgbmatrix_emulator'")
        sys.exit(4)

    try:
        draw_event_on_matrix(event, matrix_classes, args.font, args.width, args.height,
                             line_height=args.line_height, interval=args.interval,
                             chain=args.chain, parallel=args.parallel, gpio_slowdown=args.gpio_slowdown,
                             once=args.once, affiliation_colors=affiliation_colors,
                             header_rows=args.header_rows)
    except Exception as e:
        logging.exception("Failed to render event: %s", e)
        sys.exit(5)


if __name__ == '__main__':
    main()
