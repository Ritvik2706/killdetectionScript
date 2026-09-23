"""Shared full-screen lifecycle, scrollable pages, and inline form editing."""
from contextlib import contextmanager
import sys
import textwrap

from . import ansi, keys, layout

_depth = 0


@contextmanager
def session():
    """Keep the workspace on one alternate screen, including nested views."""
    global _depth
    if not keys.supports_raw_input():
        yield
        return
    outer = _depth == 0
    _depth += 1
    if outer:
        sys.stdout.write('\033[?1049h\033[?25l')
        sys.stdout.flush()
    try:
        yield
    finally:
        _depth -= 1
        if outer:
            sys.stdout.write('\033[0m\033[?25h\033[?1049l')
            sys.stdout.flush()


def clear():
    if keys.supports_raw_input():
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()


def frame(title, subtitle, lines, footer, offset=0):
    """Compose a bounded screen; footer stays fixed while the body scrolls."""
    width, height = max(1, layout.term_width() - 1), max(1, layout.term_height())
    margin = '  ' if width >= 30 else ''
    body_width = max(1, width - len(margin) * 2)
    content = []
    for line in lines:
        if ansi.visible_len(line) <= body_width:
            content.append(line)
        else:
            plain = ansi._ANSI_RE.sub('', line)
            content.extend(textwrap.wrap(plain, body_width, replace_whitespace=False) or [''])
    available = max(1, height - 9)
    offset = max(0, min(offset, max(0, len(content) - available)))
    scroll = f'  {offset + 1}–{min(offset + available, len(content))}/{len(content)}' if len(content) > available else ''
    rows = [
        '', margin + ansi.paint('KILLCUTTER', ansi.TEAL, bold=True)
        + ansi.paint('  /  ' + title, ansi.WHITE, bold=True),
        margin + ansi.paint(subtitle, ansi.GREY),
        margin + ansi.paint('─' * body_width, ansi.DIM), '',
    ]
    rows.extend(margin + line for line in content[offset:offset + available])
    rows.extend([''] * max(0, available - len(content[offset:offset + available])))
    rows.extend([margin + ansi.paint('─' * body_width, ansi.DIM),
                 margin + footer + ansi.paint(scroll, ansi.DIM)])
    rows = rows[:max(1, height - 1)]
    return '\033[H' + '\r\n'.join(ansi.truncate(row, width) + '\033[K' for row in rows) + '\033[J', offset, available


def draw(title, subtitle, lines, footer, offset=0):
    rendered, offset, available = frame(title, subtitle, lines, footer, offset)
    sys.stdout.write(rendered)
    sys.stdout.flush()
    return offset, available


def page(title, lines, *, subtitle='', actions=()):
    """Show a read-only page. Returns a custom action key or None for Back."""
    if not keys.supports_raw_input():
        print(layout.panel(lines, title=title))
        try:
            answer = input('  Enter to return › ').strip().lower()
            return answer if answer in dict(actions) else None
        except (EOFError, KeyboardInterrupt):
            return None
    offset = 0
    footer = layout.hint([('Enter / Esc', 'back'), ('↑/↓', 'scroll'), *actions])
    with session(), keys.raw_mode(sys.stdin.fileno()):
        while True:
            offset, available = draw(title, subtitle, lines, footer, offset)
            key = keys.read_key(sys.stdin.fileno())
            if key in ('enter', 'esc', 'q', 'ctrl-c'):
                return None
            if key in dict(actions):
                return key
            if key in ('down', 'j'):
                offset += 1
            elif key in ('up', 'k'):
                offset -= 1
            elif key in ('pagedown', 'ctrl-d', 'ctrl-f'):
                offset += available
            elif key in ('pageup', 'ctrl-u', 'ctrl-b'):
                offset -= available
            elif key in ('home', 'g'):
                offset = 0
            elif key in ('end', 'G'):
                offset = len(lines) * max(1, layout.term_width())


def edit(label, current, convert=str):
    """Edit a value on a dedicated form with validation and cancellation."""
    value, cursor, error = str(current), len(str(current)), ''
    footer = layout.hint([('Enter', 'save'), ('Esc', 'cancel'), ('Ctrl-U', 'clear')])
    with session(), keys.raw_mode(sys.stdin.fileno()):
        while True:
            width = max(1, layout.term_width() - 10)
            start = max(0, cursor - width + 1)
            field = value[start:cursor] + '▏' + value[cursor:]
            draw('EDIT VALUE', label, [
                ansi.paint(label, ansi.WHITE, bold=True), '',
                ansi.paint('› ' + ansi.truncate(field, width), ansi.TEAL), '',
                ansi.paint(error or 'Edit the current value. Changes apply when you press Enter.',
                           ansi.AMBER if error else ansi.GREY),
            ], footer)
            key = keys.read_key(sys.stdin.fileno())
            if key in ('esc', 'ctrl-c'):
                return current
            if key == 'enter':
                if value == '/cancel':
                    return current
                try:
                    if convert is str:
                        return '' if value == '/clear' else value
                    return convert(value)
                except ValueError as exc:
                    error = str(exc)
            elif key == 'backspace' and cursor:
                value = value[:cursor - 1] + value[cursor:]
                cursor -= 1
            elif key == 'ctrl-u':
                value, cursor = '', 0
            elif key == 'left':
                cursor = max(0, cursor - 1)
            elif key == 'right':
                cursor = min(len(value), cursor + 1)
            elif key == 'home':
                cursor = 0
            elif key == 'end':
                cursor = len(value)
            elif len(key) == 1 and key.isprintable():
                value = value[:cursor] + key + value[cursor:]
                cursor += 1
