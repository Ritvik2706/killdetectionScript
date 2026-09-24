"""Traits: named, tri-state facts about a kill, and the filters that use them.

A *trait* answers one yes/no question about a kill by looking at a region of the
frame around the moment it happened — "was the victim a real player?" being the
first one. Detection records every registered trait on every clip; the CLI then
keeps or drops clips by trait (``--require`` / ``--exclude``), and the exporter
can re-filter an existing ``timestamps.txt`` without rescanning the video.

Traits are deliberately **tri-state**: ``True``, ``False``, or ``None`` for "the
evidence was not on screen". Unknown is a real answer here — see
:func:`real_player` — and collapsing it into ``False`` would silently throw away
genuine highlights.

Adding a trait means registering one probe; nothing else in the pipeline needs
to know it exists.
"""

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

import cv2
import numpy as np

from killcutter import constants
from killcutter.errors import ConfigError

# How long after a kill we keep looking for the trait's evidence. The
# ELIMINATED line trails the ENEMY DOWNED banner by a beat and is only up for a
# couple of seconds, so a single frame at kill time would miss most of them.
WINDOW_SECONDS = 3.0


# ── Registry ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Trait:
    """One yes/no question about a kill.

    ``probe`` receives the cropped region named by ``region`` plus the HUD scale
    and returns ``True`` / ``False`` / ``None`` for a single frame; ``resolve``
    folds one clip's worth of per-frame answers into the final one.
    """

    name: str
    summary: str
    region: str                    # attribute on hud.Hud holding the crop box
    probe: Callable
    negative_name: str = ""        # friendly alias for "this trait is False"
    detail: str = ""
    min_votes: int = 1             # positive frames needed to call it True

    def resolve(self, observations) -> Optional[bool]:
        """Fold per-frame answers into one. Positive evidence wins.

        A probe that saw the evidence once is trusted over the frames that did
        not -- the line may have been half faded-in, or occluded, in those --
        but *one* positive frame is not enough when ``min_votes`` is higher.

        That distinction matters more than it looks. Because a single True
        decides the whole clip, per-frame false positives compound across a
        ~12-frame window while per-frame misses wash out: measured on footage
        composed from real glyphs, a 2% per-frame false-positive rate became
        17% per *kill* under a one-vote rule. Requiring two agreeing frames
        costs essentially no recall and removes the one-off fluke.

        A window that only ever yielded a frame or two (a scan stopped early, a
        kill at the very end of the file) falls back to a single vote rather
        than being punished for thin evidence.
        """
        seen = [o for o in observations if o is not None]
        if not seen:
            return None
        votes = sum(1 for o in seen if o)
        if not votes:
            return False
        return votes >= (self.min_votes if len(seen) > 2 else 1)


REGISTRY: dict = {}


def register(trait: Trait) -> Trait:
    REGISTRY[trait.name] = trait
    return trait


def get(name: str) -> Trait:
    """Look a trait up by its name or its negative alias.

    Returns the trait; use :func:`polarity` to find out which way round the
    caller asked for it.
    """
    key = name.strip().lower().replace("_", "-")
    if key in REGISTRY:
        return REGISTRY[key]
    for trait in REGISTRY.values():
        if trait.negative_name and trait.negative_name == key:
            return trait
    raise ConfigError(
        f"Unknown trait: {name!r}. Known traits: {', '.join(names())}.")


def polarity(name: str) -> bool:
    """True if ``name`` refers to the trait itself, False if to its negative."""
    key = name.strip().lower().replace("_", "-")
    trait = get(key)
    return key != trait.negative_name


def names() -> list:
    out = []
    for trait in REGISTRY.values():
        out.append(trait.name)
        if trait.negative_name:
            out.append(trait.negative_name)
    return out


def regions_needed() -> set:
    return {t.region for t in REGISTRY.values()}


