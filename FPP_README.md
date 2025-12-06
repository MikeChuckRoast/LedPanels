# FPP (Falcon Player Protocol) Support

## Overview

The LED Panels display system now supports multiple output backends:

1. **Direct Matrix Control** - Original rgbmatrix library for Raspberry Pi GPIO
2. **Emulator** - Software emulation for development/testing
3. **FPP Output** - Network-based output to Falcon Player receivers (NEW)

## FPP Architecture

### What is FPP?

Falcon Player (FPP) is a popular software package used for controlling LED displays in holiday light shows and other installations. It receives pixel data via the DDP (Distributed Display Protocol) over UDP.

### How It Works

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│  Raspberry Pi   │         │   FPP Receiver  │         │  LED Receiver   │
│  (display_event)│ ──UDP──>│   (127.0.0.1    │ ──────> │     Card        │
│                 │  DDP    │    or remote)   │  Serial │   (Pixels)      │
└─────────────────┘         └─────────────────┘         └─────────────────┘
```

**Benefits:**
- No GPIO pin requirements
- Can run from any computer (Windows, Mac, Linux)
- Network-based, allows remote display control
- FPP handles hardware interfacing details
- Professional LED receiver card support

## Usage

### Basic FPP Mode

```bash
# Use FPP output to localhost (same machine)
python display_event.py --event 11 --round 1 --heat 1 --fpp

# Specify remote FPP receiver
python display_event.py --event 11 --round 1 --heat 1 --fpp --fpp-host 192.168.1.100

# Custom port (default is 4048)
python display_event.py --event 11 --round 1 --heat 1 --fpp --fpp-host 192.168.1.100 --fpp-port 4048
```

### Command-Line Arguments

- `--fpp` - Enable FPP output mode
- `--fpp-host HOST` - FPP receiver IP address (default: 127.0.0.1)
- `--fpp-port PORT` - FPP DDP port (default: 4048)

### FPP Setup

#### Option 1: FPP on Raspberry Pi

1. Install FPP on your Raspberry Pi:
   ```bash
   # Download from https://github.com/FalconChristmas/fpp/releases
   # Or use FPP SD card image
   ```

2. Configure FPP:
   - Set display size (width x height) to match your panels
   - Configure output type (e.g., Falcon F16v3, ColorLight, etc.)
   - Test with FPP's built-in test patterns

3. Run display_event with FPP:
   ```bash
   python display_event.py --event 11 --round 1 --heat 1 --fpp --fpp-host 127.0.0.1
   ```

#### Option 2: Remote FPP

1. Set up FPP on a separate device
2. Note its IP address (e.g., 192.168.1.100)
3. Run from any computer:
   ```bash
   python display_event.py --event 11 --round 1 --heat 1 --fpp --fpp-host 192.168.1.100
   ```

## Code Architecture

### New Modules

#### `fpp_output.py`
- `FPPMatrix` - Emulates RGBMatrix API, sends DDP packets
- `FPPGraphics` - Graphics functions (DrawText, DrawLine, Color)
- `FPPFont` - Font rendering using PIL/Pillow
- DDP protocol implementation

#### `matrix_backend.py`
- `get_matrix_backend()` - Unified backend selection
- Detects and initializes appropriate backend (direct, emulator, or FPP)

#### `event_parser.py`
- Parsing and formatting functions extracted for reusability
- All event, athlete, color, and lane logic

### Module Structure

```
display_event.py         # Main application & rendering loop
├── event_parser.py      # Data parsing & formatting
├── matrix_backend.py    # Backend detection & initialization
└── fpp_output.py        # FPP/DDP implementation
```

## DDP Protocol Details

### Packet Format

```
Header (9 bytes):
  [0] Flags: 0x04 (VER=0, PUSH=1)
  [1] Sequence: 0x01
  [2] Data Type: 0x01 (RGB)
  [3] ID: 0x01 (destination)
  [4-6] Offset: 0x000000 (pixel offset)
  [7-8] Length: packet data length
  
Data: RGB bytes (R,G,B for each pixel)
```

### Performance

- Single UDP packet per frame
- ~6KB for 64x32 display (6,144 bytes RGB)
- Network overhead minimal on local network
- Uses numpy if available for better performance

## Dependencies

### Required
None - FPP mode works with Python standard library

### Optional (Recommended)
```bash
pip install numpy      # Faster buffer operations
pip install pillow     # Better text rendering
```

Without these packages:
- Text rendering uses simple pixel blocks
- Buffer operations use Python lists (slower)

## Comparison: Direct vs FPP

| Feature | Direct (rgbmatrix) | FPP Mode |
|---------|-------------------|----------|
| Hardware | Raspberry Pi GPIO | Any computer |
| OS Support | Linux only | Windows/Mac/Linux |
| Setup | Complex wiring | Network cable |
| Latency | <1ms | ~5-10ms |
| Range | GPIO pins only | Network (unlimited) |
| Receiver Cards | DIY wiring | Professional cards |
| Cost | Panel + wiring | Panel + receiver card |

## Troubleshooting

### "No module named 'fpp_output'"
Make sure all files are in the same directory:
- display_event.py
- event_parser.py
- matrix_backend.py
- fpp_output.py

### "Connection refused" or no display
1. Check FPP is running: `http://[fpp-ip-address]`
2. Verify FPP is listening on DDP port 4048
3. Check firewall settings
4. Verify IP address is correct

### Text rendering issues
Install PIL/Pillow:
```bash
pip install pillow
```

### Slow performance
Install numpy:
```bash
pip install numpy
```

## Examples

### Development Workflow
```bash
# Test on local machine with FPP
python display_event.py --event 1 --round 1 --heat 1 --fpp

# Deploy to remote FPP at track
python display_event.py --event 1 --round 1 --heat 1 --fpp --fpp-host 192.168.1.100
```

### Production Setup
```bash
# Raspberry Pi running FPP + display_event together
python display_event.py --event 11 --round 1 --heat 1 \
  --fpp --fpp-host 127.0.0.1 \
  --chain 2 --parallel 3 --header-rows 2
```

### Remote Control
```bash
# Control display from laptop via network
python display_event.py --event 11 --round 1 --heat 1 \
  --fpp --fpp-host 192.168.1.100 \
  --width 128 --height 96
```

## Advanced Configuration

### Multiple Displays
FPP supports multiple universes/displays:
```python
# Modify fpp_output.py FPPMatrix.__init__
self.destination_id = 0x01  # Change for different displays
```

### Custom Pixel Mapping
FPP handles pixel mapping in its configuration. No code changes needed.

### Brightness Control
Configure in FPP web interface - no code changes needed.

## Migration Guide

### From Direct Matrix to FPP

**Before:**
```bash
python display_event.py --event 11 --round 1 --heat 1 \
  --chain 2 --parallel 3
```

**After:**
```bash
python display_event.py --event 11 --round 1 --heat 1 \
  --chain 2 --parallel 3 \
  --fpp --fpp-host 192.168.1.100
```

The `--chain` and `--parallel` arguments still work but are used to calculate display dimensions. FPP configuration determines actual hardware layout.

## Testing

All existing unit tests pass with the refactored code:
```bash
python -m unittest test_display_event -v
```

The tests validate:
- Event parsing
- Lane filling
- Color handling
- Heat navigation
- All formatting functions

## Future Enhancements

Potential additions:
- E1.31/sACN protocol support
- ArtNet protocol support
- Multi-universe support for large displays
- Brightness/gamma correction
- FPP status monitoring
- Auto-discovery of FPP receivers

## License

Same as main project.
