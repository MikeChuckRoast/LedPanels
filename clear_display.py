#!/usr/bin/env python3
"""Clear the ColorLight LED display to black"""

import argparse
import logging
import sys
from pathlib import Path

from colorlight_output import ColorLightMatrix
from config_loader import ConfigError, ensure_config_directory, load_settings


def clear_display(config_dir='./config'):
    """Clear the display by sending all black pixels

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
    interface = net['colorlight_interface']

    print(f"Initializing ColorLight matrix on {interface} ({width}x{height})...")
    matrix = ColorLightMatrix(interface, width, height)

    print("Clearing display (all pixels to black)...")
    matrix.Clear()
    matrix.SwapOnVSync(matrix)

    print("Display cleared!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clear the ColorLight LED display to black")
    parser.add_argument('--config-dir', default='./config', help='Path to configuration directory')
    args = parser.parse_args()

    clear_display(args.config_dir)
