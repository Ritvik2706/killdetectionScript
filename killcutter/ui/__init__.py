"""Zero-dependency terminal UI toolkit for the Killfeed Auto-Cutter.

Import surface is flat — ``from killcutter import ui`` then ``ui.paint(...)``,
``ui.panel(...)``, ``ui.select(...)`` — while the implementation is split into
focused modules: ``ansi`` (colour), ``layout`` (boxes), ``progress`` (bars),
``selector`` (the interactive picker) and ``keys`` (raw input).
"""

from .ansi import (
    set_color, visible_len, paint, badge, CLEAR_LINE,
    GREEN, LIME, TEAL, CYAN, BLUE, PURPLE, AMBER, RED, WHITE, GREY, DIM, INK,
)
from .layout import (
    term_width, term_height, rel_time, rule, banner, panel, kv, hint,
)
from .progress import gradient_bar, spinner_frame
from .selector import select, fuzzy_match

__all__ = [
    "set_color", "visible_len", "paint", "badge", "CLEAR_LINE",
    "GREEN", "LIME", "TEAL", "CYAN", "BLUE", "PURPLE", "AMBER", "RED",
    "WHITE", "GREY", "DIM", "INK",
    "term_width", "term_height", "rel_time", "rule", "banner", "panel", "kv", "hint",
    "gradient_bar", "spinner_frame", "select", "fuzzy_match",
]
