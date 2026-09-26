"""The Linux installer must work in locations containing spaces."""
from pathlib import Path
import os
import shutil
import subprocess
import pytest


def test_linux_installer_keeps_user_config(tmp_path):
    if os.name == 'nt':
        pytest.skip('Linux shell installer')
    bundle = tmp_path / 'release folder'
    source = bundle / 'KillcutterStudio'
    source.mkdir(parents=True)
    icon = source / '_internal' / 'killcutter' / 'gui' / 'assets' / 'killcutter-256.png'
    icon.parent.mkdir(parents=True)
    icon.write_bytes(b'test-icon')
    executable = source / 'KillcutterStudio'
    executable.write_text('#!/bin/sh\nexit 0\n')
    executable.chmod(0o755)
    script = bundle / 'install.sh'
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'packaging' / 'install-linux.sh', script)
    destination = tmp_path / 'app data'
    env = dict(os.environ, XDG_DATA_HOME=str(destination))
    result = subprocess.run(['sh', str(script)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    installed = destination / 'killcutter-studio' / 'KillcutterStudio'
    assert installed.read_text() == executable.read_text()
    desktop = (destination / 'applications' / 'killcutter-studio.desktop').read_text()
    assert f'Exec="{installed}"' in desktop
    assert 'Icon=killcutter-studio' in desktop
    assert (destination / 'icons/hicolor/256x256/apps/killcutter-studio.png').read_bytes() == b'test-icon'


def test_bundled_runtime_discovery_preserves_explicit_overrides(tmp_path, monkeypatch):
    from killcutter.gui.runtime import configure
    (tmp_path / 'tesseract').touch()
    (tmp_path / 'libmpv.so.2').touch()
    (tmp_path / 'tessdata').mkdir()
    monkeypatch.setenv('PATH', '/original')
    monkeypatch.delenv('KILLCUTTER_MPV', raising=False)
    monkeypatch.delenv('TESSDATA_PREFIX', raising=False)
    monkeypatch.setenv('KILLCUTTER_TESSERACT', '/custom/tesseract')
    configure(tmp_path)
    assert os.environ['PATH'].startswith(str(tmp_path) + os.pathsep)
    assert os.environ['KILLCUTTER_TESSERACT'] == '/custom/tesseract'
    assert os.environ['KILLCUTTER_MPV'] == str(tmp_path / 'libmpv.so.2')
    assert os.environ['TESSDATA_PREFIX'] == str(tmp_path / 'tessdata')
