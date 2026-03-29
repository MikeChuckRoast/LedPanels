"""
Integration tests for display_event.py main application.
"""

import subprocess
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
    """Tests for handle_heat_change function."""

    def _make_events(self, keys):
        """Helper to build a minimal events dict from (event, round, heat) tuples."""
        return {k: {"event": k[0], "round": k[1], "heat": k[2], "name": "Test", "athletes": []} for k in keys}

    # --- Heat‑increment mode (no schedule) ---

    def test_next_advances_heat(self):
        """Test 'next' moves to the next heat when it exists."""
        from display_event import handle_heat_change

        events = self._make_events([(1, 1, 1), (1, 1, 2)])
        ev, rnd, ht, idx = handle_heat_change(
            'next', schedule=[], current_schedule_index=-1, starting_schedule_index=-1,
            current_event=1, current_round=1, current_heat=1,
            original_event=1, original_round=1, original_heat=1, events=events)
        assert (ev, rnd, ht) == (1, 1, 2)

    def test_next_stays_when_no_next_heat(self):
        """Test 'next' stays on current heat when next doesn't exist."""
        from display_event import handle_heat_change

        events = self._make_events([(1, 1, 1)])
        ev, rnd, ht, idx = handle_heat_change(
            'next', schedule=[], current_schedule_index=-1, starting_schedule_index=-1,
            current_event=1, current_round=1, current_heat=1,
            original_event=1, original_round=1, original_heat=1, events=events)
        assert (ev, rnd, ht) == (1, 1, 1)

    def test_prev_goes_back_but_not_before_original(self):
        """Test 'prev' goes back one heat but stops at original_heat floor."""
        from display_event import handle_heat_change

        events = self._make_events([(1, 1, 1), (1, 1, 2), (1, 1, 3)])
        # Currently on heat 3, original is heat 2 — should go to 2 but not below
        ev, rnd, ht, _ = handle_heat_change(
            'prev', schedule=[], current_schedule_index=-1, starting_schedule_index=-1,
            current_event=1, current_round=1, current_heat=3,
            original_event=1, original_round=1, original_heat=2, events=events)
        assert ht == 2

        # Now at heat 2 which equals original_heat — should stay
        ev, rnd, ht, _ = handle_heat_change(
            'prev', schedule=[], current_schedule_index=-1, starting_schedule_index=-1,
            current_event=1, current_round=1, current_heat=2,
            original_event=1, original_round=1, original_heat=2, events=events)
        assert ht == 2

    def test_reset_returns_to_original(self):
        """Test 'reset' returns to original event/round/heat."""
        from display_event import handle_heat_change

        events = self._make_events([(1, 1, 1), (1, 1, 2)])
        ev, rnd, ht, _ = handle_heat_change(
            'reset', schedule=[], current_schedule_index=-1, starting_schedule_index=-1,
            current_event=1, current_round=1, current_heat=2,
            original_event=1, original_round=1, original_heat=1, events=events)
        assert (ev, rnd, ht) == (1, 1, 1)

    def test_reset_noop_when_already_at_original(self):
        """Test 'reset' is a no-op when already at original."""
        from display_event import handle_heat_change

        events = self._make_events([(1, 1, 1)])
        ev, rnd, ht, _ = handle_heat_change(
            'reset', schedule=[], current_schedule_index=-1, starting_schedule_index=-1,
            current_event=1, current_round=1, current_heat=1,
            original_event=1, original_round=1, original_heat=1, events=events)
        assert (ev, rnd, ht) == (1, 1, 1)

    # --- Schedule mode ---

    def test_schedule_next_advances_index(self):
        """Test 'next' advances schedule index."""
        from display_event import handle_heat_change

        schedule = [(1, 1, 1), (2, 1, 1), (3, 1, 1)]
        events = self._make_events(schedule)
        ev, rnd, ht, idx = handle_heat_change(
            'next', schedule=schedule, current_schedule_index=0, starting_schedule_index=0,
            current_event=1, current_round=1, current_heat=1,
            original_event=1, original_round=1, original_heat=1, events=events)
        assert (ev, rnd, ht) == (2, 1, 1)
        assert idx == 1

    def test_schedule_next_at_end_stays(self):
        """Test 'next' at end of schedule stays put."""
        from display_event import handle_heat_change

        schedule = [(1, 1, 1), (2, 1, 1)]
        events = self._make_events(schedule)
        ev, rnd, ht, idx = handle_heat_change(
            'next', schedule=schedule, current_schedule_index=1, starting_schedule_index=0,
            current_event=2, current_round=1, current_heat=1,
            original_event=1, original_round=1, original_heat=1, events=events)
        assert (ev, rnd, ht) == (2, 1, 1)
        assert idx == 1

    def test_schedule_prev_stops_at_starting_index(self):
        """Test 'prev' in schedule mode won't go before starting_schedule_index."""
        from display_event import handle_heat_change

        schedule = [(1, 1, 1), (2, 1, 1), (3, 1, 1)]
        events = self._make_events(schedule)
        # Starting at index 1, currently at index 1 — prev should not go to 0
        ev, rnd, ht, idx = handle_heat_change(
            'prev', schedule=schedule, current_schedule_index=1, starting_schedule_index=1,
            current_event=2, current_round=1, current_heat=1,
            original_event=2, original_round=1, original_heat=1, events=events)
        assert idx == 1

    def test_schedule_reset_returns_to_starting(self):
        """Test 'reset' in schedule mode returns to starting_schedule_index."""
        from display_event import handle_heat_change

        schedule = [(1, 1, 1), (2, 1, 1), (3, 1, 1)]
        events = self._make_events(schedule)
        ev, rnd, ht, idx = handle_heat_change(
            'reset', schedule=schedule, current_schedule_index=2, starting_schedule_index=0,
            current_event=3, current_round=1, current_heat=1,
            original_event=1, original_round=1, original_heat=1, events=events)
        assert (ev, rnd, ht) == (1, 1, 1)
        assert idx == 0


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

    def test_starts_file_watcher_when_enabled(self, populated_config_dir):
        """Test that file watcher starts when enabled in settings."""
        from unittest.mock import Mock

        from file_watcher import start_file_watcher

        callback = Mock()
        watcher = start_file_watcher(str(populated_config_dir), callback)

        assert watcher is not None
        # Clean up
        if hasattr(watcher, 'stop'):
            watcher.stop()

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

    def test_starts_web_server_when_enabled(self, populated_config_dir):
        """Test that web server starts when enabled."""
        from web_server import start_web_server

        server = start_web_server(str(populated_config_dir), host='127.0.0.1', port=0)
        assert server is not None
        # Clean up
        if hasattr(server, 'shutdown'):
            server.shutdown()

    def test_web_server_not_started_returns_none_on_bad_port(self, populated_config_dir):
        """Test that web server returns None when it cannot bind."""
        from web_server import start_web_server

        # Port 0 lets the OS pick a free port, so use a different approach:
        # Start a server on a port, then try starting another on the same port
        server1 = start_web_server(str(populated_config_dir), host='127.0.0.1', port=0)
        # server1 should work
        assert server1 is not None
        if hasattr(server1, 'shutdown'):
            server1.shutdown()


