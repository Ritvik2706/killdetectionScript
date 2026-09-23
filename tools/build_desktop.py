"""Build a native portable application folder. Run on each target OS."""
from pathlib import Path
import os
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    os.environ.setdefault('PYINSTALLER_CONFIG_DIR', str(root / 'build' / 'pyinstaller-cache'))
    return subprocess.call([sys.executable, '-m', 'PyInstaller', '--noconfirm',
                            str(root / 'killcutter-desktop.spec')], cwd=root)


if __name__ == '__main__':
    raise SystemExit(main())
