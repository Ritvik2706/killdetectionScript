"""Hand the desktop off to Windows Python when launched inside WSL.

Under WSLg every Linux window is mirrored to Windows over RDP (msrdc.exe). A
Windows window manager that resizes that proxy window — any tiling WM, e.g.
GlazeWM — never gets the new size passed back to X, so Tk keeps drawing at the
old size and the window shows up blank. Nothing inside the app can see that
resize, so on WSL we run the GUI with a real Windows interpreter instead.

The Windows side is a private venv under ``%LOCALAPPDATA%\\killcutter`` holding
only third-party dependencies (installed automatically, refreshed when they
change). The killcutter code itself is imported live from this checkout over
``\\\\wsl.localhost``, appended to ``sys.path`` so the venv's Windows builds of
numpy/OpenCV always win over anything Linux-side. Installing Python or Tesseract
system-wide goes through winget and is only done after asking.

``--wslg`` or ``KILLCUTTER_WSLG=1`` keeps the old behaviour.
"""
import glob
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from killcutter import environment

MIN_PYTHON = (3, 11)
WINGET_PYTHON = 'Python.Python.3.12'
FALLBACK_REQUIREMENTS = ('opencv-python>=4.5', 'numpy>=1.21', 'pytesseract>=0.3.8', 'Pillow>=10')
STAMP = 'killcutter-requirements.txt'

# Run by each candidate interpreter; the Store stub exits 49 before getting here.
_PROBE = 'import sys, tkinter; print(sys.executable); print("%d.%d" % sys.version_info[:2])'
# Run by the venv interpreter: argv[1] is this checkout as a UNC path.
_LAUNCH = ('import sys; sys.path.append(sys.argv.pop(1)); '
           'from killcutter.gui.__main__ import main; raise SystemExit(main(sys.argv[1:]))')


class HandoffError(Exception):
    """Windows Python could not be used; the caller falls back to WSLg."""


def is_wsl():
    if sys.platform != 'linux':
        return False
    if os.environ.get('WSL_DISTRO_NAME') or os.environ.get('WSL_INTEROP'):
        return True
    return 'microsoft' in platform.uname().release.lower()


def should_hand_off():
    return is_wsl() and os.environ.get('KILLCUTTER_WSLG', '').lower() not in ('1', 'true', 'yes')


def _run(command, timeout=None, **kwargs):
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, **kwargs)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HandoffError(f'{Path(command[0]).name} failed: {exc}') from None


def to_windows(path):
    return _run(['wslpath', '-w', str(path)]).stdout.strip()


def to_linux(path):
    return _run(['wslpath', '-u', str(path)]).stdout.strip()


def windows_env(name):
    """A Windows environment variable, read through cmd.exe."""
    cmd = shutil.which('cmd.exe') or '/mnt/c/Windows/System32/cmd.exe'
    # cwd on a Windows drive: from a \\wsl.localhost cwd cmd.exe prints a UNC warning.
    value = _run([cmd, '/d', '/c', f'echo %{name}%'], timeout=20, cwd='/mnt/c').stdout.strip()
    if not value or value == f'%{name}%':
        raise HandoffError(f'Could not read %{name}% from Windows (is WSL interop enabled?)')
    return value


def probe(executable, *prefix):
    """``(linux path of the real interpreter, (major, minor))``, or None if unusable."""
    try:
        result = subprocess.run([executable, *prefix, '-c', _PROBE], capture_output=True,
                                text=True, timeout=30, cwd='/mnt/c')
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = result.stdout.strip().splitlines()
    if result.returncode != 0 or len(lines) < 2:
        return None
    try:
        version = tuple(int(part) for part in lines[-1].split('.'))
        path = to_linux(lines[-2].strip())
    except (ValueError, HandoffError):
        return None
    return (path, version) if version >= MIN_PYTHON and path else None


def _candidates(local_appdata):
    """``(executable, prefix args)`` pairs, most specific first."""
    found = []
    launcher = shutil.which('py.exe') or ('/mnt/c/Windows/py.exe' if os.path.isfile('/mnt/c/Windows/py.exe') else None)
    if launcher:
        found.append((launcher, ('-3',)))
    for name in ('python.exe', 'python3.exe'):
        if shutil.which(name):
            found.append((shutil.which(name), ()))
    patterns = [os.path.join(local_appdata, 'Programs', 'Python', 'Python3*', 'python.exe'),
                os.path.join(local_appdata, 'Python', 'pythoncore-3*', 'python.exe'),
                '/mnt/c/Python3*/python.exe', '/mnt/c/Program Files/Python3*/python.exe']
    for pattern in patterns:
        # Newest first: Python313 sorts after Python312, pythoncore-3.13-64 after 3.12.
        found.extend((path, ()) for path in sorted(glob.glob(pattern), reverse=True))
    return found


