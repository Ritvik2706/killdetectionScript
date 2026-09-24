"""Traits: the filter algebra, the timestamps round-trip, and the "#" probe."""

import cv2
import numpy as np
import pytest

from killcutter import traits
from killcutter.errors import ConfigError
from killcutter.models import Clip


def clip(**tags):
    return Clip(0.0, 1.0, "x", tags)


# ── Filter algebra ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tags, require, exclude, kept", [
    ({"real-player": True},  [], ["bot"], True),
    ({"real-player": False}, [], ["bot"], False),
    ({"real-player": True},  ["real-player"], [], True),
    ({"real-player": False}, ["real-player"], [], False),
    ({"real-player": False}, ["bot"], [], True),
    ({"real-player": True},  [], ["real-player"], False),
    ({},                     [], [], True),
])
def test_matches(tags, require, exclude, kept):
    assert traits.matches(clip(**tags), require, exclude) is kept


def test_unknown_is_kept_by_default():
    """An undetermined trait must never cost you a highlight silently."""
    assert traits.matches(clip(**{"real-player": None}), [], ["bot"]) is True
    assert traits.matches(clip(), [], ["bot"]) is True


def test_drop_unknown_is_strict():
    assert traits.matches(clip(), [], ["bot"], keep_unknown=False) is False


def test_select_partitions():
    clips = [clip(**{"real-player": True}), clip(**{"real-player": False}), clip()]
    kept, dropped = traits.select(clips, [], ["bot"])
    assert len(kept) == 2 and len(dropped) == 1


def test_unknown_trait_name_is_rejected():
    with pytest.raises(ConfigError):
        traits.get("headshot-only")


# ── Resolution and merging ──────────────────────────────────────────────────────

def test_positive_evidence_wins_over_blank_frames():
    trait = traits.get("real-player")
    assert trait.resolve([None, False, True, None]) is True
    assert trait.resolve([None, False, False]) is False
    assert trait.resolve([None, None]) is None


def test_merge_keeps_the_positive():
    assert traits.merge({"real-player": False}, {"real-player": True}) == {"real-player": True}
    assert traits.merge({"real-player": True}, {"real-player": False}) == {"real-player": True}
    assert traits.merge({"real-player": False}, {"real-player": None}) == {"real-player": False}
    # An unknown adds nothing: an absent key and a None mean the same thing.
    assert traits.merge({}, {"real-player": None}) == {}


# ── timestamps.txt round-trip ───────────────────────────────────────────────────

def test_encode_decode_round_trip():
    line = "1.000 2.000 Someone" + traits.encode({"real-player": True})
    body, tags = traits.decode(line)
    assert body == "1.000 2.000 Someone"
    assert tags == {"real-player": True}


def test_unknown_traits_are_not_written():
    assert traits.encode({"real-player": None}) == ""
    assert traits.encode({}) == ""


def test_lines_without_tags_still_parse():
    """Files written before traits existed must keep loading unchanged."""
    assert traits.decode("1.0 2.0 Someone") == ("1.0 2.0 Someone", {})
    # A name that merely ends in brackets is not a trait suffix.
    assert traits.decode("1.0 2.0 [clan] guy") == ("1.0 2.0 [clan] guy", {})


# ── The "#" probe ───────────────────────────────────────────────────────────────

def _glyph(art):
    return np.array([[255 if c == "#" else 0 for c in row] for row in art], np.uint8)


HASH = _glyph(traits.HASH_TEMPLATE_ART)

# A couple of blocky stand-ins for ordinary name glyphs, the same height as the
# "#". Rendering with an OpenCV vector font would prove nothing: the template is
# the game's HUD font by design, so a Hershey "#" is *supposed* to miss.
LETTER = _glyph((
    "..#####..", ".#######.", "###...###", "###...###", "#########",
    "#########", "###...###", "###...###", "###...###", "###...###",
    "###...###", "###...###", "###...###", "###...###", ".........", ".........",
))
DIGIT = _glyph((
    "..#####..", ".#######.", "###...###", "###...###", "###...###",
    "###...###", "###...###", "###...###", "###...###", "###...###",
    "###...###", "###...###", ".#######.", "..#####..", ".........", ".........",
))


def _strip(glyphs, *, scale=1.0, seed=0, height=38, width=560):
    """Compose a red name line on a noisy background, like the real strip."""
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 90, (height, width, 3), dtype=np.uint8)   # game world
    x = 6
    for glyph in glyphs:
        h, w = glyph.shape
        img[6:6 + h, x:x + w][glyph > 0] = (38, 57, 160)            # HUD red, BGR
        x += w + 2
    if scale != 1.0:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return img


