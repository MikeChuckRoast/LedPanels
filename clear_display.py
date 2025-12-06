#!/usr/bin/env python3
"""Clear the ColorLight LED display to black"""

import time

from colorlight_output import ColorLightMatrix


def clear_display():
    """Clear the display by sending all black pixels"""
    print("Initializing ColorLight matrix...")
    matrix = ColorLightMatrix('eth0', 128, 64)

    print("Clearing display (all pixels to black)...")
    matrix.Clear()
    matrix.SwapOnVSync(matrix)

    print("Display cleared!")

if __name__ == "__main__":
    clear_display()
