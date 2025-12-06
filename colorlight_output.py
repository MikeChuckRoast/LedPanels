"""
ColorLight 5A-75B output backend

This module implements the ColorLight 5A-75B Ethernet protocol for sending
frames directly to a ColorLight 5A-75B receiver card. Based on the PyLights
project and Chubby75 reverse engineering work.

Protocol:
- Uses raw Ethernet frames (Layer 2, AF_PACKET socket)
- Requires root/sudo privileges for raw socket access
- Sends two initialization frames before data frames
- Data packets use EtherType 0x5500 + row MSB
- Pixel data is in BGR order (not RGB)
- Max 497 pixels per packet

Requirements:
- Linux/Unix system with raw socket support (AF_PACKET)
- Root/sudo privileges
- Network interface name (e.g., 'eth0', 'enp0s3')

References:
- PyLights: https://github.com/KAkerstrom/PyLights
- Chubby75: https://github.com/q3k/chubby75

"""

import logging
import socket
import struct
import sys
from typing import Optional

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except Exception:
    NUMPY_AVAILABLE = False
    logging.debug("numpy not available; using Python lists for buffers")

# Check if AF_PACKET is available (Linux/Unix only)
try:
    AF_PACKET = socket.AF_PACKET
    SOCK_RAW = socket.SOCK_RAW
    RAW_SOCKET_AVAILABLE = True
except AttributeError:
    RAW_SOCKET_AVAILABLE = False
    logging.warning("AF_PACKET not available (Windows?). ColorLight backend requires Linux/Unix.")


