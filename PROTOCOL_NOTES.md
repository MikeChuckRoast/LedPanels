# ColorLight 5A-75B Protocol - Working Implementation

## Overview

This documents the working protocol implementation for ColorLight 5A-75B LED receiver cards, based on the PyLights project but with corrections for proper operation.

## Hardware

- **Card**: ColorLight 5A-75B
- **Panels**: P5 1/16 scan LED panels (128x64 pixels)
- **Connection**: Direct Ethernet via raw AF_PACKET sockets
- **Interface**: eth0 (or other network interface)
- **Privileges**: Requires root/sudo for raw socket access

## Protocol Details

### Initialization Sequence

Two initialization frames must be sent before data frames:

**Frame 1:**
- Destination MAC: `11:22:33:44:55:66`
- Source MAC: `22:22:33:44:55:66`
- EtherType: `0x0101`
- Data: 98 bytes of `0x00`

```python
first_frame = dst + src + b'\x01\x01' + (b'\x00' * 98)
```

**Frame 2:**
- Destination MAC: `11:22:33:44:55:66`
- Source MAC: `22:22:33:44:55:66`
- EtherType: `0x0AFF`
- Data: `0xFF 0xFF 0xFF` followed by 60 bytes of `0x00`

```python
second_frame = dst + src + b'\x0A\xFF\xFF\xFF\xFF' + (b'\x00' * 60)
```

### Data Frame Structure (WORKING FORMAT)

For each row of pixels:

```
Offset | Size | Description
-------|------|-------------
0-5    | 6    | Destination MAC (11:22:33:44:55:66)
6-11   | 6    | Source MAC (22:22:33:44:55:66)
12     | 1    | EtherType MSB (0x55)
13-14  | 2    | Row number (big-endian, 0-63 for 64-row panel)
15-16  | 2    | Pixel offset (big-endian, for multi-packet rows)
17-18  | 2    | Pixel count (big-endian, actual number of pixels)
19-20  | 2    | Magic bytes (0x08 0x80)
21-end | var  | BGR pixel data (3 bytes per pixel)
```

**Key Implementation Details:**

```python
# Build frame prefix
data_prefix = dst + src + b'\x55'

# Build complete frame
frame = data_prefix + row_num.to_bytes(2, 'big')  # Row 0-63
frame += offset.to_bytes(2, 'big')                 # Pixel offset
frame += pixel_count.to_bytes(2, 'big')           # ACTUAL pixel count
frame += b'\x08\x80'                               # Magic bytes
frame += pixel_data                                # BGR data
```

### Critical Differences from PyLights

1. **Pixel Count Field**: 
   - **PyLights bug**: Uses `width / 3` (e.g., 128/3 = 42)
   - **Correct implementation**: Uses actual pixel count (e.g., 128)
   - This was the main issue preventing proper display

2. **Row Addressing**:
   - Send all 64 rows sequentially (0-63)
   - The card handles 1/16 scan multiplexing internally
   - No need to calculate logical rows or interleave data

3. **Frame Buffering**:
   - The card DOES buffer frames in memory
   - Display persists after sending, no continuous refresh needed
   - Update display only when content changes

4. **Initialization Frames**:
   - Initialization frames must be sent AFTER all row data in every frame update
   - They act as a "commit" or "display" signal to show the new frame
   - Sending init frames before data causes a flash of old content
   - Send all row data first, then send init frames at the end of `SwapOnVSync`

## Pixel Format

- **Order**: BGR (Blue, Green, Red) - not RGB!
- **Size**: 3 bytes per pixel
- **Range**: 0-255 for each color channel

```python
# Setting a pixel
canvas.SetPixel(x, y, red, green, blue)
# Stored internally as [blue, green, red]
```

## Timing

- **Init frame delay**: 1ms between the two init frames
- **Init frames are sent**: After all row data in every frame update (at end of SwapOnVSync)
- **Data frame delay**: 1ms between rows (can be reduced to 0.1ms)
- **Frame updates**: Only send when content changes (card buffers frames)

## Working Code Example

```python
from colorlight_output import ColorLightMatrix

# Initialize
matrix = ColorLightMatrix('eth0', 128, 64)

# Draw pixels
for y in range(64):
    for x in range(128):
        matrix.SetPixel(x, y, 255, 0, 0)  # Red

# Send to display once - it will persist
matrix.SwapOnVSync(matrix)

# For animation/updates, only send when content changes:
# while True:
#     # Update pixels...
#     matrix.SwapOnVSync(matrix)
#     time.sleep(0.05)  # Update rate as needed
```

## Font Rendering

The ColorLight backend includes BDF font support for text rendering:

- Loads standard BDF font files
- Respects DWIDTH for proper character spacing
- Correctly aligns characters at baseline
- Compatible with rgbmatrix font rendering output

Key font metrics:
- **FONTBOUNDINGBOX**: Defines font height and baseline offset
- **DWIDTH**: Character advance width (cursor movement)
- **BBX**: Character bounding box (width, height, x_offset, y_offset)
- **BITMAP**: Hex-encoded bitmap data

## Troubleshooting

### Display shows artifacts or flickers
- Check pixel_count is actual pixel count, not width/3
- Verify BGR color order
- Check that data frames follow immediately after init frames

### No display output
- Verify interface is UP: `ip link show eth0`
- Check permissions: Must run with sudo
- Confirm initialization frames sent before data

### Text rendering issues
- Ensure BDF font file exists and is readable
- Check baseline calculation matches font metrics
- Verify DWIDTH is used for cursor advance

## References

- PyLights project: https://github.com/KAkerstrom/PyLights
- Chubby75 reverse engineering: https://github.com/q3k/chubby75
- This implementation corrects the PyLights pixel_count bug
