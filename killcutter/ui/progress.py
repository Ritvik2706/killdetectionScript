"""Progress affordances: a sub-cell gradient bar and a braille spinner."""

from . import ansi
from .ansi import GREEN, CYAN, DIM, TEAL, paint, lerp

_BLOCKS = " ▏▎▍▌▋▊▉█"
_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def gradient_bar(frac, width=34, c1=GREEN, c2=CYAN, track=DIM) -> str:
    """A smooth gradient progress bar with sub-cell precision."""
    frac = max(0.0, min(1.0, frac))
    filled = width * frac
    whole = int(filled)
    cells = []
    for i in range(width):
        col = lerp(c1, c2, i / max(width - 1, 1))
        if i < whole:
            cells.append(paint("█", col))
        elif i == whole and filled - whole > 0.05:
            cells.append(paint(_BLOCKS[int((filled - whole) * 8)], col))
        else:
            cells.append(paint("─", track))
    return "".join(cells)


def spinner_frame(tick: int) -> str:
    if not ansi.COLOR:
        return "*"
    return paint(_SPINNER[tick % len(_SPINNER)], TEAL, bold=True)
