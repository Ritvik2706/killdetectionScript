"""Layered TOML configuration.

Search order (first match wins) lets a power user keep a global default and
override it per project / per footage folder:

    1. path passed via --config
    2. ./.killcutter.toml           (current directory)
    3. $XDG_CONFIG_HOME/killcutter/config.toml  (~/.config/killcutter/...)

Command-line flags always override config values (the CLI wires config into
argparse defaults).
"""

import os

try:
    import tomllib            # Python 3.11+
except ImportError:           # pragma: no cover
    tomllib = None

from killcutter import ui

APP = "killcutter"
LOCAL_NAME = ".killcutter.toml"

DEFAULT_TOML = """\
# Killfeed Auto-Cutter configuration
# Anything here becomes the default; command-line flags still win.

[detect]
# clips_dir   = "/mnt/r/Videos/Clips/Warzone"
offset      = 5          # seconds before the kill for the clip start
end_offset  = 5          # seconds after the kill for the clip end
merge_gap   = 10         # merge kills closer than this into one clip
cooldown    = 3          # min seconds between detections
rate        = 2          # frame samples per second
# region    = [1598, 186, 189, 45]   # x, y, w, h  (1920x1080 banner)
export      = true       # auto-run the highlight exporter when detection ends

[export]
# fps  = 59.94           # force authoring fps (must match your sequence)
name = "Kill Highlights" # sequence name shown in Premiere

[ui]
color = true             # set false to disable ANSI colour everywhere
"""


def user_config_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, APP, "config.toml")


def _candidates(explicit=None):
    if explicit:
        return [explicit]
    return [os.path.join(os.getcwd(), LOCAL_NAME), user_config_path()]


def load(explicit=None):
    """Return ``(config_dict, source_path_or_None)``."""
    if tomllib is None:
        return {}, None
    for path in _candidates(explicit):
        if path and os.path.isfile(path):
            try:
                with open(path, "rb") as f:
                    return tomllib.load(f), path
            except Exception as exc:
                print(ui.badge("CONFIG", bg=ui.AMBER) + " "
                      + ui.paint(f"Could not parse {path}: {exc}", ui.WHITE))
                return {}, None
    return {}, None


def section(cfg, name) -> dict:
    sec = cfg.get(name, {}) if isinstance(cfg, dict) else {}
    return sec if isinstance(sec, dict) else {}


def write_default(path=None) -> str:
    """Write a commented starter config; never clobbers an existing file."""
    path = path or user_config_path()
    if os.path.isfile(path):
        print(ui.badge("EXISTS", bg=ui.AMBER) + " "
              + ui.paint(f"Config already present: {path}", ui.WHITE))
        return path
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(DEFAULT_TOML)
    print(ui.badge("WROTE", bg=ui.GREEN) + " " + ui.paint(path, ui.WHITE))
    return path
