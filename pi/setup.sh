#!/usr/bin/env bash
#
# Set up (or update) the Python environment for the LED display on a Raspberry Pi.
#
# Raspberry Pi OS Bookworm marks the system Python as externally managed
# (PEP 668), so `pip install` into it is refused. Anything this project needs
# that Debian does not package — pynput, current Flask, tomli_w — lives in the
# virtual environment created here.
#
# The venv is created with --system-site-packages, so apt-installed modules
# (python3-evdev and friends) stay visible and pip only fetches what is
# genuinely missing. Isolation is not the goal; a writable install target is.
#
# Run as root: the service runs as root for raw Ethernet access, so the venv it
# executes must be root-owned. A venv writable by an unprivileged user but run
# by root would let that user execute code as root.
#
# Usage:
#   sudo pi/setup.sh                    Create the venv, install deps, seed config
#   sudo pi/setup.sh --install-service  ...and install and enable the systemd unit
#   sudo pi/setup.sh --update           Reinstall deps only, after a git pull
#   sudo pi/setup.sh --recreate         Rebuild the venv from scratch

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
VENV_PY="$VENV_DIR/bin/python"
CONFIG_DIR="$REPO_ROOT/config"
SERVICE_SRC="$REPO_ROOT/pi/led-display.service"
SERVICE_DST="/etc/systemd/system/led-display.service"

INSTALL_SERVICE=0
RECREATE=0
UPDATE_ONLY=0

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '\033[33m    warning: %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[31merror: %s\033[0m\n' "$*" >&2; exit 1; }

usage() {
    cat <<'USAGE'
Set up (or update) the Python environment for the LED display on a Raspberry Pi.

  sudo pi/setup.sh                    Create the venv, install deps, seed config
  sudo pi/setup.sh --install-service  ...and install and enable the systemd unit
  sudo pi/setup.sh --update           Reinstall deps only, after a git pull
  sudo pi/setup.sh --recreate         Rebuild the venv from scratch
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        --install-service) INSTALL_SERVICE=1 ;;
        --update)          UPDATE_ONLY=1 ;;
        --recreate)        RECREATE=1 ;;
        -h|--help)         usage; exit 0 ;;
        *)                 usage >&2; die "unknown option: $1" ;;
    esac
    shift
done

# ---------------------------------------------------------------- preflight --

[ "$(uname -s)" = "Linux" ] || die "this script targets Raspberry Pi OS; on Windows or macOS just use 'pip install -r requirements.txt'"
[ "$(id -u)" -eq 0 ] || die "run with sudo — the venv must be root-owned because the service runs as root"

command -v python3 >/dev/null || die "python3 not found"

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    die "Python 3.11+ required (this project uses the stdlib tomllib), found $(python3 -V 2>&1)"
fi

# Debian splits these out: `venv` usually imports fine while `ensurepip` is the
# piece that is actually absent, and `python3 -m venv` then fails partway through.
if ! python3 -c 'import venv, ensurepip' 2>/dev/null; then
    die "Python's venv support is incomplete — install it with: sudo apt install python3-full"
fi

info "repository:  $REPO_ROOT"
info "interpreter: $(python3 -V 2>&1)"

# --------------------------------------------------------------------- venv --

if [ "$RECREATE" -eq 1 ] && [ -d "$VENV_DIR" ]; then
    say "Removing existing virtual environment"
    rm -rf "$VENV_DIR"
fi

if [ -d "$VENV_DIR" ]; then
    if [ "$UPDATE_ONLY" -eq 0 ]; then
        info "virtual environment already present, reusing it"
    fi
    # A venv hard-links to the interpreter it was built from. An OS upgrade that
    # moves Python to a new minor version leaves it pointing at nothing.
    if [ ! -x "$VENV_PY" ]; then
        die "$VENV_PY is missing or not executable — the system Python likely changed version. Re-run with --recreate"
    fi
else
    [ "$UPDATE_ONLY" -eq 0 ] || die "no virtual environment at $VENV_DIR — run without --update first"
    say "Creating virtual environment at $VENV_DIR"
    python3 -m venv --system-site-packages "$VENV_DIR"
fi

say "Installing dependencies"
"$VENV_PY" -m pip install --upgrade pip
"$VENV_PY" -m pip install -r "$REPO_ROOT/requirements-pi.txt"

# ------------------------------------------------------------------- config --

if [ "$UPDATE_ONLY" -eq 0 ]; then
    say "Seeding configuration"

    if [ -f "$CONFIG_DIR/settings.toml" ]; then
        info "settings.toml exists, leaving it alone"
        grep -q "^font_path = \"$REPO_ROOT/fonts\"" "$CONFIG_DIR/settings.toml" \
            || warn "[fonts].font_path does not point at $REPO_ROOT/fonts — check it by hand"
    else
        cp "$CONFIG_DIR/settings.toml.pi" "$CONFIG_DIR/settings.toml"
        # The template hardcodes /home/mike/LedPanels; point it at the real checkout.
        sed -i "s|^font_path = .*|font_path = \"$REPO_ROOT/fonts\"|" "$CONFIG_DIR/settings.toml"
        info "created settings.toml from settings.toml.pi (font_path -> $REPO_ROOT/fonts)"
    fi

    if [ -f "$CONFIG_DIR/current_event.json" ]; then
        info "current_event.json exists, leaving it alone"
    else
        cp "$CONFIG_DIR/current_event.json.example" "$CONFIG_DIR/current_event.json"
        info "created current_event.json"
    fi
fi

# ------------------------------------------------------------------ service --

if [ "$INSTALL_SERVICE" -eq 1 ]; then
    say "Installing systemd service"
    # The unit ships with /home/mike/LedPanels baked in so it can be copied
    # directly; rewrite it here for whatever path this checkout actually lives at.
    sed "s|/home/mike/LedPanels|$REPO_ROOT|g" "$SERVICE_SRC" > "$SERVICE_DST"
    systemctl daemon-reload
    systemctl enable led-display
    info "installed to $SERVICE_DST and enabled at boot"
    info "start it with: sudo systemctl start led-display"
fi

# ------------------------------------------------------------------- verify --

say "Verifying"
"$VENV_PY" - <<'PY'
import importlib.util
import sys

required = ["flask", "watchdog", "PIL", "tomli_w", "requests", "tomllib"]
missing = [m for m in required if importlib.util.find_spec(m) is None]
if missing:
    print("    MISSING: " + ", ".join(missing))
    sys.exit(1)
print("    core dependencies OK: " + ", ".join(required))

# Optional. evdev drives keyboard heat navigation in display_event; without it
# that falls back to pynput, which needs an X server and so is useless headless.
if importlib.util.find_spec("evdev") is None:
    print("    evdev not found — keyboard navigation disabled.")
    print("    Install with: sudo apt install python3-evdev")
else:
    print("    evdev OK: keyboard navigation available")
PY

say "Done"
info "Run manually:   sudo $VENV_PY $REPO_ROOT/display_manager.py --config-dir $CONFIG_DIR"

if [ "$INSTALL_SERVICE" -eq 1 ]; then
    info "Or as service:  sudo systemctl start led-display"
elif [ -f "$SERVICE_DST" ]; then
    info "Or as service:  sudo systemctl restart led-display"
else
    warn "the systemd service is not installed; 'systemctl start led-display' will report"
    warn "'Unit led-display.service not found'. Install it with:"
    warn "    sudo pi/setup.sh --install-service"
fi

IP_ADDR="$(hostname -I 2>/dev/null | awk '{print $1}')"
info "Web UI:         http://${IP_ADDR:-<pi-ip>}:5000"
