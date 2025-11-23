"""
led_display.py

Draws a two-row LED-style display:
- Top half: white background, black centered text (configurable MESSAGE).
- Bottom half: black background, white time text (HH:MM:SS).

The script will use `rgbmatrix` (the same library used in the repo) when available
so it can drive real hardware. If `rgbmatrix` is not installed, it falls back to
using `RGBMatrixEmulator` implementation when present (a drop-in emulator).

Configuration variables near the top control the font, message, resolution and
whether the script runs once or continuously.
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime

# Configuration (edit these)
# Resolution matches existing scripts in this workspace (64x32 panels)
WIDTH = 64
HEIGHT = 32

# Message to display in the top half (centered left-to-right)
MESSAGE = "Test Meet"

# Font path: for real hardware the repo uses BDF fonts in `fonts/`.
# For PIL fallback, use a TTF path if available on your system; if BDF is given
# and PIL can't load it, the script will fall back to a default bitmap font.
FONT_PATH = "/home/mike/u8g2/tools/font/bdf/helvB12.bdf"
#FONT_PATH = "/Users/mike/Documents/Code Projects/u8g2/tools/font/bdf/helvB12.bdf"
FONT_SHIFT = 7


def try_import_rgbmatrix():
    # First try the real rgbmatrix bindings
    try:
        from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
        return RGBMatrix, RGBMatrixOptions, graphics
    except Exception:
        # If the real bindings aren't present, try a common emulator which
        # exposes a drop-in replacement named `RGBMatrixEmulator`.
        try:
            from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions, graphics
            return RGBMatrix, RGBMatrixOptions, graphics
        except Exception:
            return None, None, None


def draw_with_rgbmatrix(message, font_path, width, height, chain=2, parallel=1, gpio_slowdown=3):
    RGBMatrix, RGBMatrixOptions, graphics = try_import_rgbmatrix()
    if RGBMatrix is None:
        raise RuntimeError("rgbmatrix not available")

    logging.info("Using rgbmatrix backend (width=%d height=%d)", width, height)

    # Panel options (match repo defaults)
    options = RGBMatrixOptions()
    options.rows = height
    options.cols = width
    options.chain_length = chain
    options.parallel = parallel
    options.gpio_slowdown = gpio_slowdown

    matrix = RGBMatrix(options=options)
    canvas = matrix.CreateFrameCanvas()

    # Colors
    white = graphics.Color(255, 255, 255)
    black = graphics.Color(0, 0, 0)
    red = graphics.Color(192, 0, 0)

    font = graphics.Font()
    try:
        font.LoadFont(font_path)
        logging.info("Loaded rgbmatrix font: %s", font_path)
    except Exception:
        # Try a common font path relative to repo
        alt = os.path.join(os.path.dirname(__file__), font_path)
        try:
            font.LoadFont(alt)
            logging.info("Loaded rgbmatrix font (alt): %s", alt)
        except Exception:
            raise RuntimeError(f"Failed to load font for rgbmatrix: {font_path}")

    # Use the real canvas size (accounts for chain/parallel)
    canvas = matrix.CreateFrameCanvas()
    canvas_width = canvas.width
    canvas_height = canvas.height
    logging.info("Matrix canvas size: %dx%d (chain=%d parallel=%d)", canvas_width, canvas_height, chain, parallel)

    top_h = canvas_height // 2
    bottom_h = canvas_height - top_h

    def render_once():
        nonlocal canvas
        logging.debug("Rendering frame to rgbmatrix (message='%s')", message)
        canvas.Clear()

        # Draw top half background (red)
        for y in range(0, top_h):
            graphics.DrawLine(canvas, 0, y, canvas_width - 1, y, red)

        # Draw bottom half background (black)
        for y in range(top_h, canvas_height):
            graphics.DrawLine(canvas, 0, y, canvas_width - 1, y, black)

        # Top text width (sum of character widths)
        text_width = sum(font.CharacterWidth(ord(c)) for c in message)
        x_top = max(0, (canvas_width - text_width) // 2)

        # For rgbmatrix, DrawText expects baseline y; approximate center in top half
        y_top = (top_h + font.height) // 2 - FONT_SHIFT
        graphics.DrawText(canvas, font, x_top, y_top, white, message)

        # Bottom time
        now = datetime.now().strftime('%H:%M:%S')
        time_width = sum(font.CharacterWidth(ord(c)) for c in now)
        x_bot = max(0, (canvas_width - time_width) // 2)
        # Baseline for bottom: offset by top_h
        y_bot = top_h + (bottom_h + font.height) // 2 - FONT_SHIFT
        graphics.DrawText(canvas, font, x_bot, y_bot, white, now)

        # Push to matrix
        try:
            canvas = matrix.SwapOnVSync(canvas)
            logging.debug("Swapped canvas to display")
        except Exception as e:
            logging.exception("SwapOnVSync failed: %s", e)

    try:
        while True:
            render_once()
            time.sleep(1)
    except KeyboardInterrupt:
        matrix.Clear()


def main():
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
    parser = argparse.ArgumentParser(description="Two-row LED display (top message, bottom clock)")
    parser.add_argument('--font', '-f', default=FONT_PATH, help='Path to font file to use')
    parser.add_argument('--message', '-m', default=MESSAGE, help='Top half message text')
    parser.add_argument('--width', type=int, default=WIDTH, help='Display width in pixels')
    parser.add_argument('--height', type=int, default=HEIGHT, help='Display height in pixels')
    parser.add_argument('--chain', type=int, default=2, help='Number of panels chained horizontally (chain_length)')
    parser.add_argument('--parallel', type=int, default=1, help='Number of panels stacked vertically (parallel)')
    parser.add_argument('--gpio-slowdown', type=int, default=3, help='gpio_slowdown for RGBMatrixOptions (optional)')
    args = parser.parse_args()

    logging.info("Resolved arguments: message=%s width=%d height=%d font=%s",
                 args.message, args.width, args.height, args.font)

    # Try to use rgbmatrix first so this script can run on your hardware
    RGBMatrix, RGBMatrixOptions, graphics = try_import_rgbmatrix()
    if RGBMatrix is not None:
        try:
            logging.info("Starting rgbmatrix loop (press Ctrl+C to stop)")
            draw_with_rgbmatrix(args.message, args.font, args.width, args.height,
                                 chain=args.chain, parallel=args.parallel, gpio_slowdown=args.gpio_slowdown)
            return
        except Exception as e:
            logging.exception("rgbmatrix present but failed to render: %s", e)
            sys.exit(1)
    # If we get here, neither the real rgbmatrix nor an RGBMatrixEmulator were
    # available. Inform the user and exit.
    logging.error("No rgbmatrix backend available: install 'rgbmatrix' or 'RGBMatrixEmulator'")
    sys.exit(1)


if __name__ == '__main__':
    main()
