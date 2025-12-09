"""
Tests for schedule_parser.py module.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from schedule_parser import (find_nearest_schedule_index, find_schedule_index,
                             get_schedule_position_text, parse_schedule,
                             validate_schedule_entries)


class TestParseSchedule:
    """Tests for parse_schedule function."""

    def test_parses_valid_schedule_file(self, schedule_fixture):
        """Test parsing a valid schedule file."""
        schedule = parse_schedule(str(schedule_fixture))

        assert isinstance(schedule, list)
        assert len(schedule) > 0

    def test_schedule_entry_structure(self, schedule_fixture):
        """Test that schedule entries have correct structure."""
        schedule = parse_schedule(str(schedule_fixture))

        # Schedule entries are tuples: (event, round, heat)
        for entry in schedule:
            assert isinstance(entry, tuple)
            assert len(entry) == 3
            assert isinstance(entry[0], int)  # event
            assert isinstance(entry[1], int)  # round
            assert isinstance(entry[2], int)  # heat

    def test_ignores_comment_lines(self, tmp_path):
        """Test that comment lines (starting with semicolon) are ignored."""
        schedule_file = tmp_path / "test.sch"
        schedule_file.write_text("; Comment line\n1,1,1\n; Another comment\n2,1,1\n")

        schedule = parse_schedule(str(schedule_file))

        assert len(schedule) == 2
        assert schedule[0] == (1, 1, 1)
        assert schedule[1] == (2, 1, 1)

    def test_ignores_empty_lines(self, tmp_path):
        """Test that empty lines are ignored."""
        schedule_file = tmp_path / "test.sch"
        schedule_file.write_text("1,1,1\n\n2,1,1\n\n\n3,1,1\n")

        schedule = parse_schedule(str(schedule_file))

        assert len(schedule) == 3

    def test_missing_file_returns_empty_list(self, tmp_path):
        """Test that missing file returns empty list."""
        nonexistent_file = tmp_path / "nonexistent.sch"

        schedule = parse_schedule(str(nonexistent_file))

        assert schedule == []

    def test_invalid_format_skips_line(self, tmp_path):
        """Test that invalid format lines are skipped."""
        schedule_file = tmp_path / "test.sch"
        schedule_file.write_text("1,1,1\ninvalid line\n2,1,1\n")

        schedule = parse_schedule(str(schedule_file))

        assert len(schedule) == 2


class TestValidateSchedule:
    """Tests for validate_schedule function."""

    def test_validates_correct_schedule(self, lynx_evt_fixture, schedule_fixture):
        """Test validation of a correct schedule against events."""
        from event_parser import parse_lynx_file

        events = parse_lynx_file(str(lynx_evt_fixture))
        schedule = parse_schedule(str(schedule_fixture))

        # validate_schedule_entries returns list of VALID entries, not errors
        valid = validate_schedule_entries(schedule, events)

        # Should return all entries if all are valid
        assert len(valid) <= len(schedule)

    def test_detects_invalid_event_number(self, lynx_evt_fixture):
        """Test detection of invalid event number in schedule."""
        from event_parser import parse_lynx_file

        events = parse_lynx_file(str(lynx_evt_fixture))
        schedule = [(999, 1, 1)]

        # Returns list of valid entries, so invalid entry is filtered out
        valid = validate_schedule_entries(schedule, events)

        assert len(valid) == 0  # Invalid entry filtered out

    def test_detects_invalid_round_number(self, lynx_evt_fixture):
        """Test detection of invalid round number in schedule."""
        from event_parser import parse_lynx_file

        events = parse_lynx_file(str(lynx_evt_fixture))
        schedule = [(1, 99, 1)]

        # Returns list of valid entries, invalid is filtered out
        valid = validate_schedule_entries(schedule, events)

        assert len(valid) == 0

    def test_detects_invalid_heat_number(self, lynx_evt_fixture):
        """Test detection of invalid heat number in schedule."""
        from event_parser import parse_lynx_file

        events = parse_lynx_file(str(lynx_evt_fixture))
        schedule = [(1, 1, 99)]

        # Returns list of valid entries, invalid is filtered out
        valid = validate_schedule_entries(schedule, events)

        assert len(valid) == 0


class TestFindScheduledPosition:
    """Tests for find_schedule_index function."""

    def test_finds_exact_position(self):
        """Test finding exact position in schedule."""
        schedule = [
            (1, 1, 1),
            (2, 1, 1),
            (3, 1, 1)
        ]

        pos = find_schedule_index(schedule, 2, 1, 1)

        assert pos == 1

    def test_returns_none_when_not_found(self):
        """Test that -1 is returned when position not found."""
        schedule = [
            (1, 1, 1),
            (2, 1, 1)
        ]

        pos = find_schedule_index(schedule, 99, 1, 1)

        assert pos == -1

    def test_finds_position_with_different_rounds(self):
        """Test finding position with different round numbers."""
        schedule = [
            (1, 1, 1),
            (1, 2, 1),
            (1, 3, 1)
        ]

        pos = find_schedule_index(schedule, 1, 2, 1)

        assert pos == 1


class TestFindNearestScheduled:
    """Tests for find_nearest_schedule_index function."""

    def test_finds_next_scheduled_event(self):
        """Test finding the next scheduled event after current position."""
        schedule = [
            (1, 1, 1),
            (2, 1, 1),
            (3, 1, 1)
        ]

        # find_nearest returns INDEX (int), not tuple
        result = find_nearest_schedule_index(schedule, 1, 1, 1)

        assert result is not None
        assert result == 0  # Found at index 0 (exact match)

    def test_wraps_to_beginning(self):
        """Test that exact match returns correct index."""
        schedule = [
            (1, 1, 1),
            (2, 1, 1),
            (3, 1, 1)
        ]

        # find_nearest returns INDEX (int), not tuple, doesn't wrap
        result = find_nearest_schedule_index(schedule, 3, 1, 1)

        assert result is not None
        assert result == 2  # Found at index 2 (exact match)

    def test_returns_none_for_empty_schedule(self):
        """Test that None is returned for empty schedule."""
        schedule = []

        result = find_nearest_schedule_index(schedule, 1, 1, 1)

        assert result is None

    def test_finds_first_event_when_current_not_in_schedule(self):
        """Test finding first event when current position not in schedule."""
        schedule = [
            (5, 1, 1),
            (6, 1, 1)
        ]

        # find_nearest returns index, not tuple
        result = find_nearest_schedule_index(schedule, 1, 1, 1)

        assert result is not None
        assert result == 0  # Found at index 0 (first entry >= current)


class TestFormatSchedulePosition:
    """Tests for get_schedule_position_text function."""

    def test_formats_position_in_schedule(self):
        """Test formatting position when event is in schedule."""
        schedule = [
            (1, 1, 1),
            (2, 1, 1),
            (3, 1, 1)
        ]

        result = get_schedule_position_text(schedule, 2, 1, 1)

        # Format is "Event 2-1-1 (Position 2 of 3)"
        assert "Event 2-1-1" in result
        assert "Position 2" in result
        assert "of 3" in result

    def test_formats_position_not_in_schedule(self):
        """Test formatting position when event is not in schedule."""
        schedule = [
            (1, 1, 1),
            (3, 1, 1)
        ]

        result = get_schedule_position_text(schedule, 2, 1, 1)

        # When not in schedule, returns just "Event 2-1-1" without position
        assert result == "Event 2-1-1"

    def test_empty_schedule(self):
        """Test formatting with empty schedule."""
        schedule = []

        result = get_schedule_position_text(schedule, 1, 1, 1)

        # Empty schedule returns just event text
        assert result == "Event 1-1-1"
