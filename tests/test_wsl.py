"""WSL → Windows Python handoff for the desktop, without needing Windows."""
import subprocess
from types import SimpleNamespace

import pytest

from killcutter.gui import wsl


def completed(stdout='', returncode=0):
    return SimpleNamespace(stdout=stdout, returncode=returncode)


def test_wsl_is_recognised_from_the_kernel_release(monkeypatch):
    monkeypatch.setattr(wsl.sys, 'platform', 'linux')
    monkeypatch.delenv('WSL_DISTRO_NAME', raising=False)
    monkeypatch.delenv('WSL_INTEROP', raising=False)
    monkeypatch.setattr(wsl.platform, 'uname', lambda: SimpleNamespace(release='6.6.87.2-microsoft-standard-WSL2'))
    assert wsl.is_wsl()
    monkeypatch.setattr(wsl.platform, 'uname', lambda: SimpleNamespace(release='6.10.3-arch1-1'))
    assert not wsl.is_wsl()


def test_windows_never_hands_off(monkeypatch):
    monkeypatch.setattr(wsl.sys, 'platform', 'win32')
    monkeypatch.setenv('WSL_DISTRO_NAME', 'arch')
    assert not wsl.is_wsl()


@pytest.mark.parametrize('value, expected', [('1', False), ('true', False), ('', True), ('0', True)])
def test_wslg_env_opts_out(monkeypatch, value, expected):
    monkeypatch.setattr(wsl, 'is_wsl', lambda: True)
    monkeypatch.setenv('KILLCUTTER_WSLG', value)
    assert wsl.should_hand_off() is expected


def test_probe_rejects_the_store_stub_and_old_pythons(monkeypatch):
    monkeypatch.setattr(wsl, 'to_linux', lambda p: '/mnt/c/Py/python.exe')
    outputs = iter([
        completed('Python was not found; run without arguments to install', 49),
        completed('C:\\Py\\python.exe\n3.10\n'),
        completed('C:\\Py\\python.exe\n3.12\n'),
    ])
    monkeypatch.setattr(wsl.subprocess, 'run', lambda *a, **k: next(outputs))
    assert wsl.probe('python.exe') is None
    assert wsl.probe('python.exe') is None
    assert wsl.probe('python.exe') == ('/mnt/c/Py/python.exe', (3, 12))


def test_probe_survives_a_hung_interpreter(monkeypatch):
    def hang(*a, **k):
        raise subprocess.TimeoutExpired('python.exe', 30)
    monkeypatch.setattr(wsl.subprocess, 'run', hang)
    assert wsl.probe('python.exe') is None


def test_find_python_takes_the_first_usable_candidate(monkeypatch):
    monkeypatch.setattr(wsl, '_candidates', lambda _: [('stub.exe', ()), ('py.exe', ('-3',))])
    monkeypatch.setattr(wsl, 'probe', lambda exe, *prefix: ('/real', (3, 12)) if prefix == ('-3',) else None)
    assert wsl.find_python('/mnt/c/Users/x/AppData/Local') == '/real'


def test_requirements_keep_runtime_and_gui_extras_only(monkeypatch):
    import importlib.metadata
    monkeypatch.setattr(importlib.metadata, 'requires', lambda _: [
        'opencv-python>=4.5', 'numpy>=1.21', 'pytesseract>=0.3.8',
        'pytest>=7; extra == "dev"', "Pillow>=10; extra == 'gui'", 'pyinstaller>=6.6; extra == "build"'])
    assert wsl.requirements() == ['Pillow>=10', 'numpy>=1.21', 'opencv-python>=4.5', 'pytesseract>=0.3.8']


def test_requirements_fall_back_when_not_installed(monkeypatch):
    import importlib.metadata
    def missing(_):
        raise importlib.metadata.PackageNotFoundError('killcutter')
    monkeypatch.setattr(importlib.metadata, 'requires', missing)
    assert wsl.requirements() == sorted(wsl.FALLBACK_REQUIREMENTS)


def test_venv_only_reinstalls_when_requirements_change(tmp_path, monkeypatch):
    python = tmp_path / 'venv' / 'Scripts' / 'python.exe'
    python.parent.mkdir(parents=True)
    python.write_text('')
    calls = []
    monkeypatch.setattr(wsl.subprocess, 'run', lambda cmd, **k: calls.append(cmd) or completed())
    monkeypatch.setattr(wsl, 'requirements', lambda: ['numpy>=1.21'])
    assert wsl._ensure_venv(tmp_path, '/base/python.exe') == python
    assert wsl._ensure_venv(tmp_path, '/base/python.exe') == python
    assert len(calls) == 1 and calls[0][-1] == 'numpy>=1.21'
    monkeypatch.setattr(wsl, 'requirements', lambda: ['numpy>=2'])
    wsl._ensure_venv(tmp_path, '/base/python.exe')
    assert len(calls) == 2


def test_failed_pip_install_is_retried_next_launch(tmp_path, monkeypatch):
    python = tmp_path / 'venv' / 'Scripts' / 'python.exe'
    python.parent.mkdir(parents=True)
    python.write_text('')
    monkeypatch.setattr(wsl.subprocess, 'run', lambda cmd, **k: completed(returncode=1))
    with pytest.raises(wsl.HandoffError):
        wsl._ensure_venv(tmp_path, '/base/python.exe')
    assert not (tmp_path / 'venv' / wsl.STAMP).exists()


def test_missing_python_without_a_terminal_does_not_install(monkeypatch):
    monkeypatch.setattr(wsl, 'find_python', lambda _: None)
    monkeypatch.setattr(wsl, '_interactive', lambda: False)
    monkeypatch.setattr(wsl, '_winget', lambda *a: pytest.fail('installed without asking'))
    with pytest.raises(wsl.HandoffError, match='winget install'):
        wsl._ensure_python('/mnt/c/Users/x/AppData/Local')


def test_child_args_translate_the_config_path(monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, 'to_windows', lambda p: f'WIN:{p}')
    config = tmp_path / 'k.toml'
    assert wsl.child_args(str(config), smoke_test=True) == ['--config', f'WIN:{config}', '--smoke-test']
    assert wsl.child_args() == []


def test_launch_snippet_appends_the_checkout_after_the_venv(tmp_path):
    # The checkout must go last on sys.path so Linux-side packages never shadow the venv's.
    assert 'sys.path.append' in wsl._LAUNCH and 'insert' not in wsl._LAUNCH
