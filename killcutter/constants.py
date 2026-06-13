"""Tunable defaults for detection and clip discovery, in one place.

These assume 1920x1080 footage with the current CoD HUD. If the UI changes,
re-run ``python -m killcutter calibrate`` to find fresh values.
"""

# Where the interactive picker looks for footage.
DEFAULT_CLIPS_DIR = "/mnt/r/Videos/Clips/Warzone"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".wmv"}

# "ENEMY DOWNED" banner — top-right, 1920x1080. (x, y, w, h)
DEFAULT_REGION = (1598, 186, 189, 45)

# Cheap per-frame trigger: a pixel that is white on the banner text and one
# that is red on its accent. Both must match before we pay for OCR.
TRIGGER_PIXEL_WHITE = (1581, 195)
TRIGGER_PIXEL_RED = (1607, 195)
BRIGHT_THRESHOLD = 200   # all RGB channels must exceed this to count as "white"
RED_THRESHOLD = 150      # R must exceed this; G and B must be below it

# PSM 6 (uniform block) preserves line order so we can pull the player name.
TESSERACT_CONFIG = "--psm 6"
