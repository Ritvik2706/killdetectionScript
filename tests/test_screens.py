from contextlib import nullcontext
from unittest.mock import Mock

import pytest

from killcutter.ui import ansi, screens, workspace
from killcutter import environment


@pytest.fixture
def terminal(monkeypatch):
    monkeypatch.setattr(screens.keys, 'supports_raw_input', lambda: True)
    monkeypatch.setattr(screens.keys, 'raw_mode', lambda fd: nullcontext())
    monkeypatch.setattr(screens.sys.stdin, 'fileno', lambda: 0)
    monkeypatch.setattr(screens.layout, 'term_width', lambda: 80)
    monkeypatch.setattr(screens.layout, 'term_height', lambda: 24)


def test_nested_views_enter_and_leave_alternate_screen_once(terminal, capsys):
    with screens.session():
        with screens.session():
            pass
    output = capsys.readouterr().out
    assert output.count('\033[?1049h') == 1
    assert output.count('\033[?1049l') == 1
    assert screens._depth == 0


def test_screen_restores_terminal_on_exception(terminal, capsys):
    with pytest.raises(RuntimeError):
        with screens.session():
            raise RuntimeError('failed')
    assert '\033[?25h\033[?1049l' in capsys.readouterr().out
    assert screens._depth == 0


def test_page_scrolls_and_returns_custom_action(terminal, monkeypatch):
    inputs = iter(['pagedown', 'r'])
    monkeypatch.setattr(screens.keys, 'read_key', lambda fd: next(inputs))
    draw = Mock(return_value=(0, 15))
    monkeypatch.setattr(screens, 'draw', draw)
    assert screens.page('ENVIRONMENT', ['row'] * 40, actions=[('r', 'refresh')]) == 'r'
    assert draw.call_args_list[1].args[-1] == 15


def test_frame_wraps_paths_and_bounds_output(monkeypatch):
    monkeypatch.setattr(screens.layout, 'term_width', lambda: 40)
    monkeypatch.setattr(screens.layout, 'term_height', lambda: 12)
    rendered, offset, available = screens.frame('ENVIRONMENT', 'Details', ['x' * 140], 'Esc back', 999)
    assert offset == 1
    assert available == 3
    rows = rendered.replace('\033[H', '').replace('\033[K', '').replace('\033[J', '').split('\r\n')
    assert len(rows) < 12
    assert all(ansi.visible_len(row) < 40 for row in rows)


def test_editor_validation_and_cancel_preserve_value(terminal, monkeypatch):
    inputs = iter(['ctrl-u', '-', '1', 'enter', 'esc'])
    monkeypatch.setattr(screens.keys, 'read_key', lambda fd: next(inputs))
    draw = Mock()
    monkeypatch.setattr(screens, 'draw', draw)
    assert screens.edit('Rate', 4, workspace.number) == 4
    assert any('non-negative' in str(call) for call in draw.call_args_list)


def test_editor_supports_insertion_and_clear(terminal, monkeypatch):
    inputs = iter(['home', 'x', 'end', 'backspace', 'enter'])
    monkeypatch.setattr(screens.keys, 'read_key', lambda fd: next(inputs))
    monkeypatch.setattr(screens, 'draw', Mock())
    assert screens.edit('Path', 'abc') == 'xab'


def test_environment_refreshes_and_has_settings_action(monkeypatch):
    check = Mock(return_value=[environment.Check('Python', True, '3.14')])
    monkeypatch.setattr(environment, 'check', check)
    actions = iter(['r', 's'])
    page = Mock(side_effect=lambda *a, **k: next(actions))
    monkeypatch.setattr(screens, 'page', page)
    monkeypatch.setattr(screens, 'clear', Mock())
    monkeypatch.setattr(screens.keys, 'supports_raw_input', lambda: False)
    assert workspace.environment_page({}, None) == 's'
    assert check.call_count == 2
    assert any('FFmpeg' in row for row in page.call_args.args[1])


def test_home_help_uses_page_and_preserves_menu_selection(monkeypatch):
    choices = iter([3, None])
    choose = Mock(side_effect=lambda *a: next(choices))
    monkeypatch.setattr(workspace, 'choose', choose)
    page = Mock()
    monkeypatch.setattr(screens, 'page', page)
    assert workspace.home({}, None, Mock(), {}) == 0
    assert page.call_args.args[0] == 'HELP'
    assert choose.call_args.args[2] == 3


def test_home_opens_setup_when_a_dependency_is_missing(monkeypatch):
    monkeypatch.setattr(environment, 'check',
                        Mock(return_value=[environment.Check('Tesseract OCR', False, 'not found')]))
    setup = Mock(return_value=None)
    monkeypatch.setattr(workspace, 'environment_page', setup)
    monkeypatch.setattr(workspace, 'choose', Mock(return_value=None))
    assert workspace._home({}, None, Mock(), {}) == 0
    assert setup.call_count == 1


def test_home_skips_setup_when_ready(monkeypatch):
    monkeypatch.setattr(environment, 'check',
                        Mock(return_value=[environment.Check('Tesseract OCR', True, '5.5')]))
    setup = Mock()
    monkeypatch.setattr(workspace, 'environment_page', setup)
    monkeypatch.setattr(workspace, 'choose', Mock(return_value=None))
    assert workspace._home({}, None, Mock(), {}) == 0
    setup.assert_not_called()
