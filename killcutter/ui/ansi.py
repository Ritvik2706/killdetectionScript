"""ANSI primitives: colour-capability detection, the palette, and text styling.

Everything reads the module-level :data:`COLOR` flag at *call* time, so
:func:`set_color` flips styling on or off everywhere at once.
"""

import os
import re
import sys


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


COLOR = _supports_color()


def set_color(on: bool) -> None:
    """Force colour output on or off (used by ``--no-color`` and config)."""
    global COLOR
    COLOR = bool(on)


# Windows terminals need VT processing switched on for ANSI to render.
if COLOR and os.name == "nt":  # pragma: no cover - platform specific
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleMode(
            ctypes.windll.kernel32.GetStdHandle(-11), 7
        )
    except Exception:
        pass


# ── Palette (R, G, B) — a cohesive "neon esports" theme ─────────────────────────

GREEN = (104, 231, 122)
LIME = (170, 246, 104)
TEAL = (76, 222, 206)
CYAN = (88, 196, 240)
BLUE = (116, 162, 252)
PURPLE = (185, 152, 250)
AMBER = (247, 191, 96)
RED = (250, 110, 110)
WHITE = (236, 241, 247)
GREY = (138, 150, 168)
DIM = (92, 104, 122)
INK = (17, 20, 26)   # near-black, for text on bright badges

CLEAR_LINE = "\r\033[2K"   # carriage return + erase whole line

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def visible_len(s: str) -> int:
    """Length of a string ignoring ANSI escape codes."""
    return len(_ANSI_RE.sub("", s))


def lerp(a, b, t):
    """Linear-interpolate two RGB tuples; ``t`` in [0, 1]."""
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def paint(text, rgb=WHITE, *, bold=False, dim=False, italic=False, underline=False):
    if not COLOR:
        return str(text)
    codes = []
    if bold:
        codes.append("1")
    if dim:
        codes.append("2")
    if italic:
        codes.append("3")
    if underline:
        codes.append("4")
    codes.append(f"38;2;{rgb[0]};{rgb[1]};{rgb[2]}")
    return f"\033[{';'.join(codes)}m{text}\033[0m"


def badge(text, fg=INK, bg=GREEN, *, bold=True):
    """A filled pill, e.g. a status tag."""
    if not COLOR:
        return f"[{text}]"
    b = "1;" if bold else ""
    return (
        f"\033[{b}38;2;{fg[0]};{fg[1]};{fg[2]};48;2;{bg[0]};{bg[1]};{bg[2]}m"
        f" {text} \033[0m"
    )
