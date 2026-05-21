#!/usr/bin/env python3
"""
test_colorlight_frames.py

Validates ColorLight 5A-75B frame rendering behavior, especially on power-up.

Sends a series of numbered frames (Frame 1, Frame 2, ...) so you can physically
verify which frame is actually displayed on the board at each step.

Usage:
    sudo python3 tools/test_colorlight_frames.py [--interface eth0] [--cols 128] [--rows 128]

Options:
    --interface     Network interface (default: eth0)
    --cols          Panel width in pixels (default: 128)
    --rows          Panel height in pixels (default: 128)
    --hold          Seconds to hold each frame (default: 3)
    --count         Number of test frames to send (default: 6)
    --font          BDF font path (default: fonts/helvB18.bdf)
    --no-powerup    Skip the power-up simulation test
    --init-order    One of: before, after, both, none  — override init frame order for comparison
                   'both' = init before AND after data (bookended)

Tests performed:
    1. POWER-UP SIMULATION: Sends a "stale" frame, then simulates a fresh start
       by sending a new frame.  You should see the new frame — if you see the
       stale frame, init ordering is broken.
    2. SEQUENTIAL FRAMES: Sends Frame 1 … Frame N with a hold time between each.
       Each should replace the previous immediately and cleanly.
    3. RAPID SUCCESSION: Sends several frames with minimal delay — verifies the
       board doesn't flicker or skip frames.
"""

import argparse
import os
import sys
import time

# Allow running from project root or tools/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from colorlight_output import ColorLightMatrix, ColorLightGraphics


# ---------------------------------------------------------------------------
# Simple text renderer — uses ColorLightGraphics.DrawText
# ---------------------------------------------------------------------------

def _fill(matrix: ColorLightMatrix, r: int, g: int, b: int) -> None:
    """Fill the entire buffer with a solid color."""
    for y in range(matrix.height):
        for x in range(matrix.width):
            matrix.SetPixel(x, y, r, g, b)


