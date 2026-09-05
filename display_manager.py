#!/usr/bin/env python3
"""
display_manager.py

Central process manager for LED display modes.

Launched by the systemd service (led-display.service) instead of any
individual display script.  Responsibilities:
  - Hosts the shared web UI / API on port 80
  - Starts the configured display mode as a child process
  - Monitors the child and restarts it on crash (if auto_restart=true)
  - Responds to mode-switch requests from the web UI by stopping the
    current child and starting the new one

Usage:
    python display_manager.py --config-dir ./config
"""

import argparse
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from config_loader import (
    ConfigError,
    VALID_MODES,
    ensure_config_directory,
    load_manager_config,
    load_mode_config,
    save_active_mode,
    save_mode_config,
)
from web_server import start_web_server

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Arg builders — each returns a list[str] of CLI args for the child script
# ---------------------------------------------------------------------------

def _build_display_event_args(config_dir: str) -> list:
    return ["--config-dir", config_dir, "--no-web"]


def _build_athletic_live_args(config_dir: str) -> list:
    from config_loader import load_settings
    cfg = load_mode_config(config_dir, "athletic_live_scoreboard")
    name = cfg.get("name", "").strip()
    uuid = cfg.get("uuid", "").strip()
    if not name or not uuid:
        raise ConfigError(
            "athletic_live_scoreboard requires 'name' and 'uuid' in "
            "[mode.athletic_live_scoreboard] settings"
        )
    args = ["--name", name, "--uuid", uuid]
    if "interval" in cfg:
        args += ["--interval", str(cfg["interval"])]
    if "font" in cfg:
        args += ["--font", cfg["font"]]
    args += ["--colors-csv", str(Path(config_dir) / "colors.csv")]

    # Mirror [hardware] and [network] from settings.toml — same values
    # that display_event.py uses so both scripts target the same panel.
    try:
        settings = load_settings(config_dir)
        hw = settings.get("hardware", {})
        if "height" in hw:
            args += ["--rows", str(hw["height"])]
        if "width" in hw:
            args += ["--cols", str(hw["width"])]
        if "chain" in hw:
            args += ["--chain", str(hw["chain"])]
        if "parallel" in hw:
            args += ["--parallel", str(hw["parallel"])]
        if "gpio_slowdown" in hw:
            args += ["--gpio-slowdown", str(hw["gpio_slowdown"])]

        net = settings.get("network", {})
        if net.get("colorlight_enabled", False):
            args += ["--colorlight"]
            if "colorlight_interface" in net:
                args += ["--colorlight-interface", net["colorlight_interface"]]
        elif net.get("fpp_enabled", False):
            args += ["--fpp"]
            if "fpp_host" in net:
                args += ["--fpp-host", net["fpp_host"]]
            if "fpp_port" in net:
                args += ["--fpp-port", str(net["fpp_port"])]
    except Exception as exc:
        log.warning("Could not read settings for athletic_live_scoreboard: %s", exc)

    return args


def _build_udp_scoreboard_args(config_dir: str) -> list:
    return ["--config-dir", config_dir]


def _build_animation_args(config_dir: str) -> list:
    cfg = load_mode_config(config_dir, "animation_display")
    animation_file = str(cfg.get("file", "")).strip()
    if not animation_file:
        raise ConfigError(
            "animation_display requires 'file' in [mode.animation_display] "
            "settings — upload a clip from the web UI and select it"
        )
    # Everything else (panel geometry, backend) comes from settings.toml, which
    # animation_display.py reads itself.
    args = ["--config-dir", config_dir, "--file", animation_file]
    if not cfg.get("loop", True):
        args += ["--no-loop"]
    return args


# ---------------------------------------------------------------------------
# Mode registry
# ---------------------------------------------------------------------------

MODES = {
    "display_event": {
        "script": "display_event.py",
        "build_args": _build_display_event_args,
        "label": "Event Display (Lynx)",
    },
    "athletic_live_scoreboard": {
        "script": "athletic_live_scoreboard.py",
        "build_args": _build_athletic_live_args,
        "label": "AthleticLIVE Field Scoreboard",
    },
    "udp_scoreboard": {
        "script": "udp_scoreboard.py",
        "build_args": _build_udp_scoreboard_args,
        "label": "UDP Scoreboard",
    },
    "animation_display": {
        "script": "animation_display.py",
        "build_args": _build_animation_args,
        "label": "Animation",
    },
}


# ---------------------------------------------------------------------------
# Display blanking helper
# ---------------------------------------------------------------------------

