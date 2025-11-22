"""
led_display.py

Draws a two-row LED-style display:
- Top half: white background, black centered text (configurable MESSAGE).
- Bottom half: black background, white time text (HH:MM:SS).

The script will use `rgbmatrix` (the same library used in the repo) when available
so it can drive real hardware. If `rgbmatrix` is not installed, it falls back to
rendering a PIL image and saves it as `output.png` (useful for development).

Configuration variables near the top control the font, message, resolution and
whether the script runs once or continuously.
"""

import argparse
import logging
import os
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
FONT_PATH = "fonts/9x18B.bdf"

# Run continuously when True (update time every second). Default is False -> single frame.
LOOP = True


def try_import_rgbmatrix():
    try:
        from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
        return RGBMatrix, RGBMatrixOptions, graphics
    except Exception:
        return None, None, None


def draw_with_rgbmatrix(message, font_path, width, height, once=True, chain=2, parallel=1, gpio_slowdown=3):
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
        y_top = (top_h + font.height) // 2 - 4
        graphics.DrawText(canvas, font, x_top, y_top, white, message)

        # Bottom time
        now = datetime.now().strftime('%H:%M:%S')
        time_width = sum(font.CharacterWidth(ord(c)) for c in now)
        x_bot = max(0, (canvas_width - time_width) // 2)
        # Baseline for bottom: offset by top_h
        y_bot = top_h + (bottom_h + font.height) // 2 - 4
        graphics.DrawText(canvas, font, x_bot, y_bot, white, now)

        # Push to matrix
        try:
            canvas = matrix.SwapOnVSync(canvas)
            logging.debug("Swapped canvas to display")
        except Exception as e:
            logging.exception("SwapOnVSync failed: %s", e)

    try:
        if once:
            render_once()
        else:
            while True:
                render_once()
                time.sleep(1)
    except KeyboardInterrupt:
        matrix.Clear()


def draw_with_pil(message, font_path, width, height, once=True, out_file="output.png"):
    # PIL fallback for development / simulation
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as e:
        raise RuntimeError("Pillow is required for PIL fallback: pip install pillow") from e

    top_h = height // 2
    bottom_h = height - top_h

    # Try to load a TTF font; if the path is BDF or not loadable, fall back to default
    pil_font = None
    font_size = max(10, top_h - 2)
    try:
        pil_font = ImageFont.truetype(font_path, font_size)
    except Exception:
        # Try relative path
        alt = os.path.join(os.path.dirname(__file__), font_path)
        try:
            pil_font = ImageFont.truetype(alt, font_size)
        except Exception:
            pil_font = ImageFont.load_default()

    def render_and_save():
        img = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(img)

        # Fill top white (already white), fill bottom black
        draw.rectangle([0, top_h, width, height], fill='black')

        # Helper to measure text size with various Pillow versions
        def measure_text(draw_obj, fnt, txt):
            try:
                # Pillow >= 8.0
                bbox = draw_obj.textbbox((0, 0), txt, font=fnt)
                return bbox[2] - bbox[0], bbox[3] - bbox[1]
            except Exception:
                try:
                    return fnt.getsize(txt)
                except Exception:
                    # Last fallback (older Pillow)
                    return draw_obj.textsize(txt, font=fnt)

        # Top text (black on white), centered horizontally and vertically within top half
        w, h = measure_text(draw, pil_font, message)
        x = (width - w) // 2
        y = (top_h - h) // 2
        draw.text((x, y), message, font=pil_font, fill='black')

        # Bottom time (white on black)
        now = datetime.now().strftime('%H:%M:%S')
        tw, th = measure_text(draw, pil_font, now)
        tx = (width - tw) // 2
        ty = top_h + (bottom_h - th) // 2
        draw.text((tx, ty), now, font=pil_font, fill='white')

        # Ensure output directory exists
        out_dir = os.path.dirname(out_file) or '.'
        if not os.path.isdir(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except Exception:
                logging.exception("Failed to create output directory: %s", out_dir)

        try:
            img.save(out_file)
            logging.info("Saved simulated frame to %s", out_file)
        except Exception:
            logging.exception("Failed to save simulated frame to %s", out_file)

    if once:
        render_and_save()
    else:
        try:
            while True:
                render_and_save()
                time.sleep(1)
        except KeyboardInterrupt:
            print("Stopped by user")


def main():
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
    parser = argparse.ArgumentParser(description="Two-row LED display (top message, bottom clock)")
    parser.add_argument('--font', '-f', default=FONT_PATH, help='Path to font file to use')
    parser.add_argument('--message', '-m', default=MESSAGE, help='Top half message text')
    parser.add_argument('--width', type=int, default=WIDTH, help='Display width in pixels')
    parser.add_argument('--height', type=int, default=HEIGHT, help='Display height in pixels')
    # Loop flag: default follows the top-level LOOP constant; provide --no-loop to disable
    parser.add_argument('--loop', dest='loop', action='store_true', help='Run continuously and update every second')
    parser.add_argument('--no-loop', dest='loop', action='store_false', help="Don't loop; render a single frame")
    parser.set_defaults(loop=LOOP)
    parser.add_argument('--out', default='output.png', help='Output filename for PIL fallback')
    parser.add_argument('--chain', type=int, default=1, help='Number of panels chained horizontally (chain_length)')
    parser.add_argument('--parallel', type=int, default=1, help='Number of panels stacked vertically (parallel)')
    parser.add_argument('--gpio-slowdown', type=int, default=3, help='gpio_slowdown for RGBMatrixOptions (optional)')
    args = parser.parse_args()

    logging.info("Resolved arguments: message=%s width=%d height=%d loop=%s font=%s out=%s",
                 args.message, args.width, args.height, args.loop, args.font, args.out)

    # Try to use rgbmatrix first so this script can run on your hardware
    RGBMatrix, RGBMatrixOptions, graphics = try_import_rgbmatrix()
    if RGBMatrix is not None:
        try:
            if args.loop:
                logging.info("Starting rgbmatrix loop (press Ctrl+C to stop)")
            else:
                logging.info("Rendering single rgbmatrix frame")
            draw_with_rgbmatrix(args.message, args.font, args.width, args.height, once=not args.loop,
                                 chain=args.chain, parallel=args.parallel, gpio_slowdown=args.gpio_slowdown)
            return
        except Exception as e:
            print("rgbmatrix present but failed to render (falling back to PIL):", e)

    # PIL fallback
    draw_with_pil(args.message, args.font, args.width, args.height, once=not args.loop, out_file=args.out)


if __name__ == '__main__':
    main()
