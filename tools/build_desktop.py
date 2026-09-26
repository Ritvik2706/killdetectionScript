"""Build a native portable application folder. Run on each target OS."""
from pathlib import Path
import os
import subprocess
import sys
import argparse
import shutil
import tarfile


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-dir', type=Path, help='Bundle native tools, libraries, tessdata and notices from this directory')
    parser.add_argument('--installer', action='store_true', help='Also build a native installer/archive')
    args = parser.parse_args()
    if args.runtime_dir:
        if not args.runtime_dir.is_dir():
            parser.error('--runtime-dir must be an existing directory')
        os.environ['KILLCUTTER_BUILD_RUNTIME'] = str(args.runtime_dir.resolve())
    os.environ.setdefault('PYINSTALLER_CONFIG_DIR', str(root / 'build' / 'pyinstaller-cache'))
    result = subprocess.call([sys.executable, '-m', 'PyInstaller', '--noconfirm',
                            str(root / 'killcutter-desktop.spec')], cwd=root)
    if result or not args.installer:
        return result
    if os.name == 'nt':
        compiler = shutil.which('ISCC') or shutil.which('ISCC.exe')
        if not compiler:
            candidate = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Inno Setup 6' / 'ISCC.exe'
            compiler = str(candidate) if candidate.is_file() else None
        if not compiler:
            print('Install Inno Setup 6 and add ISCC to PATH to build the installer.', file=sys.stderr)
            return 1
        return subprocess.call([compiler, str(root / 'packaging' / 'windows.iss')], cwd=root)
    folder = root / 'dist' / 'installers'
    folder.mkdir(exist_ok=True)
    with tarfile.open(folder / 'KillcutterStudio-Linux.tar.gz', 'w:gz', compresslevel=3) as archive:
        archive.add(root / 'dist' / 'KillcutterStudio', arcname='KillcutterStudio')
        archive.add(root / 'packaging' / 'install-linux.sh', arcname='install.sh')
    print(f'Installer archive: {folder}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
