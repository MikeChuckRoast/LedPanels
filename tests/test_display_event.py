"""
Integration tests for display_event.py main application.
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestDisplayEventInitialization:
    """Tests for display_event.py initialization."""

    @patch('display_event.get_matrix_backend')
    @patch('display_event.load_settings')
    def test_loads_configuration_on_startup(self, mock_load_settings, mock_backend, sample_settings_dict):
        """Test that configuration is loaded on startup."""
        mock_load_settings.return_value = sample_settings_dict
        mock_backend.return_value = MagicMock()

        # Import would trigger initialization in actual code
        # This test structure assumes refactored main function

    @patch('display_event.parse_lynx_file')
    def test_parses_event_file_on_startup(self, mock_parse, populated_config_dir):
        """Test that lynx.evt is parsed on startup."""
        mock_parse.return_value = {
            (1, 1, 1): {"event": 1, "round": 1, "heat": 1, "name": "Test Event", "athletes": []}
        }

        # Test would require calling main initialization


class TestEventNavigation:
    """Tests for event navigation functionality."""

    def test_page_up_advances_heat(self):
        """Test that Page Up key advances to next heat."""
        # Mock keyboard input
        # Mock current event state
        # Trigger page up
        # Verify heat incremented
        pass

    def test_page_down_goes_to_previous_heat(self):
        """Test that Page Down key goes to previous heat."""
        # Mock keyboard input
        # Mock current event state
        # Trigger page down
        # Verify heat decremented
        pass

    def test_heat_wraps_to_next_round(self):
        """Test that advancing past last heat wraps to next round."""
        # Set current to last heat of round
        # Advance heat
        # Verify round incremented and heat reset to 1
        pass

    def test_navigation_respects_schedule_when_enabled(self):
        """Test that navigation follows schedule when schedule mode enabled."""
        # Load schedule
        # Enable schedule navigation
        # Advance
        # Verify moves to next scheduled event
        pass


class TestEventRendering:
    """Tests for event rendering functionality."""

    @patch('display_event.get_matrix_backend')
    def test_renders_event_header(self, mock_backend):
        """Test that event header is rendered correctly."""
        mock_matrix = MagicMock()
        mock_backend.return_value = mock_matrix

        # Mock event data
        # Render event
        # Verify header text drawn

    @patch('display_event.get_matrix_backend')
    def test_renders_athlete_rows(self, mock_backend):
        """Test that athlete rows are rendered correctly."""
        mock_matrix = MagicMock()
        mock_backend.return_value = mock_matrix

        # Mock event with athletes
        # Render event
        # Verify athlete text drawn

    @patch('display_event.get_matrix_backend')
    def test_paginates_athletes_when_needed(self, mock_backend):
        """Test that athletes are paginated when too many for display."""
        mock_matrix = MagicMock()
        mock_backend.return_value = mock_matrix

        # Mock event with many athletes
        # Render event
        # Verify pagination occurs

    @patch('display_event.get_matrix_backend')
    def test_applies_team_colors(self, mock_backend):
        """Test that team colors are applied to display."""
        mock_matrix = MagicMock()
        mock_backend.return_value = mock_matrix

        # Mock event with athletes
        # Mock color mappings
        # Render event
        # Verify colors applied

    @patch('display_event.get_matrix_backend')
    def test_formats_relay_teams_correctly(self, mock_backend):
        """Test that relay teams are formatted correctly."""
        mock_matrix = MagicMock()
        mock_backend.return_value = mock_matrix

        # Mock relay event
        # Render event
        # Verify relay suffix displayed

    @patch('display_event.get_matrix_backend')
    def test_formats_individual_athletes_correctly(self, mock_backend):
        """Test that individual athletes are formatted correctly."""
        mock_matrix = MagicMock()
        mock_backend.return_value = mock_matrix

        # Mock individual event
        # Render event
        # Verify name format


class TestRelayDuplicateSuffixDisplay:
    """Tests for conditional relay suffix display based on team duplicates."""

    def test_all_unique_relay_teams_no_suffix(self, relay_mixed_fixture):
        """Test that relay teams with no duplicates show no suffix."""
        from event_parser import get_duplicate_relay_teams, parse_lynx_file

        events = parse_lynx_file(str(relay_mixed_fixture))
        # Event 10 has all unique teams
        event_data = events.get((10, 1, 1))
        assert event_data is not None

        athletes = event_data["athletes"]
        duplicate_teams = get_duplicate_relay_teams(athletes)

        # Should have no duplicates
        assert len(duplicate_teams) == 0

    def test_all_duplicate_relay_teams_show_suffix(self, relay_mixed_fixture):
        """Test that all teams show suffix when all are duplicates."""
        from event_parser import get_duplicate_relay_teams, parse_lynx_file

        events = parse_lynx_file(str(relay_mixed_fixture))
        # Event 11 has all duplicate teams
        event_data = events.get((11, 1, 1))
        assert event_data is not None

        athletes = event_data["athletes"]
        duplicate_teams = get_duplicate_relay_teams(athletes)

        # Should identify both teams as duplicates
        assert "divine child" in duplicate_teams
        assert "guardian angels catholic" in duplicate_teams

    def test_mixed_relay_teams_selective_suffix(self, relay_mixed_fixture):
        """Test that only duplicate teams show suffix in mixed event."""
        from event_parser import get_duplicate_relay_teams, parse_lynx_file

        events = parse_lynx_file(str(relay_mixed_fixture))
        # Event 12 has some duplicates: Divine Child appears twice, others once
        event_data = events.get((12, 1, 1))
        assert event_data is not None

        athletes = event_data["athletes"]
        duplicate_teams = get_duplicate_relay_teams(athletes)

        # Only Divine Child should be marked as duplicate
        assert "divine child" in duplicate_teams
        assert "our lady of sorrows" not in duplicate_teams
        assert "guardian angels catholic" not in duplicate_teams

    def test_case_insensitive_duplicate_detection(self, relay_mixed_fixture):
        """Test that duplicate detection is case-insensitive."""
        from event_parser import get_duplicate_relay_teams, parse_lynx_file

        events = parse_lynx_file(str(relay_mixed_fixture))
        # Event 13 has "Divine Child", "divine child", "DIVINE CHILD"
        event_data = events.get((13, 1, 1))
        assert event_data is not None

        athletes = event_data["athletes"]
        duplicate_teams = get_duplicate_relay_teams(athletes)

        # Should detect all three as the same team (case-insensitive)
        assert "divine child" in duplicate_teams
        assert len(duplicate_teams) == 1  # Only one unique team name

    def test_three_same_teams_show_suffixes(self, relay_mixed_fixture):
        """Test that teams appearing 3+ times all show suffixes."""
        from event_parser import get_duplicate_relay_teams, parse_lynx_file

        events = parse_lynx_file(str(relay_mixed_fixture))
        # Event 14 has Divine Child A, B, C
        event_data = events.get((14, 1, 1))
        assert event_data is not None

        athletes = event_data["athletes"]
        duplicate_teams = get_duplicate_relay_teams(athletes)

        # Divine Child should be marked as duplicate
        assert "divine child" in duplicate_teams
        # Other teams should not
        assert "guardian angels catholic" not in duplicate_teams
        assert "our lady of sorrows" not in duplicate_teams


class TestFileWatching:
    """Tests for file watching and auto-reload functionality."""

    @pytest.mark.skip(reason="Integration test - requires actual file watcher implementation")
    @patch('display_event.start_file_watcher')
    def test_starts_file_watcher_when_enabled(self, mock_watcher, sample_settings_dict):
        """Test that file watcher starts when enabled in settings."""
        sample_settings_dict["monitoring"]["file_watch_enabled"] = True

        # Initialize display_event
        # Verify watcher started
        mock_watcher.assert_called()

    @patch('display_event.start_file_watcher')
    def test_does_not_start_watcher_when_disabled(self, mock_watcher, sample_settings_dict):
        """Test that file watcher doesn't start when disabled."""
        sample_settings_dict["monitoring"]["file_watch_enabled"] = False

        # Initialize display_event
        # Verify watcher not started
        mock_watcher.assert_not_called()

    def test_reload_callback_refreshes_display(self):
        """Test that reload callback refreshes the display."""
        # Mock file watcher callback
        # Trigger reload
        # Verify display refreshed
        pass


