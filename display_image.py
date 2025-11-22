"""
display_image.py

Displays a .bmp or .png image on the LED panels using rgbmatrix if available,
or saves a preview image using PIL if not. Accepts the image path as a command-line argument.

Usage:
    python display_image.py --image path/to/image.png
    python display_image.py --image path/to/image.bmp --width 128 --height 32
"""
import argparse
import logging
import os
import time


def try_import_rgbmatrix():
    try:
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
        return RGBMatrix, RGBMatrixOptions
    except Exception:
        return None, None

def display_with_rgbmatrix(image_path, width, height, chain=1, parallel=1, gpio_slowdown=3):
    from PIL import Image
    RGBMatrix, RGBMatrixOptions = try_import_rgbmatrix()
    if RGBMatrix is None:
        raise RuntimeError("rgbmatrix not available")

    logging.info(f"Using rgbmatrix backend (width={width} height={height})")
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
    logging.info(f"Matrix canvas size: {canvas_width}x{canvas_height}")

    # Load and resize image
    img = Image.open(image_path).convert('RGB')
    img = img.resize((canvas_width, canvas_height), Image.LANCZOS)
    logging.info(f"Loaded image: {image_path} (resized to {canvas_width}x{canvas_height})")

    # Copy pixels to canvas
    for x in range(canvas_width):
        for y in range(canvas_height):
            r, g, b = img.getpixel((x, y))
            canvas.SetPixel(x, y, r, g, b)
    canvas = matrix.SwapOnVSync(canvas)
    logging.info("Image displayed on matrix.")
    time.sleep(3600)  # Keeps the image on the display for 5 seconds

def display_with_pil(image_path, width, height, out_file="output_preview.png"):
    from PIL import Image
    img = Image.open(image_path).convert('RGB')
    img = img.resize((width, height), Image.LANCZOS)
    img.save(out_file)
    logging.info(f"Saved preview image to {out_file}")


def main():
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
    parser = argparse.ArgumentParser(description="Display an image on LED panels or save a preview.")
    parser.add_argument('--image', '-i', required=True, help='Path to .bmp or .png image file')
    parser.add_argument('--width', type=int, default=64, help='Display width in pixels')
    parser.add_argument('--height', type=int, default=32, help='Display height in pixels')
    parser.add_argument('--chain', type=int, default=1, help='Number of panels chained horizontally (chain_length)')
    parser.add_argument('--parallel', type=int, default=1, help='Number of panels stacked vertically (parallel)')
    parser.add_argument('--gpio-slowdown', type=int, default=3, help='gpio_slowdown for RGBMatrixOptions')
    parser.add_argument('--out', default='output_preview.png', help='Output filename for PIL preview')
    args = parser.parse_args()

    logging.info(f"Arguments: image={args.image} width={args.width} height={args.height} chain={args.chain} parallel={args.parallel} gpio_slowdown={args.gpio_slowdown}")

    RGBMatrix, RGBMatrixOptions = try_import_rgbmatrix()
    if RGBMatrix is not None:
        try:
            display_with_rgbmatrix(args.image, args.width, args.height, args.chain, args.parallel, args.gpio_slowdown)
            return
        except Exception as e:
            logging.error(f"rgbmatrix present but failed to render: {e}")

    # PIL fallback
    display_with_pil(args.image, args.width, args.height, out_file=args.out)

if __name__ == '__main__':
    main()
