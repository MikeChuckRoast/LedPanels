"""
Configuration loader for LED Panels display system.

Handles loading of:
- settings.toml: global configuration ([hardware], [network], [fonts],
  [files], [web], [manager]) via load_settings, and per-mode settings
  ([mode.<name>]) via load_mode_config
- current_event.json: Event/round/heat tracking

Global settings describe the box and apply to whichever mode is running.
Anything only one mode reads belongs in that mode's section, so the two are
loaded and validated independently.
"""

import json
import logging
import tomllib
from pathlib import Path
from typing import Any, Dict


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


# Used when settings.toml cannot be read at all — see resolve_colors_path().
DEFAULT_COLORS_FILE = "colors.csv"
DEFAULT_LYNX_FILE = "lynx.evt"


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
        logging.info("Config directory ready: %s", config_dir)
    except Exception as e:
        raise ConfigError(f"Failed to create config directory '{config_dir}': {e}")

    # Where animation_display looks for clips, and where web uploads land.
    try:
        (config_path / "animations").mkdir(exist_ok=True)
    except Exception as e:
        raise ConfigError(f"Failed to create animations directory: {e}")

    # Create default current_event.json if it doesn't exist
    current_event_path = config_path / "current_event.json"
    if not current_event_path.exists():
        default_event = {"event": 1, "round": 1, "heat": 1}
        try:
            with open(current_event_path, "w", encoding="utf-8") as f:
                json.dump(default_event, f, indent=2)
            logging.info("Created default current_event.json")
        except Exception as e:
            raise ConfigError(f"Failed to create default current_event.json: {e}")

    # Create default settings.toml if it doesn't exist
    settings_path = config_path / "settings.toml"
    if not settings_path.exists():
        # Point at the fonts/ directory shipped alongside this module rather than
        # a hard-coded path, so a first run works wherever the repo is checked out.
        bundled_fonts = (Path(__file__).resolve().parent / "fonts").as_posix()
        default_settings = f"""# LED Panels Display Configuration
#
# Global sections describe the box itself and apply to whichever mode is
# running. Anything a single mode owns lives under [mode.<name>] below.

# --- Global ----------------------------------------------------------------

[hardware]
# Physical panel configuration — the only copy. Every mode renders to it.
width = 64           # Single panel width in pixels
height = 32          # Single panel height in pixels
chain = 2            # Panels chained horizontally
parallel = 4         # Panels stacked vertically
gpio_slowdown = 3    # GPIO slowdown for RGBMatrixOptions

[network]
# FPP (Falcon Player Protocol) settings
fpp_enabled = false
fpp_host = "127.0.0.1"
fpp_port = 4048

# ColorLight 5A-75B settings
colorlight_enabled = false
colorlight_interface = "eth0"
# Pause after each row is written, in milliseconds. Dominates ColorLight frame
# time — a 128-row panel spends ~128ms per frame here, capping it near 7fps.
# Lower it to speed up animation, but too low tears frames; tune on hardware.
colorlight_row_delay_ms = 1.0

[fonts]
# Directory holding the BDF fonts. Modes name a bare filename inside it.
# Defaults to the fonts/ directory shipped with this repo. Bundled fonts:
# helvB14.bdf, helvB18.bdf, helvB24.bdf, Roboto-Black-50.bdf
font_path = "{bundled_fonts}"

[files]
# Team color mappings, relative to this config directory. Shared by
# display_event and athletic_live_scoreboard.
colors_file = "colors.csv"

[web]
# Web interface for remote control and configuration
web_enabled = true           # Enable web interface
web_host = "0.0.0.0"         # Host to bind to (0.0.0.0 = all interfaces)
web_port = 80                # Port for web server (the service runs as root, so <1024 binds)

[manager]
# display_manager.py — the process the systemd service starts.
# It hosts the web UI and runs one display mode as a child process.
active_mode = "display_event"   # display_event | athletic_live_scoreboard | udp_scoreboard | animation_display
auto_restart = true             # Restart the display mode if it exits
restart_backoff_sec = 5         # Seconds to wait before restarting

# --- Per-mode --------------------------------------------------------------
# Only the active mode reads its own section. Panel geometry, output backend,
# font directory and colors_file all come from the global sections above.

[mode.display_event]
# Paged event listings from a Lynx .evt file.
line_height = 24              # Athlete row height in pixels
header_line_height = 16       # Header row height in pixels
header_rows = 1               # Number of header rows (allows text wrapping)
interval = 2.0                # Seconds per page when paging
font_shift = 0                # Font positioning adjustment (vertical)
font_name = "helvB14.bdf"     # Bare filename inside [fonts].font_path
lynx_file = "lynx.evt"        # Event timing data, relative to this directory
once = false                  # Render once and exit vs. continuous loop
keyboard_device = ""          # evdev input device; empty = auto-detect
file_watch_enabled = true     # Reload automatically when the data files change

[mode.athletic_live_scoreboard]
# Required before this mode can start. Both values come from the scoreboard URL:
# https://sb.athletic.live/...?name=FUSHIABOX&uuid=dc4113ed-...
name = ""                       # Scoreboard computer name
uuid = ""                       # Scoreboard UUID
poll_interval = 3.0             # Seconds between polls
font_name = "helvB14.bdf"       # Bare filename inside [fonts].font_path

[mode.udp_scoreboard]
# Two-section scoreboard driven by JSON over UDP.
udp_port = 5568                 # UDP port to listen on
buffer_size = 4096              # Maximum UDP packet size
top_height = 24                 # Height of the event-name band in pixels
top_color = "#008500"           # Hex fill for the event-name band background
bottom_height = 0               # Height of the time band; 0 = rest of the panel
top_font_name = "helvB18.bdf"            # Bare filename inside [fonts].font_path
bottom_font_name = "Roboto-Black-50.bdf" # Bare filename inside [fonts].font_path
top_font_shift_vertical = 0       # Vertical offset for the event name
top_font_shift_horizontal = 0     # Horizontal offset for the event name
bottom_font_shift_vertical = 0    # Vertical offset for the time
bottom_font_shift_horizontal = 0  # Horizontal offset for the time

[mode.animation_display]
# A bare filename resolves inside config/animations/, where web UI uploads land.
# GIF/APNG/WebP need nothing extra; MP4/MOV/WebM need ffmpeg on PATH.
file = ""                       # Required before this mode can start
fit = "contain"                 # contain (letterbox) | cover (crop) | stretch
fps = 0                         # 0 keeps the source's own timing
loop = true                     # Repeat forever vs. play once and exit
background = "#000000"          # Fill behind letterboxing and transparency
max_frames = 600                # Cap on decoded frames
ffmpeg = ""                     # Path to the ffmpeg binary; empty searches PATH
"""
        try:
            with open(settings_path, "w", encoding="utf-8") as f:
                f.write(default_settings)
            logging.info("Created default settings.toml")
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
        logging.info("Loaded settings from: %s", settings_path)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Invalid TOML in settings file: {e}")
    except Exception as e:
        raise ConfigError(f"Failed to load settings file: {e}")

    # Only the global sections are validated here. Per-mode settings live under
    # [mode.<name>] and are checked by normalize_mode_config, so one mode's
    # broken section can never stop a different mode from loading its geometry.
    required_sections = ["hardware", "network", "fonts", "files"]
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

    # Validate fonts
    fonts = settings["fonts"]
    if "font_path" not in fonts:
        raise ConfigError("Missing 'font_path' in [fonts] section")
    font_path = fonts["font_path"]
    if not isinstance(font_path, str) or not font_path:
        raise ConfigError("'font_path' must be a non-empty string")
    # Note: Not validating file existence here since font might be platform-specific

    # Validate files (relative to the config directory)
    files = settings["files"]
    if "colors_file" not in files:
        raise ConfigError("Missing 'colors_file' in [files] section")
    if not isinstance(files["colors_file"], str) or not files["colors_file"]:
        raise ConfigError("'colors_file' must be a non-empty string")
    # Note: existence is not checked here. udp_scoreboard and animation_display
    # never read team colors, and failing their config load over a missing CSV
    # would silently drop them back to built-in geometry defaults. The modes
    # that do need it resolve it through resolve_colors_path().

    # Validate network settings
    net = settings["network"]
    _validate_bool(net, "fpp_enabled", "network")
    if "fpp_host" not in net or not isinstance(net["fpp_host"], str):
        raise ConfigError("'fpp_host' must be a string in [network] section")
    _validate_port(net, "fpp_port", "network")

    _validate_bool(net, "colorlight_enabled", "network")
    if "colorlight_interface" not in net or not isinstance(net["colorlight_interface"], str):
        raise ConfigError("'colorlight_interface' must be a string in [network] section")
    # Optional — omitted means colorlight_output.DEFAULT_ROW_DELAY_MS
    if "colorlight_row_delay_ms" in net:
        value = net["colorlight_row_delay_ms"]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ConfigError(
                "'colorlight_row_delay_ms' must be a non-negative number in "
                f"[network] section (got: {value})")

    # Validate web (optional section — defaults are applied by the callers)
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
    logging.info("  Hardware: %dx%d, chain=%d, parallel=%d", hw['width'], hw['height'], hw['chain'], hw['parallel'])
    logging.info("  Fonts: %s", fonts['font_path'])
    logging.info("  Colors: %s", files['colors_file'])
    logging.info("  Network: FPP=%s, ColorLight=%s", net['fpp_enabled'], net['colorlight_enabled'])

    return settings