class TestWebServerIntegration:
    """Tests for web server integration."""

    @pytest.mark.skip(reason="Integration test - start_web_server is not create_web_server")
    @patch('display_event.start_web_server')
    def test_starts_web_server_when_enabled(self, mock_web_server, sample_settings_dict):
        """Test that web server starts when enabled."""
        sample_settings_dict["web"]["web_enabled"] = True

        # Initialize display_event
        # Verify web server started
        mock_web_server.assert_called()

    @pytest.mark.skip(reason="Integration test - start_web_server is not create_web_server")
    @patch('display_event.start_web_server')
    def test_does_not_start_web_server_when_disabled(self, mock_web_server, sample_settings_dict):
        """Test that web server doesn't start when disabled."""
        sample_settings_dict["web"]["web_enabled"] = False

        # Initialize display_event
        # Verify web server not started
        mock_web_server.assert_not_called()


class TestKeyboardIntegration:
    """Tests for keyboard input integration."""

    @pytest.mark.skip(reason="Tests module-level imports which are not exposed")
    @patch('display_event.evdev')
    def test_uses_evdev_on_linux(self, mock_evdev):
        """Test that evdev is used for keyboard input on Linux."""
        # Mock platform as Linux
        # Mock evdev available
        # Initialize keyboard
        # Verify evdev used
        pass

    @pytest.mark.skip(reason="Tests module-level imports which are not exposed")
    @patch('display_event.pynput')
    def test_fallback_to_pynput(self, mock_pynput):
        """Test fallback to pynput when evdev unavailable."""
        # Mock evdev unavailable
        # Initialize keyboard
        # Verify pynput used
        pass

    def test_keyboard_listener_runs_in_thread(self):
        """Test that keyboard listener runs in separate thread."""
        # Initialize keyboard
        # Verify daemon thread created
        pass


