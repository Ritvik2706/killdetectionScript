"""Versioned, portable detection recipes. No UI or executable code in presets."""
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import re

from .errors import ConfigError
from .outputs import atomic_text


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    detector: str = 'text'
    version: int = 1
    # Normalized x, y, width, height; independent of source resolution.
    region: tuple = (0.0, 0.0, 1.0, 1.0)
    text: str = ''
    color: tuple = (255, 0, 0)
    tolerance: int = 30
    coverage: float = .1
    label: str = 'Detected event'
    audio_db: float = -24.0

    @property
    def needs_ocr(self):
        return self.detector in ('warzone', 'text')

    @property
    def has_player_traits(self):
        return self.detector == 'warzone'

    def validate(self):
        if type(self.version) is not int or self.version != 1:
            raise ConfigError('Unsupported preset version. Expected version 1.')
        if not isinstance(self.id, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,79}', self.id):
            raise ConfigError('Preset ID must use lowercase letters, numbers, hyphens or underscores.')
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 100:
            raise ConfigError('Give the preset a name of 1–100 characters.')
        if self.detector not in ('warzone', 'text', 'color', 'motion', 'scene', 'audio'):
            raise ConfigError(f'Unknown detector: {self.detector}')
        if len(self.region) != 4 or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in self.region):
            raise ConfigError('Region must contain four finite numbers.')
        x, y, w, h = self.region
        if min(x, y) < 0 or min(w, h) <= 0 or x + w > 1.000000001 or y + h > 1.000000001:
            raise ConfigError('Region must fit inside the video (0–100%, with positive width and height).')
        if not isinstance(self.text, str) or (self.detector == 'text' and not self.text.strip()):
            raise ConfigError('Text presets need a phrase to detect.')
        if len(self.color) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in self.color):
            raise ConfigError('Colour must contain three RGB integers from 0 to 255.')
        if type(self.tolerance) is not int or not 0 <= self.tolerance <= 255:
            raise ConfigError('Colour tolerance must be an integer from 0 to 255.')
        if not isinstance(self.coverage, (int, float)) or not math.isfinite(self.coverage) or not 0 < self.coverage <= 1:
            raise ConfigError('Colour coverage must be greater than 0% and at most 100%.')
        if not isinstance(self.audio_db, (int, float)) or not math.isfinite(self.audio_db) or not -90 <= self.audio_db <= 0:
            raise ConfigError('Audio threshold must be between -90 and 0 dBFS.')
        if not isinstance(self.label, str) or not self.label.strip() or '\n' in self.label or '\r' in self.label:
            raise ConfigError('Event label must be a nonempty single line.')
        return self

    def box(self, width, height):
        x, y, w, h = self.region
        def pixel(value):
            # Normalized coordinates can land a few ulps either side of an
            # integer. Preserve exact source-pixel selections on round-trip.
            nearest = round(value)
            return nearest if math.isclose(value, nearest, rel_tol=0, abs_tol=1e-9) else value
        left, top = min(width-1, int(pixel(x*width))), min(height-1, int(pixel(y*height)))
        right = min(width, max(left+1, math.ceil(pixel((x+w)*width))))
        bottom = min(height, max(top+1, math.ceil(pixel((y+h)*height))))
        return left, top, right-left, bottom-top


WARZONE = Preset('warzone', 'Call of Duty · Warzone', detector='warzone', label='Enemy downed')


def load(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('Preset must be a JSON object.')
        data['region'] = tuple(data.get('region', (0, 0, 1, 1)))
        data['color'] = tuple(data.get('color', (255, 0, 0)))
        return Preset(**data).validate()
    except (ValueError, TypeError, KeyError, OSError) as exc:
        raise ConfigError(f'Could not load preset {path}: {exc}') from exc


def save(path, preset):
    preset.validate()
    atomic_text(path, json.dumps(asdict(preset), indent=2, ensure_ascii=False) + '\n')


class Library:
    """Built-in Warzone recipe plus user JSON files next to the configuration."""
    def __init__(self, config_path):
        self.folder = Path(config_path).expanduser().parent / 'presets'
        self.items = {WARZONE.id: WARZONE}
        self.paths = {}
        self.errors = []
        for path in sorted(self.folder.glob('*.json')):
            try:
                preset = load(path)
                if preset.id in self.items or any(p.name == preset.name for p in self.items.values()):
                    raise ConfigError(f'Duplicate or reserved preset ID: {preset.id}')
                self.items[preset.id] = preset
                self.paths[preset.id] = path
            except ConfigError as exc:
                self.errors.append(str(exc))

    def save(self, preset):
        preset.validate()
        if preset.id == WARZONE.id:
            raise ConfigError('The built-in Warzone preset is read-only. Save a copy instead.')
        if any(p.name == preset.name and p.id != preset.id for p in self.items.values()):
            raise ConfigError('Preset names must be unique.')
        self.folder.mkdir(parents=True, exist_ok=True)
        target = self.paths.get(preset.id, self.folder / f'{preset.id}.json')
        save(target, preset)
        self.paths[preset.id] = target
        self.items[preset.id] = preset

    def delete(self, preset_id):
        if preset_id == WARZONE.id:
            raise ConfigError('The built-in Warzone preset cannot be deleted.')
        path = self.paths[preset_id]
        path.unlink()
        del self.paths[preset_id]
        del self.items[preset_id]
