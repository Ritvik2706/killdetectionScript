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
# Where your recordings live. Without this, killcutter looks in the usual
# places (~/Videos/Clips/Warzone, ~/Videos, ~/Movies, %USERPROFILE%\\Videos).
# clips_dir   = "D:/Videos/Clips/Warzone"

# Separate destinations; empty means the current working directory.
timestamps_dir = ""
clips_output_dir = "highlights"
render_clips = false     # optional MP4 rendering requires FFmpeg

offset      = 5          # seconds before the kill for the clip start
end_offset  = 5          # seconds after the kill for the clip end
merge_gap   = 10         # merge kills closer than this into one clip
cooldown    = 3          # min seconds between detections
rate        = 4          # frame samples per second; higher = tighter cut timing
                         # and costs little, since every frame is decoded anyway
export      = true       # auto-run the highlight exporter when detection ends

# Trait filters (see 'killcutter traits' for the list). Names are the same ones
# --require / --exclude take, so 'exclude = ["bot"]' keeps real-player kills only.
require      = []
exclude      = []
drop_unknown = false     # true also drops kills whose trait could not be read

# The banner region is scaled automatically from the 1920x1080 reference, so
# 1440p/4K/ultrawide work without changing anything. Set this only if you have
# measured your own with 'killcutter calibrate'.
# region    = [1598, 186, 189, 45]   # x, y, w, h

[export]
output_dir = ""         # destination for EDL files
# Leave fps unset: the real rate is read from the file. Only force it if your
# Premiere sequence must stay at a rate the footage is not (see the README).
# fps  = 59.94
name = "Kill Highlights" # sequence name shown in Premiere

[ui]
color = true             # set false to disable ANSI colour everywhere

# [gui] is written by the desktop app (theme, accent, scale, chime, window
# geometry, last page, recent recordings). Edit it there; anything unusable
# here falls back to the default instead of stopping the app.
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
    with open(path, "w", encoding="utf-8") as f:
        f.write(DEFAULT_TOML)
    print(ui.badge("WROTE", bg=ui.GREEN) + " " + ui.paint(path, ui.WHITE))
    return path


def save_updates(path, updates):
    """Atomically update scalar settings, preserving comments and unknown options."""
    import json
    import re
    import tempfile
    from pathlib import Path

    target = Path(path).expanduser()
    source = target.read_text(encoding="utf-8") if target.exists() else DEFAULT_TOML
    # Never overwrite a malformed file with guessed settings.
    tomllib.loads(source)
    for section_name, values in updates.items():
        for key, value in values.items():
            literal = json.dumps(value, ensure_ascii=False)
            lines = source.splitlines()
            header = f"[{section_name}]"
            begin = next((i for i, line in enumerate(lines)
                          if line.split('#', 1)[0].strip() == header), None)
            if begin is None:
                lines.extend(["", header, f"{key} = {literal}"])
            else:
                finish = next((i for i in range(begin + 1, len(lines))
                               if lines[i].lstrip().startswith("[")), len(lines))
                match = next((i for i in range(begin + 1, finish)
                              if re.match(rf"\s*{re.escape(key)}\s*=", lines[i])), None)
                if match is None:
                    lines.insert(finish, f"{key} = {literal}")
                else:
                    lines[match] = f"{key} = {literal}"
            source = "\n".join(lines) + "\n"
    tomllib.loads(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         delete=False) as stream:
            temp = stream.name
            stream.write(source)
        os.replace(temp, target)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)
    return str(target)
