#!/usr/bin/env python3
"""
UDP Listener Utility
Listens on a specified UDP port and prints received data to the terminal.
"""

import argparse
import socket
import sys


def listen_udp(host: str, port: int, buffer_size: int = 4096):
    """
    Listen for UDP packets on the specified host and port.

    Args:
        host: Host address to bind to (use '' or '0.0.0.0' for all interfaces)
        port: UDP port number to listen on
        buffer_size: Maximum size of data to receive at once
    """
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        # Bind to the specified address and port
        sock.bind((host, port))
        print(f"Listening for UDP packets on {host if host else '0.0.0.0'}:{port}")
        print("Press Ctrl+C to stop\n")

        # Listen indefinitely
        while True:
            try:
                # Receive data
                data, addr = sock.recvfrom(buffer_size)

                # Print source address and data
                print(f"Received from {addr[0]}:{addr[1]}")
                print(f"Raw bytes ({len(data)})")

                # Try to decode as UTF-8 text
                try:
                    text = data.decode('utf-8')
                    print(f"Text: {text}")
                except UnicodeDecodeError:
                    print("(Could not decode as UTF-8 text)")

                print("-" * 60)

            except KeyboardInterrupt:
                print("\nStopping listener...")
                break
            except Exception as e:
                print(f"Error receiving data: {e}", file=sys.stderr)

    except OSError as e:
        print(f"Error binding to {host}:{port}: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        sock.close()


def main():
    parser = argparse.ArgumentParser(
        description="Listen for UDP packets and print them to the terminal"
    )
    parser.add_argument(
        '-p', '--port',
        type=int,
        required=True,
        help='UDP port to listen on'
    )
    parser.add_argument(
        '-H', '--host',
        type=str,
        default='',
        help='Host address to bind to (default: all interfaces)'
    )
    parser.add_argument(
        '-b', '--buffer-size',
        type=int,
        default=4096,
        help='Maximum buffer size for received data (default: 4096)'
    )

    args = parser.parse_args()

    listen_udp(args.host, args.port, args.buffer_size)


if __name__ == '__main__':
    main()