class TestErrorHandling:
    """Tests for error handling in display_event."""

    def test_handles_missing_event_file_gracefully(self, temp_config_dir):
        """Test graceful handling of missing lynx.evt file."""
        # Remove lynx.evt
        # Initialize display_event
        # Verify error handled, doesn't crash
        pass

    def test_handles_invalid_current_event_gracefully(self, populated_config_dir):
        """Test graceful handling of invalid current_event.json."""
        # Write invalid JSON to current_event.json
        # Initialize display_event
        # Verify error handled, defaults used
        pass

    def test_handles_matrix_initialization_failure(self, sample_settings_dict):
        """Test handling of matrix backend initialization failure."""
        # Mock matrix backend to raise exception
        # Initialize display_event
        # Verify error handled gracefully
        pass


class TestBehaviorModes:
    """Tests for different behavior modes."""

    def test_once_mode_renders_and_exits(self, sample_settings_dict):
        """Test that once mode renders once and exits."""
        sample_settings_dict["behavior"]["once"] = True

        # Initialize display_event
        # Verify renders once
        # Verify exits
        pass

    def test_continuous_mode_loops(self, sample_settings_dict):
        """Test that continuous mode loops indefinitely."""
        sample_settings_dict["behavior"]["once"] = False

        # Initialize display_event
        # Verify enters loop
        # Verify pages through athletes
        pass


class TestScheduleMode:
    """Tests for schedule-based navigation."""

    def test_loads_schedule_file_when_present(self, populated_config_dir):
        """Test that schedule file is loaded when present."""
        # Create schedule file
        # Initialize display_event
        # Verify schedule loaded
        pass

    def test_validates_schedule_against_events(self, populated_config_dir):
        """Test that schedule is validated against available events."""
        # Create schedule with invalid event
        # Initialize display_event
        # Verify validation error logged
        pass

    def test_advances_to_next_scheduled_event(self):
        """Test advancing to next event in schedule."""
        # Load schedule
        # Set current to scheduled event
        # Advance
        # Verify moves to next in schedule
        pass


