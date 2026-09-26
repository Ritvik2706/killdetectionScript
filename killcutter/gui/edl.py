"""Load cut-only CMX EDLs using source timecodes, never reel positions."""
import math
from pathlib import Path
import re

from killcutter import traits
from killcutter.models import Clip
from killcutter.timecode import resolve_fps

TC = r'\d{2,}:\d{2}:\d{2}:\d{2,3}'
EVENT = re.compile(rf'^\d+\s+\S+\s+(\S+)\s+C\s+({TC})\s+({TC})\s+({TC})\s+({TC})\s*$')


def read_text(path):
    if Path(path).stat().st_size > 5_000_000:
        raise ValueError('EDL exceeds the 5 MB import limit.')
    return Path(path).read_text(encoding='utf-8-sig')


def source_names(text):
    return re.findall(r'^\* FROM CLIP NAME:\s*(.+?)\s*$', text, re.M)


def matching_edls(folder, media):
    directory = Path(folder).expanduser()
    if not directory.exists():
        return []
    matches = []
    for path in directory.iterdir():
        if path.suffix.lower() != '.edl' or not path.is_file():
            continue
        try:
            names = source_names(read_text(path))
            if (names and all(name == Path(media.path).name for name in names)) or (
                not names and path.stem in (Path(media.path).stem, Path(media.path).stem + '_highlights')):
                matches.append((path.stat().st_mtime_ns, str(path.resolve())))
        except (OSError, UnicodeError, ValueError):
            continue
    return [path for _, path in sorted(matches, reverse=True)]


def read_edl(path, media):
    text = read_text(path)
    if re.search(r'^FCM:\s*DROP FRAME', text, re.M):
        raise ValueError('Drop-frame EDL import is not supported. Export a non-drop-frame cut EDL.')
    names = source_names(text)
    if any(name != Path(media.path).name for name in names):
        raise ValueError('This EDL references a different recording. Open its source recording first.')
    rate = re.search(r'^\* KILLCUTTER FPS:\s*(\S+)', text, re.M)
    fps = float(rate[1]) if rate else resolve_fps(media.fps)
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError('Invalid EDL frame rate.')
    nominal = round(fps)
    def seconds(tc):
        h, m, s, f = map(int, tc.split(':'))
        if m >= 60 or s >= 60 or f >= nominal:
            raise ValueError(f'Invalid source timecode: {tc}')
        return ((h * 3600 + m * 60 + s) * nominal + f) / fps
    clips = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r'^\d+\s', line):
            event = EVENT.fullmatch(line)
            if not event or event[1] not in ('V', 'B'):
                raise ValueError('Only video / audio-video cut events are supported; transitions and separate audio tracks cannot be imported.')
            start, end = seconds(event[2]), seconds(event[3])
            if not 0 <= start < end <= media.duration + 1 / fps:
                raise ValueError('EDL source range is outside this recording or has an invalid duration.')
            clips.append(Clip(start, min(end, media.duration), f'Highlight {len(clips) + 1}'))
        elif line.startswith('* KILLCUTTER TRAITS:') and clips:
            _, clips[-1].traits = traits.decode(line.partition(':')[2].strip())
        elif line.startswith('* COMMENT:') and clips:
            clips[-1].name = line.partition(':')[2].strip() or clips[-1].name
    if not clips:
        raise ValueError('No supported highlight events were found in this EDL.')
    return clips


def load_saved(folder, media, chosen=None):
    paths = matching_edls(folder, media)
    target = str(Path(chosen).resolve()) if chosen else next(iter(paths), None)
    if target and target not in paths:
        paths.insert(0, target)
    # Return discovery even if the newest file cannot be read; never replace results on error.
    try:
        clips = read_edl(target, media) if target else None
        return paths, target, clips, None
    except (OSError, ValueError, UnicodeError) as exc:
        return paths, target, None, str(exc)
