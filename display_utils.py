"""
display_utils.py

Reusable display utilities for LED matrix rendering.
Provides text measurement, font loading, layout helpers, and drawing primitives.
"""

import logging
import os
from typing import List


def load_font_with_fallback(graphics, font_path: str):
    """Load a BDF font with fallback to relative path.

    Args:
        graphics: Graphics module from matrix backend
        font_path: Path to BDF font file

    Returns:
        Loaded font object
    """
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
    return font


def load_font_metadata(font_path: str) -> dict:
    """Load BDF font metadata using bdflib.

    Args:
        font_path: Path to BDF font file

    Returns:
        Dictionary with keys: 'cap_height', 'font_ascent'

    Raises:
        ImportError: If bdflib is not installed
        FileNotFoundError: If font file does not exist
    """
    import bdflib.reader

    # Try original path
    paths_to_try = [font_path]

    # Also try relative path
    alt_path = os.path.join(os.path.dirname(__file__), font_path)
    if alt_path != font_path:
        paths_to_try.append(alt_path)

    for path in paths_to_try:
        if os.path.exists(path):
            with open(path, 'rb') as f:
                font = bdflib.reader.read_bdf(f)

            # Extract metadata
            metadata = {
                'cap_height': int(font.properties.get(b'CAP_HEIGHT', 0)),
                'font_ascent': int(font.properties.get(b'FONT_ASCENT', 0))
            }

            logging.info("Loaded font metadata from %s: %s", path, metadata)
            return metadata

    raise FileNotFoundError(f"Font file not found: {font_path}")


def measure_text_width(font, text: str) -> int:
    """Measure text width in pixels using font metrics.

    Args:
        font: Font object from graphics module
        text: Text to measure

    Returns:
        Width in pixels, or fallback estimate if font metrics unavailable
    """
    try:
        return sum(font.CharacterWidth(ord(c)) for c in text)
    except Exception:
        return max(1, len(text)) * 6


def calculate_text_baseline(y0: int, line_height: int, font_metadata: dict, font_shift: int) -> int:
    """Calculate baseline Y coordinate for vertically centered text.

    Args:
        y0: Top Y coordinate of the line
        line_height: Height of the line in pixels
        font_metadata: Dictionary with 'cap_height' and 'font_ascent' keys
        font_shift: Vertical adjustment for font positioning

    Returns:
        Y coordinate for text baseline
    """
    # Use cap_height if available, otherwise font_ascent
    font_height = font_metadata.get('cap_height') or font_metadata['font_ascent']
    offset = (line_height - font_height) / 2
    return int(y0 + line_height - offset + font_shift)


def truncate_text_to_width(font, text: str, max_width: int) -> str:
    """Truncate text to fit within max_width pixels.

    Args:
        font: Font object from graphics module
        text: Text to truncate
        max_width: Maximum width in pixels

    Returns:
        Truncated text that fits within max_width
    """
    while text and measure_text_width(font, text) > max_width:
        text = text[:-1]
    return text


def wrap_text_lines(font, text: str, max_width: int) -> List[str]:
    """Wrap text into multiple lines based on width constraints.

    Uses word-based wrapping when possible.

    Args:
        font: Font object from graphics module
        text: Text to wrap
        max_width: Maximum width per line in pixels

    Returns:
        List of text lines that fit within max_width
    """
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test_line = (current_line + " " + word).strip()
        if measure_text_width(font, test_line) <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return lines


def fill_rectangle(canvas, graphics, x0: int, y0: int, x1: int, y1: int, color):
    """Fill a rectangle with solid color.

    Args:
        canvas: Canvas object to draw on
        graphics: Graphics module from matrix backend
        x0: Left X coordinate
        y0: Top Y coordinate
        x1: Right X coordinate (inclusive)
        y1: Bottom Y coordinate (inclusive)
        color: Color object from graphics.Color()
    """
    for y in range(y0, y1 + 1):
        graphics.DrawLine(canvas, x0, y, x1, y, color)


def draw_centered_text(canvas, graphics, font, font_metadata: dict, y0: int, line_height: int,
                       canvas_width: int, text: str, color, font_shift: int):
    """Draw horizontally centered text at specified Y position.

    Note this function may not work properly on Window using RGBMatrixEmulator as it draws
    text starting at at the font bounding box X offset, which skews centering calculations.
    The Linux rgbmatrix library does not have this issue. Best workaround is to edit the BDF
    font to set the FBBXOFF property to zero.

    Args:
        canvas: Canvas object to draw on
        graphics: Graphics module from matrix backend
        font: Font object
        font_metadata: Dictionary with 'cap_height', 'font_ascent' keys
        y0: Top Y coordinate of the text line
        line_height: Height of line in pixels
        canvas_width: Width of canvas in pixels
        text: Text to draw
        color: Color object from graphics.Color()
        font_shift: Vertical adjustment for font positioning
    """
    text_width = measure_text_width(font, text)
    x_pos = max(0, (canvas_width - text_width) // 2)
    y_baseline = calculate_text_baseline(y0, line_height, font_metadata, font_shift)
    graphics.DrawText(canvas, font, x_pos, y_baseline, color, text)