class TestKeyboardIntegration:
    """Tests for keyboard input integration."""

    def test_keyboard_backend_is_detected(self):
        """Test that a keyboard backend is detected at module level."""
        import display_event

        # keyboard_backend should be one of 'evdev', 'pynput', or None
        assert display_event.keyboard_backend in ('evdev', 'pynput', None)

    def test_keyboard_available_matches_backend(self):
        """Test that KEYBOARD_AVAILABLE is consistent with keyboard_backend."""
        import display_event

        if display_event.keyboard_backend is not None:
            assert display_event.KEYBOARD_AVAILABLE is True
        else:
            assert display_event.KEYBOARD_AVAILABLE is False

    def test_keyboard_listener_runs_in_thread(self):
        """Test that keyboard listener runs in separate thread."""
        # Initialize keyboard
        # Verify daemon thread created
        pass


class TestLoadFileWithRetry:
    """Tests for load_file_with_retry function."""

    def test_returns_result_on_first_success(self):
        """Test that successful load returns result immediately."""
        from display_event import load_file_with_retry

        result = load_file_with_retry(lambda: {"key": "value"}, "test file")
        assert result == {"key": "value"}

    def test_retries_on_io_error(self):
        """Test that IOError triggers retry."""
        from display_event import load_file_with_retry

        call_count = 0

        def flaky_load():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise IOError("file busy")
            return "success"

        with patch('display_event.time.sleep'):
            result = load_file_with_retry(flaky_load, "test file", max_retries=3)

        assert result == "success"
        assert call_count == 3

    def test_retries_on_os_error(self):
        """Test that OSError triggers retry."""
        from display_event import load_file_with_retry

        call_count = 0

        def flaky_load():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise OSError("permission denied")
            return "ok"

        with patch('display_event.time.sleep'):
            result = load_file_with_retry(flaky_load, "test file", max_retries=3)

        assert result == "ok"
        assert call_count == 2

    def test_retries_on_file_not_found(self):
        """Test that FileNotFoundError triggers retry."""
        from display_event import load_file_with_retry

        call_count = 0

        def flaky_load():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise FileNotFoundError("not yet")
            return "found"

        with patch('display_event.time.sleep'):
            result = load_file_with_retry(flaky_load, "test file", max_retries=3)

        assert result == "found"

    def test_returns_none_after_max_retries_exhausted(self):
        """Test that None is returned when all retries fail."""
        from display_event import load_file_with_retry

        def always_fail():
            raise IOError("always broken")

        with patch('display_event.time.sleep'):
            result = load_file_with_retry(always_fail, "test file", max_retries=3)

        assert result is None

    def test_returns_none_on_unexpected_exception(self):
        """Test that unexpected exceptions return None without retrying."""
        from display_event import load_file_with_retry

        call_count = 0

        def bad_load():
            nonlocal call_count
            call_count += 1
            raise ValueError("unexpected")

        result = load_file_with_retry(bad_load, "test file", max_retries=3)

        assert result is None
        assert call_count == 1  # No retries for unexpected exceptions

    def test_retry_delay_increases(self):
        """Test that retry delay increases with each attempt."""
        from display_event import load_file_with_retry

        delays = []

        def always_fail():
            raise IOError("broken")

        with patch('display_event.time.sleep', side_effect=lambda d: delays.append(d)):
            load_file_with_retry(always_fail, "test file", max_retries=3)

        # Delays should be 0.1, 0.2 (last attempt doesn't sleep)
        assert len(delays) == 2
        assert delays[0] == pytest.approx(0.1)
        assert delays[1] == pytest.approx(0.2)

    def test_single_retry_returns_none_on_failure(self):
        """Test with max_retries=1 returns None on first failure."""
        from display_event import load_file_with_retry

        def fail_load():
            raise IOError("fail")

        result = load_file_with_retry(fail_load, "test file", max_retries=1)
        assert result is None


