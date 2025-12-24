#!/usr/bin/env python3
"""
Test script to send sample UDP messages to the scoreboard.
"""

import json
import socket
import sys
import time


def send_udp_message(port, message_dict):
    """Send a JSON message via UDP to localhost."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        message = json.dumps(message_dict)
        sock.sendto(message.encode('utf-8'), ('127.0.0.1', port))
        print(f"Sent: {message}")
    finally:
        sock.close()

def main():
    port = 5568
    if len(sys.argv) > 1:
        port = int(sys.argv[1])

    print(f"Sending test messages to UDP port {port}")
    print("=" * 60)

    # Test 1: Initialization (clear display)
    print("\n1. Initialization (clear display)")
    send_udp_message(port, {"initialization": True})
    time.sleep(2)

    # Test 2: Start list with event name
    print("\n2. Start list with event name")
    send_udp_message(port, {
        "startList": {
            "eventName": "100M Freestyle",
            "eventNumber": 5,
            "roundNumber": 1,
            "heatNumber": 2
        }
    })
    time.sleep(2)

    # Test 3: Update time
    print("\n3. Time running updates")
    for time_val in ["0.0", "15.3", "28.7", "42.1  ", "59.8"]:
        send_udp_message(port, {"timeRunning": time_val})
        time.sleep(1)

    # Test 4: New event
    print("\n4. New event (200M Butterfly)")
    send_udp_message(port, {
        "startList": {
            "eventName": "200M Butterfly",
            "eventNumber": 12
        }
    })
    time.sleep(2)

    # Test 5: Time updates for new event
    print("\n5. Time updates for new event")
    for time_val in ["0.0", "30.2", "1:05.4", "1:48.9"]:
        send_udp_message(port, {"timeRunning": time_val})
        time.sleep(1)

    # Test 6: Empty event name
    print("\n6. Empty event name")
    send_udp_message(port, {
        "startList": {
            "eventName": ""
        }
    })
    time.sleep(2)

    # Test 7: Malformed JSON (should be ignored)
    print("\n7. Malformed JSON (should be logged and ignored)")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(b"{ invalid json", ('127.0.0.1', port))
    sock.close()
    time.sleep(1)

    # Test 8: Clear display again
    print("\n8. Clear display (initialization)")
    send_udp_message(port, {"initialization": True})

    print("\n" + "=" * 60)
    print("Test complete!")

if __name__ == '__main__':
    main()
