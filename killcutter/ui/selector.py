"""A full-screen, vim-navigable, fuzzy-filtered single-choice picker.

Falls back to a plain numbered prompt when the terminal can't do raw input
(piped input or output).
"""

import sys

from . import ansi
from .ansi import LIME, TEAL, WHITE, GREY, DIM, AMBER, CYAN, paint, visible_len
from .layout import term_width, term_height, panel, hint
from . import keys, screens

_ALT_ENTER = "\033[?1049h\033[?25l"   # alternate screen + hide cursor
_ALT_LEAVE = "\033[?25h\033[?1049l"   # show cursor + leave alternate screen


def fuzzy_match(query: str, text: str) -> bool:
    """True if ``query`` is a subsequence of ``text`` (both lowercased upstream)."""
    it = iter(text)
    return all(c in it for c in query)


def select(items, render_row, *, title="SELECT", filter_text=None, initial=0):
    """Pick one item; returns its index into ``items`` or ``None`` if cancelled.

    render_row  — fn(item, active: bool, index: int) -> styled one-line string
    filter_text — fn(item) -> the string matched against the search query
    """
    if not items:
        return None
    if not keys.supports_raw_input():
        return _fallback(items, render_row, title)

    filter_text = filter_text or (lambda it: str(it))
    state = _State(items, filter_text, initial)

    fd = sys.stdin.fileno()
    with screens.session(), keys.raw_mode(fd):
        while True:
            view = state.view()
            state.clamp(view)
            _draw(items, render_row, view, state, title)
            result = state.handle(keys.read_key(fd), view)
            if result is not _NOTHING:
                return result


_NOTHING = object()   # sentinel: keep looping (no selection yet)


class _State:
    """All mutable picker state plus the keypress state-machine."""

    def __init__(self, items, filter_text, initial):
        self.n = len(items)
        self._lowered = [filter_text(it).lower() for it in items]
        self.query = ""
        self.mode = "normal"          # "normal" | "search"
        self.cursor = max(0, min(initial, self.n - 1))
        self.scroll = 0
        self.numbuf = ""
        self._pending_g = False

    def view(self):
        if not self.query:
            return list(range(self.n))
        q = self.query.lower()
        return [i for i in range(self.n) if fuzzy_match(q, self._lowered[i])]

    @property
    def rows_avail(self):
        return max(1, term_height() - 9)

    def clamp(self, view):
        if self.cursor >= len(view):
            self.cursor = max(0, len(view) - 1)
        avail = self.rows_avail
        if self.cursor < self.scroll:
            self.scroll = self.cursor
        elif self.cursor >= self.scroll + avail:
            self.scroll = self.cursor - avail + 1
        self.scroll = max(0, min(self.scroll, max(0, len(view) - avail)))

    def handle(self, key, view):
        """Apply one key. Returns a chosen original-index, ``None``, or _NOTHING."""
        was_g, self._pending_g = self._pending_g, False
        if key == "ctrl-c":
            return None
        if self.mode == "search":
            return self._handle_search(key, view)
        return self._handle_normal(key, view, was_g)

    def _handle_search(self, key, view):
        if key == "enter":
            self.mode = "normal"
        elif key == "esc":
            self.query, self.mode, self.cursor = "", "normal", 0
        elif key == "backspace":
            self.query, self.cursor = self.query[:-1], 0
        elif key in ("up", "ctrl-u"):
            self.cursor = max(0, self.cursor - 1)
        elif key in ("down", "ctrl-d"):
            self.cursor = min(len(view) - 1, self.cursor + 1) if view else 0
        elif len(key) == 1 and key.isprintable():
            self.query, self.cursor = self.query + key, 0
        return _NOTHING

    def _handle_normal(self, key, view, was_g):
        avail = self.rows_avail
        half, page = max(1, avail // 2), avail
        last = len(view) - 1

        if key in ("j", "down"):
            self.cursor = min(last, self.cursor + 1) if view else 0
        elif key in ("k", "up"):
            self.cursor = max(0, self.cursor - 1)
        elif key == "g":
            if was_g:
                self.cursor = 0
            else:
                self._pending_g = True
        elif key in ("G", "end"):
            self.cursor = last if view else 0
        elif key == "home":
            self.cursor = 0
        elif key in ("ctrl-d", "pagedown"):
            step = half if key == "ctrl-d" else page
            self.cursor = min(last, self.cursor + step) if view else 0
        elif key in ("ctrl-u", "pageup"):
            self.cursor = max(0, self.cursor - (half if key == "ctrl-u" else page))
        elif key == "ctrl-f":
            self.cursor = min(last, self.cursor + page) if view else 0
        elif key == "ctrl-b":
            self.cursor = max(0, self.cursor - page)
        elif key == "/":
            self.query, self.mode, self.cursor = "", "search", 0
        elif key.isdigit():
            self.numbuf += key
            return _NOTHING
        elif key == "enter":
            if self.numbuf:
                target, self.numbuf = int(self.numbuf) - 1, ""
                if 0 <= target < len(view):
                    return view[target]
            elif view:
                return view[self.cursor]
        elif key == "esc":
            if self.numbuf:
                self.numbuf = ""
            elif self.query:
                self.query, self.cursor = "", 0
            else:
                return None
        elif key == "q":
            return None
        if not key.isdigit():
            self.numbuf = ""
        return _NOTHING


def _draw(items, render_row, view, state, title):
    shown = len(view)
    position = f"{state.cursor + 1} / {shown}" if shown else "0 matches"
    rows = [ansi.truncate(render_row(items[view[i]], i == state.cursor, i + 1), max(1, term_width() - 5))
            for i in range(state.scroll, min(state.scroll + state.rows_avail, shown))]
    if not rows:
        rows = [paint(f"No matches for “{state.query}”", AMBER),
                paint("Press Esc to clear your search.", GREY)]
    if state.mode == "search":
        footer = paint("/ " + state.query + "▏", TEAL) + paint("   Enter applies · Esc clears", DIM)
    else:
        footer = hint([("↑/↓", "move"), ("Enter", "select"), ("/", "search"), ("Esc / q", "back")])
        if state.numbuf:
            footer += paint(f"  Go to {state.numbuf}", AMBER)
        elif state.query:
            footer += paint(f"  Filter: {state.query}", TEAL)
    heading = title.removeprefix("KILLCUTTER · ")
    screens.draw(heading, f"{position}   ·   {len(items)} options", rows, footer)


def _fallback(items, render_row, title):
    """Plain numbered prompt for non-TTY environments."""
    print(panel([render_row(it, False, i) for i, it in enumerate(items, 1)],
                title=title, color=CYAN))
    print()
    prompt = paint("  Select ", GREY) + paint("›", TEAL, bold=True) + " "
    while True:
        try:
            raw = input(prompt).strip()
            if raw.lower() in ("q", "quit", ""):
                return None
            choice = int(raw)
            if 1 <= choice <= len(items):
                return choice - 1
        except ValueError:
            pass
        except (KeyboardInterrupt, EOFError):
            return None
        print(paint(f"       Enter 1–{len(items)} (or q to cancel).", AMBER))