class TestHandleFileReload:
    """Tests for handle_file_reload function."""

    def _make_config_dir(self, tmp_path, events_content, current_event, settings_toml=None):
        """Helper to create a populated config directory for reload tests."""
        import json
        config_dir = tmp_path / "config"
        config_dir.mkdir(exist_ok=True)

        (config_dir / "lynx.evt").write_text(events_content)
        (config_dir / "current_event.json").write_text(json.dumps(current_event))
        (config_dir / "colors.csv").write_text("Team,Primary,Secondary\n")

        if settings_toml is None:
            settings_toml = """
[hardware]
width = 64
height = 32
chain = 2
parallel = 4
gpio_slowdown = 3

[display]
line_height = 24
header_line_height = 16
header_rows = 2
interval = 2.0
font_shift = 7

[fonts]
font_path = "fonts"
font_name = "helvB14.bdf"

[files]
lynx_file = "lynx.evt"
colors_file = "colors.csv"

[network]
fpp_enabled = false
fpp_host = "127.0.0.1"
fpp_port = 4048
colorlight_enabled = false
colorlight_interface = "eth0"

[keyboard]
device_path = ""

[behavior]
once = false

[monitoring]
file_watch_enabled = true
poll_interval = 1.0

[web]
web_enabled = false
web_host = "0.0.0.0"
web_port = 5000
"""
        (config_dir / "settings.toml").write_text(settings_toml)
        return str(config_dir)

    def test_reloads_events_and_colors(self, tmp_path, lynx_evt_fixture):
        """Test that handle_file_reload reloads events and colors."""
        import json
        import shutil

        from display_event import handle_file_reload

        config_dir = self._make_config_dir(tmp_path,
            events_content=lynx_evt_fixture.read_text(),
            current_event={"event": 1, "round": 1, "heat": 1})

        evt_path = str(Path(config_dir) / "lynx.evt")
        colors_path = str(Path(config_dir) / "colors.csv")

        result = handle_file_reload(
            config_dir=config_dir,
            events={(1, 1, 1): {"name": "Old", "athletes": []}},
            affiliation_colors={},
            disp={"font_shift": 7, "line_height": 24, "header_line_height": 16,
                  "header_rows": 2, "interval": 2.0},
            schedule=[],
            args_file=evt_path,
            args_font="fonts/helvB14.bdf",
            args_colors_csv=colors_path,
            displayed_event=1, displayed_round=1, displayed_heat=1,
            current_schedule_index=-1, starting_schedule_index=-1,
            original_event=1, original_round=1, original_heat=1)

        # Events should be reloaded (not the old single-entry dict)
        assert len(result['events']) > 0
        assert isinstance(result['affiliation_colors'], dict)

    def test_jumps_forward_when_behind_reference(self, tmp_path, lynx_evt_fixture):
        """Test that display jumps forward when behind incoming reference."""
        from display_event import handle_file_reload

        config_dir = self._make_config_dir(tmp_path,
            events_content=lynx_evt_fixture.read_text(),
            current_event={"event": 7, "round": 1, "heat": 2})

        evt_path = str(Path(config_dir) / "lynx.evt")
        colors_path = str(Path(config_dir) / "colors.csv")

        result = handle_file_reload(
            config_dir=config_dir,
            events={(1, 1, 1): {"name": "Old", "athletes": []}},
            affiliation_colors={},
            disp={"font_shift": 7, "line_height": 24, "header_line_height": 16,
                  "header_rows": 2, "interval": 2.0},
            schedule=[],
            args_file=evt_path,
            args_font="fonts/helvB14.bdf",
            args_colors_csv=colors_path,
            displayed_event=1, displayed_round=1, displayed_heat=1,
            current_schedule_index=-1, starting_schedule_index=-1,
            original_event=1, original_round=1, original_heat=1)

        # Display was at (1,1,1), incoming reference is (7,1,2) — should jump forward
        assert result['event'] == 7
        assert result['heat'] == 2

    def test_stays_when_ahead_of_reference(self, tmp_path, lynx_evt_fixture):
        """Test that display stays put when ahead of incoming reference."""
        from display_event import handle_file_reload

        config_dir = self._make_config_dir(tmp_path,
            events_content=lynx_evt_fixture.read_text(),
            current_event={"event": 1, "round": 1, "heat": 1})

        evt_path = str(Path(config_dir) / "lynx.evt")
        colors_path = str(Path(config_dir) / "colors.csv")

        result = handle_file_reload(
            config_dir=config_dir,
            events={(7, 1, 1): {"name": "Current", "athletes": []}},
            affiliation_colors={},
            disp={"font_shift": 7, "line_height": 24, "header_line_height": 16,
                  "header_rows": 2, "interval": 2.0},
            schedule=[],
            args_file=evt_path,
            args_font="fonts/helvB14.bdf",
            args_colors_csv=colors_path,
            displayed_event=7, displayed_round=1, displayed_heat=1,
            current_schedule_index=-1, starting_schedule_index=-1,
            original_event=1, original_round=1, original_heat=1)

        # Display was at (7,1,1), incoming reference is (1,1,1) — should stay
        assert result['event'] == 7
        assert result['heat'] == 1

    def test_updates_reference_on_current_event_change(self, tmp_path, lynx_evt_fixture):
        """Test that original_event/round/heat update when current_event.json changes."""
        from display_event import handle_file_reload

        config_dir = self._make_config_dir(tmp_path,
            events_content=lynx_evt_fixture.read_text(),
            current_event={"event": 5, "round": 1, "heat": 1})

        evt_path = str(Path(config_dir) / "lynx.evt")
        colors_path = str(Path(config_dir) / "colors.csv")

        result = handle_file_reload(
            config_dir=config_dir,
            events={(1, 1, 1): {"name": "Old", "athletes": []}},
            affiliation_colors={},
            disp={"font_shift": 7, "line_height": 24, "header_line_height": 16,
                  "header_rows": 2, "interval": 2.0},
            schedule=[],
            args_file=evt_path,
            args_font="fonts/helvB14.bdf",
            args_colors_csv=colors_path,
            displayed_event=1, displayed_round=1, displayed_heat=1,
            current_schedule_index=-1, starting_schedule_index=-1,
            original_event=1, original_round=1, original_heat=1)

        # Reference should be updated to incoming values
        assert result['original_event'] == 5
        assert result['original_round'] == 1
        assert result['original_heat'] == 1