def resolve_colors_path(config_dir: str) -> Path:
    """Absolute path to the team-colors CSV named by [files].colors_file.

    Every consumer of colors.csv goes through here so the setting means
    something. Never raises: an unreadable settings.toml falls back to the
    default filename rather than taking down the caller.
    """
    return Path(config_dir) / _global_file_setting(
        config_dir, "colors_file", DEFAULT_COLORS_FILE)


def resolve_lynx_path(config_dir: str) -> Path:
    """Absolute path to the Lynx event file named by [mode.display_event].lynx_file.

    Same contract as resolve_colors_path — the web UI and the file watcher
    need this without a full settings load.
    """
    try:
        cfg = load_mode_config(config_dir, "display_event")
        name = cfg.get("lynx_file") or DEFAULT_LYNX_FILE
    except Exception:
        name = DEFAULT_LYNX_FILE
    return Path(config_dir) / name


def _global_file_setting(config_dir: str, key: str, fallback: str) -> str:
    """Read one key out of [files], falling back when settings.toml is unusable."""
    try:
        with open(Path(config_dir) / "settings.toml", "rb") as f:
            raw = tomllib.load(f)
        value = (raw.get("files") or {}).get(key)
    except Exception:
        return fallback
    return value if isinstance(value, str) and value else fallback


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
        logging.info("Loaded current event from: %s", event_path)
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

    logging.info("  Current event: Event=%d, Round=%d, Heat=%d", event_data['event'], event_data['round'], event_data['heat'])

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


