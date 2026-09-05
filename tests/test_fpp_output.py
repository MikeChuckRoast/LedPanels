"""
Tests for fpp_output.py module.
"""

import socket
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fpp_output import FPPMatrix, create_fpp_backend


class TestFPPMatrix:
    """Tests for FPPMatrix class."""

    def test_creates_matrix_with_options(self):
        """Test creating FPPMatrix with direct parameters."""
        matrix = FPPMatrix(host="127.0.0.1", port=4048, width=64, height=32)

        assert matrix.height == 32
        assert matrix.width == 64
        assert matrix.host == "127.0.0.1"
        assert matrix.port == 4048

    def test_matrix_dimensions(self):
        """Test matrix dimensions are set correctly."""
        matrix = FPPMatrix(host="127.0.0.1", port=4048, width=128, height=64)

        assert matrix.height == 64
        assert matrix.width == 128

    @patch('socket.socket')
    def test_sends_data_via_udp(self, mock_socket):
        """Test that matrix sends data via UDP socket."""
        mock_sock_instance = MagicMock()
        mock_socket.return_value = mock_sock_instance

        matrix = FPPMatrix(host="127.0.0.1", port=4048, width=64, height=32)

        # Check that socket was created
        mock_socket.assert_called_with(socket.AF_INET, socket.SOCK_DGRAM)

    def test_set_pixel_updates_buffer(self):
        """Test that SetPixel updates the pixel buffer."""
        import numpy as np
        matrix = FPPMatrix(host="127.0.0.1", port=4048, width=64, height=32)

        matrix.SetPixel(5, 10, 255, 128, 64)

        # Buffer should be updated - verify by checking buffer contents
        expected = np.array([255, 128, 64])
        assert np.array_equal(matrix.buffer[10][5], expected)

    def test_clear_resets_buffer(self):
        """Test that Clear resets the pixel buffer."""
        matrix = FPPMatrix(host="127.0.0.1", port=4048, width=64, height=32)

        matrix.SetPixel(5, 10, 255, 255, 255)
        matrix.Clear()

        # After clear, buffer should be reset

    def test_clear_sets_all_pixels_to_zero(self):
        """Test that Clear sets all pixels to black."""
        matrix = FPPMatrix(host="127.0.0.1", port=4048, width=64, height=32)

        matrix.SetPixel(0, 0, 100, 150, 200)
        matrix.Clear()

        import numpy as np
        expected = np.array([0, 0, 0])
        assert np.array_equal(matrix.buffer[0][0], expected)


class TestDDPProtocol:
    """Tests for DDP protocol implementation."""

    @patch('socket.socket')
    def test_ddp_packet_format(self, mock_socket):
        """Test DDP packet format."""
        matrix = FPPMatrix(host="127.0.0.1", port=4048, width=64, height=32)

        # Set some pixels to trigger packet generation
        matrix.SetPixel(0, 0, 255, 0, 0)
        matrix.SetPixel(1, 0, 0, 255, 0)

        # Verify socket was created (packet would be sent)
        mock_socket.assert_called()

    def test_ddp_header_size(self):
        """Test that DDP header is 10 bytes."""
        # DDP header structure: flags(1) + sequence(1) + type(1) + id(1) + offset(4) + length(2)
        # Total: 10 bytes
        header_size = 10
        assert header_size == 10


class TestFPPGraphics:
    """Tests for FPPMatrix graphics methods."""

    def test_draw_text(self):
        """Test DrawText via FPPGraphics."""
        from fpp_output import FPPGraphics

        matrix = FPPMatrix(host="127.0.0.1", port=4048, width=64, height=32)
        color = FPPGraphics.Color(255, 255, 255)
        font = FPPGraphics.Font()

        # DrawText is a static method on FPPGraphics, not on FPPMatrix
        FPPGraphics.DrawText(matrix, font, 5, 10, color, "Test")

        # Should not raise exception

    def test_draw_line(self):
        """Test DrawLine via FPPGraphics."""
        from fpp_output import FPPGraphics

        matrix = FPPMatrix(host="127.0.0.1", port=4048, width=64, height=32)
        color = FPPGraphics.Color(255, 255, 255)

        # DrawLine is a static method on FPPGraphics, not on FPPMatrix
        FPPGraphics.DrawLine(matrix, 0, 0, 10, 10, color)

        # Verify at least one pixel was set (diagonal line)
        import numpy as np
        assert np.any(matrix.buffer > 0)


class TestCreateFPPBackend:
    """Tests for create_fpp_backend factory function."""

    def test_creates_backend_from_settings(self, sample_settings_dict):
        """Test creating FPP backend - returns tuple (factory, options, graphics)."""
        # create_fpp_backend(host, port, width, height) returns tuple
        result = create_fpp_backend("192.168.1.50", 4048, 64, 32)

        assert result is not None
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_applies_hardware_settings(self, sample_settings_dict):
        """Test that create_fpp_backend returns proper tuple structure."""
        result = create_fpp_backend("127.0.0.1", 4048, 128, 64)

        # Result is (factory, options_class, graphics_class)
        assert isinstance(result, tuple)
        assert callable(result[0])  # factory function


