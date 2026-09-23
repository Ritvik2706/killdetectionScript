"""Tunable defaults for detection and clip discovery, in one place.

These assume 1920x1080 footage with the current CoD HUD. If the UI changes,
run ``python -m killcutter diagnose`` to see which assumption broke, then
``python -m killcutter calibrate`` to find fresh values.
"""

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".wmv"}


def _default_clips_dir() -> str:
    """Best guess at where this machine keeps recordings.

    There is no portable answer, so try the usual places and fall back to the
    working directory. ``KILLCUTTER_CLIPS_DIR`` or ``[detect] clips_dir`` in the
    config override this; the picker prints whichever it ended up using.
    """
    import os

    override = os.environ.get("KILLCUTTER_CLIPS_DIR")
    if override:
        return override

    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, "Videos", "Clips", "Warzone"),
        os.path.join(home, "Videos", "Clips"),
        os.path.join(home, "Videos"),
        os.path.join(home, "Movies"),            # macOS
        "/mnt/r/Videos/Clips/Warzone",           # the original WSL setup
    ]
    userprofile = os.environ.get("USERPROFILE")  # Windows, incl. from WSL
    if userprofile:
        candidates.insert(0, os.path.join(userprofile, "Videos", "Clips", "Warzone"))
        candidates.append(os.path.join(userprofile, "Videos"))
    for path in candidates:
        if os.path.isdir(path):
            return path
    return os.getcwd()


# Where the interactive picker looks for footage.
DEFAULT_CLIPS_DIR = _default_clips_dir()

# "ENEMY DOWNED" banner — top-right, 1920x1080. (x, y, w, h)
# Covers the header line and the player name underneath it.
DEFAULT_REGION = (1598, 186, 189, 45)

# Notifications stack downward in fixed-height slots, newest on top. Every kill
# banner appears in slot 1 first, so scanning slot 1 alone catches them all;
# the pitch is here for diagnostics that want to look further down the stack.
BANNER_SLOT_PITCH = 95
BANNER_SLOT_HEIGHT = 84

# ── Cheap per-frame trigger ─────────────────────────────────────────────────────
# Two pixel reads gate the expensive OCR call.
#
# WHITE sits on the banner's circular icon, which is near-white for a kill and
# dark or tinted for every other notification that uses this slot — it does most
# of the filtering. ACCENT sits on the coloured bar down the banner's left edge
# and only confirms that *some* notification is present.
#
# The accent hue is deliberately NOT checked. It was red until the Sept 2026
# HUD restyle and is yellow now, and other notifications use red and orange
# there, so hue says nothing useful about what kind of banner this is.
# Enemy-vs-teammate is decided by OCR in ``BANNER_HEADER`` below.
TRIGGER_PIXEL_WHITE = (1581, 195)
TRIGGER_PIXEL_ACCENT = (1506, 208)

BRIGHT_THRESHOLD = 200   # all RGB channels must exceed this to count as "white"
ACCENT_MIN_RED = 150     # accent bar is a saturated warm colour: high R, low B
ACCENT_MAX_BLUE = 90

# ── OCR confirmation ────────────────────────────────────────────────────────────
# The pixel gate cannot tell a kill from a teammate going down — same icon, same
# accent colour — so the banner's header line is OCR'd and matched. Headers are
# compared with a fuzzy ratio because OCR mangles them ("ENEMY DOVWNED").
BANNER_HEADER = "ENEMY DOWNED"
REJECTED_HEADERS = ("TEAMMATE DOWN", "TEAMMATE DEAD")
HEADER_MIN_RATIO = 0.62

# A banner stays up ~4s, which outlives the detection cooldown, so the same one
# gets read more than once. Re-reads are recognised by the player name rather
# than by timing — but OCR rarely spells a name the same way twice ("Antho" /
# "Amtho"), so names are compared with confusable characters folded together
# and a similarity threshold rather than for equality.
NAME_MATCH_RATIO = 0.78
NAME_CONFUSABLES = {"0": "o", "1": "l", "i": "l", "5": "s", "8": "b"}

# ── Detection lag ───────────────────────────────────────────────────────────────
# We always notice a kill slightly after it happens, for two reasons: the banner
# sweeps in rather than popping, so it takes a moment to reach the trigger pixel,
# and we only look every 1/rate seconds. Left uncorrected, a clip asking for 5s
# of lead-in gets about 4.45s and feels like it starts late.
#
# The sampling half of that is computed from --rate. This constant is the other
# half: the sweep-in ramp, measured across 11 kills at 60fps as the gap between
# the banner first appearing and the trigger pixel lighting up.
BANNER_RAMP_SECONDS = 0.30

# PSM 6 (uniform block) preserves line order so we can pull the player name.
TESSERACT_CONFIG = "--psm 6"