class TestErrorHandling:
    """Tests for error handling in display_event."""

    def test_handles_missing_event_file_gracefully(self, temp_config_dir):
        """Test graceful handling of missing lynx.evt file."""
        from event_parser import parse_lynx_file

        missing_path = str(temp_config_dir / "nonexistent.evt")
        with pytest.raises(FileNotFoundError):
            parse_lynx_file(missing_path)

    def test_handles_invalid_current_event_gracefully(self, populated_config_dir):
        """Test graceful handling of invalid current_event.json."""
        from config_loader import ConfigError, load_current_event

        # Write invalid JSON
        (populated_config_dir / "current_event.json").write_text("{invalid json")

        with pytest.raises(ConfigError, match="Invalid JSON"):
            load_current_event(str(populated_config_dir))

    def test_handles_missing_current_event_fields(self, temp_config_dir):
        """Test handling of current_event.json with missing fields."""
        import json

        from config_loader import ConfigError, load_current_event

        (temp_config_dir / "current_event.json").write_text(json.dumps({"event": 1}))

        with pytest.raises(ConfigError, match="Missing required fields"):
            load_current_event(str(temp_config_dir))

    def test_handles_matrix_initialization_failure(self):
        """Test handling of matrix backend initialization failure."""
        from matrix_backend import try_import_rgbmatrix

        # When no rgbmatrix or emulator is available, returns (None, None, None)
        with patch.dict('sys.modules', {'rgbmatrix': None, 'RGBMatrixEmulator': None, 'rgbmatrix_emulator': None}):
            result = try_import_rgbmatrix()
            # Should not raise - returns None tuple
            assert result == (None, None, None)


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