# ---------------------------------------------------------------------------
# Display Manager config helpers
# ---------------------------------------------------------------------------

_MANAGER_DEFAULTS = {
    "active_mode": "display_event",
    "auto_restart": True,
    "restart_backoff_sec": 5,
}

_MODE_DEFAULTS: Dict[str, Dict] = {
    "display_event": {
        "line_height": 24,
        "header_line_height": 16,
        "header_rows": 2,
        "interval": 2.0,
        "font_shift": 0,
        "font_name": "helvB14.bdf",
        "lynx_file": DEFAULT_LYNX_FILE,
        "once": False,
        "keyboard_device": "",
        "file_watch_enabled": True,
    },
    "athletic_live_scoreboard": {
        "name": "",
        "uuid": "",
        "poll_interval": 3.0,
        "font_name": "helvB14.bdf",
    },
    "udp_scoreboard": {
        "udp_port": 5568,
        "buffer_size": 4096,
        "top_height": 24,
        # 0 means "the rest of the panel", so the default adapts to any height.
        "bottom_height": 0,
        "top_font_name": "helvB18.bdf",
        "bottom_font_name": "Roboto-Black-50.bdf",
        "top_font_shift_vertical": 0,
        "top_font_shift_horizontal": 0,
        "bottom_font_shift_vertical": 0,
        "bottom_font_shift_horizontal": 0,
        "top_color": "#008500",
    },
    "animation_display": {
        "file": "",
        "fit": "contain",
        "fps": 0,
        "loop": True,
        "background": "#000000",
        "max_frames": 600,  # animation_loader.DEFAULT_MAX_FRAMES
        "ffmpeg": "",
    },
}

