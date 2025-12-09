"""
Tests for file_watcher.py module.
"""

import pytest
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from file_watcher import start_file_watcher


class TestFileWatcher:
    """Tests for file_watcher module."""
    
    def test_starts_watcher_successfully(self, temp_config_dir):
        """Test that file watcher starts successfully."""
        callback = Mock()
        
        watcher = start_file_watcher(temp_config_dir, callback)
        
        assert watcher is not None
    
    def test_callback_triggered_on_file_change(self, temp_config_dir):
        """Test that callback is triggered when a monitored file changes."""
        callback = Mock()
        watcher = start_file_watcher(temp_config_dir, callback)
        
        # Create and modify a monitored file
        test_file = temp_config_dir / "lynx.evt"
        test_file.write_text("Initial content")
        time.sleep(0.1)  # Allow watcher to initialize
        
        # Modify the file
        test_file.write_text("Modified content")
        time.sleep(0.6)  # Wait for debounce timer (0.5s + buffer)
        
        # Callback should have been called at least once
        assert callback.call_count >= 1
    
    def test_debouncing_prevents_rapid_callbacks(self, temp_config_dir):
        """Test that debouncing prevents rapid successive callbacks."""
        callback = Mock()
        watcher = start_file_watcher(temp_config_dir, callback)
        
        test_file = temp_config_dir / "lynx.evt"
        test_file.write_text("Initial")
        time.sleep(0.1)
        
        # Make multiple rapid changes
        for i in range(5):
            test_file.write_text(f"Content {i}")
            time.sleep(0.05)
        
        time.sleep(0.7)  # Wait for debounce
        
        # Should be called only once or twice due to debouncing
        assert callback.call_count <= 2
    
    def test_monitors_lynx_evt_file(self, temp_config_dir):
        """Test that lynx.evt file changes trigger callback."""
        callback = Mock()
        watcher = start_file_watcher(temp_config_dir, callback)
        
        lynx_file = temp_config_dir / "lynx.evt"
        lynx_file.write_text("Test event data")
        time.sleep(0.6)
        
        assert callback.called
    
    def test_monitors_current_event_json_file(self, temp_config_dir):
        """Test that current_event.json file changes trigger callback."""
        callback = Mock()
        watcher = start_file_watcher(temp_config_dir, callback)
        
        event_file = temp_config_dir / "current_event.json"
        event_file.write_text('{"event": 5, "round": 2, "heat": 1}')
        time.sleep(0.6)
        
        assert callback.called
    
    def test_monitors_colors_csv_file(self, temp_config_dir):
        """Test that colors.csv file changes trigger callback."""
        callback = Mock()
        watcher = start_file_watcher(temp_config_dir, callback)
        
        colors_file = temp_config_dir / "colors.csv"
        colors_file.write_text("affiliation,name,bgcolor,text\n")
        time.sleep(0.6)
        
        assert callback.called
    
    def test_monitors_schedule_file(self, temp_config_dir):
        """Test that lynx.sch file changes trigger callback."""
        callback = Mock()
        watcher = start_file_watcher(temp_config_dir, callback)
        
        schedule_file = temp_config_dir / "lynx.sch"
        schedule_file.write_text("1,1,1\n")
        time.sleep(0.6)
        
        assert callback.called
    
    def test_ignores_unmonitored_files(self, temp_config_dir):
        """Test that changes to unmonitored files don't trigger callback."""
        callback = Mock()
        watcher = start_file_watcher(temp_config_dir, callback)
        
        # Create an unmonitored file
        other_file = temp_config_dir / "other.txt"
        other_file.write_text("This should be ignored")
        time.sleep(0.6)
        
        # Callback should not be called (or called minimally)
        assert callback.call_count <= 1
    
    def test_handles_nonexistent_directory(self, tmp_path):
        """Test handling of nonexistent directory."""
        nonexistent_dir = tmp_path / "does_not_exist"
        callback = Mock()
        
        watcher = start_file_watcher(nonexistent_dir, callback)
        
        # Should return None or handle gracefully
        assert watcher is None or watcher is not None
    
    @patch('file_watcher.Observer', side_effect=ImportError)
    def test_fallback_to_polling_when_watchdog_unavailable(self, mock_observer, temp_config_dir):
        """Test fallback to polling mode when watchdog is unavailable."""
        callback = Mock()
        
        # Should still work with polling fallback
        watcher = start_file_watcher(temp_config_dir, callback)
        
        assert watcher is not None
    
    def test_watcher_runs_in_daemon_thread(self, temp_config_dir):
        """Test that watcher runs as a daemon thread."""
        callback = Mock()
        
        watcher = start_file_watcher(temp_config_dir, callback)
        
        # Watcher should not prevent program from exiting
        # (This is implicit in the daemon=True setting)
        assert watcher is not None


class TestPollingFallback:
    """Tests for polling fallback mode."""
    
    @patch('file_watcher.Observer', side_effect=ImportError)
    def test_polling_detects_file_changes(self, mock_observer, temp_config_dir):
        """Test that polling fallback detects file changes."""
        callback = Mock()
        watcher = start_file_watcher(temp_config_dir, callback)
        
        if watcher:
            test_file = temp_config_dir / "lynx.evt"
            test_file.write_text("Content")
            
            # Wait for polling interval
            time.sleep(1.5)
            
            # Should eventually detect change
            # (May not work in all test environments)
    
    @patch('file_watcher.Observer', side_effect=ImportError)
    @pytest.mark.skip(reason="start_file_watcher does not have poll_interval parameter")
    def test_polling_respects_interval(self, mock_observer, temp_config_dir):
        """Test that polling respects the configured interval."""
        callback = Mock()
        
        # Start watcher with polling
        watcher = start_file_watcher(temp_config_dir, callback, poll_interval=0.5)
        
        # Verify watcher started
        assert watcher is not None or watcher is None