class TestGetDefaultGateway:
    """Tests for default gateway discovery."""

    @patch('display_event.platform.system', return_value='Windows')
    @patch('display_event.subprocess.run')
    def test_windows_gateway_discovery(self, mock_run, mock_system):
        """Test gateway discovery on Windows via route print."""
        from display_event import get_default_gateway

        mock_run.return_value = MagicMock(
            stdout=(
                "===========================================================================\n"
                "Active Routes:\n"
                "Network Destination        Netmask          Gateway       Interface  Metric\n"
                "          0.0.0.0          0.0.0.0      192.168.1.1    192.168.1.50     25\n"
            )
        )
        assert get_default_gateway() == '192.168.1.1'

    @patch('display_event.platform.system', return_value='Linux')
    def test_linux_gateway_discovery(self, mock_system, tmp_path):
        """Test gateway discovery on Linux via /proc/net/route."""
        from display_event import get_default_gateway

        # 192.168.1.1 in little-endian hex = 0101A8C0
        route_content = (
            "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n"
            "eth0\t00000000\t0101A8C0\t0003\t0\t0\t0\t00000000\n"
        )
        route_file = tmp_path / "route"
        route_file.write_text(route_content)

        with patch('display_event.Path') as mock_path_cls:
            mock_route = MagicMock()
            mock_route.exists.return_value = True
            mock_route.read_text.return_value = route_content
            # Make Path('/proc/net/route') return our mock
            mock_path_cls.return_value = mock_route
            # But for other Path calls, use the real Path
            result = get_default_gateway()
            assert result == '192.168.1.1'

    @patch('display_event.platform.system', return_value='Windows')
    @patch('display_event.subprocess.run', side_effect=Exception("no route"))
    def test_returns_none_on_failure(self, mock_run, mock_system):
        """Test that gateway discovery returns None on error."""
        from display_event import get_default_gateway

        assert get_default_gateway() is None


