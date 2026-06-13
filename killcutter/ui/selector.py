"""A full-screen, vim-navigable, fuzzy-filtered single-choice picker.

Falls back to a plain numbered prompt when the terminal can't do raw input
(piped output, no colour, dumb terminal).
"""

import sys

from . import ansi
from .ansi import LIME, TEAL, WHITE, GREY, DIM, AMBER, CYAN, paint, visible_len
from .layout import term_width, term_height, panel, hint
from . import keys

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
    if not (ansi.COLOR and keys.supports_raw_input()):
        return _fallback(items, render_row, title)

    filter_text = filter_text or (lambda it: str(it))
    state = _State(items, filter_text, initial)

    fd = sys.stdin.fileno()
    with keys.raw_mode(fd):
        sys.stdout.write(_ALT_ENTER)
        sys.stdout.flush()
        try:
            while True:
                view = state.view()
                state.clamp(view)
                _draw(items, render_row, view, state, title)
                result = state.handle(keys.read_key(fd), view)
                if result is not _NOTHING:
                    return result
        finally:
            sys.stdout.write(_ALT_LEAVE)
            sys.stdout.flush()


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
        return max(1, term_height() - 6)

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
        half, page = avail // 2, avail
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
    width = term_width()
    out = ["\033[H"]

    def line(s=""):
        out.append(s + "\033[K\r\n")

    shown = len(view)
    pos = f"{state.cursor + 1}/{shown}" if shown else "0/0"
    head = "  " + paint("❯", LIME, bold=True) + " " + paint(title, WHITE, bold=True)
    counter = paint(pos, GREY) + paint(f"  of {state.n}", DIM)
    gap = max(1, width - visible_len(head) - visible_len(counter) - 2)
    line()
    line(head + " " * gap + counter)
    line(paint("─" * (width - 2), DIM))

    avail = state.rows_avail
    if not view:
        line("  " + paint(f"no matches for “{state.query}”", AMBER))
        for _ in range(avail - 1):
            line()
    else:
        end = min(state.scroll + avail, shown)
        for pos_i in range(state.scroll, end):
            line(render_row(items[view[pos_i]], pos_i == state.cursor, pos_i + 1))
        for _ in range(avail - (end - state.scroll)):
            line()

    line(paint("─" * (width - 2), DIM))
    if state.mode == "search":
        line("  " + paint("/", TEAL, bold=True) + paint(state.query, WHITE) + paint("▏", LIME))
    else:
        legend = hint([("j/k", "move"), ("gg/G", "ends"), ("^d/^u", "page"),
                       ("/", "search"), ("⏎", "select"), ("q", "quit")])
        status = ""
        if state.numbuf:
            status = "  " + paint(f"go to {state.numbuf}", AMBER, bold=True)
        elif state.query:
            status = "  " + paint(f"filter “{state.query}”", TEAL)
        line("  " + legend + status)
    out.append("\033[J")
    sys.stdout.write("".join(out))
    sys.stdout.flush()


def _fallback(items, render_row, title):
    """Plain numbered prompt for non-TTY / no-colour environments."""
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
