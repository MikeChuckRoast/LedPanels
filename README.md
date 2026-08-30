# LED Panels

Drives RGB LED panels at track meets. One manager process hosts a web UI and
runs one of three display modes: a Lynx starting roster, an AthleticLIVE field
scoreboard, or a UDP-driven event clock. Output goes to Raspberry Pi GPIO, a
ColorLight 5A-75B Ethernet controller, or an FPP/DDP receiver.

## Table of Contents

- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Display Modes](#display-modes)
  - [display_event — starting roster](#display_event--starting-roster)
  - [athletic_live_scoreboard — field scoreboard](#athletic_live_scoreboard--field-scoreboard)
  - [udp_scoreboard — event clock](#udp_scoreboard--event-clock)
- [Configuration](#configuration)
- [Web Interface](#web-interface)
- [Pi Systemd Service](#pi-systemd-service)
- [Utilities](#utilities)
- [Further Documentation](#further-documentation)

---

## Architecture

[`display_manager.py`](display_manager.py) is the entry point. It is what the
systemd service starts, and it is the only process you normally launch by hand.

```
display_manager.py
├── web_server.py ................ Flask UI + REST API on port 5000
└── one child process, restarted on crash and on mode switch:
    ├── display_event.py .................. Lynx starting roster
    ├── athletic_live_scoreboard.py ....... AthleticLIVE field scoreboard
    └── udp_scoreboard.py ................. UDP-driven event clock
```

The manager owns the web server; the child owns the panel. Switching modes stops
the child, persists `[manager].active_mode` to `settings.toml`, and starts the
new one. If a child exits and `auto_restart` is on, the manager restarts it after
`restart_backoff_sec`.

The child modes are ordinary scripts and can be run standalone for debugging —
just don't run one alongside the manager, or two processes will fight over the
panel and port 5000.

Shared modules: [`config_loader.py`](config_loader.py) (settings and validation),
[`event_parser.py`](event_parser.py) (Lynx `.evt` parsing, team colours),
[`schedule_parser.py`](schedule_parser.py) (`.sch` heat progression),
[`display_utils.py`](display_utils.py) (text layout, BDF metrics),
[`matrix_backend.py`](matrix_backend.py) (backend selection),
[`colorlight_output.py`](colorlight_output.py) and
[`fpp_output.py`](fpp_output.py) (the two network backends), and
[`file_watcher.py`](file_watcher.py) (config hot-reload).

---

## Quick Start

```bash
pip install -r requirements.txt          # or requirements-pi.txt on a Pi

cp config/settings.toml.example config/settings.toml
# edit [fonts].font_path to the absolute path of this repo's fonts/ directory

python display_manager.py --config-dir ./config
```

Then open `http://localhost:5000` — or `http://<pi-ip>:5000` from another
machine — and pick a display mode.

On a Pi with ColorLight or direct GPIO output, prefix with `sudo`.

---

## Installation

**Python 3.11+** is required for the stdlib `tomllib`.

### Windows / macOS (development)

Hardware packages (`evdev`, `rgbmatrix`) are not installed. The display falls
back to `RGBMatrixEmulator` if present, or FPP output over the network.

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt      # pytest and friends, optional
```

```bash
copy config\settings.toml.example config\settings.toml
copy config\current_event.json.example config\current_event.json
```

Set `font_path` under `[fonts]` to an absolute path:

```toml
[fonts]
font_path = "C:/Users/mike/Documents/Code Projects/LED Panels/fonts"
font_name = "helvB14.bdf"
```

### Raspberry Pi (production)

```bash
pip install -r requirements-pi.txt       # includes requirements.txt plus evdev, rgbmatrix
```

Or system-wide via apt:

```bash
sudo apt install python3-flask python3-watchdog python3-pillow \
                 python3-tomli-w python3-evdev
```

```bash
cp config/settings.toml.pi config/settings.toml       # Pi font path, ColorLight enabled
cp config/current_event.json.example config/current_event.json
```

Root is required for GPIO and for ColorLight's raw Ethernet sockets.

---

## Display Modes

All three read `config/settings.toml` for hardware and network settings, so the
manager passes each only what it cannot infer. Every mode accepts the backend
overrides described in [docs/BACKENDS.md](docs/BACKENDS.md).

### display_event — starting roster

Shows athletes for the current event/round/heat from a Lynx `.evt` file, paging
through them on an interval, colour-coded by team affiliation. Supports keyboard
navigation, schedule-driven progression, and live reload when config files change.

```bash
python display_event.py [options]
```

| Flag | Default | Description |
|---|---|---|
| `--config-dir PATH` | `./config` | Configuration directory |
| `--file PATH` | from settings | Path to `lynx.evt` |
| `--colors-csv PATH` | from settings | Path to `colors.csv` |
| `--event` / `--round` / `--heat NUM` | from `current_event.json` | Position to display |
| `--font PATH` | from settings | BDF font file |
| `--width` / `--height PIXELS` | `64` / `32` | Single panel dimensions |
| `--chain` / `--parallel N` | `2` / `4` | Panels horizontally / vertically |
| `--line-height PIXELS` | `24` | Athlete row height |
| `--header-line-height PIXELS` | `16` | Header row height |
| `--header-rows N` | `2` | Header rows, for wrapping long event names |
| `--interval SECONDS` | `2.0` | Seconds per page |
| `--once` | off | Render once and exit |
| `--no-web` | off | Skip the internal web server (set by the manager) |
| `--keyboard-device PATH` | auto-detect | Input device for navigation |
| `--gpio-slowdown N` | `3` | GPIO timing, 0–4 |

**Keyboard controls** (USB keyboard or presentation remote):

- **Page Down** — next heat
- **Page Up** — previous heat
- **Period (`.`)** — reset to the reference heat

```bash
python display_event.py                          # settings.toml defaults
python display_event.py --event 3 --round 2 --heat 1
python display_event.py --once                   # single render, useful for testing
```

### athletic_live_scoreboard — field scoreboard

Polls a [sb.athletic.live](https://sb.athletic.live) field-event scoreboard and
displays the current athlete, attempt number, and distance. It fetches the board
config from `fieldappapi.athletic.live` to resolve meet and event IDs, then polls
the Firebase Realtime Database for the latest mark.

`--name` and `--uuid` are required, and both come from the scoreboard URL:

```
https://sb.athletic.live/$web/boards/src/scoreboards/fieldResult/index.html
    ?name=FUSHIABOX&uuid=dc4113ed-50f3-424d-ae9c-02f0745d7285&...
```

```bash
python athletic_live_scoreboard.py --name FUSHIABOX --uuid dc4113ed-...
```

| Flag | Default | Description |
|---|---|---|
| `--name NAME` | **required** | Scoreboard computer name from the URL |
| `--uuid UUID` | **required** | Scoreboard UUID from the URL |
| `--interval SECONDS` | `5.0` | Poll interval |
| `--rows` / `--cols N` | `32` / `64` | Single panel dimensions |
| `--chain` / `--parallel N` | `2` / `4` | Panels horizontally / vertically |
| `--font PATH` | `fonts/helvB14.bdf` | BDF font |
| `--colors-csv PATH` | `config/colors.csv` | Team colours |
| `--gpio-slowdown N` | `3` | GPIO timing |

Set `name` and `uuid` under `[mode.athletic_live_scoreboard]` in `settings.toml`
(or in the web UI) so the manager can launch it. Without them the manager logs a
config error and the mode will not start.

Note that this mode's panel geometry comes from `[hardware]`, which the manager
mirrors onto the command line — it does not read `settings.toml` itself.

### udp_scoreboard — event clock

Listens for UDP JSON messages from a timing system and shows an event name over
a large elapsed-time readout. The panel is split into two regions: event name on
top (red background), running time below (black).

```bash
python udp_scoreboard.py --config-dir ./config
```

Message format:

```jsonc
{"initialization": true}                          // clear the display
{"startList": {"eventName": "100M Dash"}}         // set event name, reset time to 0.0
{"timeRunning": "42.1"}                           // update running time
```

This mode reads its own geometry and fonts from the `[scoreboard]` section
rather than `[hardware]`, so it can use a different panel arrangement than the
other two. Anything in that section can be overridden on the command line
(`--port`, `--top-font`, `--bottom-font`, `--top-font-shift-vertical`,
`--bottom-font-shift-horizontal`, and so on — see `--help`).

Send test traffic with `python tools/test_scoreboard.py --port 5568`.

---

## Configuration

Everything lives in `config/`. `settings.toml` is the main file; copy it from
`settings.toml.example` (or `settings.toml.pi` on a Pi). If it is missing,
`ensure_config_directory()` writes a default one on first run, along with
`current_event.json`.

CLI arguments override file values, which override built-in defaults.

### settings.toml sections

| Section | Purpose |
|---|---|
| `[hardware]` | Panel geometry for `display_event` and `athletic_live_scoreboard` |
| `[display]` | Row heights, header rows, page interval, font shift |
| `[fonts]` | Absolute path to the BDF font directory, plus default font name |
| `[files]` | `lynx_file` and `colors_file`, relative to the config directory |
| `[network]` | Backend selection — see [docs/BACKENDS.md](docs/BACKENDS.md) |
| `[keyboard]` | Input device path; empty means auto-detect |
| `[behavior]` | `once` mode |
| `[monitoring]` | File watching and poll interval |
| `[web]` | Web UI enable, host, port |
| `[scoreboard]` | Everything `udp_scoreboard` needs — its own geometry and fonts |
| `[manager]` | `active_mode`, `auto_restart`, `restart_backoff_sec` |
| `[mode.*]` | Per-mode settings; only `athletic_live_scoreboard` has any |

```toml
[hardware]
width = 64          # single panel width
height = 32         # single panel height
chain = 2           # panels chained horizontally
parallel = 4        # panels stacked vertically
gpio_slowdown = 3   # 0–4; raise if the display is glitchy

[display]
line_height = 24
header_line_height = 16
header_rows = 2
interval = 2.0
font_shift = 0

[fonts]
font_path = "/home/mike/LedPanels/fonts"
font_name = "helvB14.bdf"

[web]
web_enabled = true
web_host = "0.0.0.0"      # 127.0.0.1 to restrict to the Pi itself
web_port = 5000

[manager]
active_mode = "athletic_live_scoreboard"
auto_restart = true
restart_backoff_sec = 5

[mode.athletic_live_scoreboard]
name = "FUSHIABOX"
uuid = "dc4113ed-50f3-424d-ae9c-02f0745d7285"
interval = 10
font = "fonts/helvB14.bdf"
```

Bundled fonts in `fonts/`: `helvB14.bdf`, `helvB18.bdf`, `helvB24.bdf`,
`Roboto-Black-50.bdf`.

### Data files

**`config/current_event.json`** — the currently displayed position, updated by
keyboard navigation, the web UI, and schedule progression:

```json
{"event": 1, "round": 1, "heat": 1}
```

**`config/colors.csv`** — team affiliation to display colour:

```
affiliation_name,display_name,background_hex,text_hex
DDCM,Desert Dogs,#0066CC,#FFFFFF
SCVT,Sac Valley,#FFCC00,#000000
```

Teams present in `lynx.evt` but missing here fall back to dark grey. Fill the
gaps with `python tools/update_team_colors.py config/` or the web UI's
"add missing" button.

**`config/lynx.evt`** — event data exported from the Lynx timing system.
**`config/lynx.sch`** — schedule file for automatic heat progression.

### Version control

Tracked: `settings.toml.example`, `settings.toml.pi`,
`current_event.json.example`, `lynx.sch.example`, `colors.csv`.
Gitignored: `settings.toml` (local paths), `current_event.json` (runtime state),
`lynx.evt` (meet data).

### Troubleshooting

| Message | Fix |
|---|---|
| `Settings file not found` | Copy an example file into place, or let the first run create defaults. |
| `Invalid TOML` | Quote strings, leave numbers bare, comment with `#` not `//`. |
| `Font file not found` | `font_path` must be an absolute path to the directory holding the `.bdf` files. |
| `Lynx event file not found` | Put `lynx.evt` in the config directory, or point `[files].lynx_file` at it. |
| `requires 'name' and 'uuid'` | Fill in `[mode.athletic_live_scoreboard]` before selecting that mode. |

---

## Web Interface

[`web_server.py`](web_server.py) serves a Flask UI and REST API, started by the
manager on port 5000. There is **no authentication** — keep it on a trusted
network, or bind `web_host` to `127.0.0.1`.

| URL | Purpose |
|---|---|
| `/` | Dashboard — mode switching, display power, event selection, AthleticLIVE settings |
| `/teams` | Team colour editor backed by `colors.csv` |
| `/display` | Display layout settings |

The mode-switching section only appears when running under `display_manager.py`.
Launch a mode script directly and the manager endpoints return HTTP 501, so the
UI hides that section.

### Key endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/events` | All events parsed from `lynx.evt` |
| GET/POST | `/api/current_event` | Get or set event/round/heat |
| GET/POST | `/api/teams` | Get or update team colours |
| POST | `/api/teams/add_missing` | Append teams found in `lynx.evt` but absent from `colors.csv` |
| GET/POST | `/api/display_settings` | Get or update the `[display]` section |
| GET/POST | `/api/display_power` | Read or set display power (see below) |
| GET | `/api/display_modes` | Available modes and their labels |
| GET/POST | `/api/active_mode` | Read or switch the active mode |
| GET | `/api/mode_status` | Child process state — running, pid, exit code |
| GET/POST | `/api/mode_settings/<mode>` | Read or update a `[mode.*]` section |
| POST | `/api/upload/events` | Upload a new `lynx.evt` |
| POST | `/api/upload/schedule` | Upload a new `lynx.sch` |
| POST | `/api/upload/combined` | Upload both together (preferred — keeps them consistent) |

Full request and response schemas are in
[docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md).

### Display power

Powering off stops the child process and blanks the panel. Blanking only works
on the network backends — with direct `rgbmatrix` the child owns the hardware,
so the manager logs a warning and the panel keeps its last frame. Powering on
restarts the active mode.

### How changes reach the display

Most settings travel through files rather than IPC:

```
Browser → Flask → config files → file watcher → display reloads
```

Changes land within a second or two. Mode switches and mode settings are the
exception — those restart the child process directly.

---

## Pi Systemd Service

[`pi/led-display.service`](pi/led-display.service) runs `display_manager.py` at
boot as root, which is required for GPIO and raw Ethernet.

```bash
sudo cp pi/led-display.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable led-display
sudo systemctl start led-display
```

```bash
sudo systemctl status led-display
sudo systemctl restart led-display        # after config changes
sudo journalctl -u led-display -f         # follow logs
```

The unit hardcodes `/home/mike/LedPanels`. Update `WorkingDirectory` and
`ExecStart` if you install elsewhere.

Note that both systemd (`Restart=always`) and the manager (`auto_restart`)
restart things. Systemd restarts the manager; the manager restarts the display
mode. A mode that crashes on startup will loop every `restart_backoff_sec`
seconds — check `journalctl` rather than assuming the display is merely blank.

---

## Utilities

Everything in `tools/` is run from the project root.

| Script | Purpose |
|---|---|
| `tools/clear_display.py` | Send an all-black frame. Dispatches on the enabled `[network]` backend; with neither enabled it reports that raw `rgbmatrix` cannot be blanked externally and exits. |
| `tools/display_image.py` | Show a `.bmp`/`.png`, resized to the panel. Without `rgbmatrix` it saves a preview PNG instead. Holds for an hour, then exits. |
| `tools/update_team_colors.py` | Append affiliations found in `lynx.evt` but missing from `colors.csv`, with default colours. |
| `tools/fetch_team_colors.py` | Scrape team badge colours from athletic.net by team ID. Needs `requirements-tools.txt` and ChromeDriver. |
| `tools/upload_events.py` | Push `lynx.evt` / `lynx.sch` to a running web server without SSH. |
| `tools/test_scoreboard.py` | Send a scripted UDP sequence to `udp_scoreboard.py`. |
| `tools/test_udp.py` | Generic UDP listener; prints whatever arrives. |
| `tools/test_watcher.py` | Exercise the file watcher and log each reload it triggers. |
| `tools/test_colorlight_frames.py` | Send known frame patterns to a ColorLight card to debug ordering and timing. |
| `tools/test_keyboard.py` | List `/dev/input/` devices and print key presses; use it to find `[keyboard].device_path`. |

```bash
sudo python tools/clear_display.py
python tools/display_image.py --image logo.png --out preview.png
python tools/update_team_colors.py config/
python tools/upload_events.py --server-url http://192.168.1.50:5000 \
  --events-file config/lynx.evt --schedule-file config/lynx.sch --combined
sudo python tools/test_keyboard.py
```

### archive/

Retired scripts, kept for reference. Nothing imports them and they are not part
of the running system:

| File | What it was |
|---|---|
| `archive/scroll.py`, `archive/scroll2.py` | Scrolling-text demos. Edit `TEXT`, `COLOR`, `FONT_PATH`, `SCROLL_SPEED` at the top. |
| `archive/led_display.py` | Early message + clock prototype, superseded by `udp_scoreboard.py`. Hard-codes a `u8g2` font path that no longer exists. |
| `archive/keyboard_listener.py` | Standalone `pynput` key printer, superseded by `tools/test_keyboard.py`. |

---

## Further Documentation

| Document | Contents |
|---|---|
| [docs/BACKENDS.md](docs/BACKENDS.md) | ColorLight and FPP setup, selection precedence, performance, troubleshooting |
| [docs/PROTOCOL_NOTES.md](docs/PROTOCOL_NOTES.md) | ColorLight 5A-75B wire protocol — frame layout, ordering, cold-boot priming |
| [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md) | Full HTTP API reference with request/response schemas |
| [docs/NETWORK_MANAGEMENT.md](docs/NETWORK_MANAGEMENT.md) | Raspberry Pi WiFi, interface, and mDNS/hostname management |
| [tests/README.md](tests/README.md) | Running the test suite, fixtures, writing new tests |

Run the tests with `pytest` from the project root.
