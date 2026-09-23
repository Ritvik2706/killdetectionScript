# Build on the target OS: python tools/build_desktop.py
from pathlib import Path
root = Path(SPECPATH)
a = Analysis(
    [str(root / 'tools' / 'desktop_entry.py')], pathex=[str(root)],
    binaries=[], datas=[], hiddenimports=['PIL._tkinter_finder', 'tkinter.filedialog', 'tkinter.messagebox'],
    excludes=['pytest', 'matplotlib', 'IPython', 'PyQt5', 'PyQt6', 'PySide6'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='KillcutterStudio',
          debug=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='KillcutterStudio')
