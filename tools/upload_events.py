#!/usr/bin/env python3
"""
Test script for uploading event and schedule files to LED display web server.

This script reads lynx.evt and/or lynx.sch files and uploads them to the
web server using the file upload API endpoints.

Usage:
    # Upload both files separately
    python upload_events.py --server-url http://localhost:5000 \
        --events-file config/lynx.evt \
        --schedule-file config/lynx.sch

    # Upload both files atomically (recommended)
    python upload_events.py --server-url http://localhost:5000 \
        --events-file config/lynx.evt \
        --schedule-file config/lynx.sch \
        --combined

    # Upload only events file
    python upload_events.py --server-url http://localhost:5000 \
        --events-file config/lynx.evt

    # Upload only schedule file
    python upload_events.py --server-url http://localhost:5000 \
        --schedule-file config/lynx.sch
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print("Error: 'requests' library not found.", file=sys.stderr)
    print("Install it with: pip install requests", file=sys.stderr)
    sys.exit(1)


def read_file(file_path: str) -> str:
    """Read file contents with UTF-8 encoding.

    Args:
        file_path: Path to file to read

    Returns:
        File contents as string

    Raises:
        FileNotFoundError: If file doesn't exist
        IOError: If file cannot be read
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not path.is_file():
        raise IOError(f"Not a file: {file_path}")

    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def upload_events(server_url: str, events_file: str) -> bool:
    """Upload events file to server.

    Args:
        server_url: Base URL of web server (e.g., http://localhost:5000)
        events_file: Path to lynx.evt file

    Returns:
        True if upload succeeded, False otherwise
    """
    try:
        content = read_file(events_file)
    except Exception as e:
        print(f"✗ Error reading events file: {e}", file=sys.stderr)
        return False

    url = f"{server_url.rstrip('/')}/api/upload/events"
    data = {"content": content}

    print(f"Uploading events from {events_file}...")

    try:
        response = requests.post(url, json=data, timeout=30)
    except requests.exceptions.ConnectionError:
        print(f"✗ Error: Could not connect to server at {server_url}", file=sys.stderr)
        print("  Is the server running?", file=sys.stderr)
        return False
    except requests.exceptions.Timeout:
        print(f"✗ Error: Request timed out after 30 seconds", file=sys.stderr)
        return False
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        return False

    if response.status_code == 200:
        result = response.json()
        print(f"✓ Successfully uploaded {result['event_count']} events")
        return True
    else:
        try:
            error = response.json().get('error', 'Unknown error')
        except:
            error = response.text
        print(f"✗ Upload failed (HTTP {response.status_code}): {error}", file=sys.stderr)
        return False


def upload_schedule(server_url: str, schedule_file: str) -> bool:
    """Upload schedule file to server.

    Args:
        server_url: Base URL of web server (e.g., http://localhost:5000)
        schedule_file: Path to lynx.sch file

    Returns:
        True if upload succeeded, False otherwise
    """
    try:
        content = read_file(schedule_file)
    except Exception as e:
        print(f"✗ Error reading schedule file: {e}", file=sys.stderr)
        return False

    url = f"{server_url.rstrip('/')}/api/upload/schedule"
    data = {"content": content}

    print(f"Uploading schedule from {schedule_file}...")

    try:
        response = requests.post(url, json=data, timeout=30)
    except requests.exceptions.ConnectionError:
        print(f"✗ Error: Could not connect to server at {server_url}", file=sys.stderr)
        print("  Is the server running?", file=sys.stderr)
        return False
    except requests.exceptions.Timeout:
        print(f"✗ Error: Request timed out after 30 seconds", file=sys.stderr)
        return False
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        return False

    if response.status_code == 200:
        result = response.json()
        print(f"✓ Successfully uploaded schedule: {result['valid_entries']}/{result['total_entries']} valid entries")

        if result['invalid_entries'] > 0:
            print(f"  ⚠ Warning: {result['invalid_entries']} entries don't match existing events")

        return True
    else:
        try:
            error = response.json().get('error', 'Unknown error')
        except:
            error = response.text
        print(f"✗ Upload failed (HTTP {response.status_code}): {error}", file=sys.stderr)
        return False


