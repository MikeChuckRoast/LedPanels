"""
Matrix output backend management.

Handles detection and initialization of different output backends:
- rgbmatrix (direct GPIO control on Raspberry Pi)
- RGBMatrixEmulator (software emulator)
- FPP (Falcon Player Protocol via network)
"""

import logging
from typing import Any, Optional, Tuple

from colorlight_output import create_colorlight_backend
from fpp_output import create_fpp_backend


def try_import_rgbmatrix():
    """Try to import a real rgbmatrix backend or an emulator.

    Returns a tuple (RGBMatrix, RGBMatrixOptions, graphics) or (None, None, None).
    """
    try:
        from rgbmatrix import (RGBMatrix, RGBMatrixOptions,  # type: ignore
                               graphics)
        return RGBMatrix, RGBMatrixOptions, graphics
    except Exception:
        # Try common emulator module names. The user's environment may provide
        # a module named `RGBMatrixEmulator` which exposes the same API.
        try:
            from RGBMatrixEmulator import RGBMatrix  # type: ignore
            from RGBMatrixEmulator import RGBMatrixOptions, graphics
            return RGBMatrix, RGBMatrixOptions, graphics
        except Exception:
            try:
                # Some emulators use lowercase package names
                from rgbmatrix_emulator import RGBMatrix  # type: ignore
                from rgbmatrix_emulator import RGBMatrixOptions, graphics
                return RGBMatrix, RGBMatrixOptions, graphics
            except Exception:
                return None, None, None


def get_matrix_backend(use_fpp: bool = False,
                       fpp_host: str = "127.0.0.1",
                       fpp_port: int = 4048,
                       use_colorlight: bool = False,
                       colorlight_interface: str = "eth0",
                       width: int = 64,
                       height: int = 32) -> Tuple[Optional[Any], Optional[Any], Optional[Any]]:
    """Get appropriate matrix output backend.

    Args:
        use_fpp: If True, use FPP output instead of direct matrix control
        fpp_host: FPP receiver IP address
        fpp_port: FPP DDP port (default 4048)
        use_colorlight: If True, use ColorLight 5A-75B direct Ethernet output
        colorlight_interface: Network interface name for ColorLight (e.g., 'eth0', 'enp0s3')
        width: Display width in pixels
        height: Display height in pixels

    Returns:
        Tuple of (matrix_class, options_class, graphics_class) or (None, None, None)
    """
    # Priority: ColorLight -> FPP -> direct/emulator
    if use_colorlight:
        logging.info("Using ColorLight 5A-75B output backend on interface: %s", colorlight_interface)
        return create_colorlight_backend(colorlight_interface, width, height)

    if use_fpp:
        logging.info("Using FPP output backend: %s:%d", fpp_host, fpp_port)
        return create_fpp_backend(fpp_host, fpp_port, width, height)

    # Try to load direct matrix control or emulator
    logging.info("Attempting to load rgbmatrix or emulator backend")
    return try_import_rgbmatrix()
