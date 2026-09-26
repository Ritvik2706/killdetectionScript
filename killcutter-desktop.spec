# Build on the target OS: python tools/build_desktop.py
from pathlib import Path
import os
import sys
root = Path(SPECPATH)
assets = root / 'killcutter' / 'gui' / 'assets'
runtime_binaries, runtime_data = [], [(str(assets), 'killcutter/gui/assets')]
runtime_dir = os.environ.get('KILLCUTTER_BUILD_RUNTIME')
if runtime_dir:
    runtime = Path(runtime_dir)
    for source in runtime.rglob('*'):
        if not source.is_file():
            continue
        destination = str(Path('runtime') / source.relative_to(runtime).parent)
        native = source.suffix.lower() in ('.exe', '.dll', '.dylib') or '.so' in source.name or source.name in ('ffmpeg', 'ffprobe', 'tesseract')
        (runtime_binaries if native else runtime_data).append((str(source), destination))
a = Analysis(
    [str(root / 'tools' / 'desktop_entry.py')], pathex=[str(root)],
    binaries=runtime_binaries, datas=runtime_data, hiddenimports=['PIL._tkinter_finder', 'tkinter.filedialog', 'tkinter.messagebox'],
    excludes=['pytest', 'matplotlib', 'IPython', 'PyQt5', 'PyQt6', 'PySide6'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='KillcutterStudio',
          debug=False, strip=False, upx=False, console=False,
          icon=str(assets / ('killcutter.icns' if sys.platform == 'darwin' else 'killcutter.ico')))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='KillcutterStudio')

if sys.platform == 'darwin':
    app = BUNDLE(coll, name='Killcutter Studio.app', icon=str(assets / 'killcutter.icns'),
                 bundle_identifier='studio.killcutter.desktop')
