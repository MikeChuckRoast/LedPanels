# Configuration Guide

The LED Panels display system uses a configuration folder to manage settings, data files, and current event tracking.

## Directory Structure

```
config/
├── settings.toml              # Main configuration file (gitignored)
├── settings.toml.example      # Example configuration with comments
├── current_event.json         # Tracks current event/round/heat (gitignored)
├── current_event.json.example # Example current event file
├── lynx.evt                   # Event timing data (gitignored)
└── colors.csv                 # Team color mappings (in version control)
```

## Configuration Files

### settings.toml

Main configuration file containing all display, hardware, and network settings. This file is automatically created with defaults on first run if it doesn't exist.

**Sections:**
- `[hardware]` - Physical panel configuration (width, height, chain, parallel, gpio_slowdown)
- `[display]` - Display layout and timing (line heights, intervals, font shift)
- `[fonts]` - Font file paths (absolute paths)
- `[files]` - Data file paths relative to config directory (lynx_file, colors_file)
- `[network]` - FPP and ColorLight network output settings
- `[keyboard]` - Keyboard input device configuration
- `[behavior]` - Runtime behavior (once mode, looping)

### current_event.json

Tracks the currently selected event, round, and heat. Used as default values when running `display_event.py` without explicit `--event`, `--round`, `--heat` arguments.

```json
{
  "event": 1,
  "round": 1,
  "heat": 1
}
```

## Usage

### Basic Usage

Run with default configuration:
```bash
python display_event.py
```

This will use values from:
- `config/settings.toml` for all display/hardware settings
- `config/current_event.json` for event/round/heat selection

### Override Configuration

Any setting can be overridden via command-line arguments:

```bash
# Override event selection
python display_event.py --event 2 --round 1 --heat 3

# Override display settings
python display_event.py --width 128 --height 64 --interval 3.0

# Use different config directory
python display_event.py --config-dir ./my-config
```

### First-Time Setup

1. **Copy example files:**
   ```bash
   cd config
   cp settings.toml.example settings.toml
   cp current_event.json.example current_event.json
   ```

2. **Edit settings.toml:**
   - Update `font_path` to point to your BDF font file
   - Adjust hardware settings for your LED panel configuration
   - Configure network settings if using FPP or ColorLight output

3. **Add your data:**
   - Place your `lynx.evt` file in the `config/` directory
   - Update `colors.csv` with your team color mappings

### Platform-Specific Settings

**Font Paths:**
- macOS: `/Users/username/path/to/fonts/helvB12.bdf`
- Linux: `/home/username/path/to/fonts/helvB12.bdf`
- Windows: `C:/Users/username/path/to/fonts/helvB12.bdf`

Update the `font_path` in `settings.toml` for your platform.

## Configuration Priority

Settings are loaded in this order (highest priority last):
1. Default values (from config_loader.py)
2. settings.toml / current_event.json
3. Command-line arguments

This means CLI arguments always override config file values.

## File Paths

- **Relative paths**: `lynx_file` and `colors_file` in settings.toml are relative to the config directory
- **Absolute paths**: `font_path` should be an absolute path to the BDF font file

## Validation

The configuration loader performs strict validation:
- All required sections and fields must be present
- Numeric values must be in valid ranges
- File paths are checked for existence
- TOML syntax must be valid

If configuration is invalid, the program will exit with a clear error message.

## Version Control

**Tracked files:**
- `settings.toml.example`
- `current_event.json.example`
- `colors.csv`

**Gitignored files:**
- `settings.toml` (contains local paths)
- `current_event.json` (runtime state)
- `lynx.evt` (event data)

This allows each user to have their own local configuration while sharing example files and color mappings.

## Troubleshooting

**"Settings file not found"**
- Ensure `config/settings.toml` exists
- Run once to auto-create default files, or copy from .example files

**"Invalid TOML"**
- Check for syntax errors in settings.toml
- Ensure strings are quoted, numbers are unquoted
- Use `#` for comments, not `//`

**"Font file not found"**
- Verify `font_path` in settings.toml points to a valid BDF font file
- Use absolute paths for fonts
- Check file permissions

**"Lynx event file not found"**
- Ensure `lynx.evt` exists in the config directory
- Check `lynx_file` setting in settings.toml

## Example Configurations

### Development Setup (Emulator)
```toml
[hardware]
width = 64
height = 32
chain = 2
parallel = 1

[network]
fpp_enabled = false
colorlight_enabled = false
```

### Production Setup (Real Hardware)
```toml
[hardware]
width = 128
height = 64
chain = 2
parallel = 4
gpio_slowdown = 3

[network]
fpp_enabled = false
colorlight_enabled = false
```

### Network Output (FPP)
```toml
[hardware]
width = 128
height = 64

[network]
fpp_enabled = true
fpp_host = "192.168.1.100"
fpp_port = 4048
colorlight_enabled = false
```
