"""
Keyboard Listener Script
Listens for keyboard input and displays the name of the key pressed.
Press 'Esc' to exit.
"""

try:
    from pynput import keyboard
except ImportError:
    print("Error: pynput library is not installed.")
    print("Install it using: pip install pynput")
    exit(1)


def on_press(key):
    """Callback function when a key is pressed."""
    try:
        # Try to get the character of the key
        print(f"Key pressed: {key.char}")
    except AttributeError:
        # Special keys (like Esc, Ctrl, etc.) don't have a char attribute
        print(f"Special key pressed: {key}")


def on_release(key):
    """Callback function when a key is released."""
    # Stop listener when Esc is pressed
    if key == keyboard.Key.esc:
        print("\nEsc pressed. Exiting...")
        return False


def main():
    print("Keyboard Listener Started")
    print("Press any key to see its name")
    print("Press 'Esc' to exit\n")

    # Create and start the listener
    with keyboard.Listener(
        on_press=on_press,
        on_release=on_release
    ) as listener:
        listener.join()


if __name__ == "__main__":
    main()
