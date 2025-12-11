"""
FPP (Falcon Player Protocol) output backend for LED displays.

This module provides an alternative output method that sends pixel data
to FPP receivers via DDP (Distributed Display Protocol) over UDP.
"""

import logging
import socket
from typing import Optional

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logging.warning("numpy not available. FPP mode will have reduced performance.")

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logging.warning("PIL/Pillow not available. Text rendering in FPP mode will be limited.")


class FPPMatrix:
    """Emulates RGBMatrix API but outputs to FPP via DDP (Distributed Display Protocol)."""

    def __init__(self, host: str, port: int, width: int, height: int):
        """Initialize FPP output.

        Args:
            host: FPP receiver IP address
            port: FPP DDP port (typically 4048)
            width: Display width in pixels
            height: Display height in pixels
        """
        self.host = host
        self.port = port
        self.width = width
        self.height = height
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Create frame buffer
        if NUMPY_AVAILABLE:
            self.buffer = np.zeros((height, width, 3), dtype=np.uint8)
        else:
            # Fallback to list of lists
            self.buffer = [[[0, 0, 0] for _ in range(width)] for _ in range(height)]

        logging.info("FPP output initialized: %s:%d (%dx%d)", host, port, width, height)

    def CreateFrameCanvas(self):
        """Return a canvas object (self in this case)."""
        return self

    def Clear(self):
        """Clear the display buffer."""
        if NUMPY_AVAILABLE:
            self.buffer.fill(0)
        else:
            for y in range(self.height):
                for x in range(self.width):
                    self.buffer[y][x] = [0, 0, 0]

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int):
        """Set a single pixel.

        Args:
            x: X coordinate
            y: Y coordinate
            r: Red value (0-255)
            g: Green value (0-255)
            b: Blue value (0-255)
        """
        if 0 <= x < self.width and 0 <= y < self.height:
            self.buffer[y][x] = [r, g, b]

    def SwapOnVSync(self, canvas):
        """Send the buffer to FPP via DDP protocol.

        DDP (Distributed Display Protocol) packet format:
        Header: 0x04 0x01 [data_type] [id] [offset_high] [offset_mid] [offset_low] [len_high] [len_low]
        Data: RGB bytes

        Returns:
            self (the "new" canvas)
        """
        # Convert buffer to flat RGB bytes
        if NUMPY_AVAILABLE:
            rgb_data = self.buffer.reshape(-1).tobytes()
        else:
            rgb_data = bytes([val for row in self.buffer for pixel in row for val in pixel])

        # Build DDP packet
        data_len = len(rgb_data)
        packet = bytearray([
            0x04,  # Flags: VER=0, PUSH=1 (display immediately)
            0x01,  # Sequence (increment for multi-packet, we use single packet)
            0x01,  # Data type: RGB (0x01)
            0x01,  # Destination ID
            0x00,  # Offset high byte
            0x00,  # Offset mid byte
            0x00,  # Offset low byte
            (data_len >> 8) & 0xFF,  # Length high byte
            data_len & 0xFF,         # Length low byte
        ])
        packet.extend(rgb_data)

        try:
            self.socket.sendto(packet, (self.host, self.port))
        except Exception as e:
            logging.error("Failed to send DDP packet: %s", e)

        return self  # Return self as the "new" canvas

    def close(self):
        """Close the socket."""
        self.socket.close()


class FPPMatrixOptions:
    """Configuration options for FPP output (matches RGBMatrix API)."""

    def __init__(self):
        self.rows = 32
        self.cols = 64
        self.chain_length = 1
        self.parallel = 1
        self.gpio_slowdown = 0


class FPPColor:
    """RGB color representation for FPP output."""

    def __init__(self, r: int, g: int, b: int):
        self.r = r
        self.g = g
        self.b = b