def _name(n=6):
    return [LETTER if i % 2 else DIGIT for i in range(n)]


def test_name_mask_rejects_the_background():
    """The whole point of the colour mask: only the red text survives it."""
    rng = np.random.default_rng(1)
    noise = rng.integers(0, 90, (40, 560, 3), dtype=np.uint8)
    assert np.count_nonzero(traits.name_mask(noise)) == 0


def test_blank_strip_is_unknown_not_false():
    """No ELIMINATED line on screen is "don't know", never "bot"."""
    blank = np.zeros((40, 560, 3), dtype=np.uint8)
    assert traits.real_player(blank) is None
    assert traits.real_player(None) is None


def test_hash_structure_accepted_and_lookalikes_rejected():
    template = np.array([[255 if c == "#" else 0 for c in row]
                         for row in traits.HASH_TEMPLATE_ART], dtype=np.uint8)
    assert traits.looks_like_hash(template) is True
    # A solid block has no structure; a single crossbar is an "H", not a "#".
    assert traits.looks_like_hash(np.full((16, 13), 255, np.uint8)) is False
    bar = np.zeros((16, 13), np.uint8)
    bar[2:4, :] = 255
    bar[:, 2:5] = 255
    assert traits.looks_like_hash(bar) is False


def test_probe_finds_a_hash_in_a_composed_strip():
    mask = traits.name_mask(_strip(_name() + [HASH] + _name(7)))
    score, x, confirmed = traits.find_hash(mask)
    assert confirmed, f"no # found (best score {score:.2f})"


def test_probe_reports_no_hash_for_a_bare_name():
    assert traits.real_player(_strip(_name(9))) is False


@pytest.mark.parametrize("scale", [0.83, 1.0, 1.33])
def test_hash_is_found_at_other_hud_sizes(scale):
    """The game has its own HUD-size setting, so the glyph is not always 1.0."""
    strip = _strip(_name() + [HASH] + _name(7), scale=scale)
    assert traits.real_player(strip, scale) is True


def test_hash_is_found_even_when_the_scale_guess_is_wrong():
    """A frame-derived scale can be well off; the search must absorb it."""
    strip = _strip(_name() + [HASH] + _name(7))
    assert traits.real_player(strip, 1.2) is True
    assert traits.real_player(strip, 0.8) is True


def test_hash_at_the_very_end_is_not_a_suffix():
    """A real suffix is "#<digits>" -- a trailing "#"-shape has nothing after it."""
    assert traits.real_player(_strip(_name() + [HASH])) is False


def test_a_tall_red_blob_is_unknown_not_bot():
    """An explosion in the strip must not be read as "this was a bot"."""
    img = np.zeros((38, 560, 3), np.uint8)
    img[2:36, 40:300] = (38, 57, 160)
    assert traits.real_player(img) is None


# ── Vote rule ───────────────────────────────────────────────────────────────────

def test_one_flukey_frame_does_not_decide_a_kill():
    """False positives compound over a window; one vote is not enough."""
    trait = traits.get("real-player")
    assert trait.resolve([False, False, True, False, False]) is False
    assert trait.resolve([False, True, True, False]) is True


def test_thin_evidence_still_counts():
    """A window that only yielded a frame or two is not punished for it."""
    trait = traits.get("real-player")
    assert trait.resolve([True]) is True
    assert trait.resolve([None, True, None]) is True


# ── Interactive selection ───────────────────────────────────────────────────────

def test_kill_filter_choices_map_to_trait_flags():
    """The menu's three choices must be exactly the useful filter states."""
    from killcutter.ui import workspace
    labels = [label for label, _, _ in workspace.KILL_FILTERS]
    assert labels[0].startswith("All")
    assert workspace.filter_label([], []) == labels[0]
    assert workspace.filter_label([], ["bot"]) == labels[1]
    assert workspace.filter_label(["bot"], []) == labels[2]
    # Every choice the menu offers must be a filter the CLI actually accepts.
    for _, require, exclude in workspace.KILL_FILTERS:
        for spec in list(require) + list(exclude):
            traits.get(spec)


def test_kill_filter_choices_actually_filter():
    from killcutter.ui import workspace
    real, bot = clip(**{"real-player": True}), clip(**{"real-player": False})
    for label, require, exclude in workspace.KILL_FILTERS:
        kept, _ = traits.select([real, bot], require, exclude)
        expected = {"All kills": 2}.get(label.split(" ·")[0], 1)
        assert len(kept) == expected, label


def test_unrecognised_filter_pair_falls_back_to_all():
    from killcutter.ui import workspace
    assert workspace.filter_index(["real-player"], ["bot"]) == 0
