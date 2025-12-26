#!/usr/bin/env python3
"""
udp_scoreboard.py

Display real-time scoreboard data on an RGB LED matrix via UDP messages.

Features:
- Listens for JSON-formatted UDP messages on configurable port
- Two-section display: event name (top) and time (bottom)
- Separate fonts for each section
- Supports multiple backends: direct matrix, emulator, FPP, ColorLight

Message types:
- {"startList": {"eventName": "...", ...}} - Sets event name, resets time to "0.0"
- {"timeRunning": "42.1"} - Updates time display
- {"initialization": true} - Clears display to black
"""

import argparse
import json
import logging
import os
import socket
import sys
from pathlib import Path
from typing import Dict, Optional

from config_loader import ConfigError, load_settings
from display_utils import (calculate_text_baseline, draw_centered_text,
                           fill_rectangle, load_font_metadata,
                           load_font_with_fallback, measure_text_width,
                           truncate_text_to_width)
from matrix_backend import get_matrix_backend


def handle_message(data: dict, current_state: Dict[str, str]) -> Optional[Dict[str, str]]:
    """Handle incoming JSON message and return updated state.

    Args:
        data: Parsed JSON data
        current_state: Current display state with 'event_name' and 'time_value'

    Returns:
        Updated state dict, or None if message is invalid (preserves current state)
    """
    try:
        # Handle initialization - clear display
        if "initialization" in data and data["initialization"]:
            logging.info("Received initialization - clearing display")
            return {"event_name": "", "time_value": ""}

        # Handle startList - update event name and reset time
        if "startList" in data:
            start_list = data["startList"]
            if not isinstance(start_list, dict):
                logging.warning("startList field is not a dictionary")
                return None

            # Only update event_name if eventName field is present
            if "eventName" in start_list:
                event_name = start_list["eventName"]
                if not isinstance(event_name, str):
                    logging.warning("startList.eventName is not a string")
                    return None

                logging.info("Received startList - event: '%s'", event_name)
                return {
                    "event_name": event_name,
                    "time_value": "0.0"
                }
            else:
                # startList exists but no eventName - just reset time
                logging.info("Received startList without eventName - resetting time")
                return {
                    "event_name": current_state["event_name"],
                    "time_value": "0.0"
                }

        # Handle timeRunning - update time only
        if "timeRunning" in data:
            time_value = data["timeRunning"]
            if not isinstance(time_value, str):
                logging.warning("timeRunning field is not a string")
                return None

            # Strip whitespace
            time_value = time_value.strip()
            logging.debug("Received timeRunning: '%s'", time_value)
            return {
                "event_name": current_state["event_name"],
                "time_value": time_value
            }

        # Message doesn't contain any recognized fields
        logging.debug("Received message with no recognized fields")
        return None

    except Exception as e:
        logging.warning("Error handling message: %s", e)
        return None


def render_scoreboard(canvas, graphics, top_font, bottom_font,
                     top_font_metadata, bottom_font_metadata,
                     event_name: str, time_value: str,
                     canvas_width: int, canvas_height: int,
                     top_font_shift_v: int, top_font_shift_h: int,
                     bottom_font_shift_v: int, bottom_font_shift_h: int):
    """Render scoreboard display with event name and time.

    Args:
        canvas: Canvas object to draw on
        graphics: Graphics module from matrix backend
        top_font: Font for event name section
        bottom_font: Font for time section
        top_font_metadata: Metadata dict for top font (from load_font_metadata)
        bottom_font_metadata: Metadata dict for bottom font (from load_font_metadata)
        event_name: Event name to display (top section)
        time_value: Time value to display (bottom section)
        canvas_width: Canvas width in pixels
        canvas_height: Canvas height in pixels
        top_font_shift_v: Vertical adjustment for top section font
        top_font_shift_h: Horizontal adjustment for top section font
        bottom_font_shift_v: Vertical adjustment for bottom section font
        bottom_font_shift_h: Horizontal adjustment for bottom section font
    """
    canvas.Clear()

    # Define section heights
    top_height = 24
    bottom_y_start = 24
    bottom_height = canvas_height - top_height

    # Colors
    red = graphics.Color(255, 0, 0)
    white = graphics.Color(255, 255, 255)
    black = graphics.Color(0, 0, 0)

    # Draw top section (event name) - red background, white text
    fill_rectangle(canvas, graphics, 0, 0, canvas_width - 1, top_height - 1, red)

    if event_name:
        # Truncate event name to fit display width (with 2px margin on each side)
        available_width = canvas_width - 4
        event_name_display = truncate_text_to_width(top_font, event_name, available_width)
        draw_centered_text(canvas, graphics, top_font, top_font_metadata, 0, top_height, canvas_width,
                           event_name_display, white, top_font_shift_v)

    # Draw bottom section (time) - black background, white text
    fill_rectangle(canvas, graphics, 0, bottom_y_start, canvas_width - 1,
                  canvas_height - 1, black)

    if time_value:
        # Truncate time to fit display width (with 2px margin on each side)
        available_width = canvas_width - 4
        time_value_display = format_time(time_value)
        time_value_display = truncate_text_to_width(bottom_font, time_value_display, available_width)
        draw_centered_text(canvas, graphics, bottom_font, bottom_font_metadata, bottom_y_start, bottom_height, canvas_width,
                           time_value_display, white, bottom_font_shift_v)