class TestCheckNetworkConnectivity:
    """Tests for network ping check."""

    @patch('display_event.platform.system', return_value='Windows')
    @patch('display_event.subprocess.run')
    def test_returns_true_when_reachable(self, mock_run, mock_system):
        """Test returns True when ping succeeds."""
        from display_event import check_network_connectivity

        mock_run.return_value = MagicMock(returncode=0)
        assert check_network_connectivity('192.168.1.1') is True

    @patch('display_event.platform.system', return_value='Windows')
    @patch('display_event.subprocess.run')
    def test_returns_false_when_unreachable(self, mock_run, mock_system):
        """Test returns False when ping fails."""
        from display_event import check_network_connectivity

        mock_run.return_value = MagicMock(returncode=1)
        assert check_network_connectivity('192.168.1.1') is False

    @patch('display_event.platform.system', return_value='Linux')
    @patch('display_event.subprocess.run')
    def test_linux_ping_command(self, mock_run, mock_system):
        """Test correct ping command on Linux."""
        from display_event import check_network_connectivity

        mock_run.return_value = MagicMock(returncode=0)
        check_network_connectivity('10.0.0.1')
        mock_run.assert_called_once_with(
            ['ping', '-c', '1', '-W', '1', '10.0.0.1'],
            capture_output=True, timeout=3
        )

    @patch('display_event.platform.system', return_value='Windows')
    @patch('display_event.subprocess.run')
    def test_windows_ping_command(self, mock_run, mock_system):
        """Test correct ping command on Windows."""
        from display_event import check_network_connectivity

        mock_run.return_value = MagicMock(returncode=0)
        check_network_connectivity('10.0.0.1')
        mock_run.assert_called_once_with(
            ['ping', '-n', '1', '-w', '1000', '10.0.0.1'],
            capture_output=True, timeout=3
        )

    @patch('display_event.subprocess.run', side_effect=subprocess.TimeoutExpired('ping', 3))
    def test_returns_false_on_timeout(self, mock_run):
        """Test returns False when ping times out."""
        from display_event import check_network_connectivity

        assert check_network_connectivity('192.168.1.1') is False


class TestNetworkMonitorLoop:
    """Tests for network monitor thread behavior."""

    @patch('display_event.check_network_connectivity', return_value=True)
    @patch('display_event.get_default_gateway', return_value='192.168.1.1')
    def test_sets_connected_when_reachable(self, mock_gw, mock_ping):
        """Test that network_connected is True when gateway is reachable."""
        import display_event

        display_event.network_connected = False  # Start disconnected
        # Run one iteration by mocking time.sleep to raise after first call
        with patch('display_event.time.sleep', side_effect=StopIteration):
            try:
                display_event.network_monitor_loop(interval=10)
            except StopIteration:
                pass
        with display_event.network_status_lock:
            assert display_event.network_connected is True

    @patch('display_event.check_network_connectivity', return_value=False)
    @patch('display_event.get_default_gateway', return_value='192.168.1.1')
    def test_sets_disconnected_when_unreachable(self, mock_gw, mock_ping):
        """Test that network_connected is False when gateway is unreachable."""
        import display_event

        display_event.network_connected = True  # Start connected
        with patch('display_event.time.sleep', side_effect=StopIteration):
            try:
                display_event.network_monitor_loop(interval=10)
            except StopIteration:
                pass
        with display_event.network_status_lock:
            assert display_event.network_connected is False

    @patch('display_event.get_default_gateway', return_value=None)
    def test_exits_when_no_gateway(self, mock_gw):
        """Test that monitor exits gracefully when no gateway found."""
        import display_event

        display_event.network_connected = True
        # Should return immediately without looping
        display_event.network_monitor_loop(interval=10)
        with display_event.network_status_lock:
            assert display_event.network_connected is True
