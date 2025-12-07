#!/usr/bin/env python3
"""Quick test of file_watcher module"""

import logging
import time
from pathlib import Path

from file_watcher import start_file_watcher

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

reload_count = 0

def on_reload():
    global reload_count
    reload_count += 1
    logging.info(f"RELOAD CALLBACK TRIGGERED! (count: {reload_count})")

# Start watcher
config_dir = Path("config")
print(f"Starting file watcher for: {config_dir.absolute()}")
watcher = start_file_watcher(config_dir, on_reload)

if watcher:
    print("[OK] File watcher started successfully")
    print(f"  Watching: lynx.evt, current_event.json, colors.csv")
    print("\nTest: Modify config/current_event.json to trigger reload")
    print("Waiting for file changes... (Ctrl+C to exit)")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping watcher...")
        watcher.stop()
        print(f"Final reload count: {reload_count}")
else:
    print("[FAIL] Failed to start file watcher")
