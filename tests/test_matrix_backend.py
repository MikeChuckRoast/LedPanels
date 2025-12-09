"""
Tests for matrix_backend.py module.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestGetMatrixBackend:
    """Tests for get_matrix_backend function."""
    
    def test_returns_colorlight_when_enabled(self):
        """Test ColorLight backend is returned when use_colorlight=True."""
        from matrix_backend import get_matrix_backend
        
        with patch('matrix_backend.create_colorlight_backend') as mock_colorlight:
            mock_colorlight.return_value = ('ColorLightMatrix', None, None)
            result = get_matrix_backend(use_colorlight=True, colorlight_interface='eth0')
            
            mock_colorlight.assert_called_once_with('eth0', 64, 32)
            assert result[0] == 'ColorLightMatrix'
    
    def test_returns_fpp_when_enabled(self):
        """Test FPP backend is returned when use_fpp=True."""
        from matrix_backend import get_matrix_backend
        
        with patch('matrix_backend.create_fpp_backend') as mock_fpp:
            mock_fpp.return_value = ('FPPMatrix', None, None)
            result = get_matrix_backend(use_fpp=True, fpp_host='192.168.1.100')
            
            mock_fpp.assert_called_once_with('192.168.1.100', 4048, 64, 32)
            assert result[0] == 'FPPMatrix'
    
    def test_colorlight_priority_over_fpp(self):
        """Test ColorLight takes priority when both are enabled."""
        from matrix_backend import get_matrix_backend
        
        with patch('matrix_backend.create_colorlight_backend') as mock_colorlight:
            with patch('matrix_backend.create_fpp_backend') as mock_fpp:
                mock_colorlight.return_value = ('ColorLightMatrix', None, None)
                result = get_matrix_backend(use_colorlight=True, use_fpp=True)
                
                mock_colorlight.assert_called_once()
                mock_fpp.assert_not_called()
    
    def test_returns_direct_matrix_when_networks_disabled(self):
        """Test rgbmatrix/emulator backend when network backends disabled."""
        from matrix_backend import get_matrix_backend
        
        with patch('matrix_backend.try_import_rgbmatrix') as mock_rgb:
            mock_rgb.return_value = ('RGBMatrix', 'RGBMatrixOptions', 'graphics')
            result = get_matrix_backend(use_colorlight=False, use_fpp=False)
            
            mock_rgb.assert_called_once()
            assert result[0] == 'RGBMatrix'
    
    def test_fallback_to_emulator_when_rgbmatrix_unavailable(self):
        """Test fallback to None when no backend available."""
        from matrix_backend import get_matrix_backend
        
        with patch('matrix_backend.try_import_rgbmatrix') as mock_rgb:
            mock_rgb.return_value = (None, None, None)
            result = get_matrix_backend(use_colorlight=False, use_fpp=False)
            
            assert result == (None, None, None)
    
    def test_passes_hardware_settings_to_matrix(self):
        """Test hardware settings are passed correctly."""
        from matrix_backend import get_matrix_backend
        
        with patch('matrix_backend.create_fpp_backend') as mock_fpp:
            mock_fpp.return_value = ('FPPMatrix', None, None)
            result = get_matrix_backend(
                use_fpp=True,
                fpp_host='10.0.0.1',
                fpp_port=9999,
                width=128,
                height=64
            )
            
            mock_fpp.assert_called_once_with('10.0.0.1', 9999, 128, 64)