# Value kind per mode setting, driving both coercion and validation in
# normalize_mode_config. Keys absent from a mode's schema are rejected, which
# is what catches a setting left behind in an old section name.
_MODE_SCHEMA: Dict[str, Dict[str, str]] = {
    "display_event": {
        "line_height": "positive_int",
        "header_line_height": "positive_int",
        "header_rows": "positive_int",
        "interval": "positive_float",
        "font_shift": "int",
        "font_name": "bdf_name",
        "lynx_file": "non_empty_str",
        "once": "bool",
        "keyboard_device": "str",
        "file_watch_enabled": "bool",
    },
    "athletic_live_scoreboard": {
        "name": "str",
        "uuid": "str",
        "poll_interval": "positive_float",
        "font_name": "bdf_name",
    },
    "udp_scoreboard": {
        "udp_port": "port",
        "buffer_size": "positive_int",
        "top_height": "positive_int",
        "bottom_height": "non_negative_int",
        "top_font_name": "bdf_name",
        "bottom_font_name": "bdf_name",
        "top_font_shift_vertical": "int",
        "top_font_shift_horizontal": "int",
        "bottom_font_shift_vertical": "int",
        "bottom_font_shift_horizontal": "int",
        "top_color": "str",
    },
    "animation_display": {
        "file": "str",
        "fit": "fit_mode",
        "fps": "non_negative_float",
        "loop": "bool",
        "background": "str",
        "max_frames": "positive_int",
        "ffmpeg": "str",
    },
}

VALID_MODES = list(_MODE_DEFAULTS.keys())


def load_manager_config(config_dir: str) -> Dict[str, Any]:
    """Return [manager] section with defaults injected for missing keys.

    Never raises — if settings.toml is unreadable the full defaults are returned.
    """
    try:
        settings_path = Path(config_dir) / "settings.toml"
        with open(settings_path, "rb") as f:
            raw = tomllib.load(f)
        section = raw.get("manager", {})
    except Exception:
        section = {}

    result = dict(_MANAGER_DEFAULTS)
    result.update(section)
    return result


_FIT_MODES = ("contain", "cover", "stretch")  # animation_loader.FIT_MODES


def _coerce_mode_value(mode: str, key: str, kind: str, value: Any) -> Any:
    """Coerce and check one mode setting, returning the cleaned value.

    Web form posts arrive as strings, so numeric kinds are cast rather than
    type-checked. Raises ConfigError with a message fit for a 400 response.
    """
    where = f"[mode.{mode}].{key}"

    if kind == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return value.strip().lower() == "true"
        raise ConfigError(f"{where} must be a boolean (got: {value!r})")

    if kind in ("int", "positive_int", "non_negative_int", "port"):
        # bool is an int subclass, so it has to be excluded explicitly.
        if isinstance(value, bool):
            raise ConfigError(f"{where} must be an integer (got: {value!r})")
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise ConfigError(f"{where} must be an integer (got: {value!r})")
        if kind == "positive_int" and number <= 0:
            raise ConfigError(f"{where} must be a positive integer (got: {number})")
        if kind == "non_negative_int" and number < 0:
            raise ConfigError(f"{where} must be zero or greater (got: {number})")
        if kind == "port" and not 1 <= number <= 65535:
            raise ConfigError(f"{where} must be a valid port number 1-65535 (got: {number})")
        return number

    if kind in ("positive_float", "non_negative_float"):
        if isinstance(value, bool):
            raise ConfigError(f"{where} must be a number (got: {value!r})")
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ConfigError(f"{where} must be a number (got: {value!r})")
        if kind == "positive_float" and number <= 0:
            raise ConfigError(f"{where} must be a positive number (got: {number})")
        if kind == "non_negative_float" and number < 0:
            raise ConfigError(f"{where} must be zero or greater (got: {number})")
        return number

    if kind == "bdf_name":
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"{where} must be a non-empty font filename")
        if not value.endswith(".bdf"):
            raise ConfigError(f"{where} must name a .bdf font file (got: {value!r})")
        return value.strip()

    if kind == "non_empty_str":
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"{where} must be a non-empty string")
        return value.strip()

    if kind == "fit_mode":
        if value not in _FIT_MODES:
            raise ConfigError(f"{where} must be one of {list(_FIT_MODES)} (got: {value!r})")
        return value

    if kind == "str":
        if not isinstance(value, str):
            raise ConfigError(f"{where} must be a string (got: {value!r})")
        return value

    raise ConfigError(f"Unknown validation kind '{kind}' for {where}")


