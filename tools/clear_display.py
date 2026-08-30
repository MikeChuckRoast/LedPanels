#!/usr/bin/env python3
"""Clear the LED display to black using the configured network backend."""

import argparse
import logging
import os
import sys

# Allow running from project root or tools/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config_loader import ConfigError, ensure_config_directory, load_settings


def clear_display(config_dir='./config'):
    """Clear the display by sending an all-black frame

    Dispatches on the backend selected in [network] — the same precedence
    display_manager._blank_display() uses.  Raw rgbmatrix cannot be blanked
    from a separate process, so it is reported rather than attempted.

    Args:
        config_dir: Path to configuration directory (default: './config')
    """
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

    # Ensure config directory exists and has default files
    try:
        ensure_config_directory(config_dir)
    except ConfigError as e:
        logging.error(f"Configuration directory error: {e}")
        sys.exit(1)

    # Load settings
    try:
        settings = load_settings(config_dir)
    except ConfigError as e:
        logging.error(f"Configuration error: {e}")
        sys.exit(1)

    # Extract hardware and network settings
    hw = settings['hardware']
    net = settings['network']

    # Calculate total display dimensions
    width = hw['width'] * hw['chain']
    height = hw['height'] * hw['parallel']

    if net.get('colorlight_enabled', False):
        from colorlight_output import ColorLightMatrix
        interface = net.get('colorlight_interface', 'eth0')
        print(f"Initializing ColorLight matrix on {interface} ({width}x{height})...")
        matrix = ColorLightMatrix(interface, width, height)
    elif net.get('fpp_enabled', False):
        from fpp_output import FPPMatrix
        host = net.get('fpp_host', '127.0.0.1')
        port = int(net.get('fpp_port', 4048))
        print(f"Initializing FPP matrix at {host}:{port} ({width}x{height})...")
        matrix = FPPMatrix(host, port, width, height)
    else:
        logging.error(
            "No network backend enabled in [network] (colorlight_enabled / "
            "fpp_enabled are both false). Raw rgbmatrix hardware is owned by the "
            "display process and cannot be blanked from here — stop the display "
            "instead, or use the web UI's display power toggle."
        )
        sys.exit(1)

    print("Clearing display (all pixels to black)...")
    matrix.Clear()
    matrix.SwapOnVSync(matrix)

    print("Display cleared!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clear the LED display to black")
    parser.add_argument('--config-dir', default='./config', help='Path to configuration directory')
    args = parser.parse_args()

    clear_display(args.config_dir)