# ── The "real player" trait ─────────────────────────────────────────────────────
#
# CoD suffixes a real account's name with "#" plus its Activision number on the
# bottom-centre ELIMINATED line; bots have a bare name. That "#" is the whole
# signal, and it is *not* on the ENEMY DOWNED banner we already scan -- only on
# the ELIMINATED line -- so this trait needs its own region.
#
# OCR cannot be trusted with it. Tesseract reads the glyph as "s" on real
# footage ("Twitch ZenXe#1028757" comes back as "Twitch ZenxXes 1028757"), on
# every page-segmentation mode tried, which is precisely the error that would
# make the feature useless. So the "#" is found geometrically instead.
#
# What makes that reliable is the colour: the player name is drawn in saturated
# red while "ELIMINATED:" beside it is white, so a red mask isolates exactly the
# name and its suffix and rejects the entire game world behind it -- measured on
# real frames, with zero background bleed. On that clean binary the "#" is found
# two independent ways, and both have to agree:
#
#   1. template match against the glyph at the HUD's scale, and
#   2. a structural check -- "#" is the only glyph in this font with two
#      near-full-width horizontal bars crossing two full-height verticals.
#      "E" and "8" have three bars, "H" has one, "=" has no verticals.

# The "#" glyph at the 1920x1080 reference scale, traced from real footage.
HASH_TEMPLATE_ART = (
    "..###...###..",
    ".###########.",
    ".############",
    ".############",
    ".############",
    ".####..#####.",
    ".####..####..",
    ".####..####..",
    ".####..####..",
    ".####.#####..",
    "############.",
    "############.",
    ".####.#####..",
    ".###..#####..",
    ".###...###...",
    "..##...##....",
)

# Match score below which we do not even run the structural check.
#
# Set by two measurements together, and it is worth keeping both in mind before
# touching it:
#
#  * On strips composed from glyphs cut out of the real screenshots, scored the
#    way the pipeline actually decides (per *kill*, over a window, not per
#    frame), per-kill recall is flat at ~100% from 0.45 upwards, so the number
#    is chosen by false positives: 0.50 measured 28% per kill, 0.55 measured
#    3.4%, 0.58 measured 1.7%.
#  * But real re-encoded frames peak around 0.60 and fail outright at 0.65 --
#    the composed strips paste clean bitmaps and so score higher than genuine
#    H.264 footage does. Tuning on them alone once pushed this to 0.65 and
#    silently broke every real frame in the test set.
#
# 0.55 keeps roughly 0.05 of headroom on real footage. That headroom is worth
# more than the last point of false-positive rate, because the two errors are
# not symmetric: a missed "#" marks a real player as a bot and '--exclude bot'
# then throws the highlight away, while a false "#" merely keeps a bot clip.
HASH_MATCH_MIN = 0.55

# A row counts as a "bar" when it is nearly as inked as the fullest row in the
# glyph, and a column as a "stem" at this fraction of the glyph's height.
#
# BAR_FILL is relative rather than absolute on purpose. Video compression
# thickens these strokes -- on a re-encoded frame the "#" stems alone fill 80%
# of the glyph's width -- so a fixed 0.8 cutoff swallows the gaps between the
# crossbars and the whole thing reads as one solid band. Measuring against the
# glyph's own fullest row survives that.
BAR_FILL = 0.90          # fraction of the fullest row
BAR_FLOOR = 0.80         # ...which must itself be this full, or there are no bars
STEM_FILL = 0.70

# Height of the name's text band, in pixels, at the 1920x1080 reference. Used to
# read the real font size straight off the mask instead of trusting the frame
# size -- see :func:`_candidate_scales`.
REFERENCE_BAND_HEIGHT = 19.0
SCALE_SEARCH = (0.85, 0.93, 1.0, 1.08, 1.16)
MIN_SCALE, MAX_SCALE = 0.35, 4.0

# Fewer inked pixels than this in the strip means no ELIMINATED line is up, so
# the trait is unknown rather than false.
MIN_TEXT_PIXELS = 60

# A real suffix always has digits after the "#", so this much ink must follow it.
MIN_SUFFIX_PIXELS = 12

# The name is one line of text. If the red ink spans much more of the strip than
# a line of text can, we are looking at something else -- an explosion, a hit
# marker, a red vehicle -- and the honest answer is "don't know", not "bot".
MAX_BAND_FRACTION = 0.80


def _template(scale: float):
    art = np.array([[255 if c == "#" else 0 for c in row]
                    for row in HASH_TEMPLATE_ART], dtype=np.uint8)
    if abs(scale - 1.0) < 1e-6:
        return art
    h = max(6, int(round(art.shape[0] * scale)))
    w = max(5, int(round(art.shape[1] * scale)))
    resized = cv2.resize(art, (w, h), interpolation=cv2.INTER_AREA)
    return ((resized > 127) * 255).astype(np.uint8)


