"""
Configuration loader for LED Panels display system.

Handles loading of:
- settings.toml: Display, hardware, and network configuration
- current_event.json: Event/round/heat tracking
"""

import json
import logging
import os
import tomllib
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


def ensure_config_directory(config_dir: str) -> None:
    """Create config directory and default files if they don't exist.

    Args:
        config_dir: Path to configuration directory

    Raises:
        ConfigError: If directory cannot be created
    """
    config_path = Path(config_dir)

    try:
        config_path.mkdir(parents=True, exist_ok=True)
        logging.info(f"Config directory ready: {config_dir}")
    except Exception as e:
        raise ConfigError(f"Failed to create config directory '{config_dir}': {e}")

    # Create default current_event.json if it doesn't exist
    current_event_path = config_path / "current_event.json"
    if not current_event_path.exists():
        default_event = {"event": 1, "round": 1, "heat": 1}
        try:
            with open(current_event_path, "w", encoding="utf-8") as f:
                json.dump(default_event, f, indent=2)
            logging.info(f"Created default current_event.json")
        except Exception as e:
            raise ConfigError(f"Failed to create default current_event.json: {e}")

    # Create default settings.toml if it doesn't exist
    settings_path = config_path / "settings.toml"
    if not settings_path.exists():
        default_settings = """# LED Panels Display Configuration

[hardware]
# Physical panel configuration
width = 64           # Display width in pixels
height = 32          # Display height in pixels
chain = 2            # Panels chained horizontally
parallel = 4         # Panels stacked vertically
gpio_slowdown = 3    # GPIO slowdown for RGBMatrixOptions

[display]
# Display layout and timing
line_height = 24              # Athlete row height in pixels
header_line_height = 16       # Header row height in pixels
header_rows = 1               # Number of header rows (allows text wrapping)
interval = 2.0                # Seconds per page when paging
font_shift = 7                # Font positioning adjustment (vertical)

[fonts]
# Font configuration (use absolute path for font_path)
font_path = "/Users/mike/Documents/Code Projects/u8g2/tools/font/bdf"  # Directory containing font files
font_name = "helvB12.bdf"  # Font filename (can be changed via web UI)

[files]
# Data file paths (relative to config directory)
lynx_file = "lynx.evt"       # Event timing data file
colors_file = "colors.csv"   # Team color mappings file

[network]
# FPP (Falcon Player Protocol) settings
fpp_enabled = false
fpp_host = "127.0.0.1"
fpp_port = 4048

# ColorLight 5A-75B settings
colorlight_enabled = false
colorlight_interface = "eth0"

[keyboard]
# Keyboard input settings (empty = auto-detect)
device_path = ""

[behavior]
# Runtime behavior
once = false  # Render once and exit vs. continuous loop

[monitoring]
# File monitoring for automatic reload
file_watch_enabled = true    # Enable automatic file monitoring (requires watchdog library)
poll_interval = 1.0          # Polling interval in seconds (fallback mode only)

[web]
# Web interface for remote control and configuration
web_enabled = true           # Enable web interface
web_host = "0.0.0.0"          # Host to bind to (0.0.0.0 = all interfaces)
web_port = 5000              # Port for web server
"""
        try:
            with open(settings_path, "w", encoding="utf-8") as f:
                f.write(default_settings)
            logging.info(f"Created default settings.toml")
        except Exception as e:
            raise ConfigError(f"Failed to create default settings.toml: {e}")