class FPPFont:
    """Font class for FPP output using PIL/Pillow."""

    def __init__(self):
        self.height = 12
        self._pil_font = None

        if PIL_AVAILABLE:
            try:
                # Try to load a default font
                self._pil_font = ImageFont.load_default()
            except Exception as e:
                logging.warning("Failed to load default PIL font: %s", e)

    def LoadFont(self, path: str):
        """Load BDF font (convert to PIL if needed).

        Note: PIL doesn't natively support BDF fonts. For production use,
        consider converting BDF to TTF or using a BDF parsing library.

        Args:
            path: Path to font file
        """
        if not PIL_AVAILABLE:
            logging.warning("PIL not available, cannot load font")
            return

        try:
            # Try to load as TrueType (if user provides TTF instead of BDF)
            if path.lower().endswith('.ttf') or path.lower().endswith('.otf'):
                self._pil_font = ImageFont.truetype(path, 12)
                logging.info("Loaded TrueType font: %s", path)
            else:
                # BDF not directly supported, use default
                self._pil_font = ImageFont.load_default()
                logging.warning("BDF fonts not fully supported in FPP mode, using default font")
        except Exception as e:
            logging.error("Failed to load font for FPP: %s", e)
            self._pil_font = ImageFont.load_default()

    def CharacterWidth(self, char_code: int) -> int:
        """Get character width in pixels.

        Args:
            char_code: Unicode character code

        Returns:
            Width in pixels
        """
        if self._pil_font and PIL_AVAILABLE:
            try:
                char = chr(char_code)
                bbox = self._pil_font.getbbox(char)
                return bbox[2] - bbox[0] if bbox else 6
            except Exception:
                pass
        return 6  # Default width


class FPPGraphics:
    """Graphics functions for FPP output (matches rgbmatrix.graphics API)."""

    Color = FPPColor
    Font = FPPFont

    @staticmethod
    def DrawText(canvas, font, x: int, y: int, color, text: str):
        """Draw text on canvas.

        Args:
            canvas: FPPMatrix canvas
            font: FPPFont instance
            x: X coordinate
            y: Y coordinate (baseline)
            color: FPPColor instance
            text: Text to draw
        """
        if not PIL_AVAILABLE:
            # Fallback: draw simple pixel blocks for each character
            for i, char in enumerate(text):
                char_x = x + (i * 6)
                # Draw a simple 5x7 rectangle for each character (placeholder)
                for dy in range(-7, 0):
                    for dx in range(5):
                        canvas.SetPixel(char_x + dx, y + dy, color.r, color.g, color.b)
            return

        try:
            # Create temporary image for text rendering
            img = Image.new('RGB', (canvas.width, canvas.height), (0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Adjust y coordinate (PIL uses top-left, we use baseline)
            adjusted_y = y - font.height + 2

            # Draw text
            draw.text((x, adjusted_y), text, fill=(color.r, color.g, color.b), font=font._pil_font)

            # Copy non-black pixels to canvas
            pixels = img.load()
            for py in range(canvas.height):
                for px in range(canvas.width):
                    r, g, b = pixels[px, py]
                    if r > 0 or g > 0 or b > 0:  # Only set non-black pixels
                        canvas.SetPixel(px, py, r, g, b)
        except Exception as e:
            logging.error("Failed to draw text in FPP mode: %s", e)

    @staticmethod
    def DrawLine(canvas, x0: int, y0: int, x1: int, y1: int, color):
        """Draw line on canvas using Bresenham's algorithm.

        Args:
            canvas: FPPMatrix canvas
            x0, y0: Start coordinates
            x1, y1: End coordinates
            color: FPPColor instance
        """
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy

        x, y = x0, y0
        while True:
            canvas.SetPixel(x, y, color.r, color.g, color.b)
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy


def create_fpp_backend(host: str, port: int, width: int, height: int):
    """Create FPP output backend.

    Args:
        host: FPP receiver IP address
        port: FPP DDP port
        width: Display width (individual panel width)
        height: Display height (individual panel height)

    Returns:
        Tuple of (matrix_class, options_class, graphics_class)

    Note:
        The factory calculates total display size by multiplying panel dimensions
        by chain_length and parallel from the options.
    """
    def create_matrix(options=None):
        """Factory function to create FPPMatrix with options."""
        if options:
            # Calculate total display size: panel size × chain × parallel
            w = options.cols * options.chain_length
            h = options.rows * options.parallel
        else:
            w = width
            h = height
        return FPPMatrix(host, port, w, h)

    return create_matrix, FPPMatrixOptions, FPPGraphics
