"""Raw-mode single-keypress reading, normalised to friendly key names.

Returns names like ``"up"``, ``"enter"``, ``"ctrl-d"``, ``"backspace"`` or, for
ordinary input, the literal character. Unix uses termios; Windows uses msvcrt.
"""

import os
import sys

try:                                   # Unix
    import termios
    import tty
    import select as _select
    UNIX_TTY = True
except ImportError:                    # pragma: no cover - platform specific
    UNIX_TTY = False

try:                                   # Windows
    import msvcrt
    WIN_TTY = True
except ImportError:
    WIN_TTY = False


def supports_raw_input() -> bool:
    return (UNIX_TTY or WIN_TTY) and sys.stdin.isatty() and sys.stdout.isatty()


class raw_mode:
    """Context manager putting the terminal into cbreak/raw mode (Unix no-op elsewhere)."""

    def __init__(self, fd):
        self.fd = fd
        self._saved = None

    def __enter__(self):
        if UNIX_TTY:
            self._saved = termios.tcgetattr(self.fd)
            tty.setraw(self.fd)
        return self

    def __exit__(self, *exc):
        if UNIX_TTY and self._saved is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self._saved)


def _read_unix(fd) -> str:
    ch = os.read(fd, 1)
    simple = {
        b"\x03": "ctrl-c", b"\x04": "ctrl-d", b"\x15": "ctrl-u",
        b"\x06": "ctrl-f", b"\x02": "ctrl-b", b"\r": "enter", b"\n": "enter",
        b"\x7f": "backspace", b"\x08": "backspace",
    }
    if ch in simple:
        return simple[ch]
    if ch == b"\x1b":
        ready, _, _ = _select.select([fd], [], [], 0.0015)
        if not ready:
            return "esc"
        seq = os.read(fd, 1)
        if seq == b"[":
            code = os.read(fd, 1)
            if code in (b"5", b"6"):
                os.read(fd, 1)  # consume trailing '~'
                return "pageup" if code == b"5" else "pagedown"
            return {b"A": "up", b"B": "down", b"C": "right", b"D": "left",
                    b"H": "home", b"F": "end"}.get(code, "esc")
        if seq == b"O":
            return {b"H": "home", b"F": "end"}.get(os.read(fd, 1), "esc")
        return "esc"
    # Reassemble a UTF-8 char if the first byte signals a multibyte sequence.
    b0 = ch[0]
    extra = 3 if b0 >= 0xF0 else 2 if b0 >= 0xE0 else 1 if b0 >= 0xC0 else 0
    if extra:
        ch += os.read(fd, extra)
    return ch.decode("utf-8", "ignore")


def _read_win() -> str:  # pragma: no cover - platform specific
    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):
        return {"H": "up", "P": "down", "K": "left", "M": "right",
                "G": "home", "O": "end", "I": "pageup", "Q": "pagedown"}.get(
                    msvcrt.getwch(), "esc")
    simple = {"\x03": "ctrl-c", "\x04": "ctrl-d", "\x15": "ctrl-u",
              "\x06": "ctrl-f", "\x02": "ctrl-b", "\r": "enter", "\n": "enter",
              "\x08": "backspace", "\x1b": "esc"}
    return simple.get(ch, ch)


def read_key(fd) -> str:
    return _read_unix(fd) if UNIX_TTY else _read_win()