class ColorLightMatrix:
    """ColorLight 5A-75B matrix backend using raw Ethernet frames."""

    # Protocol constants from PyLights
    MAX_PIXELS_PER_PACKET = 497

    # P5 panels use 1/16 scan multiplexing
    # This means 64 physical rows are divided into 4 logical rows (64/16=4)
    SCAN_RATE = 16

    # MAC addresses (can be arbitrary for 5A-75B)
    DST_MAC = b'\x11\x22\x33\x44\x55\x66'
    SRC_MAC = b'\x22\x22\x33\x44\x55\x66'

    def __init__(self, interface: str, width: int, height: int):
        """Initialize ColorLight backend.

        Args:
            interface: Network interface name (e.g., 'eth0', 'enp0s3')
            width: Display width in pixels
            height: Display height in pixels
        """
        if not RAW_SOCKET_AVAILABLE:
            raise RuntimeError(
                "ColorLight backend requires AF_PACKET (Linux/Unix only). "
                "Windows is not supported for direct ColorLight communication."
            )

        self.interface = interface
        self.width = int(width)
        self.height = int(height)

        # Create raw socket and bind to interface
        try:
            self.sock = socket.socket(AF_PACKET, SOCK_RAW)
            self.sock.bind((interface, 0))
            logging.info("ColorLight backend bound to interface '%s'", interface)
        except PermissionError:
            raise RuntimeError(
                "ColorLight backend requires root/sudo privileges for raw socket access. "
                "Please run with: sudo python display_event.py --colorlight ..."
            )
        except OSError as e:
            raise RuntimeError(
                f"Failed to bind to interface '{interface}': {e}. "
                "Available interfaces: check 'ip link' or 'ifconfig'"
            )

        # Frame buffer: height x width x 3 (BGR order for ColorLight)
        if NUMPY_AVAILABLE:
            self.buffer = np.zeros((self.height, self.width, 3), dtype='uint8')
        else:
            self.buffer = [[[0, 0, 0] for _ in range(self.width)] for _ in range(self.height)]

        logging.info("ColorLight 5A-75B initialized on %s: %dx%d", interface, width, height)

    def _send_init_frames(self):
        """Send the two initialization frames required by ColorLight 5A-75B."""
        import time

        # First initialization frame: EtherType 0x0101, 98 bytes of zeros
        first_frame = self.DST_MAC + self.SRC_MAC + b'\x01\x01'
        first_frame += b'\x00' * 98

        # Second initialization frame: EtherType 0x0AFF, starts with 0xFF 0xFF 0xFF
        second_frame = self.DST_MAC + self.SRC_MAC + b'\x0A\xFF'
        second_frame += b'\xFF\xFF\xFF'
        second_frame += b'\x00' * 60

        try:
            sent1 = self.sock.send(first_frame)
            time.sleep(0.001)  # Small delay between init frames
            sent2 = self.sock.send(second_frame)
            # No delay before data - send immediately to prevent flash of old content
            logging.debug("Sent ColorLight init frames: frame1=%d bytes, frame2=%d bytes", sent1, sent2)
        except Exception as e:
            logging.error("Failed to send initialization frames: %s", e)

    def CreateFrameCanvas(self):
        return self

    def Clear(self):
        if NUMPY_AVAILABLE:
            self.buffer.fill(0)
        else:
            for y in range(self.height):
                for x in range(self.width):
                    self.buffer[y][x] = [0, 0, 0]

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int):
        """Set pixel at (x, y) to RGB color. ColorLight uses BGR order internally."""
        if 0 <= x < self.width and 0 <= y < self.height:
            if NUMPY_AVAILABLE:
                # Store as BGR for ColorLight
                self.buffer[y, x, 0] = int(b)  # Blue
                self.buffer[y, x, 1] = int(g)  # Green
                self.buffer[y, x, 2] = int(r)  # Red
            else:
                self.buffer[y][x] = [int(b), int(g), int(r)]  # BGR order

    def _build_data_frame(self, row_num: int, pixel_data: bytes, offset: int = 0) -> bytes:
        """Build a ColorLight data frame for one row.

        Args:
            row_num: Row number (0-indexed)
            pixel_data: BGR pixel data for this row
            offset: Pixel offset within the row (for multi-packet rows)

        Returns:
            Complete Ethernet frame ready to send
        """
        # Calculate actual pixel count from data
        pixel_count = len(pixel_data) // 3

        # Build frame header: MAC addresses + EtherType (0x55)
        data_prefix = self.DST_MAC + self.SRC_MAC + b'\x55'

        # Frame structure (matching PyLights exactly):
        # - Row number: 2 bytes (big-endian)
        # - Pixel offset: 2 bytes (big-endian)
        # - Pixel count: 2 bytes (big-endian)
        # - Magic bytes: 0x08 0x80
        # - BGR pixel data
        frame = data_prefix + row_num.to_bytes(2, 'big')
        frame += struct.pack('>H', offset)  # Pixel offset (big-endian)
        frame += struct.pack('>H', pixel_count)  # Pixel count (big-endian)
        frame += b'\x08\x80'  # Magic bytes
        frame += pixel_data

        return frame

    def SwapOnVSync(self, canvas):
        """Send the frame buffer to the ColorLight card."""
        import time

        frame_count = 0
        bytes_sent = 0

        try:
            # Use the canvas buffer (should be self, but be explicit)
            buffer_to_send = canvas.buffer if hasattr(canvas, 'buffer') else self.buffer

            # Send each row sequentially FIRST
            for row_num in range(self.height):
                if NUMPY_AVAILABLE:
                    row_data = bytes(buffer_to_send[row_num].flatten().tolist())
                else:
                    row_data = bytearray()
                    for pixel in buffer_to_send[row_num]:
                        row_data.extend(bytes(pixel))
                    row_data = bytes(row_data)

                # Send entire row in one frame (128 pixels < 497 max)
                frame = self._build_data_frame(row_num, row_data, offset=0)
                sent = self.sock.send(frame)
                frame_count += 1
                bytes_sent += sent
                time.sleep(0.001)  # 1ms delay between frames (same as PyLights)

                # Debug first few rows
                if row_num < 3:
                    logging.debug(f"Row {row_num}: sent {sent} bytes, pixel_count={len(row_data)//3}")

            # Send init frames AFTER all data to commit/display the new frame
            self._send_init_frames()

            logging.info("ColorLight frame sent: %d data frames, %d total bytes", frame_count, bytes_sent)

        except Exception as e:
            logging.error("Failed to send frame to ColorLight: %s", e)

        return self

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


class ColorLightOptions:
    """Options object compatible with RGBMatrix API."""
    def __init__(self):
        self.rows = 32
        self.cols = 64
        self.chain_length = 1
        self.parallel = 1
        self.gpio_slowdown = 0  # Not used for ColorLight


