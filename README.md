# LED Panels

Displays athlete event data and real-time scoreboards on RGB LED panels, driven by data from the Lynx timing system. Supports multiple output backends: direct Raspberry Pi GPIO matrix control, ColorLight 5A-75B Ethernet controllers, and FPP/DDP network output.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [Windows (Development)](#windows-development)
  - [Raspberry Pi (Production)](#raspberry-pi-production)
- [Configuration](#configuration)
  - [settings.toml](#settingstoml)
  - [Output Backends](#output-backends)
  - [Other Config Files](#other-config-files)
- [Main Applications](#main-applications)
  - [display_event.py](#display_eventpy)
  - [udp_scoreboard.py](#udp_scoreboardpy)
- [Web Interface](#web-interface)
- [Utilities](#utilities)
  - [tools/](#tools)
  - [archive/](#archive)
- [Pi Systemd Service](#pi-systemd-service)

---

## Prerequisites

- **Python 3.11+** (required for stdlib `tomllib`)
- On Raspberry Pi: root/sudo access is required for GPIO and raw Ethernet operations

---

## Installation

### Windows (Development)

Use Windows for development and simulation. Hardware-specific packages (`evdev`, `rgbmatrix`) are not installed — the display will run in emulator/simulation mode.

```bash
# Install core runtime dependencies
pip install -r requirements.txt

# Install dev/test tools (optional)
pip install -r requirements-dev.txt
```

**Config setup:**

```bash
# Copy example config files
copy config\settings.toml.example config\settings.toml
copy config\current_event.json.example config\current_event.json
```

Edit `config/settings.toml` and update `font_path` under `[fonts]` to the absolute path of the `fonts/` directory on your machine:

```toml
[fonts]
font_path = "C:/Users/mike/Documents/Code Projects/LED Panels/fonts"
font_name = "helvB14.bdf"
```

---

### Raspberry Pi (Production)

```bash
# Install runtime + hardware dependencies
pip install -r requirements-pi.txt
```

Or using apt for system-wide packages:

```bash
sudo apt install python3-flask python3-watchdog python3-pillow python3-tomli-w python3-evdev
```

**Config setup:**

```bash
# Use the pre-configured Pi template (has Pi font path and ColorLight enabled)
cp config/settings.toml.pi config/settings.toml
cp config/current_event.json.example config/current_event.json
```

> Alternatively, use `settings.toml.example` as a starting point and manually update `font_path`.

Verify `font_path` in `config/settings.toml` matches your install location:

```toml
[fonts]
font_path = "/home/mike/LedPanels/fonts"
font_name = "helvB14.bdf"
```

---

## Configuration

All configuration lives in the `config/` directory. The main file is `config/settings.toml` (copy from `config/settings.toml.example`).

### settings.toml

#### `[hardware]` — Physical panel layout

```toml
[hardware]
width = 64          # Display width in pixels
height = 32         # Display height in pixels
chain = 2           # Panels chained horizontally
parallel = 4        # Panels stacked vertically
gpio_slowdown = 3   # GPIO timing stability (0–4; increase if display is glitchy)
```

#### `[display]` — Layout and timing

```toml
[display]
line_height = 24            # Athlete row height in pixels
header_line_height = 16     # Header row height in pixels
header_rows = 2             # Header rows (allows wrapping of long event names)
interval = 2.0              # Seconds per page when scrolling through athletes
font_shift = 0              # Vertical font positioning adjustment in pixels
```

#### `[fonts]` — Font files

```toml
[fonts]
font_path = "/home/mike/LedPanels/fonts"   # Absolute path to BDF font directory
font_name = "helvB14.bdf"                  # Default font (changeable via web UI)
```

Available fonts in `fonts/`: `helvB14.bdf`, `helvB18.bdf`, `helvB24.bdf`, `Roboto-Black-50.bdf`

#### `[files]` — Data files (relative to config dir)

```toml
[files]
lynx_file = "lynx.evt"       # Event data from Lynx timing system
colors_file = "colors.csv"   # Team name → color mappings
```

#### `[web]` — Web interface

```toml
[web]
web_enabled = true
web_host = "0.0.0.0"    # Bind to all interfaces; use 127.0.0.1 for localhost only
web_port = 5000
```

#### `[scoreboard]` — UDP scoreboard settings

```toml
[scoreboard]
udp_port = 5568
top_height = 24                       # Event name section height
bottom_height = 40                    # Time section height
top_font_name = "helvB18.bdf"
bottom_font_name = "Roboto-Black-50.bdf"
width = 64
height = 32
chain = 3
parallel = 2
gpio_slowdown = 4
```

#### `[keyboard]` — Keyboard navigation device

```toml
[keyboard]
device_path = ""    # Leave empty for auto-detect, or specify: "/dev/input/event2"
```

#### `[monitoring]` — Auto-reload on file changes

```toml
[monitoring]
file_watch_enabled = true
poll_interval = 1.0
```

---

### Output Backends

Three output methods are supported. Configure in `[network]` in `settings.toml`, or override via command-line flags.

| Backend | Platform | How to enable |
|---|---|---|
| Direct matrix (rgbmatrix) | Pi only | Default when `evdev`/`rgbmatrix` installed; requires sudo |
| **ColorLight 5A-75B** | Pi/Linux | `colorlight_enabled = true`; requires sudo for raw Ethernet |
| **FPP/DDP** | Any | `fpp_enabled = true`; set `fpp_host` to FPP receiver IP |
| Emulator/simulation | Windows | Automatic fallback when hardware packages not installed |

```toml
[network]
# Pick one:
fpp_enabled = false
colorlight_enabled = false

# FPP settings (if fpp_enabled = true):
fpp_host = "192.168.1.50"
fpp_port = 4048

# ColorLight settings (if colorlight_enabled = true):
colorlight_interface = "eth0"    # Find with: ip link show
```

---

### Other Config Files

**`config/current_event.json`** — Tracks the currently displayed event position:
```json
{"event": 1, "round": 1, "heat": 1}
```
Updated automatically by keyboard navigation, web UI, and schedule navigation.

**`config/colors.csv`** — Maps team affiliations to display colors:
```
affiliation_name,display_name,background_hex,text_hex
DDCM,Desert Dogs,#0066CC,#FFFFFF
SCVT,Sac Valley,#FFCC00,#000000
```
Generate missing entries from `lynx.evt` automatically with `tools/update_team_colors.py`.

**`config/lynx.evt`** — Event data exported from the Lynx timing system.

**`config/lynx.sch`** — Schedule file for automatic heat progression.

---

## Main Applications

### display_event.py

Displays athlete/event information from a Lynx timing system file on the LED panels. Supports automatic paging, team color coding, keyboard navigation (Page Up/Down), schedule-driven progression, and a web control interface.

```bash
python display_event.py [options]
```

**Key options:**

| Flag | Default | Description |
|---|---|---|
| `--config-dir PATH` | `./config` | Configuration directory |
| `--file PATH` | from settings | Path to `lynx.evt` |
| `--colors-csv PATH` | from settings | Path to `colors.csv` |
| `--event NUM` | from `current_event.json` | Event number |
| `--round NUM` | from `current_event.json` | Round number |
| `--heat NUM` | from `current_event.json` | Heat number |
| `--font PATH` | from settings | BDF font file |
| `--width PIXELS` | `64` | Display width |
| `--height PIXELS` | `32` | Display height |
| `--line-height PIXELS` | `24` | Athlete row height |
| `--header-line-height PIXELS` | `16` | Header row height |
| `--header-rows N` | `2` | Number of header rows |
| `--interval SECONDS` | `2.0` | Seconds per page |
| `--once` | off | Render once and exit |
| `--chain N` | `2` | Horizontal panel count |
| `--parallel N` | `4` | Vertical panel count |
| `--gpio-slowdown N` | `3` | GPIO timing (0–4) |
| `--fpp` | off | Use FPP/DDP output |
| `--fpp-host HOST` | `127.0.0.1` | FPP receiver IP |
| `--fpp-port PORT` | `4048` | FPP port |
| `--colorlight` | off | Use ColorLight output |
| `--colorlight-interface NAME` | — | Network interface (e.g., `eth0`) |
| `--keyboard-device PATH` | auto | Keyboard input device |

**Examples:**

```bash
# Run with settings from config/settings.toml
python display_event.py

# Display specific event
python display_event.py --event 3 --round 2 --heat 1

# Use FPP network output
python display_event.py --fpp --fpp-host 192.168.1.100

# Use ColorLight direct Ethernet (requires sudo on Linux)
sudo python display_event.py --colorlight --colorlight-interface eth0

# Render once (useful for testing)
python display_event.py --once
```

**Keyboard controls** (Page Up/Down remote or USB keyboard):
- **Page Down** — next heat
- **Page Up** — previous heat
- **Period (`.`)** — reset to first heat

---

### udp_scoreboard.py

Displays a real-time event name and elapsed time on the LED panels, driven by UDP JSON messages from a timing system. The display is split into two regions: event name (top, red background) and elapsed time (bottom, black background).

```bash
python udp_scoreboard.py [options]
```

**UDP message format:**

```json
// Clear display
{"initialization": true}

// Set event name (resets time to "0.0")
{"startList": {"eventName": "100M Dash"}}

// Update running time
{"timeRunning": "42.1"}
```

**Key options:**

| Flag | Default | Description |
|---|---|---|
| `--port PORT` | `5568` | UDP port to listen on |
| `--width PIXELS` | `64` | Display width |
| `--height PIXELS` | `32` | Display height |
| `--top-font PATH` | from settings | BDF font for event name |
| `--bottom-font PATH` | from settings | BDF font for elapsed time |
| `--chain N` | `3` | Horizontal panel count |
| `--parallel N` | `2` | Vertical panel count |
| `--gpio-slowdown N` | `4` | GPIO timing (0–4) |
| `--fpp` | off | Use FPP/DDP output |
| `--fpp-host HOST` | — | FPP receiver IP |
| `--fpp-port PORT` | `4048` | FPP port |
| `--colorlight` | off | Use ColorLight output |
| `--colorlight-interface NAME` | — | Network interface |
| `--top-font-shift-vertical N` | `7` | Vertical offset for event name |
| `--bottom-font-shift-vertical N` | `15` | Vertical offset for time |
| `--bottom-font-shift-horizontal N` | `34` | Horizontal offset for time |

**Examples:**

```bash
# Listen on default port 5568
python udp_scoreboard.py

# Custom port with FPP output
python udp_scoreboard.py --port 6000 --fpp --fpp-host 192.168.1.50

# Send test messages (in a separate terminal)
python tools/test_scoreboard.py --port 5568
```

---

## Web Interface

`web_server.py` provides a Flask-based browser interface for remotely controlling the display. It starts automatically when `display_event.py` runs (if `web_enabled = true` in settings).

**Access:** `http://<raspberry-pi-ip>:5000`

**Pages:**

| URL | Description |
|---|---|
| `/` | Dashboard — current event selector, display settings |
| `/teams` | View and edit team colors from `colors.csv` |
| `/display` | Current display rendering info |

**Key API endpoints:**

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/events` | All events from `lynx.evt` |
| GET/POST | `/api/current_event` | Get or set current event/round/heat |
| GET/POST | `/api/teams` | Get or update team colors |
| GET/POST | `/api/display_settings` | Get or update display settings |
| POST | `/api/teams/add_missing` | Add teams from `lynx.evt` not in `colors.csv` |
| POST | `/api/upload/events` | Upload a new `lynx.evt` file |
| POST | `/api/upload/schedule` | Upload a new `lynx.sch` file |
| POST | `/api/upload/combined` | Upload `lynx.evt` and `lynx.sch` together |

See [API_DOCUMENTATION.md](API_DOCUMENTATION.md) for full request/response schemas.

---

## Utilities

All utilities live in `tools/` and are run from the project root.

### tools/

#### clear_display.py

Sends an all-black frame to the display. Useful before rebooting to avoid leaving a static image on the panels.

Dispatches on the backend enabled in `[network]` — ColorLight first, then FPP. Raw `rgbmatrix` hardware is owned by the display process and cannot be blanked from a separate process; with neither network backend enabled the script reports this and exits. Use the web UI's display power toggle instead.

```bash
sudo python tools/clear_display.py
sudo python tools/clear_display.py --config-dir /path/to/config
```

---

#### display_image.py

Displays a `.bmp` or `.png` image on the LED panels, automatically resizing it to the display dimensions. On Windows (no `rgbmatrix`), saves a preview PNG instead. Holds the image for one hour, then exits.

```bash
python tools/display_image.py --image logo.png
python tools/display_image.py --image logo.png --width 128 --height 32 --chain 2
python tools/display_image.py --image logo.png --out preview.png   # Save preview only
```

| Flag | Default | Description |
|---|---|---|
| `--image PATH` | required | Path to `.bmp` or `.png` |
| `--width PIXELS` | `64` | Display width |
| `--height PIXELS` | `32` | Display height |
| `--chain N` | `1` | Horizontal panel count |
| `--parallel N` | `1` | Vertical panel count |
| `--gpio-slowdown N` | `3` | GPIO timing |
| `--out FILENAME` | `output_preview.png` | Preview output path |

---

#### update_team_colors.py

Scans `lynx.evt` for team affiliations not present in `colors.csv` and appends them with default colors (black background, white text).

```bash
python tools/update_team_colors.py config/
```

#### fetch_team_colors.py

Scrapes team badge colors from athletic.net by team ID (requires `selenium` and ChromeDriver). Returns comma-separated hex colors.

```bash
pip install -r requirements-tools.txt
python tools/fetch_team_colors.py <team_id>
# Example: python tools/fetch_team_colors.py 318420
```

#### upload_events.py

Uploads `lynx.evt` and/or `lynx.sch` files to the web server API. Useful for pushing updated event files without SSH access.

```bash
# Upload events file
python tools/upload_events.py --server-url http://192.168.1.50:5000 \
  --events-file config/lynx.evt

# Upload both files together (recommended)
python tools/upload_events.py --server-url http://192.168.1.50:5000 \
  --events-file config/lynx.evt \
  --schedule-file config/lynx.sch \
  --combined
```

#### test_scoreboard.py

Sends a sequence of test UDP messages to `udp_scoreboard.py` — initialization, event name, and time updates — to verify the scoreboard is receiving correctly.

```bash
# Terminal 1: start scoreboard
python udp_scoreboard.py

# Terminal 2: send test messages
python tools/test_scoreboard.py --port 5568
```

#### test_udp.py

Generic UDP listener — prints all received data to stdout. Use for debugging messages from a timing system or other UDP source.

```bash
python tools/test_udp.py --port 5568
```

#### test_watcher.py

Tests the file watcher module by starting it and waiting for changes to files in `config/`. Prints a message each time a reload is triggered.

```bash
python tools/test_watcher.py
# Then modify config/current_event.json to trigger a reload
```

#### test_keyboard.py

Lists all `/dev/input/` devices and listens for key presses using `evdev`. Use to identify the correct keyboard device path for the `[keyboard]` config, or to debug why keyboard navigation isn't working.

```bash
sudo python tools/test_keyboard.py
```

---

### archive/

Retired scripts, kept for reference only. Not part of the running system and not
imported by anything:

| File | What it was |
|---|---|
| `archive/scroll.py`, `archive/scroll2.py` | Scrolling-text demos. Edit `TEXT`, `COLOR`, `FONT_PATH`, `SCROLL_SPEED` at the top of each file. |
| `archive/led_display.py` | Early two-row message + clock prototype. Superseded by `udp_scoreboard.py`. Hard-codes a `u8g2` font path that no longer exists. |
| `archive/keyboard_listener.py` | Standalone `pynput` key-name printer. Superseded by `tools/test_keyboard.py`. |

---

## Pi Systemd Service

The `pi/led-display.service` file configures `display_manager.py` to run automatically at boot. The manager hosts the web UI and starts whichever display mode is set in `[manager].active_mode`.

**Setup:**

```bash
# Copy service file (edit WorkingDirectory/ExecStart paths first if needed)
sudo cp pi/led-display.service /etc/systemd/system/

# Enable at boot and start now
sudo systemctl daemon-reload
sudo systemctl enable led-display
sudo systemctl start led-display
```

**Management commands:**

```bash
sudo systemctl status led-display        # Check if running
sudo systemctl stop led-display          # Stop the service
sudo systemctl restart led-display       # Restart after config changes
sudo journalctl -u led-display -f        # Follow live logs
sudo journalctl -u led-display -n 100    # View last 100 log lines
```

**Note:** The service runs as `root` (required for GPIO and raw Ethernet access). If you change the install path, update `WorkingDirectory` and `ExecStart` in the service file before copying it.