def normalize_mode_config(mode: str, values: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce and validate *values* against *mode*'s schema.

    Returns a cleaned copy. Raises ConfigError naming the offending key, so
    callers writing settings (the web API, save_mode_config) can reject bad
    input instead of persisting it.
    """
    if mode not in _MODE_SCHEMA:
        raise ConfigError(f"Unknown mode '{mode}'. Valid modes: {VALID_MODES}")

    schema = _MODE_SCHEMA[mode]
    unknown = [k for k in values if k not in schema]
    if unknown:
        raise ConfigError(
            f"Unknown setting(s) for [mode.{mode}]: {sorted(unknown)}. "
            f"Valid keys: {sorted(schema)}")

    return {key: _coerce_mode_value(mode, key, schema[key], value)
            for key, value in values.items()}


def load_mode_config(config_dir: str, mode: str) -> Dict[str, Any]:
    """Return flattened config for *mode*, merging defaults with [mode.<mode>] overrides."""
    if mode not in _MODE_DEFAULTS:
        raise ConfigError(f"Unknown mode '{mode}'. Valid modes: {VALID_MODES}")

    try:
        settings_path = Path(config_dir) / "settings.toml"
        with open(settings_path, "rb") as f:
            raw = tomllib.load(f)
        section = (raw.get("mode") or {}).get(mode, {})
    except Exception:
        section = {}

    # Merge leniently: a key that is unknown or fails validation is logged and
    # left at its default rather than raising, so one typo cannot stop a
    # display from starting.
    result = dict(_MODE_DEFAULTS[mode])
    schema = _MODE_SCHEMA[mode]
    for key, value in section.items():
        if key not in schema:
            logging.warning("Ignoring unknown setting [mode.%s].%s", mode, key)
            continue
        try:
            result[key] = _coerce_mode_value(mode, key, schema[key], value)
        except ConfigError as exc:
            logging.warning("%s — falling back to %r", exc, result[key])
    return result


def save_mode_config(config_dir: str, mode: str, values: Dict[str, Any]) -> None:
    """Persist *values* into the [mode.<mode>] section of settings.toml.

    Only keys present in *values* are updated; other keys in that section
    and all other sections are left intact. Values are validated first, so a
    bad setting is rejected rather than written to disk.
    """
    import tomli_w  # optional dep — only needed by manager

    if mode not in _MODE_DEFAULTS:
        raise ConfigError(f"Unknown mode '{mode}'. Valid modes: {VALID_MODES}")

    values = normalize_mode_config(mode, values)

    settings_path = Path(config_dir) / "settings.toml"
    try:
        with open(settings_path, "rb") as f:
            config = tomllib.load(f)
    except Exception as e:
        raise ConfigError(f"Failed to load settings.toml: {e}")

    if "mode" not in config:
        config["mode"] = {}
    if mode not in config["mode"]:
        config["mode"][mode] = {}
    config["mode"][mode].update(values)

    try:
        with open(settings_path, "wb") as f:
            tomli_w.dump(config, f)
    except Exception as e:
        raise ConfigError(f"Failed to write settings.toml: {e}")

    logging.info("Saved mode config [mode.%s]: %s", mode, values)


def save_active_mode(config_dir: str, mode: str) -> None:
    """Persist [manager].active_mode to settings.toml."""
    import tomli_w  # optional dep — only needed by manager

    if mode not in _MODE_DEFAULTS:
        raise ConfigError(f"Unknown mode '{mode}'. Valid modes: {VALID_MODES}")

    settings_path = Path(config_dir) / "settings.toml"
    try:
        with open(settings_path, "rb") as f:
            config = tomllib.load(f)
    except Exception as e:
        raise ConfigError(f"Failed to load settings.toml: {e}")

    if "manager" not in config:
        config["manager"] = dict(_MANAGER_DEFAULTS)
    config["manager"]["active_mode"] = mode

    try:
        with open(settings_path, "wb") as f:
            tomli_w.dump(config, f)
    except Exception as e:
        raise ConfigError(f"Failed to write settings.toml: {e}")

    logging.info("Saved active_mode = %s", mode)