def _blank_display(config_dir: str) -> None:
    """Send an all-black frame to the configured hardware backend.

    Supports ColorLight and FPP backends.  Raw rgbmatrix is owned by the
    child process so it cannot be blanked from here; a warning is logged.
    """
    try:
        from config_loader import load_settings
        settings = load_settings(config_dir)
        hw = settings.get("hardware", {})
        net = settings.get("network", {})

        width = hw.get("width", 64) * hw.get("chain", 1)
        height = hw.get("height", 32) * hw.get("parallel", 1)

        if net.get("colorlight_enabled", False):
            from colorlight_output import ColorLightMatrix
            interface = net.get("colorlight_interface", "eth0")
            matrix = ColorLightMatrix(interface, width, height)
            matrix.Clear()
            matrix.SwapOnVSync(matrix)
            log.info("Display blanked via ColorLight")
        elif net.get("fpp_enabled", False):
            from fpp_output import FPPMatrix
            host = net.get("fpp_host", "127.0.0.1")
            port = int(net.get("fpp_port", 4048))
            matrix = FPPMatrix(host, port, width, height)
            matrix.Clear()
            matrix.SwapOnVSync(matrix)
            log.info("Display blanked via FPP")
        else:
            log.warning(
                "No network backend configured; cannot blank rgbmatrix hardware "
                "from the manager process"
            )
    except Exception as exc:
        log.warning("Could not blank display hardware: %s", exc)


# ---------------------------------------------------------------------------
# ModeProcess — manages a single child process lifecycle
# ---------------------------------------------------------------------------

class ModeProcess:
    """Wraps a subprocess.Popen for a display mode child."""

    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._mode: Optional[str] = None
        self._exit_code: Optional[int] = None
        self._lock = threading.Lock()

    def start(self, mode: str, config_dir: str) -> None:
        """Start the child process for *mode*."""
        with self._lock:
            self._stop_locked()

            entry = MODES[mode]
            try:
                extra_args = entry["build_args"](config_dir)
            except ConfigError as exc:
                log.error("Cannot start %s: %s", mode, exc)
                self._mode = mode
                self._exit_code = -1
                return

            cmd = [sys.executable, entry["script"]] + extra_args
            log.info("Starting mode %s: %s", mode, " ".join(cmd))

            try:
                self._proc = subprocess.Popen(
                    cmd,
                    cwd=str(Path(__file__).parent),
                )
                self._mode = mode
                self._exit_code = None
                log.info("Mode %s started (pid=%d)", mode, self._proc.pid)
            except Exception as exc:
                log.error("Failed to start %s: %s", mode, exc)
                self._proc = None
                self._mode = mode
                self._exit_code = -1

    def stop(self, timeout: float = 5.0) -> None:
        with self._lock:
            self._stop_locked(timeout)

    def _stop_locked(self, timeout: float = 5.0) -> None:
        """Stop child process; caller must hold self._lock."""
        if self._proc is None:
            return
        pid = self._proc.pid
        log.info("Stopping mode %s (pid=%d)…", self._mode, pid)
        self._proc.terminate()
        try:
            self._exit_code = self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            log.warning("Process %d did not exit after %.1fs, sending SIGKILL", pid, timeout)
            self._proc.kill()
            self._exit_code = self._proc.wait()
        log.info("Process %d exited with code %s", pid, self._exit_code)
        self._proc = None

    def poll(self) -> Optional[int]:
        """Return exit code if child has exited, None if still running."""
        with self._lock:
            if self._proc is None:
                return self._exit_code
            ret = self._proc.poll()
            if ret is not None:
                self._exit_code = ret
                self._proc = None
            return ret

    @property
    def status(self) -> dict:
        with self._lock:
            running = self._proc is not None
            pid = self._proc.pid if self._proc else None
            return {
                "mode": self._mode,
                "running": running,
                "pid": pid,
                "exit_code": self._exit_code if not running else None,
            }


# ---------------------------------------------------------------------------
# ManagerState — thread-safe shared state, passed to web server via callbacks
# ---------------------------------------------------------------------------

