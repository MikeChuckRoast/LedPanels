"""
Tests for display_utils.py text measurement, layout, and rendering utilities.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from display_utils import (calculate_text_baseline, measure_text_width,
                           truncate_text_to_width, wrap_text_lines)


class MockFont:
    """Mock font where each character is 8 pixels wide."""

    def CharacterWidth(self, char_ord):
        return 8


class NarrowFont:
    """Mock font where each character is 5 pixels wide."""

    def CharacterWidth(self, char_ord):
        return 5


class BrokenFont:
    """Mock font that raises on CharacterWidth."""

    def CharacterWidth(self, char_ord):
        raise AttributeError("no width")


class TestMeasureTextWidth:
    """Tests for measure_text_width."""

    def test_measures_empty_string(self):
        assert measure_text_width(MockFont(), "") == 0

    def test_measures_single_char(self):
        assert measure_text_width(MockFont(), "A") == 8

    def test_measures_multiple_chars(self):
        assert measure_text_width(MockFont(), "Hello") == 40

    def test_measures_with_spaces(self):
        # Spaces are characters too
        assert measure_text_width(MockFont(), "A B") == 24

    def test_fallback_on_broken_font(self):
        # Fallback is max(1, len(text)) * 6
        result = measure_text_width(BrokenFont(), "Hello")
        assert result == 30  # 5 * 6

    def test_fallback_empty_string_broken_font(self):
        result = measure_text_width(BrokenFont(), "")
        # Empty string: sum of empty sequence = 0 via try path
        # Actually the try block does sum() over empty string which is 0
        assert result == 0


class TestTruncateTextToWidth:
    """Tests for truncate_text_to_width."""

    def test_returns_text_unchanged_if_fits(self):
        font = MockFont()
        # "Hi" = 16px, max_width = 100
        assert truncate_text_to_width(font, "Hi", 100) == "Hi"

    def test_truncates_to_fit(self):
        font = MockFont()
        # "Hello" = 40px, max_width = 24 -> need 3 chars max
        result = truncate_text_to_width(font, "Hello", 24)
        assert measure_text_width(font, result) <= 24
        assert result == "Hel"

    def test_returns_empty_if_max_width_zero(self):
        font = MockFont()
        result = truncate_text_to_width(font, "Hello", 0)
        assert result == ""

    def test_returns_empty_string_unchanged(self):
        font = MockFont()
        assert truncate_text_to_width(font, "", 100) == ""

    def test_single_char_fits(self):
        font = MockFont()
        assert truncate_text_to_width(font, "A", 8) == "A"

    def test_single_char_does_not_fit(self):
        font = MockFont()
        assert truncate_text_to_width(font, "A", 5) == ""

    def test_exact_width_match(self):
        font = MockFont()
        # "AB" = 16px, max_width = 16
        assert truncate_text_to_width(font, "AB", 16) == "AB"


class TestWrapTextLines:
    """Tests for wrap_text_lines."""

    def test_single_word_fits(self):
        font = MockFont()
        # "Hello" = 40px, max_width = 100
        lines = wrap_text_lines(font, "Hello", 100)
        assert lines == ["Hello"]

    def test_two_words_fit_on_one_line(self):
        font = MockFont()
        # "Hi Lo" = 40px, max_width = 100
        lines = wrap_text_lines(font, "Hi Lo", 100)
        assert lines == ["Hi Lo"]

    def test_wraps_to_multiple_lines(self):
        font = MockFont()
        # "Hello World" = 88px, max_width = 50
        # "Hello" = 40, "World" = 40
        # "Hello World" = 88 > 50, so wraps
        lines = wrap_text_lines(font, "Hello World", 50)
        assert lines == ["Hello", "World"]

    def test_three_words_two_lines(self):
        font = MockFont()
        # "A B C" each word 8px, "A B" = 24, "A B C" = 40
        # max_width = 30 -> "A B" fits (24), then "C"
        lines = wrap_text_lines(font, "A B C", 30)
        assert lines == ["A B", "C"]

    def test_empty_string(self):
        font = MockFont()
        lines = wrap_text_lines(font, "", 100)
        assert lines == []

    def test_single_long_word_exceeds_width(self):
        font = MockFont()
        # "Extraordinarily" = 120px, max_width = 50
        # Can't break it, so it goes on its own line (exceeds width)
        lines = wrap_text_lines(font, "Extraordinarily", 50)
        assert lines == ["Extraordinarily"]

    def test_preserves_word_order(self):
        font = NarrowFont()
        # Each char 5px: "One Two Three" = 65px, max_width = 40
        # "One Two" = 35, fits. "One Two Three" = 65 > 40
        lines = wrap_text_lines(font, "One Two Three", 40)
        assert lines == ["One Two", "Three"]

    def test_many_short_words(self):
        font = MockFont()
        # "A B C D E" -> each word 8px
        # "A B" = 24, "A B C" = 40, max_width = 28
        # Line1: "A B" (24), then "C" starts new line
        # "C D" = 24, "C D E" = 40 > 28
        # Line2: "C D" (24), Line3: "E"
        lines = wrap_text_lines(font, "A B C D E", 28)
        assert lines == ["A B", "C D", "E"]


class TestCalculateTextBaseline:
    """Tests for calculate_text_baseline."""

    def test_basic_centering(self):
        # line_height=24, cap_height=10, font_shift=0
        # offset = (24 - 10) / 2 = 7
        # baseline = 0 + 24 - 7 + 0 = 17
        result = calculate_text_baseline(0, 24, {'cap_height': 10, 'font_ascent': 12}, 0)
        assert result == 17

    def test_with_font_shift(self):
        # line_height=24, cap_height=10, font_shift=3
        # offset = (24 - 10) / 2 = 7
        # baseline = 0 + 24 - 7 + 3 = 20
        result = calculate_text_baseline(0, 24, {'cap_height': 10, 'font_ascent': 12}, 3)
        assert result == 20

    def test_with_y_offset(self):
        # y0=16, line_height=24, cap_height=10, font_shift=0
        # offset = (24 - 10) / 2 = 7
        # baseline = 16 + 24 - 7 + 0 = 33
        result = calculate_text_baseline(16, 24, {'cap_height': 10, 'font_ascent': 12}, 0)
        assert result == 33

    def test_uses_font_ascent_when_cap_height_zero(self):
        # cap_height=0 (falsy) -> uses font_ascent=12
        # offset = (24 - 12) / 2 = 6
        # baseline = 0 + 24 - 6 + 0 = 18
        result = calculate_text_baseline(0, 24, {'cap_height': 0, 'font_ascent': 12}, 0)
        assert result == 18

    def test_negative_font_shift(self):
        # line_height=24, cap_height=10, font_shift=-2
        # offset = (24 - 10) / 2 = 7
        # baseline = 0 + 24 - 7 + (-2) = 15
        result = calculate_text_baseline(0, 24, {'cap_height': 10, 'font_ascent': 12}, -2)
        assert result == 15
