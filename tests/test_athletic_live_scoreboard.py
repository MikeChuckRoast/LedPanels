"""
Unit tests for athletic_live_scoreboard.py formatting helpers.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from athletic_live_scoreboard import _format_mark, _ordinal_place


class TestOrdinalPlace:
    """Tests for _ordinal_place()."""

    def test_1st(self):
        assert _ordinal_place("1") == "1st Place"

    def test_2nd(self):
        assert _ordinal_place("2") == "2nd Place"

    def test_3rd(self):
        assert _ordinal_place("3") == "3rd Place"

    def test_4th(self):
        assert _ordinal_place("4") == "4th Place"

    def test_11th(self):
        assert _ordinal_place("11") == "11th Place"

    def test_12th(self):
        assert _ordinal_place("12") == "12th Place"

    def test_13th(self):
        assert _ordinal_place("13") == "13th Place"

    def test_21st(self):
        assert _ordinal_place("21") == "21st Place"

    def test_22nd(self):
        assert _ordinal_place("22") == "22nd Place"

    def test_23rd(self):
        assert _ordinal_place("23") == "23rd Place"

    def test_15th(self):
        assert _ordinal_place("15") == "15th Place"

    def test_non_numeric_passthrough(self):
        assert _ordinal_place("DNS") == "DNS"

    def test_empty_string_passthrough(self):
        assert _ordinal_place("") == ""


class TestFormatMark:
    """Tests for _format_mark()."""

    def test_feet_and_fractional_inches(self):
        assert _format_mark("18-05.75") == "18' 5.75\""

    def test_whole_inches(self):
        assert _format_mark("27-01") == "27' 1\""

    def test_whole_inches_with_dot_zero(self):
        assert _format_mark("27-01.00") == "27' 1\""

    def test_zero_feet(self):
        assert _format_mark("0-11.50") == "0' 11.5\""

    def test_large_feet(self):
        assert _format_mark("60-09.25") == "60' 9.25\""

    def test_foul_passthrough(self):
        assert _format_mark("FOUL") == "FOUL"

    def test_standing_passthrough(self):
        assert _format_mark("(standing)") == "(standing)"

    def test_empty_passthrough(self):
        assert _format_mark("") == ""

    def test_no_dash_passthrough(self):
        # Metric or unrecognized format: return as-is
        assert _format_mark("12.34") == "12.34"

    def test_leading_trailing_whitespace_stripped(self):
        assert _format_mark("  18-05.75  ") == "18' 5.75\""

    def test_trailing_zero_trimmed(self):
        # 9.50 inches should display as 9.5
        assert _format_mark("18-09.50") == "18' 9.5\""