def load_settings(config_dir: str) -> Dict[str, Any]:
    """Load settings from settings.toml file.

    Args:
        config_dir: Path to configuration directory

    Returns:
        Dictionary containing all settings organized by section

    Raises:
        ConfigError: If settings file is missing or invalid
    """
    settings_path = Path(config_dir) / "settings.toml"

    if not settings_path.exists():
        raise ConfigError(f"Settings file not found: {settings_path}")

    try:
        with open(settings_path, "rb") as f:
            settings = tomllib.load(f)
        logging.info(f"Loaded settings from: {settings_path}")
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Invalid TOML in settings file: {e}")
    except Exception as e:
        raise ConfigError(f"Failed to load settings file: {e}")

    # Validate required sections (monitoring is optional)
    required_sections = ["hardware", "display", "fonts", "files", "network", "keyboard", "behavior"]
    missing_sections = [s for s in required_sections if s not in settings]
    if missing_sections:
        raise ConfigError(f"Missing required sections in settings.toml: {missing_sections}")

    # Validate hardware settings
    hw = settings["hardware"]
    _validate_positive_int(hw, "width", "hardware")
    _validate_positive_int(hw, "height", "hardware")
    _validate_positive_int(hw, "chain", "hardware")
    _validate_positive_int(hw, "parallel", "hardware")
    _validate_non_negative_int(hw, "gpio_slowdown", "hardware")

    # Validate display settings
    disp = settings["display"]
    _validate_positive_int(disp, "line_height", "display")
    _validate_positive_int(disp, "header_line_height", "display")
    _validate_positive_int(disp, "header_rows", "display")
    _validate_positive_float(disp, "interval", "display")
    _validate_int(disp, "font_shift", "display")

    # Validate fonts
    fonts = settings["fonts"]
    if "font_path" not in fonts:
        raise ConfigError("Missing 'font_path' in [fonts] section")
    if "font_name" not in fonts:
        raise ConfigError("Missing 'font_name' in [fonts] section")
    font_path = fonts["font_path"]
    font_name = fonts["font_name"]
    if not isinstance(font_path, str) or not font_path:
        raise ConfigError("'font_path' must be a non-empty string")
    if not isinstance(font_name, str) or not font_name:
        raise ConfigError("'font_name' must be a non-empty string")
    # Note: Not validating file existence here since font might be platform-specific

    # Validate files (relative paths)
    files = settings["files"]
    if "lynx_file" not in files:
        raise ConfigError("Missing 'lynx_file' in [files] section")
    if "colors_file" not in files:
        raise ConfigError("Missing 'colors_file' in [files] section")

    # Validate file existence (resolve relative to config_dir)
    config_path = Path(config_dir)
    lynx_path = config_path / files["lynx_file"]
    colors_path = config_path / files["colors_file"]

    if not lynx_path.exists():
        raise ConfigError(f"Lynx event file not found: {lynx_path}")
    if not colors_path.exists():
        raise ConfigError(f"Colors file not found: {colors_path}")

    # Validate network settings
    net = settings["network"]
    _validate_bool(net, "fpp_enabled", "network")
    if "fpp_host" not in net or not isinstance(net["fpp_host"], str):
        raise ConfigError("'fpp_host' must be a string in [network] section")
    _validate_port(net, "fpp_port", "network")

    _validate_bool(net, "colorlight_enabled", "network")
    if "colorlight_interface" not in net or not isinstance(net["colorlight_interface"], str):
        raise ConfigError("'colorlight_interface' must be a string in [network] section")

    # Validate keyboard
    kbd = settings["keyboard"]
    if "device_path" not in kbd or not isinstance(kbd["device_path"], str):
        raise ConfigError("'device_path' must be a string in [keyboard] section")

    # Validate behavior
    behavior = settings["behavior"]
    _validate_bool(behavior, "once", "behavior")

    # Validate monitoring (optional section for backward compatibility)
    if "monitoring" in settings:
        monitoring = settings["monitoring"]
        if "file_watch_enabled" in monitoring:
            _validate_bool(monitoring, "file_watch_enabled", "monitoring")
        if "poll_interval" in monitoring:
            _validate_positive_float(monitoring, "poll_interval", "monitoring")

    # Validate web (optional section for backward compatibility)
    if "web" in settings:
        web = settings["web"]
        if "web_enabled" in web:
            _validate_bool(web, "web_enabled", "web")
        if "web_host" in web:
            if not isinstance(web["web_host"], str):
                raise ConfigError("web.web_host must be a string")
        if "web_port" in web:
            _validate_port(web, "web_port", "web")

    # Log loaded configuration
    logging.info("Configuration loaded successfully:")
    logging.info(f"  Hardware: {hw['width']}x{hw['height']}, chain={hw['chain']}, parallel={hw['parallel']}")
    logging.info(f"  Display: line_height={disp['line_height']}, header={disp['header_line_height']}, interval={disp['interval']}s")
    logging.info(f"  Files: lynx={files['lynx_file']}, colors={files['colors_file']}")
    logging.info(f"  Font: {fonts['font_path']}/{fonts['font_name']}")
    logging.info(f"  Network: FPP={net['fpp_enabled']}, ColorLight={net['colorlight_enabled']}")

    return settings


