"""
Tests for animation_loader.py module.
"""

import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from animation_loader import (DEFAULT_VIDEO_FPS, FALLBACK_FRAME_DURATION,
                              SUPPORTED_EXTENSIONS, AnimationError,
                              build_ffmpeg_filter, find_ffmpeg, fit_frame,
                              load_animation, scaled_size)

has_ffmpeg = shutil.which("ffmpeg") is not None
skipif_no_ffmpeg = pytest.mark.skipif(not has_ffmpeg, reason="ffmpeg not installed")


def write_gif(path, size=(20, 10), frames=3, duration=80, colors=None):
    """Write a simple multi-frame GIF and return its path."""
    colors = colors or [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    images = [Image.new("RGB", size, colors[i % len(colors)]) for i in range(frames)]
    images[0].save(path, save_all=True, append_images=images[1:],
                   duration=duration, loop=0)
    return path


class TestScaledSize:
    """Tests for scaled_size geometry."""

    def test_stretch_ignores_aspect_ratio(self):
        assert scaled_size(10, 100, 64, 32, "stretch") == (64, 32)

    def test_contain_fits_inside_the_panel(self):
        # 100x50 source into a 64x64 panel: width is the binding constraint.
        assert scaled_size(100, 50, 64, 64, "contain") == (64, 32)

    def test_cover_fills_the_panel(self):
        # Same source under cover: height binds, width overflows and is cropped.
        assert scaled_size(100, 50, 64, 64, "cover") == (128, 64)

    def test_square_source_on_square_panel_is_exact(self):
        assert scaled_size(32, 32, 128, 128, "contain") == (128, 128)

    def test_rejects_unknown_fit_mode(self):
        with pytest.raises(AnimationError, match="Unknown fit mode"):
            scaled_size(10, 10, 64, 64, "squish")

    def test_rejects_zero_dimension_source(self):
        with pytest.raises(AnimationError, match="Invalid source dimensions"):
            scaled_size(0, 10, 64, 64, "contain")


class TestFitFrame:
    """Tests for fit_frame output size and letterboxing."""

    @pytest.mark.parametrize("fit", ["contain", "cover", "stretch"])
    def test_always_returns_panel_sized_frame(self, fit):
        source = Image.new("RGB", (100, 37), (255, 255, 255))
        result = fit_frame(source, 128, 128, fit)
        assert result.size == (128, 128)

    def test_contain_letterboxes_with_background(self):
        # A wide source on a square panel leaves bars top and bottom.
        source = Image.new("RGB", (100, 50), (255, 255, 255))
        result = fit_frame(source, 64, 64, "contain", background=(10, 20, 30))

        assert result.getpixel((32, 0)) == (10, 20, 30)      # top bar
        assert result.getpixel((32, 63)) == (10, 20, 30)     # bottom bar
        assert result.getpixel((32, 32)) == (255, 255, 255)  # image itself

    def test_cover_leaves_no_background_showing(self):
        source = Image.new("RGB", (100, 50), (255, 255, 255))
        result = fit_frame(source, 64, 64, "cover", background=(10, 20, 30))

        colors = {result.getpixel((x, y)) for x in (0, 32, 63) for y in (0, 32, 63)}
        assert colors == {(255, 255, 255)}


class TestLoadGif:
    """Tests for the Pillow decoding path."""

    def test_decodes_every_frame_at_panel_size(self, tmp_path):
        gif = write_gif(tmp_path / "clip.gif", frames=3)
        animation = load_animation(gif, 64, 64)

        assert len(animation) == 3
        assert all(frame.size == (64, 64) for frame in animation.frames)
        assert animation.width == 64 and animation.height == 64

    def test_reads_per_frame_duration_from_the_file(self, tmp_path):
        gif = write_gif(tmp_path / "clip.gif", frames=2, duration=120)
        animation = load_animation(gif, 32, 32)

        assert animation.durations == pytest.approx([0.12, 0.12])
        assert animation.total_duration == pytest.approx(0.24)

    def test_zero_duration_falls_back_to_a_sane_delay(self, tmp_path):
        # Authoring tools emit 0 for "as fast as possible"; browsers substitute
        # 100ms and so do we, otherwise the schedule collapses.
        gif = write_gif(tmp_path / "fast.gif", frames=2, duration=0)
        animation = load_animation(gif, 32, 32)

        assert animation.durations == [FALLBACK_FRAME_DURATION] * 2

    def test_fps_override_replaces_source_timing(self, tmp_path):
        gif = write_gif(tmp_path / "clip.gif", frames=4, duration=500)
        animation = load_animation(gif, 32, 32, fps=10)

        assert animation.durations == pytest.approx([0.1] * 4)

    def test_max_frames_truncates_and_flags(self, tmp_path):
        gif = write_gif(tmp_path / "long.gif", frames=10)
        animation = load_animation(gif, 32, 32, max_frames=4)

        assert len(animation) == 4
        assert animation.truncated is True

    def test_transparency_is_flattened_onto_the_background(self, tmp_path):
        # A fully transparent GIF frame must take the background colour, not
        # black, or the background setting silently does nothing.
        path = tmp_path / "transparent.gif"
        frame = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        frame.save(path, save_all=True, append_images=[frame], duration=100,
                   transparency=0, disposal=2)

        animation = load_animation(path, 16, 16, fit="stretch", background=(0, 0, 255))
        assert animation.frames[0].getpixel((8, 8)) == (0, 0, 255)

    def test_single_frame_png_loads_as_a_one_frame_animation(self, tmp_path):
        path = tmp_path / "still.png"
        Image.new("RGB", (40, 40), (12, 34, 56)).save(path)

        animation = load_animation(path, 32, 32)
        assert len(animation) == 1


class TestLoadErrors:
    """Tests for the error paths callers surface to the user."""

    def test_missing_file(self, tmp_path):
        with pytest.raises(AnimationError, match="not found"):
            load_animation(tmp_path / "nope.gif", 64, 64)

    def test_directory_is_not_a_file(self, tmp_path):
        with pytest.raises(AnimationError, match="Not a file"):
            load_animation(tmp_path, 64, 64)

    def test_unsupported_extension_lists_what_is_supported(self, tmp_path):
        path = tmp_path / "notes.txt"
        path.write_text("hello")

        with pytest.raises(AnimationError, match="Unsupported file type") as exc:
            load_animation(path, 64, 64)
        assert ".gif" in str(exc.value)

    def test_corrupt_image_reports_cleanly(self, tmp_path):
        path = tmp_path / "broken.gif"
        path.write_bytes(b"GIF89a not really a gif")

        with pytest.raises(AnimationError, match="Could not open image"):
            load_animation(path, 64, 64)

    def test_missing_ffmpeg_names_the_package(self, tmp_path):
        path = tmp_path / "clip.mp4"
        path.write_bytes(b"\x00" * 64)

        with patch('animation_loader.find_ffmpeg', return_value=None):
            with pytest.raises(AnimationError, match="apt install ffmpeg"):
                load_animation(path, 64, 64)


class TestFfmpegFilter:
    """Tests for the ffmpeg filter graph, which mirrors the Pillow geometry."""

    def test_contain_scales_down_then_pads(self):
        chain = build_ffmpeg_filter(128, 64, "contain", 15, (0, 0, 0))

        assert "force_original_aspect_ratio=decrease" in chain
        assert "pad=128:64" in chain
        assert "color=0x000000" in chain

    def test_cover_scales_up_then_crops(self):
        chain = build_ffmpeg_filter(128, 64, "cover", 15, (0, 0, 0))

        assert "force_original_aspect_ratio=increase" in chain
        assert "crop=128:64" in chain

    def test_stretch_is_a_bare_scale(self):
        chain = build_ffmpeg_filter(128, 64, "stretch", 15, (0, 0, 0))

        assert "scale=128:64" in chain
        assert "pad=" not in chain and "crop=" not in chain

    def test_background_colour_is_passed_through_as_hex(self):
        chain = build_ffmpeg_filter(64, 64, "contain", 10, (255, 128, 0))
        assert "color=0xFF8000" in chain

    def test_fps_stage_comes_first(self):
        # The fps filter must precede scaling so ffmpeg drops frames before
        # spending time resampling them.
        chain = build_ffmpeg_filter(64, 64, "contain", 12.5, (0, 0, 0))
        assert chain.startswith("fps=12.5,")

    def test_rejects_unknown_fit_mode(self):
        with pytest.raises(AnimationError, match="Unknown fit mode"):
            build_ffmpeg_filter(64, 64, "squish", 15, (0, 0, 0))


class TestFindFfmpeg:
    """Tests for ffmpeg discovery."""

    def test_returns_none_when_absent(self):
        with patch('animation_loader.shutil.which', return_value=None):
            assert find_ffmpeg() is None

    def test_explicit_path_is_checked_before_use(self, tmp_path):
        missing = tmp_path / "not-ffmpeg"
        with patch('animation_loader.shutil.which', return_value=None):
            assert find_ffmpeg(str(missing)) is None


@skipif_no_ffmpeg
class TestLoadVideo:
    """Tests for the ffmpeg decoding path. Requires ffmpeg on PATH."""

    @staticmethod
    def _make_mp4(path, seconds=1, fps=10, size="32x32"):
        import subprocess
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
             "-i", f"testsrc=duration={seconds}:size={size}:rate={fps}",
             "-pix_fmt", "yuv420p", str(path)],
            check=True,
        )
        return path

    def test_decodes_video_at_the_default_rate(self, tmp_path):
        clip = self._make_mp4(tmp_path / "clip.mp4", seconds=1, fps=30)
        animation = load_animation(clip, 64, 64)

        # One second decoded at DEFAULT_VIDEO_FPS regardless of source rate.
        assert len(animation) == pytest.approx(DEFAULT_VIDEO_FPS, abs=2)
        assert all(frame.size == (64, 64) for frame in animation.frames)

    def test_explicit_fps_controls_the_frame_count(self, tmp_path):
        clip = self._make_mp4(tmp_path / "clip.mp4", seconds=2, fps=30)
        animation = load_animation(clip, 32, 32, fps=5)

        assert len(animation) == pytest.approx(10, abs=2)
        assert animation.durations[0] == pytest.approx(0.2)

    def test_max_frames_truncates_video_too(self, tmp_path):
        clip = self._make_mp4(tmp_path / "clip.mp4", seconds=2, fps=30)
        animation = load_animation(clip, 32, 32, max_frames=3)

        assert len(animation) == 3
        assert animation.truncated is True


class TestSupportedExtensions:
    """Tests for the extension allowlist the web upload shares."""

    def test_covers_both_decoders(self):
        assert ".gif" in SUPPORTED_EXTENSIONS
        assert ".mp4" in SUPPORTED_EXTENSIONS

    def test_every_entry_is_a_lowercase_dotted_suffix(self):
        for ext in SUPPORTED_EXTENSIONS:
            assert ext.startswith(".") and ext == ext.lower()
