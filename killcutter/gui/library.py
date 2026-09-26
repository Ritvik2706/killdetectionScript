"""Recording inventory and export matching, independent of Tk."""
from dataclasses import dataclass
from pathlib import Path
import math
import time

from killcutter import video
from killcutter.constants import VIDEO_EXTENSIONS


@dataclass(frozen=True)
class Recording:
    path: Path
    size: int
    modified: float
    duration: float | None
    edl: Path | None
    timestamps: Path | None

    @property
    def status(self):
        return 'Done' if self.edl else 'Timestamps' if self.timestamps else 'Pending'


def relative_age(modified, now=None):
    seconds = max(0, (time.time() if now is None else now) - modified)
    for divisor, unit in ((86400, 'day'), (3600, 'hour'), (60, 'min')):
        if seconds >= divisor:
            count = int(seconds // divisor)
            return f'{count} {unit}{"s" if count != 1 else ""} ago'
    return 'Just now'


def scan_directory(folder, edl_folder, timestamps_folder, cache):
    """Match exact output names; cache probes only while size and mtime agree."""
    def inventory(directory):
        path = Path(directory).expanduser()
        try:
            return {p.name: p for p in path.iterdir() if p.is_file()}
        except FileNotFoundError:
            return {}

    edls, timestamps = inventory(edl_folder), inventory(timestamps_folder)
    from .edl import read_text, source_names
    references = {}
    for path in edls.values():
        if path.suffix.lower() != '.edl':
            continue
        try:
            names = set(source_names(read_text(path)))
            if len(names) == 1:
                name = next(iter(names))
                if name not in references or path.stat().st_mtime_ns > references[name].stat().st_mtime_ns:
                    references[name] = path
        except (OSError, ValueError, UnicodeError):
            continue
    rows, updated = [], {}
    for path in Path(folder).expanduser().resolve().iterdir():
        if path.suffix.lower() not in VIDEO_EXTENSIONS | {'.webm', '.m4v'} or not path.is_file():
            continue
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        key = (str(path), stat.st_size, stat.st_mtime_ns)
        duration = cache.get(key)
        if key not in cache:
            try:
                _, _, duration = video.measure(str(path))
                if not math.isfinite(duration) or duration <= 0:
                    duration = None
            except Exception:
                duration = None
        updated[key] = duration
        edl = references.get(path.name) or edls.get(path.stem + '_highlights.edl') or edls.get(path.stem + '.edl')
        stamp = timestamps.get(path.stem + '_timestamps.txt')
        rows.append(Recording(path, stat.st_size, stat.st_mtime, duration, edl, stamp))
    return sorted(rows, key=lambda r: r.modified, reverse=True), updated