def load_current_event(config_dir: str) -> Dict[str, int]:
    """Load current event/round/heat from current_event.json.

    Args:
        config_dir: Path to configuration directory

    Returns:
        Dictionary with 'event', 'round', and 'heat' keys

    Raises:
        ConfigError: If file is missing or invalid
    """
    event_path = Path(config_dir) / "current_event.json"

    if not event_path.exists():
        raise ConfigError(f"Current event file not found: {event_path}")

    try:
        with open(event_path, "r", encoding="utf-8") as f:
            event_data = json.load(f)
        logging.info(f"Loaded current event from: {event_path}")
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in current_event.json: {e}")
    except Exception as e:
        raise ConfigError(f"Failed to load current_event.json: {e}")

    # Validate required fields
    required_fields = ["event", "round", "heat"]
    missing_fields = [f for f in required_fields if f not in event_data]
    if missing_fields:
        raise ConfigError(f"Missing required fields in current_event.json: {missing_fields}")

    # Validate types and values
    for field in required_fields:
        value = event_data[field]
        if not isinstance(value, int):
            raise ConfigError(f"'{field}' must be an integer in current_event.json")
        if value < 1:
            raise ConfigError(f"'{field}' must be >= 1 in current_event.json")

    logging.info(f"  Current event: Event={event_data['event']}, Round={event_data['round']}, Heat={event_data['heat']}")

    return event_data


def _validate_positive_int(config: Dict, key: str, section: str) -> None:
    """Validate that a config value is a positive integer."""
    if key not in config:
        raise ConfigError(f"Missing '{key}' in [{section}] section")
    value = config[key]
    if not isinstance(value, int) or value <= 0:
        raise ConfigError(f"'{key}' must be a positive integer in [{section}] section (got: {value})")


def _validate_non_negative_int(config: Dict, key: str, section: str) -> None:
    """Validate that a config value is a non-negative integer."""
    if key not in config:
        raise ConfigError(f"Missing '{key}' in [{section}] section")
    value = config[key]
    if not isinstance(value, int) or value < 0:
        raise ConfigError(f"'{key}' must be a non-negative integer in [{section}] section (got: {value})")


def _validate_int(config: Dict, key: str, section: str) -> None:
    """Validate that a config value is an integer."""
    if key not in config:
        raise ConfigError(f"Missing '{key}' in [{section}] section")
    value = config[key]
    if not isinstance(value, int):
        raise ConfigError(f"'{key}' must be an integer in [{section}] section (got: {value})")


def _validate_positive_float(config: Dict, key: str, section: str) -> None:
    """Validate that a config value is a positive number (int or float)."""
    if key not in config:
        raise ConfigError(f"Missing '{key}' in [{section}] section")
    value = config[key]
    if not isinstance(value, (int, float)) or value <= 0:
        raise ConfigError(f"'{key}' must be a positive number in [{section}] section (got: {value})")


def _validate_port(config: Dict, key: str, section: str) -> None:
    """Validate that a config value is a valid port number (1-65535)."""
    if key not in config:
        raise ConfigError(f"Missing '{key}' in [{section}] section")
    value = config[key]
    if not isinstance(value, int) or value < 1 or value > 65535:
        raise ConfigError(f"'{key}' must be a valid port number (1-65535) in [{section}] section (got: {value})")


def _validate_bool(config: Dict, key: str, section: str) -> None:
    """Validate that a config value is a boolean."""
    if key not in config:
        raise ConfigError(f"Missing '{key}' in [{section}] section")
    value = config[key]
    if not isinstance(value, bool):
        raise ConfigError(f"'{key}' must be a boolean in [{section}] section (got: {value})")
