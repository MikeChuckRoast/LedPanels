"""
Event data parsing and formatting utilities.

Handles:
- Lynx file parsing
- Color configuration loading
- Athlete formatting
- Lane filling
"""

import csv
import logging
import os
from typing import Dict, List, Optional, Tuple


def parse_hex_color(hex_str: str) -> Tuple[int, int, int]:
    """Parse a hex color string to RGB tuple.

    Args:
        hex_str: Hex color string (with or without # prefix)

    Returns:
        Tuple of (r, g, b) values (0-255)

    Raises:
        ValueError: If hex string is invalid
    """
    hex_str = hex_str.lstrip('#')
    if len(hex_str) != 6:
        raise ValueError(f"Invalid hex color length: {hex_str}")
    try:
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    except ValueError as e:
        raise ValueError(f"Invalid hex color format: {hex_str}") from e


def load_affiliation_colors(csv_path: str) -> Dict[str, Tuple[Tuple[int, int, int], Tuple[int, int, int], str]]:
    """Load affiliation color mappings from CSV file.

    CSV format: affiliation, name, bgcolor (hex), textcolor (hex)
    Returns: Dict mapping affiliation -> ((bg_r, bg_g, bg_b), (text_r, text_g, text_b), display_name)
    """
    colors = {}
    if not os.path.isfile(csv_path):
        logging.warning("Colors file not found: %s", csv_path)
        return colors

    try:
        with open(csv_path, "r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                affil = row.get("affiliation", "").strip()
                name = row.get("name", "").strip()
                bg_hex = row.get("bgcolor", "").strip()
                text_hex = row.get("text", "").strip()

                if not affil or not bg_hex or not text_hex:
                    continue

                # Parse hex colors (format: #RRGGBB)
                try:
                    bg_rgb = parse_hex_color(bg_hex)
                    text_rgb = parse_hex_color(text_hex)
                    # Store display name (use affiliation as fallback if name is empty)
                    display_name = name if name else affil
                    colors[affil] = (bg_rgb, text_rgb, display_name)
                except ValueError:
                    logging.warning("Invalid color format for %s: bg=%s, text=%s", affil, bg_hex, text_hex)
                    continue
    except Exception as e:
        logging.error("Failed to load colors from %s: %s", csv_path, e)

    logging.info("Loaded %d affiliation color mappings", len(colors))
    return colors


def parse_lynx_file(path: str) -> Dict[Tuple[int, int, int], Dict]:
    """Parse the lynx.evt CSV file into a mapping of (event, round, heat) -> event dict.

    Event header lines start with a number in the first column. Athlete lines
    have an empty first column (start with a comma).

    Event header format (we only care about the first 4 columns):
      event number, round number, heat number, event name, ...

    Athlete line format (we only care about the first 6 columns):
      '', athleteId, lane, last name, first name, affiliation, ...
    """
    events: Dict[Tuple[int, int, int], Dict] = {}

    if not os.path.isfile(path):
        raise FileNotFoundError(f"lynx file not found: {path}")

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        current_event_key: Optional[Tuple[int, int, int]] = None
        for raw in fh:
            line = raw.strip('\n')
            if not line:
                continue
            # Split CSV; use simple split because format is basic
            parts = [p.strip() for p in line.split(',')]
            if not parts:
                continue
            first = parts[0]
            # Event header if first column contains a number
            if first and first.isdigit():
                try:
                    ev = int(parts[0])
                    rd = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                    ht = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
                    name = parts[3] if len(parts) > 3 else ""
                except Exception:
                    # Malformed header; skip
                    current_event_key = None
                    continue
                key = (ev, rd, ht)
                events[key] = {"event": ev, "round": rd, "heat": ht, "name": name, "athletes": []}
                current_event_key = key
            else:
                # Athlete line if it starts with an empty first column
                if current_event_key is None:
                    # No current event; ignore
                    continue
                # athleteId, lane, last, first, affiliation
                # parts[0] is empty
                athlete = {}
                athlete["id"] = parts[1] if len(parts) > 1 else ""
                athlete["lane"] = parts[2] if len(parts) > 2 else ""
                athlete["last"] = parts[3] if len(parts) > 3 else ""
                athlete["first"] = parts[4] if len(parts) > 4 else ""
                athlete["affiliation"] = parts[5] if len(parts) > 5 else ""
                events[current_event_key]["athletes"].append(athlete)

    return events


def is_relay_event(athletes: List[Dict]) -> bool:
    """Detect if this is a relay event based on athlete data.

    Relay events have:
    - All first names empty
    - Last names matching pattern like 'Riverview' or 'Milan'
    - Affiliation matching pattern like 'RICO  A' or 'MILA  A'
    """
    if not athletes:
        return False

    import re
    for athlete in athletes:
        first = (athlete.get("first") or "").strip()
        last = (athlete.get("last") or "").strip()
        affil = (athlete.get("affiliation") or "").strip()

        # If any athlete has a first name, it's not a relay
        if first:
            return False

        # Check if affiliation matches relay pattern (3-4 letters, spaces, then a letter)
        if not re.match(r'^\w{3,4}\s+\w$', affil):
            return False

    return True


def extract_relay_suffix(affiliation: str) -> str:
    """Extract the relay suffix letter from affiliation (e.g., 'RICO  A' -> 'A')."""
    affil = affiliation.strip()
    if affil:
        # Get the last non-space character
        return affil.split()[-1] if affil.split() else ""
    return ""


def format_athlete_line(a: Dict, is_relay: bool = False) -> str:
    """Format athlete display string for the name column.

    For individual events: 'First L'
    For relay events: 'Team Name A' (team from last name, suffix from affiliation)

    NOTE: lane is displayed separately in its own column.
    """
    if is_relay:
        # For relay events, last name contains team name
        team_name = (a.get("last") or "").strip()
        affiliation = (a.get("affiliation") or "").strip()
        suffix = extract_relay_suffix(affiliation)
        return f"{team_name} {suffix}".strip()
    else:
        # For individual events
        first = (a.get("first") or "").strip()
        last = (a.get("last") or "").strip()
        last_initial = (last[0] + '.') if last else ""
        return f"{first} {last_initial}".strip()


def fill_lanes_with_empty_rows(athletes: List[Dict]) -> List[Dict]:
    """Fill in missing lanes with empty rows from lane 1 to max lane.

    Args:
        athletes: List of athlete dicts with "lane" field

    Returns:
        List with all lanes from 1 to max, with empty dicts for missing lanes
    """
    if not athletes:
        return []

    # Find max lane number and build lane mapping
    max_lane = 0
    athletes_by_lane = {}

    for athlete in athletes:
        lane_str = (athlete.get("lane") or "").strip()
        if lane_str.isdigit():
            lane_num = int(lane_str)
            max_lane = max(max_lane, lane_num)
            athletes_by_lane[lane_num] = athlete

    if max_lane == 0:
        return []

    # Create full list from lane 1 to max_lane
    full_list = []
    for lane in range(1, max_lane + 1):
        if lane in athletes_by_lane:
            full_list.append(athletes_by_lane[lane])
        else:
            # Empty lane - placeholder with only lane number
            full_list.append({"lane": str(lane)})

    return full_list


def paginate_items(items: List[Dict], page_size: int):
    """Yield successive pages (lists) of items of size `page_size`."""
    for i in range(0, len(items), page_size):
        yield items[i:i + page_size]
