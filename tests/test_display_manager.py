"""
Tests for display_manager.py mode registry.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config_loader import ConfigError, VALID_MODES
from display_manager import MODES, _build_animation_args


class TestModeRegistry:
    """The registry and config_loader's mode list must not drift apart."""

    def test_registry_matches_valid_modes(self):
        assert sorted(MODES) == sorted(VALID_MODES)

    @pytest.mark.parametrize("mode", list(MODES))
    def test_every_mode_names_a_script_that_exists(self, mode):
        script = Path(__file__).parent.parent / MODES[mode]["script"]
        assert script.exists(), f"{mode} points at a missing script"

    @pytest.mark.parametrize("mode", list(MODES))
    def test_every_mode_has_a_label_and_arg_builder(self, mode):
        assert MODES[mode]["label"]
        assert callable(MODES[mode]["build_args"])


class TestBuildAnimationArgs:
    """Tests for the animation_display command line the manager constructs."""

    @staticmethod
    def _config(tmp_path, **mode_values):
        import tomli_w
        settings = {"mode": {"animation_display": mode_values}}
        with open(tmp_path / "settings.toml", "wb") as f:
            tomli_w.dump(settings, f)
        return str(tmp_path)

    def test_passes_config_dir_and_file(self, tmp_path):
        config_dir = self._config(tmp_path, file="logo.gif")

        args = _build_animation_args(config_dir)

        assert args == ["--config-dir", config_dir, "--file", "logo.gif"]

    def test_adds_no_loop_when_looping_is_off(self, tmp_path):
        config_dir = self._config(tmp_path, file="logo.gif", loop=False)

        assert "--no-loop" in _build_animation_args(config_dir)

    def test_omits_no_loop_by_default(self, tmp_path):
        config_dir = self._config(tmp_path, file="logo.gif")

        assert "--no-loop" not in _build_animation_args(config_dir)

    @pytest.mark.parametrize("value", ["", "   "])
    def test_missing_file_raises_a_config_error(self, tmp_path, value):
        config_dir = self._config(tmp_path, file=value)

        with pytest.raises(ConfigError, match="requires 'file'"):
            _build_animation_args(config_dir)

    def test_unset_file_raises_a_config_error(self, tmp_path):
        # A ConfigError here is what makes the manager log and stop, rather
        # than crash-looping the child every restart_backoff_sec.
        config_dir = self._config(tmp_path)

        with pytest.raises(ConfigError, match="requires 'file'"):
            _build_animation_args(config_dir)
