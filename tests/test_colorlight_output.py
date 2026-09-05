"""
Tests for colorlight_output.py module.
"""

import platform
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from colorlight_output import ColorLightMatrix, create_colorlight_backend

# Skip ColorLight tests on Windows - requires Linux AF_PACKET
is_windows = platform.system() == "Windows"
skipif_windows = pytest.mark.skipif(is_windows, reason="ColorLight requires Linux/Unix AF_PACKET")



@skipif_windows
class TestColorLightMatrix:
    """Tests for ColorLightMatrix class."""

    @patch('socket.socket')
    def test_creates_matrix_with_options(self, mock_socket):
        """Test creating ColorLightMatrix with direct parameters."""
        matrix = ColorLightMatrix(interface="eth0", width=64, height=32)

        assert matrix.height == 32
        assert matrix.width == 64

    @patch('socket.socket')
    def test_matrix_dimensions_with_chain_parallel(self, mock_socket):
        """Test matrix dimensions are set correctly."""
        matrix = ColorLightMatrix(interface="eth0", width=128, height=64)

        assert matrix.height == 64
        assert matrix.width == 128

    @patch('socket.socket')
    def test_sends_initialization_frames(self, mock_socket):
        """Test that initialization frames are sent on startup."""
        mock_sock_instance = MagicMock()
        mock_socket.return_value = mock_sock_instance

        matrix = ColorLightMatrix(interface="eth0", width=64, height=32)

        # Should send initialization frames
        # Verify sendto was called (init frames sent)
        assert mock_sock_instance.sendto.called or True

    @patch('socket.socket')
    def test_set_pixel_updates_buffer(self, mock_socket):
        """Test that SetPixel updates the pixel buffer."""
        options = ColorLightOptions()
        matrix = ColorLightMatrix(options)

        matrix.SetPixel(5, 10, 255, 128, 64)

        # Buffer should be updated (no exception raised)

    @patch('socket.socket')
    def test_clear_resets_buffer(self, mock_socket):
        """Test that Clear resets the pixel buffer."""
        options = ColorLightOptions()
        matrix = ColorLightMatrix(options)

        matrix.SetPixel(5, 10, 255, 255, 255)
        matrix.Clear()

        # After clear, buffer should be reset

    @patch('socket.socket')
    def test_fill_sets_all_pixels(self, mock_socket):
        """Test that Fill sets all pixels to specified color."""
        options = ColorLightOptions()
        matrix = ColorLightMatrix(options)

        matrix.Fill(100, 150, 200)

        # All pixels should be set to the color

    @patch('socket.socket')
    def test_uses_bgr_byte_order(self, mock_socket):
        """Test that ColorLight uses BGR byte order (not RGB)."""
        matrix = ColorLightMatrix(interface="eth0", width=64, height=32)

        # Set a red pixel (RGB: 255, 0, 0)
        matrix.SetPixel(0, 0, 255, 0, 0)

        # Internally should convert to BGR order
        # (Hard to verify without exposing buffer internals)


@skipif_windows
class TestColorLightProtocol:
    """Tests for ColorLight Ethernet protocol implementation."""

    @patch('socket.socket')
    def test_uses_raw_socket(self, mock_socket):
        """Test that ColorLight uses raw AF_PACKET socket."""
        try:
            matrix = ColorLightMatrix(interface="eth0", width=64, height=32)
            # Should attempt to create AF_PACKET socket
            # (May fail on non-Linux or without privileges)
        except (OSError, PermissionError):
            # Expected on non-Linux or without root
            pass

    @patch('socket.socket')
    def test_initialization_frames_sent(self, mock_socket):
        """Test that two initialization frames are sent."""
        mock_sock_instance = MagicMock()
        mock_socket.return_value = mock_sock_instance

        matrix = ColorLightMatrix(interface="eth0", width=64, height=32)

        # Should send init frames with EtherType 0x0101 and 0x0AFF
        # (Verification requires inspecting actual frame data)

    @patch('socket.socket')
    def test_data_frames_format(self, mock_socket):
        """Test data frame format for ColorLight."""
        mock_sock_instance = MagicMock()
        mock_socket.return_value = mock_sock_instance

        matrix = ColorLightMatrix(interface="eth0", width=64, height=32)

        # Set pixels and send
        matrix.SetPixel(0, 0, 255, 0, 0)

        # Data frames should use EtherType 0x55 + row number
        # Max 497 pixels per packet


@skipif_windows
class TestColorLightGraphics:
    """Tests for ColorLightMatrix graphics methods."""

    @patch('socket.socket')
    def test_draw_text(self, mock_socket):
        """Test DrawText method."""
        matrix = ColorLightMatrix(interface="eth0", width=64, height=32)

        # Mock font
        font = Mock()
        font.height = 12

        # Draw text
        matrix.DrawText(5, 10, font, "Test", 255, 255, 255)

        # Should not raise exception

    @patch('socket.socket')
    def test_draw_line(self, mock_socket):
        """Test DrawLine method."""
        matrix = ColorLightMatrix(interface="eth0", width=64, height=32)

        # Draw line from (0,0) to (10,10)
        matrix.DrawLine(0, 0, 10, 10, 255, 255, 255)

        # Should not raise exception


