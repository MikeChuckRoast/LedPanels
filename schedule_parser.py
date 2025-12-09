"""
Schedule parsing and navigation utilities.

Handles loading and parsing of lynx.sch schedule files which define
the competition order of events.
"""

import logging
import os
from typing import Dict, List, Optional, Tuple


def parse_schedule(path: str) -> List[Tuple[int, int, int]]:
    """Parse schedule file into ordered list of (event, round, heat) tuples.

    File format:
    - Lines starting with semicolon are ignored (comments/headers)
    - Each line contains: event,round,heat
    - Entries are in competition order

    Args:
        path: Path to lynx.sch file

    Returns:
        Ordered list of (event, round, heat) tuples
        Returns empty list if file not found or has no valid entries
    """
    schedule = []

    if not os.path.isfile(path):
        logging.info(f"Schedule file not found: {path}")
        return schedule

    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Skip empty lines and comments (lines starting with semicolon)
                if not line or line.startswith(';'):
                    continue

                # Parse CSV line
                parts = line.split(',')
                if len(parts) != 3:
                    logging.warning(f"Schedule line {line_num}: Invalid format (expected 3 fields): {line}")
                    continue

                try:
                    event = int(parts[0].strip())
                    round_num = int(parts[1].strip())
                    heat = int(parts[2].strip())

                    if event <= 0 or round_num <= 0 or heat <= 0:
                        logging.warning(f"Schedule line {line_num}: Invalid values (must be positive): {line}")
                        continue

                    schedule.append((event, round_num, heat))
                except ValueError:
                    logging.warning(f"Schedule line {line_num}: Invalid integer values: {line}")
                    continue

        logging.info(f"Loaded schedule with {len(schedule)} entries from: {path}")
    except Exception as e:
        logging.error(f"Error reading schedule file {path}: {e}")
        return []

    return schedule


def validate_schedule_entries(schedule: List[Tuple[int, int, int]],
                              events_dict: Dict[Tuple[int, int, int], Dict]) -> List[Tuple[int, int, int]]:
    """Validate schedule entries against available events and filter out invalid ones.

    Args:
        schedule: List of (event, round, heat) tuples from schedule file
        events_dict: Dictionary of parsed events from lynx.evt (keys are (event, round, heat))

    Returns:
        Filtered list containing only valid schedule entries
    """
    valid_schedule = []
    invalid_count = 0

    for entry in schedule:
        if entry in events_dict:
            valid_schedule.append(entry)
        else:
            event, round_num, heat = entry
            logging.warning(f"Schedule entry Event {event}, Round {round_num}, Heat {heat} not found in lynx.evt - skipping")
            invalid_count += 1

    if invalid_count > 0:
        logging.warning(f"Filtered out {invalid_count} invalid schedule entries")

    if valid_schedule:
        logging.info(f"Validated schedule: {len(valid_schedule)} valid entries")
    else:
        logging.warning("No valid entries in schedule after validation")

    return valid_schedule


def find_schedule_index(schedule: List[Tuple[int, int, int]],
                       event: int, round_num: int, heat: int) -> int:
    """Find the index of an event in the schedule.

    Args:
        schedule: Ordered list of (event, round, heat) tuples
        event: Event number
        round_num: Round number
        heat: Heat number

    Returns:
        Index in schedule (0-based), or -1 if not found
    """
    try:
        return schedule.index((event, round_num, heat))
    except ValueError:
        return -1


def find_nearest_schedule_index(schedule: List[Tuple[int, int, int]],
                                event: int, round_num: int, heat: int) -> Optional[int]:
    """Find the nearest schedule entry at or after the given event.

    Used when current event is not in schedule - finds closest match to allow
    forward navigation from current position.

    Strategy:
    1. Try exact match first
    2. Find first entry with event >= current event
    3. If same event, prefer same round, then same/higher heat
    4. Return None if current is after all scheduled events

    Args:
        schedule: Ordered list of (event, round, heat) tuples
        event: Current event number
        round_num: Current round number
        heat: Current heat number

    Returns:
        Index of nearest entry at or after current position, or None if past schedule end
    """
    if not schedule:
        return None

    # Try exact match first
    exact_index = find_schedule_index(schedule, event, round_num, heat)
    if exact_index >= 0:
        return exact_index

    # Find nearest entry at or after current position
    # Score each entry: prioritize event match, then round, then heat
    best_index = None

    for i, (sch_event, sch_round, sch_heat) in enumerate(schedule):
        # Must be at or after current position
        if (sch_event, sch_round, sch_heat) >= (event, round_num, heat):
            if best_index is None:
                best_index = i
            else:
                # Found a candidate - take the first one (earliest in schedule)
                break

    if best_index is not None:
        sch_event, sch_round, sch_heat = schedule[best_index]
        logging.info(f"Current event {event}-{round_num}-{heat} not in schedule - using nearest entry at index {best_index}: {sch_event}-{sch_round}-{sch_heat}")
    else:
        logging.info(f"Current event {event}-{round_num}-{heat} is past all scheduled events")

    return best_index


def get_schedule_position_text(schedule: List[Tuple[int, int, int]],
                               event: int, round_num: int, heat: int) -> str:
    """Get formatted text showing position in schedule.

    Args:
        schedule: Ordered list of (event, round, heat) tuples
        event: Current event number
        round_num: Current round number
        heat: Current heat number

    Returns:
        Formatted string like "Event 7-1-2 (Position 4 of 43)" or just "Event 7-1-2" if not in schedule
    """
    event_text = f"Event {event}-{round_num}-{heat}"

    if not schedule:
        return event_text

    index = find_schedule_index(schedule, event, round_num, heat)
    if index >= 0:
        position = index + 1  # Convert to 1-based
        total = len(schedule)
        return f"{event_text} (Position {position} of {total})"
    else:
        return event_text