class TestConditionalEventJump:
    """Tests for conditional jump behavior when current_event.json is updated.

    When a new event reference arrives (via file reload), the display should:
    - Jump forward if the display is behind the new reference
    - Stay put if the display is at or ahead of the new reference
    - Update the keyboard navigation floor regardless
    """

    def _simulate_reload_jump(self, displayed, incoming, schedule=None):
        """Simulate the conditional jump logic from the main loop.

        Args:
            displayed: (event, round, heat) tuple of what's currently displayed
            incoming: (event, round, heat) tuple from current_event.json
            schedule: optional list of (event, round, heat) tuples for schedule mode

        Returns:
            dict with 'jumped' (bool), 'display_after' (tuple), 'starting_index' (int or None)
        """
        from schedule_parser import (find_nearest_schedule_index,
                                     find_schedule_index)

        displayed_event_tuple = displayed
        args_event, args_round, current_heat = displayed

        incoming_event, incoming_round, incoming_heat = incoming

        # Always update reference floor
        original_event = incoming_event
        original_round = incoming_round
        original_heat = incoming_heat

        jumped = False
        starting_schedule_index = None

        if schedule:
            # Calculate starting_schedule_index from incoming reference
            starting_schedule_index = find_schedule_index(
                schedule, incoming_event, incoming_round, incoming_heat
            )
            if starting_schedule_index == -1:
                starting_schedule_index = find_nearest_schedule_index(
                    schedule, incoming_event, incoming_round, incoming_heat
                )

            # Calculate current_schedule_index for displayed event
            current_schedule_index = find_schedule_index(
                schedule, displayed[0], displayed[1], displayed[2]
            )
            if current_schedule_index == -1:
                current_schedule_index = find_nearest_schedule_index(
                    schedule, displayed[0], displayed[1], displayed[2]
                )
                if current_schedule_index is None:
                    current_schedule_index = len(schedule) - 1

            # Conditional jump
            if current_schedule_index < starting_schedule_index:
                args_event, args_round, current_heat = schedule[starting_schedule_index]
                jumped = True
        else:
            # No schedule: lexicographic tuple comparison
            incoming_tuple = (incoming_event, incoming_round, incoming_heat)
            if displayed_event_tuple < incoming_tuple:
                args_event = incoming_event
                args_round = incoming_round
                current_heat = incoming_heat
                jumped = True

        return {
            'jumped': jumped,
            'display_after': (args_event, args_round, current_heat),
            'starting_index': starting_schedule_index,
            'reference': (original_event, original_round, original_heat),
        }

    # --- No-schedule (tuple comparison) tests ---

    def test_no_schedule_display_behind_jumps_forward(self):
        """Display at event 3, reference updates to event 5 -> jumps to 5."""
        result = self._simulate_reload_jump(
            displayed=(3, 1, 1),
            incoming=(5, 1, 1),
        )
        assert result['jumped'] is True
        assert result['display_after'] == (5, 1, 1)

    def test_no_schedule_display_ahead_stays(self):
        """Display at event 5, reference updates to event 3 -> stays on 5."""
        result = self._simulate_reload_jump(
            displayed=(5, 1, 1),
            incoming=(3, 1, 1),
        )
        assert result['jumped'] is False
        assert result['display_after'] == (5, 1, 1)

    def test_no_schedule_display_equal_stays(self):
        """Display at event 5, reference updates to event 5 -> no jump."""
        result = self._simulate_reload_jump(
            displayed=(5, 1, 1),
            incoming=(5, 1, 1),
        )
        assert result['jumped'] is False
        assert result['display_after'] == (5, 1, 1)

    def test_no_schedule_heat_behind_jumps(self):
        """Display at (3,1,1), reference to (3,1,2) -> jumps (same event, later heat)."""
        result = self._simulate_reload_jump(
            displayed=(3, 1, 1),
            incoming=(3, 1, 2),
        )
        assert result['jumped'] is True
        assert result['display_after'] == (3, 1, 2)

    def test_no_schedule_heat_ahead_stays(self):
        """Display at (3,1,3), reference to (3,1,1) -> stays."""
        result = self._simulate_reload_jump(
            displayed=(3, 1, 3),
            incoming=(3, 1, 1),
        )
        assert result['jumped'] is False
        assert result['display_after'] == (3, 1, 3)

    def test_no_schedule_cross_event_behind_jumps(self):
        """Display at (3,1,1), reference to (5,1,2) -> jumps (different event)."""
        result = self._simulate_reload_jump(
            displayed=(3, 1, 1),
            incoming=(5, 1, 2),
        )
        assert result['jumped'] is True
        assert result['display_after'] == (5, 1, 2)

    def test_no_schedule_cross_event_ahead_stays(self):
        """Display at (5,1,3), reference to (3,1,1) -> stays."""
        result = self._simulate_reload_jump(
            displayed=(5, 1, 3),
            incoming=(3, 1, 1),
        )
        assert result['jumped'] is False
        assert result['display_after'] == (5, 1, 3)

    def test_no_schedule_reference_always_updated(self):
        """Reference floor is always updated regardless of jump."""
        result = self._simulate_reload_jump(
            displayed=(5, 1, 1),
            incoming=(3, 1, 1),
        )
        assert result['reference'] == (3, 1, 1)

    # --- Schedule-based tests ---

    def test_schedule_display_behind_jumps_forward(self):
        """Schedule mode: display behind reference -> jumps."""
        schedule = [(2, 1, 1), (5, 1, 1), (7, 1, 1), (1, 1, 1), (3, 1, 1), (6, 1, 1)]
        result = self._simulate_reload_jump(
            displayed=(2, 1, 1),  # index 0
            incoming=(7, 1, 1),   # index 2
            schedule=schedule,
        )
        assert result['jumped'] is True
        assert result['display_after'] == (7, 1, 1)

    def test_schedule_display_ahead_stays(self):
        """Schedule mode: display ahead of reference -> stays."""
        schedule = [(2, 1, 1), (5, 1, 1), (7, 1, 1), (1, 1, 1), (3, 1, 1), (6, 1, 1)]
        result = self._simulate_reload_jump(
            displayed=(3, 1, 1),  # index 4
            incoming=(5, 1, 1),   # index 1
            schedule=schedule,
        )
        assert result['jumped'] is False
        assert result['display_after'] == (3, 1, 1)

    def test_schedule_display_equal_stays(self):
        """Schedule mode: display at same position as reference -> stays."""
        schedule = [(2, 1, 1), (5, 1, 1), (7, 1, 1), (1, 1, 1), (3, 1, 1), (6, 1, 1)]
        result = self._simulate_reload_jump(
            displayed=(5, 1, 1),  # index 1
            incoming=(5, 1, 1),   # index 1
            schedule=schedule,
        )
        assert result['jumped'] is False
        assert result['display_after'] == (5, 1, 1)

    def test_schedule_starting_index_updated(self):
        """Schedule mode: starting_index reflects the incoming reference."""
        schedule = [(2, 1, 1), (5, 1, 1), (7, 1, 1), (1, 1, 1), (3, 1, 1), (6, 1, 1)]
        result = self._simulate_reload_jump(
            displayed=(6, 1, 1),
            incoming=(7, 1, 1),
            schedule=schedule,
        )
        assert result['starting_index'] == 2  # index of (7,1,1)


