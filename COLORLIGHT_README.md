# ColorLight 5A-75B Direct Output

This project now supports sending frames directly to a **ColorLight 5A-75B** LED receiver card using raw Ethernet frames, bypassing the need for FPP or other intermediaries.

## Overview

The ColorLight 5A-75B is a low-cost LED receiver card with an FPGA that can accept LED panel data via Ethernet. This implementation uses the reverse-engineered protocol from the [PyLights](https://github.com/KAkerstrom/PyLights) and [Chubby75](https://github.com/q3k/chubby75) projects.

## Requirements

### Hardware
- ColorLight 5A-75B LED receiver card (V6.1, V7.0, V8.0, or V8.2)
- Direct Ethernet connection between your computer and the ColorLight card
- LED panels connected to the ColorLight card's HUB75 outputs

### Software
- **Linux or Unix system** (Mac, Raspberry Pi, etc.)
  - Windows is **not supported** (requires AF_PACKET raw sockets)
- **Root/sudo privileges** (required for raw socket access)
- Python 3.x
- Optional: `numpy` for better performance

## Usage

### Basic Command

```bash
sudo python display_event.py \
  --event 1 --round 1 --heat 1 \
  --colorlight \
  --colorlight-interface eth0
```

### Important Notes

1. **Must run with sudo**: Raw Ethernet sockets require root privileges
   ```bash
   sudo python display_event.py --colorlight ...
   ```

2. **Network interface**: Specify the interface connected to the ColorLight card
   ```bash
   --colorlight-interface eth0      # Linux
   --colorlight-interface enp0s3    # Linux (newer naming)
   --colorlight-interface en0       # macOS
   ```
   
   Find your interfaces:
   ```bash
   ip link                # Linux
   ifconfig              # macOS/Unix
   ```

3. **Direct connection**: The ColorLight card should be directly connected to your computer (not through a switch/router with other traffic)

### Complete Example

```bash
sudo python display_event.py \
  --file lynx.evt \
  --colors-csv colors.csv \
  --event 101 --round 1 --heat 1 \
  --colorlight \
  --colorlight-interface eth1 \
  --width 64 --height 32 \
  --interval 3.0
```

## How It Works

### Protocol Details

The ColorLight 5A-75B uses a custom Layer 2 (Ethernet) protocol:

1. **Initialization Frames**: Two special frames are sent at startup:
   - Frame 1: EtherType `0x0101`, 98 bytes of zeros
   - Frame 2: EtherType `0x0AFF`, starts with `0xFF 0xFF 0xFF`, then 60 zeros

2. **Data Frames**: One frame per row of pixels:
   - EtherType: `0x5500` (rows 0-255) or `0x5501` (rows 256-511)
   - Payload:
     - Pixel offset (2 bytes, big-endian)
     - Pixel count (2 bytes, big-endian)
     - Magic bytes: `0x08 0x80`
     - **BGR pixel data** (Blue-Green-Red order, not RGB!)

3. **MAC Addresses**:
   - Destination: `11:22:33:44:55:66`
   - Source: `22:22:33:44:55:66`
   - (These can be arbitrary for the 5A-75B)

### Pixel Data Format

- **BGR order** (not RGB): Each pixel is sent as Blue, Green, Red bytes
- Row-by-row transmission
- Max 497 pixels per packet (for wide displays, rows are split into multiple packets)

## Troubleshooting

### "AF_PACKET not available"
**Problem**: Running on Windows  
**Solution**: ColorLight direct output only works on Linux/Unix. On Windows, use `--fpp` to send to FPP instead, or use WSL2 with USB Ethernet adapter passthrough.

### "Permission denied" or socket bind error
**Problem**: Not running with sufficient privileges  
**Solution**: Run with `sudo`:
```bash
sudo python display_event.py --colorlight ...
```

### "Failed to bind to interface 'eth0'"
**Problem**: Interface name is incorrect or interface is down  
**Solutions**:
- Check available interfaces: `ip link` or `ifconfig`
- Verify interface is UP: `sudo ip link set eth0 up`
- Try a different interface name with `--colorlight-interface`

### No display on LED panels
**Possible causes**:
1. **Wrong interface**: Verify you're using the interface connected to ColorLight
2. **Panel configuration**: Ensure `--width` and `--height` match your actual LED panel dimensions
3. **Cable connection**: Check HUB75 cables between ColorLight card and LED panels
4. **Power**: Verify LED panels have adequate power supply
5. **Card version**: This protocol is tested on 5A-75B V6.1-V8.x; other versions may differ

### Firewall blocking
Some systems may have firewall rules blocking raw Ethernet frames:
```bash
# Temporarily disable firewall (Ubuntu/Debian)
sudo ufw disable

# Or allow the interface
sudo ufw allow in on eth0
```

## Performance

- Frame rate depends on:
  - Number of pixels
  - CPU speed
  - Network interface performance
- Typical performance: 20-60 FPS for 64x32 displays
- Use `numpy` (if available) for faster buffer operations

## Comparison with FPP

| Feature | ColorLight Direct | FPP |
|---------|------------------|-----|
| Protocol | Raw Ethernet (Layer 2) | UDP/IP (DDP) |
| Privileges | Requires root/sudo | Standard user |
| OS Support | Linux/Unix only | Cross-platform |
| Network | Direct connection | Can route over network |
| Setup | Simple, no daemon | Requires FPP running |
| Performance | Excellent | Very good |

**When to use ColorLight direct**:
- You have a ColorLight 5A-75B card
- Running on Linux/Raspberry Pi
- Want lowest latency
- Direct Ethernet connection available

**When to use FPP instead**:
- Running on Windows
- Need to route over network/WiFi
- Don't want to run as root
- Using FPP for other features

## References

- **PyLights**: https://github.com/KAkerstrom/PyLights
  - Original Python implementation of ColorLight protocol
- **Chubby75**: https://github.com/q3k/chubby75
  - Comprehensive reverse engineering documentation
  - Hardware pinouts and FPGA programming

## Technical Notes

### Implementation Details
- Uses Python `socket.AF_PACKET` for raw Ethernet access
- Implements PyLights-compatible packet structure
- Sends initialization frames before each frame buffer
- Automatically handles row splitting for wide displays (>497 pixels)
- Internal buffer stores pixels in BGR order for efficiency

### Limitations
- Linux/Unix only (no Windows support for AF_PACKET)
- Requires root privileges
- Direct network connection required (not routable)
- Only tested on ColorLight 5A-75B versions 6.1-8.x

### Future Enhancements
- Add support for other ColorLight models (5A-75E, etc.)
- Optimize frame pacing for consistent refresh rates
- Add statistics/monitoring (FPS counter, dropped frames)
- Support for alternative MAC addresses
- Panel configuration detection