def upload_combined(server_url: str, events_file: str, schedule_file: str) -> bool:
    """Upload both files atomically to server.

    Args:
        server_url: Base URL of web server (e.g., http://localhost:5000)
        events_file: Path to lynx.evt file
        schedule_file: Path to lynx.sch file

    Returns:
        True if upload succeeded, False otherwise
    """
    try:
        events_content = read_file(events_file)
    except Exception as e:
        print(f"✗ Error reading events file: {e}", file=sys.stderr)
        return False

    try:
        schedule_content = read_file(schedule_file)
    except Exception as e:
        print(f"✗ Error reading schedule file: {e}", file=sys.stderr)
        return False

    url = f"{server_url.rstrip('/')}/api/upload/combined"
    data = {
        "events": events_content,
        "schedule": schedule_content
    }

    print(f"Uploading both files atomically...")
    print(f"  Events:   {events_file}")
    print(f"  Schedule: {schedule_file}")

    try:
        response = requests.post(url, json=data, timeout=30)
    except requests.exceptions.ConnectionError:
        print(f"✗ Error: Could not connect to server at {server_url}", file=sys.stderr)
        print("  Is the server running?", file=sys.stderr)
        return False
    except requests.exceptions.Timeout:
        print(f"✗ Error: Request timed out after 30 seconds", file=sys.stderr)
        return False
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        return False

    if response.status_code == 200:
        result = response.json()
        print(f"✓ Successfully uploaded both files:")
        print(f"  Events:   {result['events']['event_count']} events")
        print(f"  Schedule: {result['schedule']['valid_entries']}/{result['schedule']['total_entries']} valid entries")

        if result['schedule']['invalid_entries'] > 0:
            print(f"  ⚠ Warning: {result['schedule']['invalid_entries']} schedule entries don't match events")

        return True
    else:
        try:
            error = response.json().get('error', 'Unknown error')
        except:
            error = response.text
        print(f"✗ Upload failed (HTTP {response.status_code}): {error}", file=sys.stderr)
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Upload event and schedule files to LED display web server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload both files atomically (recommended)
  %(prog)s --server-url http://localhost:5000 \\
    --events-file config/lynx.evt \\
    --schedule-file config/lynx.sch \\
    --combined

  # Upload both files separately
  %(prog)s --server-url http://localhost:5000 \\
    --events-file config/lynx.evt \\
    --schedule-file config/lynx.sch

  # Upload only events
  %(prog)s --server-url http://localhost:5000 \\
    --events-file config/lynx.evt

  # Upload only schedule
  %(prog)s --server-url http://localhost:5000 \\
    --schedule-file config/lynx.sch
        """
    )

    parser.add_argument(
        '--server-url',
        required=True,
        help='Base URL of web server (e.g., http://localhost:5000)'
    )

    parser.add_argument(
        '--events-file',
        help='Path to lynx.evt file to upload'
    )

    parser.add_argument(
        '--schedule-file',
        help='Path to lynx.sch file to upload'
    )

    parser.add_argument(
        '--combined',
        action='store_true',
        help='Upload both files atomically (requires both --events-file and --schedule-file)'
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.events_file and not args.schedule_file:
        parser.error("At least one of --events-file or --schedule-file is required")

    if args.combined:
        if not args.events_file or not args.schedule_file:
            parser.error("--combined requires both --events-file and --schedule-file")

    # Execute uploads
    success = True

    if args.combined:
        # Atomic upload of both files
        success = upload_combined(args.server_url, args.events_file, args.schedule_file)
    else:
        # Upload files separately
        if args.events_file:
            if not upload_events(args.server_url, args.events_file):
                success = False

        if args.schedule_file:
            if not upload_schedule(args.server_url, args.schedule_file):
                success = False

    # Exit with appropriate status
    if success:
        print("\n✓ All uploads completed successfully!")
        sys.exit(0)
    else:
        print("\n✗ One or more uploads failed", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