def find_python(local_appdata):
    for executable, prefix in _candidates(local_appdata):
        result = probe(executable, *prefix)
        if result:
            return result[0]
    return None


def requirements():
    """Runtime + GUI requirements, from the installed metadata when available."""
    try:
        from importlib.metadata import PackageNotFoundError, requires
        declared = requires('killcutter') or []
    except (ImportError, PackageNotFoundError):
        declared = []
    kept = []
    for requirement in declared:
        spec, _, marker = requirement.partition(';')
        marker = marker.replace("'", '"').replace(' ', '')
        if not marker or marker == 'extra=="gui"':
            kept.append(spec.strip())
    return sorted(kept) if kept else sorted(FALLBACK_REQUIREMENTS)


def _interactive():
    return sys.stdin.isatty() and sys.stdout.isatty()


def _confirm(question):
    if not _interactive():
        return False
    try:
        answer = input(f'{question} [Y/n] ').strip().lower()
    except EOFError:
        return False
    return answer in ('', 'y', 'yes')


def _winget(package_id, *extra):
    winget = shutil.which('winget.exe')
    if not winget:
        raise HandoffError(f'winget is not available; install {package_id} on Windows yourself')
    print(f'Installing {package_id} with winget…', flush=True)
    result = subprocess.run([winget, 'install', '-e', '--id', package_id, '--accept-package-agreements',
                             '--accept-source-agreements', *extra], cwd='/mnt/c')
    if result.returncode != 0:
        raise HandoffError(f'winget could not install {package_id} (exit {result.returncode})')


def _ensure_python(local_appdata):
    python = find_python(local_appdata)
    if python:
        return python
    if not _confirm('The desktop app runs with Windows Python on WSL, and none is installed. '
                    f'Install {WINGET_PYTHON} with winget now?'):
        raise HandoffError('no Windows Python 3.11+ with Tk was found. '
                           f'Install one with: winget install {WINGET_PYTHON}')
    _winget(WINGET_PYTHON, '--scope', 'user')
    python = find_python(local_appdata)
    if not python:
        raise HandoffError('Python was installed but could not be found; open a new terminal and retry')
    return python


def _ensure_venv(home, base_python):
    venv = home / 'venv'
    python = venv / 'Scripts' / 'python.exe'
    if not python.is_file():
        print('Setting up the Windows desktop environment (one time)…', flush=True)
        result = subprocess.run([base_python, '-m', 'venv', to_windows(venv)], cwd='/mnt/c')
        if result.returncode != 0 or not python.is_file():
            raise HandoffError('could not create the Windows virtual environment')
    wanted = '\n'.join(requirements()) + '\n'
    stamp = venv / STAMP
    if not stamp.is_file() or stamp.read_text(encoding='utf-8') != wanted:
        print('Installing desktop dependencies into Windows Python…', flush=True)
        result = subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
                                 *wanted.split()], cwd='/mnt/c')
        if result.returncode != 0:
            raise HandoffError('pip could not install the desktop dependencies on Windows')
        stamp.write_text(wanted, encoding='utf-8')
    return python


def _check_tesseract(home):
    """Offer Tesseract once; the desktop still opens without it (analysis will explain)."""
    for candidate in environment._WINDOWS_CANDIDATES:
        drive, rest = candidate.split(':', 1)
        if os.path.isfile(f'/mnt/{drive.lower()}' + rest.replace('\\', '/')):
            return
    if shutil.which('tesseract.exe'):
        return
    asked = home / 'tesseract-declined'
    if asked.exists() or not _interactive():
        return
    package = environment._COMPONENTS['tesseract'][1]['windows']
    if _confirm('Tesseract OCR is not installed on Windows, so analysis will not work. Install it with winget now?'):
        try:
            _winget(package)
        except HandoffError as exc:
            print(f'{exc}. The desktop will still open.', file=sys.stderr)
    else:
        asked.touch()
        print(f'Skipped. Install later with: winget install {package}', file=sys.stderr)


def child_args(config=None, smoke_test=False):
    args = []
    if config:
        args += ['--config', to_windows(Path(config).expanduser().resolve())]
    if smoke_test:
        args.append('--smoke-test')
    return args


def source_root():
    import killcutter
    return Path(killcutter.__file__).resolve().parent.parent


def run_on_windows(config=None, smoke_test=False):
    """Launch the desktop with Windows Python and return its exit code."""
    local_appdata = to_linux(windows_env('LOCALAPPDATA'))
    home = Path(local_appdata) / 'killcutter' / 'wsl-desktop'
    home.mkdir(parents=True, exist_ok=True)
    python = _ensure_venv(home, _ensure_python(local_appdata))
    _check_tesseract(home)
    command = [str(python), '-c', _LAUNCH, to_windows(source_root()), *child_args(config, smoke_test)]
    try:
        return subprocess.run(command).returncode
    except KeyboardInterrupt:
        return 130
