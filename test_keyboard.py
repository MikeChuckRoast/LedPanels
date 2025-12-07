#!/usr/bin/env python3
"""
Test script to debug keyboard input with evdev.
Run with: sudo python3 test_keyboard.py

This will:
1. List all input devices
2. Show which ones look like keyboards
3. Listen for key presses and print them
"""

import sys

try:
    import evdev
    from evdev import InputDevice, categorize, ecodes
except ImportError:
    print("ERROR: evdev is not installed")
    print("Install with: sudo apt install python3-evdev")
    sys.exit(1)

def list_all_devices():
    """List all input devices and their capabilities."""
    print("=" * 60)
    print("ALL INPUT DEVICES:")
    print("=" * 60)
    
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    
    if not devices:
        print("No input devices found!")
        print("Make sure you're running with sudo: sudo python3 test_keyboard.py")
        return []
    
    keyboard_devices = []
    
    for i, device in enumerate(devices):
        print(f"\n[{i}] Device: {device.name}")
        print(f"    Path: {device.path}")
        print(f"    Physical: {device.phys}")
        
        capabilities = device.capabilities(verbose=False)
        
        # Check if it's a keyboard
        is_keyboard = False
        if ecodes.EV_KEY in capabilities:
            keys = capabilities[ecodes.EV_KEY]
            # Check for common keyboard keys
            has_keys = []
            if ecodes.KEY_ENTER in keys:
                has_keys.append("ENTER")
            if ecodes.KEY_SPACE in keys:
                has_keys.append("SPACE")
            if ecodes.KEY_A in keys:
                has_keys.append("A-Z")
            if ecodes.KEY_PAGEUP in keys:
                has_keys.append("PAGEUP")
            if ecodes.KEY_PAGEDOWN in keys:
                has_keys.append("PAGEDOWN")
            
            if has_keys:
                print(f"    ** Looks like a KEYBOARD (has: {', '.join(has_keys)})")
                is_keyboard = True
                keyboard_devices.append((i, device))
            else:
                print(f"    Has KEY events but not a full keyboard (might be mouse/gamepad)")
        
        # Show all capability types
        cap_types = [ecodes.EV[cap_type] for cap_type in capabilities.keys()]
        print(f"    Capabilities: {', '.join(cap_types)}")
    
    return keyboard_devices


def test_device(device):
    """Listen to a device and print all key events."""
    print("\n" + "=" * 60)
    print(f"LISTENING TO: {device.name}")
    print(f"Path: {device.path}")
    print("=" * 60)
    print("\nPress keys (Ctrl+C to stop)...")
    print("Looking for: Page Up, Page Down, Period (.)")
    print("-" * 60)
    
    try:
        for event in device.read_loop():
            if event.type == ecodes.EV_KEY:
                key_event = categorize(event)
                
                # Create status string
                if key_event.keystate == 0:
                    status = "UP"
                elif key_event.keystate == 1:
                    status = "DOWN"
                elif key_event.keystate == 2:
                    status = "HOLD"
                else:
                    status = f"STATE_{key_event.keystate}"
                
                print(f"Key: {key_event.keycode:20s} | Status: {status:6s} | Code: {key_event.scancode}")
                
                # Highlight the keys we care about
                if key_event.keycode in ['KEY_PAGEUP', 'KEY_PAGEDOWN', 'KEY_DOT']:
                    print(f"  >>> IMPORTANT KEY DETECTED! <<<")
                
    except KeyboardInterrupt:
        print("\n\nStopped listening.")


def main():
    print("EVDEV KEYBOARD DEBUG TOOL")
    print("=" * 60)
    
    # List all devices
    keyboard_devices = list_all_devices()
    
    if not keyboard_devices:
        print("\n" + "=" * 60)
        print("NO KEYBOARD DEVICES FOUND!")
        print("=" * 60)
        print("\nTroubleshooting:")
        print("1. Make sure you're running with sudo")
        print("2. Make sure a keyboard is connected")
        print("3. Try: ls -l /dev/input/event*")
        print("4. Check permissions on /dev/input/event* files")
        return
    
    # If multiple keyboards, ask which to test
    print("\n" + "=" * 60)
    print(f"FOUND {len(keyboard_devices)} KEYBOARD DEVICE(S)")
    print("=" * 60)
    
    if len(keyboard_devices) == 1:
        print(f"\nAutomatically selecting device [0]: {keyboard_devices[0][1].name}")
        test_device(keyboard_devices[0][1])
    else:
        print("\nWhich device would you like to test?")
        for i, (idx, dev) in enumerate(keyboard_devices):
            print(f"  {i}: [{idx}] {dev.name}")
        
        try:
            choice = int(input("\nEnter number (0-%d): " % (len(keyboard_devices) - 1)))
            if 0 <= choice < len(keyboard_devices):
                test_device(keyboard_devices[choice][1])
            else:
                print("Invalid choice")
        except (ValueError, KeyboardInterrupt):
            print("\nCancelled")


if __name__ == '__main__':
    main()