def format_time(time_str: str) -> str:
    """Format time string to ensure consistent display.

    Args:
        time_str: Raw time string from message

    Returns:
        Formatted time string
    """
    # Remove any fractional seconds
    if '.' in time_str:
        time_str = time_str.split('.')[0]

    return time_str


def main():
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

    # Try to load settings from config
    try:
        settings = load_settings('./config')
        hw = settings.get('hardware', {})
        fonts_cfg = settings.get('fonts', {})
        net = settings.get('network', {})
        scoreboard_cfg = settings.get('scoreboard', {})
    except ConfigError as e:
        logging.warning("Could not load config: %s. Using defaults.", e)
        hw = {}
        fonts_cfg = {}
        net = {}
        scoreboard_cfg = {}

    # Build default font paths
    font_path = fonts_cfg.get('font_path', './config/fonts')
    default_top_font = os.path.join(font_path, scoreboard_cfg.get('top_font_name', 'helvB12.bdf'))
    default_bottom_font = os.path.join(font_path, scoreboard_cfg.get('bottom_font_name', 'helvB18.bdf'))

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Display scoreboard data from UDP on LED matrix")
    parser.add_argument('--port', '-p', type=int,
                       default=scoreboard_cfg.get('udp_port', 5568),
                       help='UDP port to listen on (default: 5568)')
    parser.add_argument('--width', type=int,
                       default=scoreboard_cfg.get('width', 64),
                       help='Base panel width in pixels (default: 64)')
    parser.add_argument('--height', type=int,
                       default=scoreboard_cfg.get('height', 32),
                       help='Base panel height in pixels (default: 32)')
    parser.add_argument('--top-font',
                       default=default_top_font,
                       help='Path to BDF font for event name (top section)')
    parser.add_argument('--bottom-font',
                       default=default_bottom_font,
                       help='Path to BDF font for time (bottom section)')
    parser.add_argument('--chain', type=int,
                       default=scoreboard_cfg.get('chain', 3),
                       help='Panels chained horizontally (default: 3)')
    parser.add_argument('--parallel', type=int,
                       default=scoreboard_cfg.get('parallel', 2),
                       help='Panels stacked vertically (default: 2)')
    parser.add_argument('--gpio-slowdown', type=int,
                       default=scoreboard_cfg.get('gpio_slowdown', 4),
                       help='GPIO slowdown for RGBMatrixOptions')
    parser.add_argument('--fpp', action='store_true',
                       default=net.get('fpp_enabled', False),
                       help='Use FPP output instead of direct matrix control')
    parser.add_argument('--fpp-host',
                       default=net.get('fpp_host', '127.0.0.1'),
                       help='FPP host IP address')
    parser.add_argument('--fpp-port', type=int,
                       default=net.get('fpp_port', 4048),
                       help='FPP DDP port')
    parser.add_argument('--colorlight', action='store_true',
                       default=net.get('colorlight_enabled', False),
                       help='Send frames to ColorLight 5A-75B via raw Ethernet')
    parser.add_argument('--colorlight-interface',
                       default=net.get('colorlight_interface', 'eth0'),
                       help='Network interface for ColorLight (e.g., eth0)')
    parser.add_argument('--top-font-shift-vertical', type=int,
                       default=scoreboard_cfg.get('top_font_shift_vertical', 7),
                       help='Vertical font adjustment for top section (default: 7)')
    parser.add_argument('--top-font-shift-horizontal', type=int,
                       default=scoreboard_cfg.get('top_font_shift_horizontal', 0),
                       help='Horizontal font adjustment for top section (default: 0)')
    parser.add_argument('--bottom-font-shift-vertical', type=int,
                       default=scoreboard_cfg.get('bottom_font_shift_vertical', 15),
                       help='Vertical font adjustment for bottom section (default: 15)')
    parser.add_argument('--bottom-font-shift-horizontal', type=int,
                       default=scoreboard_cfg.get('bottom_font_shift_horizontal', 34),
                       help='Horizontal font adjustment for bottom section (default: 34)')

    args = parser.parse_args()

    # Get matrix backend
    matrix_classes = get_matrix_backend(
        use_fpp=args.fpp,
        fpp_host=args.fpp_host,
        fpp_port=args.fpp_port,
        use_colorlight=args.colorlight,
        colorlight_interface=args.colorlight_interface,
        width=args.width,
        height=args.height
    )

    RGBMatrix, RGBMatrixOptions, graphics = matrix_classes
    if RGBMatrix is None:
        logging.error("No rgbmatrix backend available")
        sys.exit(1)

    # Configure matrix
    options = RGBMatrixOptions()
    options.rows = args.height
    options.cols = args.width
    options.chain_length = args.chain
    options.parallel = args.parallel
    options.gpio_slowdown = args.gpio_slowdown

    matrix = RGBMatrix(options=options)
    canvas = matrix.CreateFrameCanvas()

    # Load fonts
    logging.info("Loading fonts...")
    top_font = load_font_with_fallback(graphics, args.top_font)
    bottom_font = load_font_with_fallback(graphics, args.bottom_font)
    top_font_metadata = load_font_metadata(args.top_font)
    bottom_font_metadata = load_font_metadata(args.bottom_font)

    # Initialize state
    state = {
        "event_name": "",
        "time_value": ""
    }

    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.05)  # 50ms timeout for responsive rendering

    try:
        sock.bind(('', args.port))
        logging.info("Listening for UDP messages on port %d", args.port)
        logging.info("Display: %dx%d, Top font: %s, Bottom font: %s",
                    args.width, args.height, args.top_font, args.bottom_font)

        # Initial render (blank display)
        render_scoreboard(canvas, graphics, top_font, bottom_font,
                         top_font_metadata, bottom_font_metadata,
                         state["event_name"], state["time_value"],
                         canvas.width, canvas.height,
                         args.top_font_shift_vertical, args.top_font_shift_horizontal,
                         args.bottom_font_shift_vertical, args.bottom_font_shift_horizontal)
        canvas = matrix.SwapOnVSync(canvas)

        # Main loop
        while True:
            try:
                # Try to receive UDP message
                data, addr = sock.recvfrom(4096)

                # Parse JSON
                try:
                    message = json.loads(data.decode('utf-8'))
                    logging.debug("Received from %s: %s", addr, message)

                    # Handle message and update state
                    new_state = handle_message(message, state)
                    if new_state is not None:
                        state = new_state

                except json.JSONDecodeError as e:
                    logging.warning("Received malformed JSON from %s: %s", addr, e)
                except UnicodeDecodeError as e:
                    logging.warning("Received non-UTF8 data from %s: %s", addr, e)

            except socket.timeout:
                # No message received, continue to render
                pass

            # Render current state (every loop iteration for immediate updates)
            render_scoreboard(canvas, graphics, top_font, bottom_font,
                             top_font_metadata, bottom_font_metadata,
                             state["event_name"], state["time_value"],
                             canvas.width, canvas.height,
                             args.top_font_shift_vertical, args.top_font_shift_horizontal,
                             args.bottom_font_shift_vertical, args.bottom_font_shift_horizontal)
            canvas = matrix.SwapOnVSync(canvas)

    except KeyboardInterrupt:
        logging.info("Shutting down...")
    finally:
        sock.close()
        matrix.Clear()
        logging.info("Cleanup complete")


if __name__ == '__main__':
    main()
