"""
File watcher for automatic reload of event data files.

Monitors config directory for changes to:
- lynx.evt (event timing data)
- current_event.json (current event selection)
- colors.csv (team color mappings)

Uses watchdog library for cross-platform file system monitoring.
Debounces changes to handle multiple rapid writes.
"""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    logging.warning("watchdog library not available - file watching disabled")


class ConfigFileHandler(FileSystemEventHandler):
    """Handler for config file change events."""

    def __init__(self, reload_callback):
        """Initialize handler.

        Args:
            reload_callback: Function to call when reload should be triggered
        """
        super().__init__()
        self.reload_callback = reload_callback
        self.debounce_timer: Optional[threading.Timer] = None
        self.lock = threading.Lock()

    def should_monitor_file(self, file_path: str) -> bool:
        """Check if file should trigger reload.

        Args:
            file_path: Path to file that changed

        Returns:
            True if file should trigger reload
        """
        # Monitor these files (case-insensitive on Windows)
        basename = os.path.basename(file_path).lower()
        return basename in ['lynx.evt', 'current_event.json', 'colors.csv']

    def on_modified(self, event: FileSystemEvent):
        """Handle file modification event.

        Args:
            event: File system event
        """
        if event.is_directory:
            return

        if self.should_monitor_file(event.src_path):
            logging.debug(f"File modified: {event.src_path}")
            self.debounce_reload(event.src_path)

    def on_moved(self, event: FileSystemEvent):
        """Handle file move/rename event (e.g., atomic write pattern).

        Args:
            event: File system event with src_path and dest_path
        """
        if event.is_directory:
            return

        # Check destination path for atomic writes (temp -> final)
        if hasattr(event, 'dest_path') and self.should_monitor_file(event.dest_path):
            logging.debug(f"File moved to: {event.dest_path}")
            self.debounce_reload(event.dest_path)

    def on_created(self, event: FileSystemEvent):
        """Handle file creation event.

        Args:
            event: File system event
        """
        if event.is_directory:
            return

        if self.should_monitor_file(event.src_path):
            logging.debug(f"File created: {event.src_path}")
            self.debounce_reload(event.src_path)

    def debounce_reload(self, file_path: str):
        """Debounce reload requests to handle multiple rapid changes.

        Uses a cancellable timer that resets on each change. Only triggers
        reload if file has been stable for the debounce period.

        Args:
            file_path: Path to file that changed
        """
        with self.lock:
            # Cancel existing timer if any
            if self.debounce_timer is not None:
                self.debounce_timer.cancel()

            # Start new timer
            self.debounce_timer = threading.Timer(0.5, self.trigger_reload, args=(file_path,))
            self.debounce_timer.daemon = True
            self.debounce_timer.start()

    def trigger_reload(self, file_path: str):
        """Trigger the reload callback after debounce period.

        Args:
            file_path: Path to file that changed
        """
        logging.info(f"File change detected: {os.path.basename(file_path)} - reload requested")
        self.reload_callback()


class PollingFileWatcher:
    """Fallback file watcher using polling (no watchdog dependency)."""

    def __init__(self, config_dir: str, reload_callback):
        """Initialize polling watcher.

        Args:
            config_dir: Directory to watch
            reload_callback: Function to call when reload should be triggered
        """
        self.config_dir = Path(config_dir)
        self.reload_callback = reload_callback
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # Track modification times
        self.file_mtimes = {}
        for filename in ['lynx.evt', 'current_event.json', 'colors.csv']:
            file_path = self.config_dir / filename
            if file_path.exists():
                try:
                    self.file_mtimes[str(file_path)] = file_path.stat().st_mtime
                except OSError:
                    pass

    def start(self):
        """Start the polling thread."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        logging.info("Started polling file watcher (1 second interval)")

    def stop(self):
        """Stop the polling thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)

    def _poll_loop(self):
        """Main polling loop."""
        while self.running:
            time.sleep(1.0)  # Poll interval

            for file_path in list(self.file_mtimes.keys()):
                try:
                    current_mtime = Path(file_path).stat().st_mtime
                    last_mtime = self.file_mtimes[file_path]

                    if current_mtime > last_mtime:
                        self.file_mtimes[file_path] = current_mtime
                        # Simple debounce: wait a bit before triggering
                        time.sleep(0.3)
                        logging.info(f"File change detected: {os.path.basename(file_path)} - reload requested")
                        self.reload_callback()
                        break  # Only reload once per poll

                except OSError:
                    # File might be temporarily inaccessible
                    pass


def start_file_watcher(config_dir: str, reload_callback, use_polling: bool = False):
    """Start file watcher for config directory.

    Args:
        config_dir: Path to config directory to watch
        reload_callback: Function to call when files change (no arguments)
        use_polling: Force use of polling instead of watchdog

    Returns:
        Observer or PollingFileWatcher instance (with start() called)
        None if watcher could not be started
    """
    if not use_polling and WATCHDOG_AVAILABLE:
        try:
            # Use watchdog for event-driven monitoring
            event_handler = ConfigFileHandler(reload_callback)
            observer = Observer()
            observer.schedule(event_handler, config_dir, recursive=False)
            observer.start()
            logging.info(f"Started file watcher (watchdog) for: {config_dir}")
            return observer
        except Exception as e:
            logging.warning(f"Failed to start watchdog observer: {e}")
            # Fall through to polling

    # Use polling as fallback
    try:
        watcher = PollingFileWatcher(config_dir, reload_callback)
        watcher.start()
        return watcher
    except Exception as e:
        logging.error(f"Failed to start file watcher: {e}")
        return None
