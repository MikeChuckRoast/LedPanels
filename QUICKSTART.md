# Quick Start Guide - FPP Mode

## 1. Install Optional Dependencies (Recommended)

```bash
pip install numpy pillow
```

## 2. Run with FPP

### Local FPP (same machine)
```bash
python display_event.py --event 11 --round 1 --heat 1 --fpp
```

### Remote FPP (network)
```bash
python display_event.py --event 11 --round 1 --heat 1 --fpp --fpp-host 192.168.1.100
```

### Full Example
```bash
python display_event.py \
  --event 11 --round 1 --heat 1 \
  --fpp --fpp-host 192.168.1.100 \
  --width 128 --height 96 \
  --chain 2 --parallel 3 \
  --header-rows 2
```

## 3. Keyboard Controls

- **Page Down** - Next heat
- **Page Up** - Previous heat  
- **Period (.)** - Return to original heat
- **Ctrl+C** - Exit

## 4. Test Everything Works

```bash
# Run unit tests
python -m unittest test_display_event -v

# Check command-line help
python display_event.py --help
```

## 5. FPP Setup (First Time)

1. Install FPP on Raspberry Pi: https://github.com/FalconChristmas/fpp
2. Access FPP web interface: http://[fpp-ip-address]
3. Configure:
   - Display size (e.g., 128x96)
   - Output type (your LED receiver card model)
   - Test with built-in patterns
4. Note the IP address
5. Run display_event with `--fpp --fpp-host [ip-address]`

## File Overview

| File | Purpose |
|------|---------|
| `display_event.py` | Main application |
| `event_parser.py` | Data parsing |
| `matrix_backend.py` | Hardware abstraction |
| `fpp_output.py` | FPP/DDP protocol |
| `test_display_event.py` | Unit tests |
| `lynx.evt` | Event data |
| `colors.csv` | Team colors |

## Common Issues

**"Cannot import fpp_output"**
- Make sure all .py files are in same directory

**"No display"**
- Verify FPP is running: http://[fpp-ip]
- Check firewall settings
- Verify IP address

**"Poor text quality"**
- Install Pillow: `pip install pillow`

**"Slow performance"**
- Install numpy: `pip install numpy`

## More Info

- **FPP_README.md** - Complete FPP documentation
- **TEST_README.md** - Testing guide
- **REFACTORING_SUMMARY.md** - Technical details
