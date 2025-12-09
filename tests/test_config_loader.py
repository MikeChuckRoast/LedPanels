"""
Tests for config_loader.py module.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config_loader import (ConfigError, ensure_config_directory,
                           load_current_event, load_settings)


class TestEnsureConfigDirectory:
    """Tests for ensure_config_directory function."""

    def test_creates_config_directory(self, tmp_path):
        """Test that config directory is created if it doesn't exist."""
        config_dir = tmp_path / "config"
        assert not config_dir.exists()

        ensure_config_directory(str(config_dir))

        assert config_dir.exists()
        assert config_dir.is_dir()

    def test_creates_default_current_event_json(self, tmp_path):
        """Test that default current_event.json is created."""
        config_dir = tmp_path / "config"

        ensure_config_directory(str(config_dir))

        current_event_file = config_dir / "current_event.json"
        assert current_event_file.exists()

        with open(current_event_file) as f:
            data = json.load(f)

        assert data == {"event": 1, "round": 1, "heat": 1}

    def test_does_not_overwrite_existing_current_event(self, tmp_path):
        """Test that existing current_event.json is not overwritten."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        current_event_file = config_dir / "current_event.json"
        existing_data = {"event": 5, "round": 2, "heat": 3}
        current_event_file.write_text(json.dumps(existing_data))

        ensure_config_directory(str(config_dir))

        with open(current_event_file) as f:
            data = json.load(f)

        assert data == existing_data

    def test_creates_default_settings_toml(self, tmp_path):
        """Test that default settings.toml is created."""
        config_dir = tmp_path / "config"

        ensure_config_directory(str(config_dir))

        settings_file = config_dir / "settings.toml"
        assert settings_file.exists()

        content = settings_file.read_text()
        assert "[hardware]" in content
        assert "[display]" in content
        assert "[fonts]" in content


class TestLoadCurrentEvent:
    """Tests for load_current_event function."""

    def test_loads_valid_current_event(self, temp_config_dir):
        """Test loading a valid current_event.json file."""
        current_event_file = temp_config_dir / "current_event.json"
        event_data = {"event": 3, "round": 2, "heat": 1}
        current_event_file.write_text(json.dumps(event_data))

        result = load_current_event(str(temp_config_dir))

        assert result == event_data

    def test_missing_file_raises_error(self, temp_config_dir):
        """Test that missing file raises ConfigError."""
        with pytest.raises(ConfigError, match="not found"):
            load_current_event(str(temp_config_dir))

    def test_invalid_json_raises_error(self, temp_config_dir):
        """Test that invalid JSON raises ConfigError."""
        current_event_file = temp_config_dir / "current_event.json"
        current_event_file.write_text("{ invalid json }")

        with pytest.raises(ConfigError, match="Invalid JSON"):
            load_current_event(str(temp_config_dir))

    def test_missing_required_fields_raises_error(self, temp_config_dir):
        """Test that missing required fields raises ConfigError."""
        current_event_file = temp_config_dir / "current_event.json"

        # Missing 'heat' field
        incomplete_data = {"event": 1, "round": 1}
        current_event_file.write_text(json.dumps(incomplete_data))

        with pytest.raises(ConfigError, match="Missing required field"):
            load_current_event(str(temp_config_dir))

    @pytest.mark.parametrize("field,value", [
        ("event", 0),
        ("event", -1),
        ("round", 0),
        ("heat", -5),
    ])
    def test_invalid_field_values_raise_error(self, temp_config_dir, field, value):
        """Test that invalid field values raise ConfigError."""
        current_event_file = temp_config_dir / "current_event.json"
        event_data = {"event": 1, "round": 1, "heat": 1}
        event_data[field] = value
        current_event_file.write_text(json.dumps(event_data))

        with pytest.raises(ConfigError, match="must be >= 1"):
            load_current_event(str(temp_config_dir))


class TestLoadSettings:
    """Tests for load_settings function."""

    def test_loads_valid_settings_toml(self, temp_config_dir, settings_toml_fixture):
        """Test loading a valid settings.toml file."""
        import shutil
        shutil.copy(settings_toml_fixture, temp_config_dir / "settings.toml")

        # Create lynx.evt and colors.csv that config_loader validates exist
        (temp_config_dir / "lynx.evt").write_text("Event 1    Test Event\n")
        (temp_config_dir / "colors.csv").write_text("affiliation,name,bgcolor,fgcolor\n")

        settings = load_settings(str(temp_config_dir))

        assert "hardware" in settings
        assert "display" in settings
        assert "fonts" in settings
        assert settings["hardware"]["width"] == 64
        assert settings["hardware"]["height"] == 32

    def test_missing_file_raises_error(self, temp_config_dir):
        """Test that missing settings.toml raises ConfigError."""
        with pytest.raises(ConfigError, match="not found"):
            load_settings(str(temp_config_dir))

    def test_invalid_toml_raises_error(self, temp_config_dir):
        """Test that invalid TOML raises ConfigError."""
        settings_file = temp_config_dir / "settings.toml"
        settings_file.write_text("[invalid toml\nmissing closing bracket")

        with pytest.raises(ConfigError, match="Invalid TOML"):
            load_settings(str(temp_config_dir))