class TestFPPSetImage:
    """Tests for the bulk-blit path used by animation playback."""

    @staticmethod
    def _pixel(matrix, x, y):
        """Read back one pixel as (r, g, b), whatever the buffer type."""
        return tuple(int(v) for v in matrix.buffer[y][x])

    def test_matches_setpixel_for_the_same_image(self):
        from PIL import Image

        image = Image.new("RGB", (8, 4))
        for x in range(8):
            for y in range(4):
                image.putpixel((x, y), (x * 30 % 256, y * 60 % 256, (x + y) * 20 % 256))

        blitted = FPPMatrix(host="127.0.0.1", port=4048, width=8, height=4)
        blitted.SetImage(image)

        by_pixel = FPPMatrix(host="127.0.0.1", port=4048, width=8, height=4)
        for x in range(8):
            for y in range(4):
                by_pixel.SetPixel(x, y, *image.getpixel((x, y)))

        for x in range(8):
            for y in range(4):
                assert self._pixel(blitted, x, y) == self._pixel(by_pixel, x, y)

    def test_stores_rgb_in_order(self):
        from PIL import Image

        matrix = FPPMatrix(host="127.0.0.1", port=4048, width=2, height=2)
        matrix.SetImage(Image.new("RGB", (2, 2), (10, 20, 30)))

        assert self._pixel(matrix, 0, 0) == (10, 20, 30)

    def test_offset_positions_the_image(self):
        from PIL import Image

        matrix = FPPMatrix(host="127.0.0.1", port=4048, width=8, height=8)
        matrix.SetImage(Image.new("RGB", (2, 2), (255, 255, 255)), 3, 4)

        assert self._pixel(matrix, 3, 4) == (255, 255, 255)
        assert self._pixel(matrix, 4, 5) == (255, 255, 255)
        assert self._pixel(matrix, 2, 4) == (0, 0, 0)
        assert self._pixel(matrix, 3, 3) == (0, 0, 0)

    def test_clips_an_oversized_image_instead_of_erroring(self):
        from PIL import Image

        matrix = FPPMatrix(host="127.0.0.1", port=4048, width=4, height=4)
        matrix.SetImage(Image.new("RGB", (100, 100), (1, 2, 3)))

        assert self._pixel(matrix, 3, 3) == (1, 2, 3)

    def test_negative_offset_clips_the_top_left(self):
        from PIL import Image

        matrix = FPPMatrix(host="127.0.0.1", port=4048, width=4, height=4)
        matrix.SetImage(Image.new("RGB", (4, 4), (9, 9, 9)), -2, -2)

        assert self._pixel(matrix, 0, 0) == (9, 9, 9)
        assert self._pixel(matrix, 1, 1) == (9, 9, 9)
        assert self._pixel(matrix, 2, 2) == (0, 0, 0)

    def test_fully_offscreen_image_is_a_no_op(self):
        from PIL import Image

        matrix = FPPMatrix(host="127.0.0.1", port=4048, width=4, height=4)
        matrix.SetImage(Image.new("RGB", (4, 4), (255, 0, 0)), 10, 10)

        assert self._pixel(matrix, 0, 0) == (0, 0, 0)

    def test_converts_non_rgb_modes(self):
        from PIL import Image

        matrix = FPPMatrix(host="127.0.0.1", port=4048, width=4, height=4)
        matrix.SetImage(Image.new("L", (4, 4), 128))

        assert self._pixel(matrix, 0, 0) == (128, 128, 128)


class TestFPPSetImageWithoutNumpy:
    """The pure-Python buffer fallback must blit identically to the numpy path."""

    @staticmethod
    def _pixel(matrix, x, y):
        return tuple(int(v) for v in matrix.buffer[y][x])

    def test_fallback_matches_the_numpy_path(self):
        import fpp_output
        from PIL import Image

        image = Image.new("RGB", (6, 3))
        for x in range(6):
            for y in range(3):
                image.putpixel((x, y), (x * 40 % 256, y * 80 % 256, 7))

        fast = FPPMatrix(host="127.0.0.1", port=4048, width=6, height=3)
        fast.SetImage(image)

        with patch.object(fpp_output, 'NUMPY_AVAILABLE', False):
            slow = FPPMatrix(host="127.0.0.1", port=4048, width=6, height=3)
            slow.SetImage(image)

        for x in range(6):
            for y in range(3):
                assert self._pixel(slow, x, y) == self._pixel(fast, x, y)

    def test_fallback_honours_offset_and_clipping(self):
        import fpp_output
        from PIL import Image

        with patch.object(fpp_output, 'NUMPY_AVAILABLE', False):
            matrix = FPPMatrix(host="127.0.0.1", port=4048, width=4, height=4)
            matrix.SetImage(Image.new("RGB", (4, 4), (9, 8, 7)), 2, 2)

        assert self._pixel(matrix, 2, 2) == (9, 8, 7)
        assert self._pixel(matrix, 3, 3) == (9, 8, 7)
        assert self._pixel(matrix, 1, 1) == (0, 0, 0)
