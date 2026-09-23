"""Tests for the live progress line.

The bar is redrawn with a carriage return, which only rewinds to the start of
the final screen row. If the line is wider than the terminal it wraps, and every
redraw then leaves its previous rows on screen — the bar turns into a wall of
scrolling text. So the one thing that really must hold is that it always fits.
"""

import pytest

from killcutter import ui
from killcutter.reporting import ConsoleReporter


@pytest.fixture(autouse=True)
def _color_on():
    """Exercise the coloured path — widths must ignore ANSI escapes."""
    ui.set_color(True)
    yield
    ui.set_color(False)


WIDTHS = [200, 120, 100, 90, 84, 80, 72, 60, 50, 40, 30, 24, 20]


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("kills", [0, 1, 12, 137])
def test_bar_never_exceeds_the_terminal_width(width, kills):
    line = ConsoleReporter._bar(137, 400, 63.2, 300.0, kills, 3, 42.0, width=width)
    assert ui.visible_len(line) <= width - 1


@pytest.mark.parametrize("width", WIDTHS)
def test_bar_survives_an_unknown_eta(width):
    line = ConsoleReporter._bar(0, 400, 0.0, 300.0, 0, 0, None, width=width)
    assert ui.visible_len(line) <= width - 1


def test_wide_terminal_keeps_every_segment():
    line = ConsoleReporter._bar(137, 400, 63.2, 300.0, 2, 3, 42.0, width=120)
    plain = _plain(line)
    assert "34.2%" in plain
    assert "/" in plain          # clock
    assert "ETA" in plain
    assert "KILLS" in plain      # tally badge


def test_narrow_terminal_drops_eta_before_the_clock():
    line = ConsoleReporter._bar(137, 400, 63.2, 300.0, 2, 3, 42.0, width=52)
    plain = _plain(line)
    assert "ETA" not in plain
    assert "1:03.200" in plain


def test_percentage_and_bar_always_survive():
    line = ConsoleReporter._bar(137, 400, 63.2, 300.0, 2, 3, 42.0, width=22)
    plain = _plain(line)
    assert "34.2%" in plain
    assert "█" in plain or "─" in plain


def _plain(line):
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", line)
