"""Desktop-only appearance and session preferences.

These live in the same TOML file as the CLI settings, under ``[gui]``, so one
file still describes the whole tool. Every value is validated on load: a
hand-edited or stale file degrades to the default rather than failing to start.
"""
from dataclasses import dataclass, replace
import re

from killcutter import config
from .theme import ACCENTS, PALETTES

MIN_SCALE, MAX_SCALE = 0.8, 1.6
GEOMETRY = re.compile(r'^\d+x\d+([+-]\d+[+-]\d+)?$')
HEX = re.compile(r'^#[0-9A-Fa-f]{6}$')
PAGES = ('workspace', 'results', 'presets', 'settings')
RECENT_LIMIT = 8


@dataclass(frozen=True)
class Preferences:
    theme: str = next(iter(PALETTES))
    accent: str = ACCENTS['Blue']
    scale: float = 1.0
    chime: bool = True
    geometry: str = ''
    page: str = PAGES[0]
    recents: tuple[str, ...] = ()

    @property
    def appearance(self):
        """The subset that changes how the window looks."""
        return self.theme, self.accent, self.scale


def _scale(value):
    return round(min(MAX_SCALE, max(MIN_SCALE, float(value))), 2)


def load(cfg):
    """Read ``[gui]`` from a loaded config, ignoring anything unusable."""
    values = config.section(cfg, 'gui')
    prefs = Preferences()
    updates = {}
    theme = values.get('theme')
    if theme in PALETTES:
        updates['theme'] = theme
    accent = values.get('accent')
    if isinstance(accent, str) and HEX.match(accent):
        updates['accent'] = accent.upper()
    try:
        updates['scale'] = _scale(values.get('scale', prefs.scale))
    except (TypeError, ValueError):
        pass
    if isinstance(values.get('chime'), bool):
        updates['chime'] = values['chime']
    geometry = values.get('geometry')
    if isinstance(geometry, str) and GEOMETRY.match(geometry):
        updates['geometry'] = geometry
    if values.get('page') == 'inspector':
        updates['page'] = 'presets'
    if values.get('page') in PAGES:
        updates['page'] = values['page']
    recents = values.get('recents')
    if isinstance(recents, list):
        updates['recents'] = tuple(str(item) for item in recents[:RECENT_LIMIT] if isinstance(item, str))
    return replace(prefs, **updates)


def remember(prefs, path):
    """Return preferences with ``path`` promoted to the front of the recents."""
    recents = (str(path),) + tuple(p for p in prefs.recents if p != str(path))
    return replace(prefs, recents=recents[:RECENT_LIMIT])


def save(path, prefs):
    config.save_updates(path, {'gui': {
        'theme': prefs.theme, 'accent': prefs.accent, 'scale': prefs.scale,
        'chime': prefs.chime, 'geometry': prefs.geometry, 'page': prefs.page,
        'recents': list(prefs.recents)}})
