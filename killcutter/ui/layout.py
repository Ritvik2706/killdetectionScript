"""Structural building blocks: terminal sizing, rules, banners, panels, legends."""

import shutil
import time

from .ansi import DIM, GREEN, CYAN, LIME, TEAL, WHITE, GREY, paint, lerp, visible_len


def term_width(default=90) -> int:
    try:
        return shutil.get_terminal_size((default, 24)).columns
    except Exception:
        return default


def term_height(default=24) -> int:
    try:
        return shutil.get_terminal_size((90, default)).lines
    except Exception:
        return default


def rel_time(ts: float) -> str:
    """Compact 'time ago' string for a unix timestamp."""
    delta = max(0.0, time.time() - ts)
    for span, unit in ((604800, "w"), (86400, "d"), (3600, "h"), (60, "m")):
        if delta >= span:
            return f"{int(delta // span)}{unit} ago"
    return "just now"


def _box_width() -> int:
    return min(term_width() - 2, 84)


def rule(color=DIM, char="─", width=None) -> str:
    return paint(char * (width or _box_width()), color)


def banner(title: str, subtitle: str = "") -> str:
    """Top-of-screen header with a gradient title inside a rounded box."""
    inner = _box_width() - 2

    glyphs = []
    chars = list(title)
    for i, ch in enumerate(chars):
        t = i / max(len(chars) - 1, 1)
        col = lerp(GREEN, CYAN, t) if t < 1 else CYAN
        glyphs.append(paint(ch, col, bold=True))
    title_str = "".join(glyphs)

    left = f" {paint('◎', LIME, bold=True)}  {title_str}"
    sub = paint(subtitle.upper(), DIM) if subtitle else ""
    gap = max(inner - visible_len(left) - visible_len(sub) - 1, 1)

    bar = paint("│", DIM)
    top = paint("╭" + "─" * inner + "╮", DIM)
    bot = paint("╰" + "─" * inner + "╯", DIM)
    mid = f"{bar}{left}{' ' * gap}{sub} {bar}"
    return f"\n{top}\n{mid}\n{bot}"


def panel(rows, title="", color=TEAL) -> str:
    """A rounded box around pre-rendered rows. ``title`` sits in the top border."""
    inner = _box_width() - 2

    if title:
        label = paint(f" {title} ", color, bold=True)
        fill = inner - visible_len(label) - 1
        top = paint("╭─", DIM) + label + paint("─" * max(fill, 0) + "╮", DIM)
    else:
        top = paint("╭" + "─" * inner + "╮", DIM)

    bar = paint("│", DIM)
    out = [top]
    for row in rows:
        pad = inner - 1 - visible_len(row)
        out.append(f"{bar} {row}{' ' * max(pad, 0)}{bar}")
    out.append(paint("╰" + "─" * inner + "╯", DIM))
    return "\n".join(out)


def kv(key, value, *, key_color=GREY, val_color=WHITE, key_w=14) -> str:
    """A label / value row for use inside a panel."""
    return f"{paint(f'{key:<{key_w}}', key_color)}{paint(value, val_color)}"


def hint(pairs) -> str:
    """Render a footer key-legend from (key, description) pairs."""
    sep = paint("  ·  ", DIM)
    return sep.join(
        paint(k, TEAL, bold=True) + " " + paint(d, DIM) for k, d in pairs
    )
