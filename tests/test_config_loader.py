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


class TestAnimationModeRegistration:
    """Tests for the animation_display mode being wired into the config."""

    def test_mode_is_valid(self):
        from config_loader import VALID_MODES

        assert "animation_display" in VALID_MODES

    def test_defaults_cover_every_setting_the_mode_reads(self, temp_config_dir):
        from config_loader import load_mode_config

        cfg = load_mode_config(str(temp_config_dir), "animation_display")

        assert cfg == {
            "file": "",
            "fit": "contain",
            "fps": 0,
            "loop": True,
            "background": "#000000",
        }

    def test_file_setting_round_trips(self, temp_config_dir):
        from config_loader import (ensure_config_directory, load_mode_config,
                                   save_mode_config)

        ensure_config_directory(str(temp_config_dir))
        save_mode_config(str(temp_config_dir), "animation_display",
                         {"file": "logo.gif", "fit": "cover"})

        cfg = load_mode_config(str(temp_config_dir), "animation_display")
        assert cfg["file"] == "logo.gif"
        assert cfg["fit"] == "cover"
        # Untouched keys keep their defaults.
        assert cfg["loop"] is True

    def test_generated_settings_include_the_mode_section(self, temp_config_dir):
        import tomllib

        from config_loader import ensure_config_directory

        ensure_config_directory(str(temp_config_dir))
        with open(temp_config_dir / "settings.toml", "rb") as f:
            settings = tomllib.load(f)

        assert "animation_display" in settings["mode"]

    def test_animations_directory_is_created(self, temp_config_dir):
        from config_loader import ensure_config_directory

        ensure_config_directory(str(temp_config_dir))

        assert (temp_config_dir / "animations").is_dir()


class TestColorLightRowDelaySetting:
    """Tests for the optional [network].colorlight_row_delay_ms validation."""

    @staticmethod
    def _write(config_dir, sample_settings_dict, value=None):
        import tomli_w
        settings = dict(sample_settings_dict)
        settings["network"] = dict(settings["network"])
        if value is not None:
            settings["network"]["colorlight_row_delay_ms"] = value
        settings["files"] = {"lynx_file": "lynx.evt", "colors_file": "colors.csv"}
        (config_dir / "colors.csv").write_text("affiliation_name,display_name,background_hex,text_hex\n")
        with open(config_dir / "settings.toml", "wb") as f:
            tomli_w.dump(settings, f)
        return str(config_dir)

    def test_absent_is_accepted(self, temp_config_dir, sample_settings_dict):
        from config_loader import load_settings

        path = self._write(temp_config_dir, sample_settings_dict)
        assert "colorlight_row_delay_ms" not in load_settings(path)["network"]

    @pytest.mark.parametrize("value", [0, 0.25, 1.0, 5])
    def test_non_negative_numbers_are_accepted(self, temp_config_dir,
                                               sample_settings_dict, value):
        from config_loader import load_settings

        path = self._write(temp_config_dir, sample_settings_dict, value)
        assert load_settings(path)["network"]["colorlight_row_delay_ms"] == value

    @pytest.mark.parametrize("value", [-1, -0.5])
    def test_negative_values_are_rejected(self, temp_config_dir,
                                          sample_settings_dict, value):
        from config_loader import ConfigError, load_settings

        path = self._write(temp_config_dir, sample_settings_dict, value)
        with pytest.raises(ConfigError, match="colorlight_row_delay_ms"):
            load_settings(path)

    def test_non_numeric_is_rejected(self, temp_config_dir, sample_settings_dict):
        from config_loader import ConfigError, load_settings

        path = self._write(temp_config_dir, sample_settings_dict, "fast")
        with pytest.raises(ConfigError, match="colorlight_row_delay_ms"):
            load_settings(path)

    def test_boolean_is_rejected(self, temp_config_dir, sample_settings_dict):
        """bool is an int subclass, so it needs excluding explicitly."""
        from config_loader import ConfigError, load_settings

        path = self._write(temp_config_dir, sample_settings_dict, True)
        with pytest.raises(ConfigError, match="colorlight_row_delay_ms"):
            load_settings(path)