class ColorLightGraphics:
    """Graphics compatibility layer for display_event with BDF font support."""

    class Color:
        def __init__(self, r, g, b):
            self.r = int(r)
            self.g = int(g)
            self.b = int(b)

    class Font:
        def __init__(self):
            self.height = 12
            self.glyphs = {}  # char -> (bbx, dwidth, bitmap)
            self.baseline = 10

        def LoadFont(self, path: str):
            """Load BDF font file."""
            try:
                with open(path, 'r') as f:
                    lines = f.readlines()

                i = 0
                while i < len(lines):
                    line = lines[i].strip()

                    if line.startswith('FONTBOUNDINGBOX'):
                        parts = line.split()
                        self.height = int(parts[2])
                        # Y offset in FONTBOUNDINGBOX is typically negative
                        # baseline is the distance from top of font to baseline
                        font_y_offset = int(parts[4])
                        self.baseline = self.height + font_y_offset

                    elif line.startswith('STARTCHAR'):
                        # Parse character
                        char_name = line.split()[1]
                        i += 1

                        encoding = None
                        dwidth = None
                        bbx = None
                        bitmap = []

                        while i < len(lines):
                            line = lines[i].strip()

                            if line.startswith('ENCODING'):
                                encoding = int(line.split()[1])
                            elif line.startswith('DWIDTH'):
                                parts = line.split()
                                dwidth = int(parts[1])  # Device width (cursor advance)
                            elif line.startswith('BBX'):
                                parts = line.split()
                                bbx = (int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]))
                            elif line.startswith('BITMAP'):
                                i += 1
                                while i < len(lines) and not lines[i].strip().startswith('ENDCHAR'):
                                    bitmap.append(lines[i].strip())
                                    i += 1
                                break
                            i += 1

                        if encoding is not None and bbx is not None:
                            try:
                                char = chr(encoding)
                                # Use dwidth if available, otherwise use bbx width
                                advance = dwidth if dwidth is not None else bbx[0]
                                self.glyphs[char] = (bbx, advance, bitmap)
                            except:
                                pass

                    i += 1

                logging.info(f"Loaded BDF font: {len(self.glyphs)} glyphs, height={self.height}, baseline={self.baseline}")
                return True
            except Exception as e:
                logging.error(f"Failed to load font {path}: {e}")
                return False

        def CharacterWidth(self, char_code: int) -> int:
            try:
                char = chr(char_code)
                if char in self.glyphs:
                    _, dwidth, _ = self.glyphs[char]
                    return dwidth  # Return device width (cursor advance)
            except:
                pass
            return 6  # Default width

    @staticmethod
    def DrawText(canvas, font, x: int, y: int, color, text: str):
        """Draw text using BDF font glyphs.

        Args:
            canvas: Drawing surface
            font: BDF font with loaded glyphs
            x, y: Starting position (y is baseline position)
            color: Text color
            text: String to draw
        """
        cursor_x = x

        for char in text:
            if char not in font.glyphs:
                # Use space width for unknown chars
                cursor_x += font.CharacterWidth(ord(' ')) if ' ' in font.glyphs else 6
                continue

            bbx, dwidth, bitmap = font.glyphs[char]
            char_width, char_height, x_offset, y_offset = bbx

            # Draw each row of the bitmap
            for row_idx, hex_row in enumerate(bitmap):
                if not hex_row:
                    continue

                # Convert hex string to bytes
                try:
                    # BDF bitmaps are hex strings, may need padding
                    hex_str = hex_row
                    # Calculate bytes needed based on char_width
                    bytes_needed = (char_width + 7) // 8
                    # Pad hex string if needed
                    hex_str = hex_str.zfill(bytes_needed * 2)
                    # Convert to integer
                    row_bits = int(hex_str, 16)
                except:
                    continue

                # Draw each bit in the row (MSB first)
                for bit_idx in range(char_width):
                    # Check bit from left to right (MSB to LSB)
                    bit_position = (bytes_needed * 8) - 1 - bit_idx
                    if row_bits & (1 << bit_position):
                        px = cursor_x + x_offset + bit_idx
                        # In BDF: y_offset is distance from baseline to bottom of char bbox
                        # Positive y_offset means char extends above baseline
                        # Negative y_offset means char extends below baseline
                        # We draw from top to bottom, so subtract from y to go up
                        py = y - y_offset - char_height + row_idx
                        if 0 <= px < canvas.width and 0 <= py < canvas.height:
                            canvas.SetPixel(px, py, color.r, color.g, color.b)

            # Advance cursor by device width (DWIDTH)
            cursor_x += dwidth

    @staticmethod
    def DrawLine(canvas, x0: int, y0: int, x1: int, y1: int, color):
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


def create_colorlight_backend(interface: str, width: int, height: int):
    """Create a ColorLight backend factory.

    Args:
        interface: Network interface name (e.g., 'eth0', 'enp0s3')
        width: Display width in pixels
        height: Display height in pixels

    Returns:
        Tuple of (factory, options_class, graphics_class)

    Note:
        Requires root/sudo privileges and Linux/Unix system with AF_PACKET support.
        Uses ColorLightGraphics wrapper which provides rgbmatrix-compatible API.
    """
    def factory(options=None):
        w = options.cols if options else width
        h = options.rows if options else height
        return ColorLightMatrix(interface, w, h)
    return factory, ColorLightOptions, ColorLightGraphics
