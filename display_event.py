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


def format_athlete_line(a: Dict) -> str:
    """Format athlete display string for the name column: 'First L'.

    NOTE: lane is displayed separately in its own column.
    """
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
                         affiliation_colors: Optional[Dict[str, Tuple[Tuple[int, int, int], Tuple[int, int, int]]]] = None):
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

    # Calculate how many athlete lines fit per page: total lines minus 1 for header
    total_lines = canvas_height // line_height
    athlete_lines_per_page = max(0, total_lines - 1)
    if athlete_lines_per_page <= 0:
        raise RuntimeError("Display height too small for required line height")

    # Prepare text elements
    header = event.get("name", "")
    athletes = event.get("athletes", [])
    athlete_pages = list(paginate_items(athletes, athlete_lines_per_page)) or [[]]

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

    def render_page(page_index: int):
        nonlocal canvas
        page = athlete_pages[page_index]
        canvas.Clear()

        # Draw header background (white) for the first line_height rows
        for y in range(0, line_height):
            graphics.DrawLine(canvas, 0, y, canvas_width - 1, y, white)

        # Header text: black on white. Compute baseline for header line (centered in box)
        try:
            header_text_width = sum(font.CharacterWidth(ord(c)) for c in header)
        except Exception:
            header_text_width = len(header) * 6
        x_header = max(0, (canvas_width - header_text_width) // 2)
        # Baseline y for header
        y_header = (line_height + font.height) // 2 - FONT_SHIFT
        graphics.DrawText(canvas, font, x_header, y_header, black, header)

        # Draw athlete lines
        for idx, athlete in enumerate(page):
            # Row index on screen (0 is header line, so athletes start at 1)
            row = idx + 1
            y0 = row * line_height
            y1 = y0 + line_height - 1

            # Look up colors for this athlete's affiliation
            affil = (athlete.get("affiliation") or "").strip()
            text_color = white
            bg_color = black

            if affiliation_colors and affil in affiliation_colors:
                bg_rgb, text_rgb = affiliation_colors[affil]
                bg_color = graphics.Color(bg_rgb[0], bg_rgb[1], bg_rgb[2])
                text_color = graphics.Color(text_rgb[0], text_rgb[1], text_rgb[2])

            # Fill background for this line
            for y in range(y0, y1 + 1):
                graphics.DrawLine(canvas, 0, y, canvas_width - 1, y, bg_color)

            # Draw lane and name in columns
            lane_txt = (athlete.get("lane") or "").strip()
            name_txt = format_athlete_line(athlete)
            # Baseline for this row
            y_txt = y0 + (line_height + font.height) // 2 - FONT_SHIFT
            # Draw lane (left column)
            graphics.DrawText(canvas, font, lane_x, y_txt, text_color, lane_txt)
            # Draw name starting at name_x
            graphics.DrawText(canvas, font, name_x, y_txt, text_color, name_txt)

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

    matrix_classes = try_import_rgbmatrix()
    if matrix_classes[0] is None:
        logging.error("No rgbmatrix backend available: install 'rgbmatrix' or an emulator module named 'RGBMatrixEmulator' or 'rgbmatrix_emulator'")
        sys.exit(4)

    try:
        draw_event_on_matrix(event, matrix_classes, args.font, args.width, args.height,
                             line_height=args.line_height, interval=args.interval,
                             chain=args.chain, parallel=args.parallel, gpio_slowdown=args.gpio_slowdown,
                             once=args.once, affiliation_colors=affiliation_colors)
    except Exception as e:
        logging.exception("Failed to render event: %s", e)
        sys.exit(5)


if __name__ == '__main__':
    main()