def name_mask(roi):
    """Binary mask of the red player-name text inside the ELIMINATED strip.

    Keeps pixels that are bright red and clearly redder than they are green or
    blue, which is what separates the name from both the white "ELIMINATED:"
    label and whatever the player happens to be looking at.
    """
    b, g, r = (c.astype(np.int16) for c in cv2.split(roi))
    keep = ((r > constants.NAME_RED_MIN)
            & ((r - g) > constants.NAME_RED_MARGIN)
            & ((r - b) > constants.NAME_RED_MARGIN))
    return (keep.astype(np.uint8) * 255)


def _bands(flags) -> list:
    """Contiguous runs of True in ``flags``, as ``(start, stop)`` pairs."""
    runs, start = [], None
    for i, on in enumerate(flags):
        if on and start is None:
            start = i
        elif not on and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(flags)))
    return runs


def looks_like_hash(window) -> bool:
    """Structural test: does this binary glyph window have the "#" topology?

    Two separated near-full-width horizontal bars, at least two full-height
    vertical stems, and ink above the first bar and below the last (a "#"
    overhangs its crossbars; an "E" or an "8" does not).
    """
    ink = window > 0
    if not ink.any():
        return False
    rows = np.flatnonzero(ink.any(axis=1))
    cols = np.flatnonzero(ink.any(axis=0))
    glyph = ink[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    height, width = glyph.shape
    if height < 6 or width < 5:
        return False

    row_fill = glyph.sum(axis=1) / width
    if row_fill.max() < BAR_FLOOR:
        return False
    bars = _bands(row_fill >= BAR_FILL * row_fill.max())
    if len(bars) != 2:
        return False
    # Both bars must be thin, and neither may sit at the very top or bottom --
    # a "#" pokes out above and below its crossbars.
    for start, stop in bars:
        if (stop - start) > 0.40 * height:
            return False
    if bars[0][0] == 0 or bars[1][1] == height:
        return False

    stems = _bands(glyph.sum(axis=0) >= STEM_FILL * height)
    return len(stems) >= 2


def _candidate_scales(mask, hud_scale: float) -> list:
    """Template scales worth trying, best guess first.

    The HUD scale derived from the frame size is only a guess: the game has its
    own HUD-size setting, so the glyphs can be a different size on a 1080p
    capture than the reference. Measuring the text band in the mask gives a
    direct reading of the font size instead, and a few steps either side absorb
    what is left. This matters enormously -- with a single template sized from
    the frame alone, a 1.2x error in that guess dropped per-frame recall from
    78% to 9%; searching the range brings it back to 82%.
    """
    scales, rows = [], np.flatnonzero((mask > 0).any(axis=1))
    bases = []
    if len(rows):
        bases.append((rows[-1] - rows[0] + 1) / REFERENCE_BAND_HEIGHT)
    bases.append(hud_scale)
    for base in bases:
        for factor in SCALE_SEARCH:
            value = round(base * factor, 3)
            if MIN_SCALE <= value <= MAX_SCALE and value not in scales:
                scales.append(value)
    return scales


def find_hash(mask, scale: float = 1.0):
    """Best "#" candidate in a name mask: ``(score, x, confirmed)``.

    Every position clearing :data:`HASH_MATCH_MIN`, at every candidate scale, is
    offered to the structural check -- the true "#" is not always the global
    peak on a name containing a busy glyph, so taking only the best match loses
    real hits.
    """
    best = 0.0
    for candidate in _candidate_scales(mask, scale):
        template = _template(candidate)
        th, tw = template.shape
        if mask.shape[0] < th or mask.shape[1] < tw:
            continue
        scores = cv2.matchTemplate(mask.astype(np.float32),
                                   template.astype(np.float32), cv2.TM_CCOEFF_NORMED)
        ys, xs = np.nonzero(scores >= HASH_MATCH_MIN)
        for y, x in zip(ys, xs):
            best = max(best, float(scores[y, x]))
            window = mask[y:y + th, x:x + tw]
            if not looks_like_hash(window):
                continue
            # A real suffix is "#<digits>": there is always ink to the right of
            # the glyph. A "#"-shaped blob at the very end of the name is not one.
            if int(np.count_nonzero(mask[:, x + tw:])) < MIN_SUFFIX_PIXELS:
                continue
            return float(scores[y, x]), int(x), True
    return best, -1, False


def real_player(roi, scale: float = 1.0) -> Optional[bool]:
    """True if the eliminated player's name carries an Activision "#" suffix.

    ``None`` when no ELIMINATED line is on screen at all. That is common and
    must not be read as "bot": the line only appears for the *finishing* blow,
    so a knock a teammate confirms produces a kill banner with no line behind it.
    """
    if roi is None or roi.size == 0:
        return None
    mask = name_mask(roi)
    if int(np.count_nonzero(mask)) < MIN_TEXT_PIXELS:
        return None
    rows = np.flatnonzero((mask > 0).any(axis=1))
    if len(rows) and (rows[-1] - rows[0] + 1) > MAX_BAND_FRACTION * mask.shape[0]:
        return None      # too tall to be a line of text -- see MAX_BAND_FRACTION
    _, _, confirmed = find_hash(mask, scale)
    return bool(confirmed)


register(Trait(
    name="real-player",
    negative_name="bot",
    summary="victim was a real player, not a bot",
    region="eliminated",
    probe=real_player,
    min_votes=2,
    detail=('Real accounts show "#<Activision id>" after the name on the '
            'ELIMINATED line; bots show a bare name.'),
))


# ── Recording traits during a scan ──────────────────────────────────────────────

@dataclass
class Observation:
    """Trait evidence being gathered for one clip, over a window of frames."""

    clip_index: int
    until: float
    seen: dict = field(default_factory=dict)

    def note(self, trait_name: str, answer) -> None:
        self.seen.setdefault(trait_name, []).append(answer)

    def resolve(self) -> dict:
        return {name: REGISTRY[name].resolve(answers)
                for name, answers in self.seen.items()}


def merge(existing: dict, new: dict) -> dict:
    """Combine trait maps when two kills merge into one clip.

    Positive wins, for the same reason it does within a window: a clip holding
    one confirmed real-player kill is a real-player clip, whatever else is in it.
    """
    out = dict(existing or {})
    for name, value in (new or {}).items():
        current = out.get(name)
        if current is True or value is None:
            continue
        if value is True or current is None:
            out[name] = value
    return out


# ── Filtering ───────────────────────────────────────────────────────────────────

def matches(clip, require=(), exclude=(), keep_unknown=True) -> bool:
    """Does ``clip`` survive the requested trait filters?

    ``keep_unknown`` decides what happens when a trait could not be determined:
    by default the clip is kept, so a filter never costs you a highlight it was
    merely unsure about.
    """
    traits = getattr(clip, "traits", None) or {}
    for spec, wanted in [(s, True) for s in require] + [(s, False) for s in exclude]:
        trait = get(spec)
        # "--exclude bot" asks for real-player == False; flip back to the trait.
        target = wanted if polarity(spec) else not wanted
        value = traits.get(trait.name)
        if value is None:
            if not keep_unknown:
                return False
            continue
        if value != target:
            return False
    return True


def select(clips, require=(), exclude=(), keep_unknown=True):
    """Return ``(kept, dropped)`` for a list of clips."""
    kept, dropped = [], []
    for clip in clips:
        (kept if matches(clip, require, exclude, keep_unknown) else dropped).append(clip)
    return kept, dropped


# ── timestamps.txt round-trip ───────────────────────────────────────────────────
#
# Traits ride along on the end of each line in square brackets, so the exporter
# can re-filter without rescanning and older files (which have none) still load.

_TAG_RE = re.compile(r"\s*\[([^\]]*)\]\s*$")


def encode(traits: dict) -> str:
    """Render a trait map as the ``[name=yes, other=no]`` line suffix."""
    known = {k: v for k, v in (traits or {}).items() if v is not None}
    if not known:
        return ""
    body = ", ".join(f"{k}={'yes' if v else 'no'}" for k, v in sorted(known.items()))
    return f" [{body}]"


def decode(text: str):
    """Split a trailing ``[...]`` trait suffix off ``text``.

    Returns ``(remaining_text, traits)``. Text without a suffix -- every file
    written before this feature existed -- comes back with an empty map.
    """
    match = _TAG_RE.search(text)
    if not match:
        return text, {}
    traits = {}
    for item in match.group(1).split(","):
        key, _, value = item.partition("=")
        key = key.strip().lower()
        if key in REGISTRY:
            traits[key] = value.strip().lower() in ("yes", "true", "1")
    if not traits:
        return text, {}
    return text[:match.start()], traits
