"""
Pytest configuration and shared fixtures for LED Panels tests.
"""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory for tests."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def sample_settings_dict() -> Dict[str, Any]:
    """Return a sample settings dictionary for testing."""
    return {
        "hardware": {
            "width": 64,
            "height": 32,
            "chain": 2,
            "parallel": 4,
            "gpio_slowdown": 3
        },
        "display": {
            "line_height": 24,
            "header_line_height": 16,
            "header_rows": 2,
            "interval": 2.0,
            "font_shift": 7
        },
        "fonts": {
            "font_path": "/path/to/font.bdf"
        },
        "files": {
            "lynx_file": "lynx.evt",
            "colors_file": "colors.csv"
        },
        "network": {
            "fpp_enabled": False,
            "fpp_host": "127.0.0.1",
            "fpp_port": 4048,
            "colorlight_enabled": False,
            "colorlight_interface": "eth0"
        },
        "keyboard": {
            "device_path": ""
        },
        "behavior": {
            "once": False
        },
        "monitoring": {
            "file_watch_enabled": True,
            "poll_interval": 1.0
        },
        "web": {
            "web_enabled": True,
            "web_host": "0.0.0.0",
            "web_port": 5000
        }
    }


@pytest.fixture
def sample_current_event_dict() -> Dict[str, int]:
    """Return a sample current event dictionary."""
    return {
        "event": 1,
        "round": 1,
        "heat": 1
    }


@pytest.fixture
def fixture_path():
    """Return the path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def lynx_evt_fixture(fixture_path) -> Path:
    """Return path to sample lynx.evt fixture file."""
    return fixture_path / "sample_lynx.evt"


@pytest.fixture
def colors_csv_fixture(fixture_path) -> Path:
    """Return path to sample colors.csv fixture file."""
    return fixture_path / "sample_colors.csv"


@pytest.fixture
def settings_toml_fixture(fixture_path) -> Path:
    """Return path to sample settings.toml fixture file."""
    return fixture_path / "sample_settings.toml"


@pytest.fixture
def schedule_fixture(fixture_path) -> Path:
    """Return path to sample lynx.sch fixture file."""
    return fixture_path / "sample_schedule.sch"


@pytest.fixture
def populated_config_dir(temp_config_dir, lynx_evt_fixture, colors_csv_fixture):
    """Create a config directory populated with sample files."""
    import shutil

    # Copy fixture files to temp config directory
    shutil.copy(lynx_evt_fixture, temp_config_dir / "lynx.evt")
    shutil.copy(colors_csv_fixture, temp_config_dir / "colors.csv")

    # Create current_event.json
    current_event = {"event": 1, "round": 1, "heat": 1}
    (temp_config_dir / "current_event.json").write_text(json.dumps(current_event, indent=2))

    return temp_config_dir


@pytest.fixture
def mock_matrix():
    """Create a mock RGB matrix object for testing."""
    class MockMatrix:
        def __init__(self, width=128, height=128):
            self.width = width
            self.height = height
            self.brightness = 100
            self.pwm_bits = 11

        def SetPixel(self, x, y, r, g, b):
            pass

        def Clear(self):
            pass

        def Fill(self, r, g, b):
            pass

    return MockMatrix()


@pytest.fixture
def mock_graphics():
    """Create a mock graphics/canvas object for testing."""
    class MockCanvas:
        def __init__(self, matrix=None):
            self.matrix = matrix

        def Clear(self):
            pass

        def Fill(self, r, g, b):
            pass

    return MockCanvas()


@pytest.fixture
def mock_font():
    """Create a mock font object for testing."""
    class MockFont:
        def __init__(self, path=None):
            self.path = path
            self.height = 12

        def CharacterWidth(self, char):
            return 8

    return MockFont()