class ManagerState:
    def __init__(self, config_dir: str, proc: ModeProcess):
        self._config_dir = config_dir
        self._proc = proc
        self._lock = threading.Lock()
        cfg = load_manager_config(config_dir)
        self._active_mode: str = cfg["active_mode"]
        self._power_on: bool = True

    # -- display power -------------------------------------------------------

    def get_display_power(self) -> bool:
        with self._lock:
            return self._power_on

    def set_display_power(self, state: bool) -> None:
        """Turn the display on (True) or off (False).

        Power-off stops the child process then blanks the hardware.
        Power-on restarts the child process for the current active mode.
        """
        with self._lock:
            self._power_on = state
        if state:
            mode = self.get_active_mode()
            log.info("Display power on — starting mode %s", mode)
            self._proc.start(mode, self._config_dir)
        else:
            log.info("Display power off — stopping child process")
            self._proc.stop()
            _blank_display(self._config_dir)

    # -- mode access ---------------------------------------------------------

    def get_active_mode(self) -> str:
        with self._lock:
            return self._active_mode

    def set_active_mode(self, mode: str) -> None:
        """Persist mode change and restart the child process."""
        if mode not in VALID_MODES:
            raise ConfigError(f"Unknown mode '{mode}'")
        with self._lock:
            if mode == self._active_mode:
                log.info("Mode already %s, restarting…", mode)
            else:
                log.info("Switching mode %s → %s", self._active_mode, mode)
            self._active_mode = mode
        save_active_mode(self._config_dir, mode)
        # Restart outside the lock to avoid blocking status reads
        self._proc.start(mode, self._config_dir)

    def get_mode_status(self) -> dict:
        return self._proc.status

    def get_mode_config(self, mode: str) -> dict:
        return load_mode_config(self._config_dir, mode)

    def set_mode_config(self, mode: str, values: dict) -> None:
        """Persist mode settings. If it is the active mode, restart child."""
        save_mode_config(self._config_dir, mode, values)
        with self._lock:
            active = self._active_mode
        if mode == active:
            log.info("Mode settings updated for active mode %s — restarting", mode)
            self._proc.start(mode, self._config_dir)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="LED Display Manager")
    parser.add_argument("--config-dir", default="./config",
                        help="Path to configuration directory (default: ./config)")
    args = parser.parse_args()
    config_dir = args.config_dir

    try:
        ensure_config_directory(config_dir)
    except ConfigError as exc:
        log.error("Configuration error: %s", exc)
        sys.exit(1)

    mgr_cfg = load_manager_config(config_dir)
    auto_restart: bool = mgr_cfg.get("auto_restart", True)
    restart_backoff: float = float(mgr_cfg.get("restart_backoff_sec", 5))

    proc = ModeProcess()
    state = ManagerState(config_dir, proc)

    # -- Web server ----------------------------------------------------------
    from config_loader import load_settings
    try:
        settings = load_settings(config_dir)
        web_cfg = settings.get("web", {})
        web_enabled = web_cfg.get("web_enabled", True)
        web_host = web_cfg.get("web_host", "0.0.0.0")
        web_port = web_cfg.get("web_port", 80)
    except ConfigError:
        web_enabled = True
        web_host = "0.0.0.0"
        web_port = 80

    if web_enabled:
        start_web_server(
            config_dir,
            web_host,
            web_port,
            get_display_power=state.get_display_power,
            set_display_power=state.set_display_power,
            get_active_mode=state.get_active_mode,
            set_active_mode=state.set_active_mode,
            get_mode_status=state.get_mode_status,
            get_mode_config=state.get_mode_config,
            set_mode_config=state.set_mode_config,
            available_modes={k: {"label": v["label"]} for k, v in MODES.items()},
        )
        log.info("Web interface available at http://%s:%d", web_host, web_port)

    # -- Signal handling -----------------------------------------------------
    shutdown_event = threading.Event()

    def _handle_signal(sig, _frame):
        log.info("Received signal %s, shutting down…", sig)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # -- Start active mode ---------------------------------------------------
    active_mode = state.get_active_mode()
    log.info("Starting active mode: %s", active_mode)
    proc.start(active_mode, config_dir)

    # -- Monitor loop --------------------------------------------------------
    log.info("Manager running. Press Ctrl-C or send SIGTERM to stop.")
    while not shutdown_event.is_set():
        exit_code = proc.poll()
        if exit_code is not None:
            current_mode = state.get_active_mode()
            log.warning("Mode %s exited with code %s", current_mode, exit_code)
            if auto_restart and not shutdown_event.is_set() and state.get_display_power():
                log.info("Auto-restarting %s in %.0fs…", current_mode, restart_backoff)
                # Sleep in small increments so SIGTERM wakes us promptly
                deadline = time.monotonic() + restart_backoff
                while time.monotonic() < deadline and not shutdown_event.is_set():
                    time.sleep(0.25)
                if not shutdown_event.is_set() and state.get_display_power():
                    proc.start(current_mode, config_dir)
        time.sleep(0.5)

    # -- Graceful shutdown ---------------------------------------------------
    log.info("Stopping child process…")
    proc.stop()
    log.info("Manager stopped.")


if __name__ == "__main__":
    main()