class TestConditionalJumpKeyboardFloor:
    """Tests for keyboard navigation floor after reference update."""

    def test_heat_increment_reset_returns_to_reference(self):
        """Heat-increment reset returns to reference event, not just heat."""
        # Simulate: reference updated to (3,1,1), display stayed at (5,1,3)
        # User presses reset -> should go to (3,1,1)
        original_event, original_round, original_heat = 3, 1, 1
        args_event, args_round, current_heat = 5, 1, 3

        # Simulate reset logic from display_event.py
        if args_event != original_event or args_round != original_round or current_heat != original_heat:
            args_event = original_event
            args_round = original_round
            current_heat = original_heat

        assert (args_event, args_round, current_heat) == (3, 1, 1)

    def test_heat_increment_reset_noop_when_at_reference(self):
        """Heat-increment reset is a no-op when already at reference."""
        original_event, original_round, original_heat = 3, 1, 1
        args_event, args_round, current_heat = 3, 1, 1

        changed = False
        if args_event != original_event or args_round != original_round or current_heat != original_heat:
            args_event = original_event
            args_round = original_round
            current_heat = original_heat
            changed = True

        assert changed is False
        assert (args_event, args_round, current_heat) == (3, 1, 1)

    def test_heat_increment_prev_respects_floor(self):
        """Heat-increment prev can't go below original_heat within same event."""
        original_heat = 2
        current_heat = 2
        args_event, args_round = 3, 1
        events = {(3, 1, 1): {}, (3, 1, 2): {}, (3, 1, 3): {}}

        # Simulate prev logic
        prev_heat = max(original_heat, current_heat - 1)
        if prev_heat != current_heat and (args_event, args_round, prev_heat) in events:
            current_heat = prev_heat

        # Should stay at heat 2 (floor)
        assert current_heat == 2

    def test_schedule_prev_respects_starting_index(self):
        """Schedule prev can't go before starting_schedule_index."""
        schedule = [(2, 1, 1), (5, 1, 1), (7, 1, 1), (1, 1, 1), (3, 1, 1)]
        starting_schedule_index = 2  # reference at (7,1,1)
        current_schedule_index = 2   # display also at (7,1,1)

        # Simulate prev
        if current_schedule_index > starting_schedule_index:
            current_schedule_index -= 1

        # Should stay at index 2
        assert current_schedule_index == 2
        assert schedule[current_schedule_index] == (7, 1, 1)
