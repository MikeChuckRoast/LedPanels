"""
Tests for animation_display.py module.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from animation_display import (MIN_SLEEP, FrameScheduler, play,
                               resolve_animation_path)
from animation_loader import Animation, AnimationError


class TestFrameSchedulerLooping:
    """Tests for frame lookup when the clip repeats."""

    def setup_method(self):
        self.scheduler = FrameScheduler([0.1, 0.1, 0.1], loop=True)

    def test_total_is_the_sum_of_durations(self):
        assert self.scheduler.total == pytest.approx(0.3)
        assert len(self.scheduler) == 3

    @pytest.mark.parametrize("elapsed,expected", [
        (0.0, 0),
        (0.05, 0),
        (0.1, 1),
        (0.15, 1),
        (0.25, 2),
    ])
    def test_maps_elapsed_time_onto_the_right_frame(self, elapsed, expected):
        assert self.scheduler.frame_at(elapsed) == expected

    def test_wraps_around_after_a_full_pass(self):
        assert self.scheduler.frame_at(0.35) == 0
        assert self.scheduler.frame_at(0.45) == 1
        assert self.scheduler.frame_at(3.05) == 0

    def test_negative_elapsed_clamps_to_the_first_frame(self):
        assert self.scheduler.frame_at(-1.0) == 0

    def test_next_boundary_advances_across_cycles(self):
        assert self.scheduler.next_boundary(0.0) == pytest.approx(0.1)
        assert self.scheduler.next_boundary(0.25) == pytest.approx(0.3)
        assert self.scheduler.next_boundary(0.35) == pytest.approx(0.4)


class TestFrameSchedulerOnce:
    """Tests for frame lookup when the clip plays once."""

    def setup_method(self):
        self.scheduler = FrameScheduler([0.1, 0.1, 0.1], loop=False)

    def test_plays_through_to_the_last_frame(self):
        assert self.scheduler.frame_at(0.29) == 2

    def test_returns_none_once_the_clip_is_over(self):
        # Compared against .total rather than a hand-summed 0.3: accumulating
        # three 0.1s durations lands on 0.30000000000000004, and the end of the
        # clip is wherever that accumulation actually puts it.
        assert self.scheduler.frame_at(self.scheduler.total) is None
        assert self.scheduler.frame_at(99.0) is None

    def test_next_boundary_ends_with_the_clip(self):
        assert self.scheduler.next_boundary(0.25) == pytest.approx(0.3)
        assert self.scheduler.next_boundary(self.scheduler.total) is None


class TestFrameSchedulerEdgeCases:
    """Tests for degenerate schedules."""

    def test_empty_schedule_has_no_frames(self):
        scheduler = FrameScheduler([], loop=True)

        assert scheduler.frame_at(0.0) is None
        assert scheduler.next_boundary(0.0) is None

    def test_zero_durations_are_floored_rather_than_collapsing(self):
        # A zero-length frame would make total 0 and the modulo in frame_at
        # divide by zero, spinning the playback loop.
        scheduler = FrameScheduler([0.0, 0.0], loop=True)

        assert scheduler.total > 0
        assert scheduler.frame_at(0.0) == 0

    def test_single_frame_clip_never_advances(self):
        scheduler = FrameScheduler([0.5], loop=True)

        assert scheduler.frame_at(0.0) == 0
        assert scheduler.frame_at(10.0) == 0


# ---------------------------------------------------------------------------
# Playback loop, driven by a fake clock so timing is deterministic
# ---------------------------------------------------------------------------

class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeStopEvent:
    """Stands in for threading.Event, advancing the clock instead of sleeping."""

    def __init__(self, clock):
        self.clock = clock
        self._set = False

    def is_set(self):
        return self._set

    def set(self):
        self._set = True

    def wait(self, timeout=None):
        self.clock.advance(timeout or 0)
        return self._set


class FakeMatrix:
    def __init__(self, clock, swap_cost=0.0):
        self.clock = clock
        self.swap_cost = swap_cost
        self.shown = []

    def SwapOnVSync(self, canvas):
        self.clock.advance(self.swap_cost)
        return canvas


class FakeCanvas:
    def __init__(self, matrix):
        self.matrix = matrix

    def SetImage(self, image, offset_x=0, offset_y=0):
        self.matrix.shown.append(image)

    def Clear(self):
        pass


def make_animation(count, duration=0.1, size=(8, 8)):
    """Build an Animation whose frames are distinguishable by identity."""
    frames = [Image.new("RGB", size, (i, i, i)) for i in range(count)]
    return Animation(frames=frames, durations=[duration] * count,
                     width=size[0], height=size[1])


class TestPlay:
    """Tests for the playback loop."""

    def _run(self, animation, loop, swap_cost):
        clock = FakeClock()
        matrix = FakeMatrix(clock, swap_cost=swap_cost)
        canvas = FakeCanvas(matrix)
        scheduler = FrameScheduler(animation.durations, loop=loop)
        stop_event = FakeStopEvent(clock)

        outcome, _ = play(matrix, canvas, animation, scheduler, stop_event,
                          None, clock=clock)

        shown = [animation.frames.index(image) for image in matrix.shown]
        return outcome, shown

    def test_fast_panel_shows_every_frame_once(self):
        animation = make_animation(5)
        outcome, shown = self._run(animation, loop=False, swap_cost=0.0)

        assert outcome == "finished"
        assert shown == [0, 1, 2, 3, 4]

    def test_slow_panel_drops_frames_instead_of_falling_behind(self):
        # 10 frames of 0.1s is a 1s clip; a 0.35s panel write cannot keep up.
        animation = make_animation(10)
        outcome, shown = self._run(animation, loop=False, swap_cost=0.35)

        assert outcome == "finished"
        assert len(shown) < 10
        # Whatever it managed to show must still be in order and in-bounds:
        # playback keeps real time by skipping ahead, never by rewinding.
        assert shown == sorted(shown)
        assert len(set(shown)) == len(shown)

    def test_stop_event_ends_a_looping_clip(self):
        clock = FakeClock()
        matrix = FakeMatrix(clock, swap_cost=0.0)
        canvas = FakeCanvas(matrix)
        animation = make_animation(3)
        scheduler = FrameScheduler(animation.durations, loop=True)

        class StopAfterTwo(FakeStopEvent):
            def is_set(inner):
                return len(matrix.shown) >= 2

        outcome, _ = play(matrix, canvas, animation, scheduler,
                          StopAfterTwo(clock), None, clock=clock)

        assert outcome == "stopped"

    def test_every_pass_advances_the_clock(self):
        """The loop must always yield, even when it is exactly on a boundary.

        Frame boundaries are accumulated floats, so the time left before the
        next one rounds to zero (or below) fairly often. Sleeping only on a
        strictly positive remainder spins the loop against the clock — with a
        fake clock that never advances on its own, it hangs outright.
        """
        clock = FakeClock()
        matrix = FakeMatrix(clock, swap_cost=0.0)
        canvas = FakeCanvas(matrix)
        animation = make_animation(3)
        scheduler = FrameScheduler(animation.durations, loop=True)

        class RecordingStop(FakeStopEvent):
            def __init__(inner, clock):
                super().__init__(clock)
                inner.waits = []

            def wait(inner, timeout=None):
                inner.waits.append(timeout)
                # play() checks is_set(), not wait()'s return value.
                if len(inner.waits) >= 50:
                    inner.set()
                return super().wait(timeout)

        stop_event = RecordingStop(clock)
        outcome, _ = play(matrix, canvas, animation, scheduler, stop_event,
                          None, clock=clock)

        assert outcome == "stopped"
        assert len(stop_event.waits) == 50
        assert all(w >= MIN_SLEEP for w in stop_event.waits)
        assert clock.now > 1000.0

    def test_reloads_when_the_source_file_changes(self, tmp_path):
        source = tmp_path / "clip.gif"
        source.write_bytes(b"original")

        clock = FakeClock()
        matrix = FakeMatrix(clock, swap_cost=0.0)
        canvas = FakeCanvas(matrix)
        animation = make_animation(3)
        scheduler = FrameScheduler(animation.durations, loop=True)

        fingerprints = [(1.0, 8), (1.0, 8), (2.0, 99)]

        with patch('animation_display._source_fingerprint',
                   side_effect=lambda _p: fingerprints[min(len(fingerprints) - 1,
                                                           len(matrix.shown))]):
            outcome, _ = play(matrix, canvas, animation, scheduler,
                              FakeStopEvent(clock), source, clock=clock)

        assert outcome == "reload"


class TestResolveAnimationPath:
    """Tests for turning a configured filename into a path."""

    def test_bare_name_resolves_into_the_animations_directory(self):
        result = resolve_animation_path("./config", "logo.gif")
        assert result == Path("./config") / "animations" / "logo.gif"

    def test_absolute_path_is_used_as_given(self, tmp_path):
        absolute = tmp_path / "elsewhere" / "clip.mp4"
        assert resolve_animation_path("./config", str(absolute)) == absolute

    def test_relative_path_with_a_separator_is_config_relative(self):
        result = resolve_animation_path("./config", "extras/clip.gif")
        assert result == Path("./config") / "extras" / "clip.gif"

    def test_surrounding_whitespace_is_ignored(self):
        result = resolve_animation_path("./config", "  logo.gif  ")
        assert result.name == "logo.gif"

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_empty_setting_explains_what_to_do(self, value):
        with pytest.raises(AnimationError, match="No animation file configured"):
            resolve_animation_path("./config", value)
