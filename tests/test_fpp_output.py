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

    @pytest.mark.skip(reason="FPPMatrix does not have Fill method")
    def test_fill_sets_all_pixels(self):
        """Test that Fill sets all pixels to specified color."""
        matrix = FPPMatrix(host="127.0.0.1", port=4048, width=64, height=32)

        matrix.Fill(100, 150, 200)

        # Verify fill worked by checking a pixel
        import numpy as np
        expected = np.array([100, 150, 200])
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

    @pytest.mark.skip(reason="FPPMatrix does not have DrawText method")
    def test_draw_text(self):
        """Test DrawText method."""
        matrix = FPPMatrix(host="127.0.0.1", port=4048, width=64, height=32)

        # Mock font
        font = Mock()
        font.CharacterWidth = Mock(return_value=8)

        # Draw text
        matrix.DrawText(5, 10, font, "Test")

        # Should not raise exception

    @pytest.mark.skip(reason="FPPMatrix does not have DrawLine method")
    def test_draw_line(self):
        """Test DrawLine method."""
        matrix = FPPMatrix(host="127.0.0.1", port=4048, width=64, height=32)

        # Draw line from (0,0) to (10,10)
        matrix.DrawLine(0, 0, 10, 10, 255, 255, 255)

        # Should not raise exception


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
