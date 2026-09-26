"""Discover optional native runtimes included in a desktop distribution."""
from pathlib import Path
import os
import sys


def configure(folder=None):
    if folder is None:
        if not getattr(sys, 'frozen', False):
            return
        folder = Path(sys._MEIPASS) / 'runtime'
    folder = Path(folder)
    if not folder.is_dir():
        return
    os.environ['PATH'] = str(folder) + os.pathsep + os.environ.get('PATH', '')
    for name in ('tesseract.exe', 'tesseract'):
        candidate = folder / name
        if candidate.is_file():
            os.environ.setdefault('KILLCUTTER_TESSERACT', str(candidate))
            break
    for pattern in ('mpv-2.dll', 'libmpv-2.dll', 'libmpv.so*', 'libmpv*.dylib'):
        candidates = sorted(folder.glob(pattern))
        if candidates:
            os.environ.setdefault('KILLCUTTER_MPV', str(candidates[0]))
            break
    if (folder / 'tessdata').is_dir():
        os.environ.setdefault('TESSDATA_PREFIX', str(folder / 'tessdata'))