def _centered_text(
    matrix: ColorLightMatrix,
    graphics: ColorLightGraphics,
    font,
    text: str,
    fg_r: int, fg_g: int, fg_b: int,
    bg_r: int, bg_g: int, bg_b: int,
    label: str = "",
) -> None:
    """Fill with bg color and draw text centered on the panel."""
    matrix.Clear()
    _fill(matrix, bg_r, bg_g, bg_b)

    color = graphics.Color(fg_r, fg_g, fg_b)
    canvas = matrix  # ColorLightMatrix IS the canvas

    # Measure text width using character-width estimation
    char_w = max(8, font.height // 2 + 2)
    text_w = len(text) * char_w
    x = max(2, (matrix.width - text_w) // 2)
    y = (matrix.height + font.height) // 2  # vertical center baseline

    graphics.DrawText(canvas, font, x, y, color, text)

    if label:
        # Draw small label in top-left corner
        label_color = graphics.Color(180, 180, 180)
        graphics.DrawText(canvas, font, 2, font.height, label_color, label)


def send_frame(matrix: ColorLightMatrix, init_order: str = "before") -> None:
    """Send the current buffer using the specified init frame ordering."""
    canvas = matrix.CreateFrameCanvas()
    if init_order == "before":
        matrix._send_init_frames()
        _send_data_rows(matrix, canvas)
    elif init_order == "after":
        _send_data_rows(matrix, canvas)
        matrix._send_init_frames()
    elif init_order == "both":
        matrix._send_init_frames()
        _send_data_rows(matrix, canvas)
        matrix._send_init_frames()
    elif init_order == "none":
        _send_data_rows(matrix, canvas)
    else:
        raise ValueError(f"Unknown init_order: {init_order!r}")


def _send_data_rows(matrix: ColorLightMatrix, canvas) -> None:
    """Send all row data packets without managing init frames."""
    import numpy as np
    NUMPY_AVAILABLE = True
    try:
        import numpy as np
    except ImportError:
        NUMPY_AVAILABLE = False

    for row_num in range(matrix.height):
        if NUMPY_AVAILABLE:
            try:
                row_data = bytes(canvas.buffer[row_num].flatten().tolist())
            except Exception:
                row_data = _row_bytes_slow(canvas, row_num, matrix.width)
        else:
            row_data = _row_bytes_slow(canvas, row_num, matrix.width)

        frame = matrix._build_data_frame(row_num, row_data, offset=0)
        matrix.sock.send(frame)
        time.sleep(0.001)


def _row_bytes_slow(canvas, row_num: int, width: int) -> bytes:
    out = bytearray()
    for x in range(width):
        out.extend(bytes(canvas.buffer[row_num][x]))
    return bytes(out)


# ---------------------------------------------------------------------------
# Individual tests
# ---------------------------------------------------------------------------

COLORS = [
    # (bg_r, bg_g, bg_b, fg_r, fg_g, fg_b, name)
    (  0,   0, 160, 255, 255, 255, "Blue"),
    (  0, 140,   0, 255, 255, 255, "Green"),
    (160,   0,   0, 255, 255, 255, "Red"),
    (130,   0, 130, 255, 255, 255, "Purple"),
    (140,  90,   0, 255, 255, 255, "Orange"),
    (  0, 120, 120, 255, 255, 255, "Teal"),
]


def test_powerup_simulation(matrix, graphics, font, hold: float, init_order: str) -> None:
    """
    Simulate what happens on power-up when a stale frame is already latched.

    Step 1: Send a 'STALE' frame (red background).
    Step 2: Pause — this is the equivalent of the board being powered down.
    Step 3: Send a 'NEW' frame immediately (green background).
    Expected: Board shows NEW frame. If it shows STALE, init ordering is broken.
    """
    print("\n=== TEST 1: Power-up simulation ===")
    print("  Sending STALE frame (red)...")
    matrix.Clear()
    _fill(matrix, 80, 0, 0)
    color = graphics.Color(255, 255, 255)
    graphics.DrawText(matrix, font, 10, matrix.height // 2, color, "STALE")
    send_frame(matrix, init_order)

    print(f"  Holding STALE for {hold:.0f}s — note what is displayed...")
    time.sleep(hold)

    print("  Sending NEW frame (green) — board should switch immediately...")
    matrix.Clear()
    _fill(matrix, 0, 80, 0)
    graphics.DrawText(matrix, font, 10, matrix.height // 2, color, "NEW")
    send_frame(matrix, init_order)

    print(f"  Holding NEW for {hold:.0f}s — board SHOULD show NEW (green).")
    print("  FAIL if board still shows STALE (red).")
    time.sleep(hold)


def test_sequential_frames(matrix, graphics, font, hold: float, count: int, init_order: str) -> None:
    """Send numbered frames and verify each replaces the previous cleanly."""
    print(f"\n=== TEST 2: Sequential frames (1–{count}) ===")
    for i in range(1, count + 1):
        bg_r, bg_g, bg_b, fg_r, fg_g, fg_b, color_name = COLORS[(i - 1) % len(COLORS)]
        label = f"F{i}/{count}"
        text = f"Frame {i}"
        print(f"  [{i}/{count}] {text}  bg={color_name}")

        matrix.Clear()
        _fill(matrix, bg_r, bg_g, bg_b)
        color = graphics.Color(fg_r, fg_g, fg_b)

        # Large frame number centered
        cx = max(2, (matrix.width - len(text) * 10) // 2)
        cy = matrix.height // 2
        graphics.DrawText(matrix, font, cx, cy, color, text)

        # Color name at bottom
        small_color = graphics.Color(200, 200, 200)
        nx = max(2, (matrix.width - len(color_name) * 8) // 2)
        graphics.DrawText(matrix, font, nx, cy + font.height + 4, small_color, color_name)

        send_frame(matrix, init_order)
        print(f"       Sent. Hold {hold:.1f}s — should see '{text}' on {color_name} background.")
        time.sleep(hold)


def test_rapid_succession(matrix, graphics, font, init_order: str) -> None:
    """Send frames as fast as possible to check for flicker or skipped frames.

    Note: each frame takes ~(rows * 1ms) + init overhead to send.
    For a 128-row panel that's ~130ms minimum — there is no "rapid"; frames
    are sent back-to-back with no extra delay.
    """
    print("\n=== TEST 3: Rapid succession (back-to-back, no extra delay) ===")
    min_frame_ms = matrix.height  # 1ms per row
    print(f"  Min frame send time ~{min_frame_ms}ms for {matrix.height} rows.")
    print("  Sending 10 frames back-to-back...")
    for i in range(1, 11):
        bg_r, bg_g, bg_b, fg_r, fg_g, fg_b, _ = COLORS[(i - 1) % len(COLORS)]
        matrix.Clear()
        _fill(matrix, bg_r // 2, bg_g // 2, bg_b // 2)
        color = graphics.Color(fg_r, fg_g, fg_b)
        text = f"R{i}"
        cx = max(2, (matrix.width - len(text) * 10) // 2)
        graphics.DrawText(matrix, font, cx, matrix.height // 2, color, text)
        t0 = time.monotonic()
        send_frame(matrix, init_order)
        elapsed_ms = (time.monotonic() - t0) * 1000
        print(f"  Frame R{i} sent in {elapsed_ms:.0f}ms")

    print("  Done. Final frame (R10) should be visible.")
    time.sleep(2)


def test_blank(matrix, init_order: str) -> None:
    """Send a blank (all-black) frame."""
    print("\n=== Sending blank frame ===")
    matrix.Clear()
    send_frame(matrix, init_order)
    print("  Board should be all black.")
    time.sleep(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Test ColorLight 5A-75B frame rendering and power-up behavior."
    )
    parser.add_argument("--interface", default="eth0", help="Network interface (default: eth0)")
    parser.add_argument("--cols", type=int, default=128, help="Panel width in pixels (default: 128)")
    parser.add_argument("--rows", type=int, default=128, help="Panel height in pixels (default: 128)")
    parser.add_argument("--hold", type=float, default=3.0, help="Seconds to hold each frame (default: 3)")
    parser.add_argument("--count", type=int, default=6, help="Number of sequential test frames (default: 6)")
    parser.add_argument("--font", default="fonts/helvB18.bdf", help="BDF font path (default: fonts/helvB18.bdf)")
    parser.add_argument("--no-powerup", action="store_true", help="Skip power-up simulation test")
    parser.add_argument(
        "--init-order",
        choices=["before", "after", "both", "none"],
        default="after",
        help="Init frame order: after (default/correct), before, both (bookended), or none",
    )
    args = parser.parse_args()

    print(f"ColorLight frame test")
    print(f"  Interface : {args.interface}")
    print(f"  Resolution: {args.cols}x{args.rows}")
    print(f"  Hold time : {args.hold}s per frame")
    print(f"  Init order: {args.init_order}")
    print()

    try:
        matrix = ColorLightMatrix(args.interface, args.cols, args.rows)
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    graphics = ColorLightGraphics()
    font = graphics.Font()

    # Resolve font path relative to project root
    font_path = args.font
    if not os.path.isabs(font_path):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        font_path = os.path.join(project_root, font_path)

    if not os.path.exists(font_path):
        print(f"WARNING: Font not found: {font_path} — text may not render")
    else:
        font.LoadFont(font_path)
        print(f"  Font      : {font_path}")

    print()

    try:
        if not args.no_powerup:
            test_powerup_simulation(matrix, graphics, font, args.hold, args.init_order)

        test_sequential_frames(matrix, graphics, font, args.hold, args.count, args.init_order)
        test_rapid_succession(matrix, graphics, font, args.init_order)
        test_blank(matrix, args.init_order)

        print("\nAll tests complete.")

    except KeyboardInterrupt:
        print("\nInterrupted — sending blank frame.")
        matrix.Clear()
        send_frame(matrix, args.init_order)
    finally:
        matrix.close()


if __name__ == "__main__":
    main()