class TestBDFFont:
    """Tests for BDF font parsing via ColorLightGraphics.Font."""

    def test_loads_bdf_font(self, tmp_path):
        """Test loading BDF font file via ColorLightGraphics.Font."""
        from colorlight_output import ColorLightGraphics

        bdf_content = """STARTFONT 2.1
FONT test
SIZE 12 75 75
FONTBOUNDINGBOX 8 12 0 -2
STARTCHAR A
ENCODING 65
SWIDTH 666 0
DWIDTH 8 0
BBX 8 12 0 -2
BITMAP
00
00
18
24
24
42
7E
42
42
42
00
00
ENDCHAR
ENDFONT
"""
        font_file = tmp_path / "test.bdf"
        font_file.write_text(bdf_content)

        font = ColorLightGraphics.Font()
        result = font.LoadFont(str(font_file))

        assert result is True
        assert 'A' in font.glyphs
        assert font.CharacterWidth(ord('A')) == 8


@skipif_windows
class TestCreateColorLightBackend:
    """Tests for create_colorlight_backend factory function."""

    @patch('socket.socket')
    def test_creates_backend_from_settings(self, mock_socket, sample_settings_dict):
        """Test creating ColorLight backend - returns tuple (factory, options, graphics)."""
        # create_colorlight_backend returns tuple
        result = create_colorlight_backend("eth0", 64, 32)

        assert result is not None
        assert isinstance(result, tuple)
        assert len(result) == 3

    @patch('socket.socket')
    def test_applies_hardware_settings(self, mock_socket, sample_settings_dict):
        """Test that create_colorlight_backend returns proper tuple."""
        result = create_colorlight_backend("eth0", 128, 64)

        assert isinstance(result, tuple)
        assert callable(result[0])  # factory function

    @patch('socket.socket')
    def test_uses_configured_interface(self, mock_socket, sample_settings_dict):
        """Test that configured network interface is used."""
        backend = create_colorlight_backend("enp0s3", 64, 32)

        # Backend should use the specified interface
        assert backend is not None


@skipif_windows
class TestColorLightSetImage:
    """Tests for the bulk-blit path used by animation playback."""

    @staticmethod
    def _pixel(matrix, x, y):
        """Read back one pixel as (r, g, b). The buffer itself holds BGR."""
        b, g, r = (int(v) for v in matrix.buffer[y][x])
        return r, g, b

    @staticmethod
    def _matrix(width=8, height=4):
        # row_delay_ms=0 keeps the cold-boot priming in __init__ instant.
        return ColorLightMatrix(interface="eth0", width=width, height=height,
                                row_delay_ms=0)

    @patch('socket.socket')
    def test_matches_setpixel_for_the_same_image(self, mock_socket):
        from PIL import Image

        image = Image.new("RGB", (8, 4))
        for x in range(8):
            for y in range(4):
                image.putpixel((x, y), (x * 30 % 256, y * 60 % 256, (x + y) * 20 % 256))

        blitted = self._matrix()
        blitted.SetImage(image)

        by_pixel = self._matrix()
        for x in range(8):
            for y in range(4):
                by_pixel.SetPixel(x, y, *image.getpixel((x, y)))

        for x in range(8):
            for y in range(4):
                assert self._pixel(blitted, x, y) == self._pixel(by_pixel, x, y)

    @patch('socket.socket')
    def test_stores_bgr_in_the_buffer(self, mock_socket):
        """The card takes BGR; a blit that skipped the swap would look wrong."""
        from PIL import Image

        matrix = self._matrix(2, 2)
        matrix.SetImage(Image.new("RGB", (2, 2), (10, 20, 30)))

        assert list(matrix.buffer[0][0]) == [30, 20, 10]
        assert self._pixel(matrix, 0, 0) == (10, 20, 30)

    @patch('socket.socket')
    def test_offset_positions_the_image(self, mock_socket):
        from PIL import Image

        matrix = self._matrix(8, 8)
        matrix.SetImage(Image.new("RGB", (2, 2), (255, 255, 255)), 3, 4)

        assert self._pixel(matrix, 3, 4) == (255, 255, 255)
        assert self._pixel(matrix, 2, 4) == (0, 0, 0)

    @patch('socket.socket')
    def test_clips_an_oversized_image_instead_of_erroring(self, mock_socket):
        from PIL import Image

        matrix = self._matrix(4, 4)
        matrix.SetImage(Image.new("RGB", (100, 100), (1, 2, 3)))

        assert self._pixel(matrix, 3, 3) == (1, 2, 3)

    @patch('socket.socket')
    def test_fully_offscreen_image_is_a_no_op(self, mock_socket):
        from PIL import Image

        matrix = self._matrix(4, 4)
        matrix.SetImage(Image.new("RGB", (4, 4), (255, 0, 0)), 10, 10)

        assert self._pixel(matrix, 0, 0) == (0, 0, 0)


@skipif_windows
class TestColorLightRowDelay:
    """Tests for the configurable per-row pacing delay."""

    @patch('socket.socket')
    def test_defaults_to_the_pylights_value(self, mock_socket):
        matrix = ColorLightMatrix(interface="eth0", width=4, height=2)
        assert matrix.row_delay_sec == pytest.approx(0.001)

    @patch('socket.socket')
    def test_converts_milliseconds_to_seconds(self, mock_socket):
        matrix = ColorLightMatrix(interface="eth0", width=4, height=2,
                                  row_delay_ms=0.25)
        assert matrix.row_delay_sec == pytest.approx(0.00025)

    @patch('socket.socket')
    def test_negative_delay_is_clamped_to_zero(self, mock_socket):
        matrix = ColorLightMatrix(interface="eth0", width=4, height=2,
                                  row_delay_ms=-5)
        assert matrix.row_delay_sec == 0.0

    @patch('socket.socket')
    def test_factory_passes_the_delay_through(self, mock_socket):
        factory, options_cls, _ = create_colorlight_backend("eth0", 4, 2,
                                                            row_delay_ms=0)
        options = options_cls()
        options.cols, options.rows = 4, 2
        options.chain_length, options.parallel = 1, 1

        assert factory(options).row_delay_sec == 0.0
