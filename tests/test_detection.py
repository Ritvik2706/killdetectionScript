"""Tests for the presentation-free parts of kill detection.

The pixel gates and the header matcher are the two places a game update breaks
things, so they are covered with the real strings and colours observed in
footage from both HUD eras (pre- and post-Sept-2026 restyle).
"""

import numpy as np
import pytest

from killcutter import constants
from killcutter.detection import (_banner_visible, _is_kill_header, _merge_names,
                                  _notice_lag, _pixel_is_accent, _pixel_is_white,
                                  _same_player, _samples)


def frame_with(pixels, size=(1080, 1920)):
    """Build a black BGR frame with ``{(x, y): (r, g, b)}`` painted in."""
    f = np.zeros((size[0], size[1], 3), dtype=np.uint8)
    for (x, y), (r, g, b) in pixels.items():
        f[y, x] = (b, g, r)
    return f


# ── Pixel gates ─────────────────────────────────────────────────────────────────

def test_white_pixel_accepts_banner_icon():
    f = frame_with({constants.TRIGGER_PIXEL_WHITE: (242, 236, 225)})
    assert _pixel_is_white(f, constants.TRIGGER_PIXEL_WHITE)


@pytest.mark.parametrize("rgb", [
    (49, 25, 9),      # QUICKDROP KIT icon
    (113, 103, 71),   # CONTRACT TIER icon
    (158, 148, 142),  # NAPALM STRIKE icon
    (253, 225, 0),    # accent bar swept over the pixel mid-animation
])
def test_white_pixel_rejects_other_notifications(rgb):
    f = frame_with({constants.TRIGGER_PIXEL_WHITE: rgb})
    assert not _pixel_is_white(f, constants.TRIGGER_PIXEL_WHITE)


@pytest.mark.parametrize("rgb", [
    (253, 37, 0),     # pre-Sept-2026 red accent
    (253, 226, 0),    # post-restyle yellow accent
])
def test_accent_pixel_is_hue_agnostic(rgb):
    """Both HUD eras must pass — that is the whole point of the warm test."""
    f = frame_with({constants.TRIGGER_PIXEL_ACCENT: rgb})
    assert _pixel_is_accent(f, constants.TRIGGER_PIXEL_ACCENT)


@pytest.mark.parametrize("rgb", [
    (6, 9, 24),       # no banner, dark HUD
    (40, 29, 39),     # dim scenery
    (90, 120, 200),   # cool/blue UI
])
def test_accent_pixel_rejects_non_banners(rgb):
    f = frame_with({constants.TRIGGER_PIXEL_ACCENT: rgb})
    assert not _pixel_is_accent(f, constants.TRIGGER_PIXEL_ACCENT)


def test_banner_visible_needs_both_pixels():
    white, accent = constants.TRIGGER_PIXEL_WHITE, constants.TRIGGER_PIXEL_ACCENT
    assert _banner_visible(frame_with({white: (242, 236, 225),
                                       accent: (253, 226, 0)}))
    assert not _banner_visible(frame_with({white: (242, 236, 225)}))
    assert not _banner_visible(frame_with({accent: (253, 226, 0)}))


def test_pixel_gates_ignore_out_of_bounds_coordinates():
    """Smaller-than-1080p footage must not raise, just fail the gate."""
    small = np.zeros((720, 1280, 3), dtype=np.uint8)
    assert not _pixel_is_white(small, constants.TRIGGER_PIXEL_WHITE)
    assert not _pixel_is_accent(small, constants.TRIGGER_PIXEL_ACCENT)
    assert not _banner_visible(small)


# ── Header matching ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("header", [
    "ENEMY DOWNED",
    "ENEMY DOVWNED",    # observed OCR noise
    "ENEMY DDWNED",
    "FLEMY DOWNED",
    "enemy downed",
])
def test_kill_headers_are_accepted(header):
    assert _is_kill_header(header)


@pytest.mark.parametrize("header", [
    "TEAMMATE DOWN",    # same icon, same accent colour — pixels cannot reject it
    "TEAMMATE DOW|",
    "TEAMMATE DOWI",
    "TEAMMATE DEAD",
    "QUICKDROP KIT",
    "CONTRACT TIER",
    "SMOKE SCREEN",
    "NAPALM STRIKE",
    "CLASSIFIED WEAPON",
    "",
    ")S",
])
def test_non_kill_headers_are_rejected(header):
    assert not _is_kill_header(header)


# ── Name merging ────────────────────────────────────────────────────────────────

def test_merge_names_prefers_real_names_over_unknown():
    assert _merge_names("???", "Ritvik") == "Ritvik"
    assert _merge_names("Ritvik", "???") == "Ritvik"
    assert _merge_names("Ritvik", "") == "Ritvik"


def test_merge_names_joins_distinct_and_dedupes_identical():
    assert _merge_names("A", "B") == "A + B"
    assert _merge_names("A", "A") == "A"


# ── Sampling ────────────────────────────────────────────────────────────────────

class FakeCapture:
    """Minimal VideoCapture stand-in that plays back fixed frame timestamps."""

    def __init__(self, times_ms):
        self.times = list(times_ms)
        self.i = -1

    def grab(self):
        self.i += 1
        return self.i < len(self.times)

    def retrieve(self):
        return True, np.zeros((4, 4, 3), dtype=np.uint8)

    def get(self, prop):
        return self.times[self.i]


def test_samples_honours_the_requested_interval():
    cap = FakeCapture([i * 1000 / 60 for i in range(600)])   # 10s at 60fps
    times = [t for t, _ in _samples(cap, 10.0, 0.5)]
    assert times[0] == pytest.approx(0.0)
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert all(g >= 0.5 - 1e-6 for g in gaps)
    assert len(times) == pytest.approx(20, abs=1)


def test_samples_stops_at_duration():
    cap = FakeCapture([i * 1000 / 60 for i in range(600)])
    times = [t for t, _ in _samples(cap, 3.0, 0.5)]
    assert times and max(times) < 3.0


def test_samples_does_not_drift_on_sparse_timestamps():
    """A gap longer than the interval must not cause a burst of catch-up samples."""
    cap = FakeCapture([0, 100, 200, 5000, 5100, 5200, 5300])
    times = [t for t, _ in _samples(cap, 10.0, 0.5)]
    assert times == pytest.approx([0.0, 5.0])


# ── Same-player matching ────────────────────────────────────────────────────────

@pytest.mark.parametrize("a,b", [
    ("MorelGlyph", "MorelGlyph"),
    ("XxIstRome", "Xx1stRome"),        # I/1 confusion
    ("NOXPhantomDO7", "NOXPhantomDOo7"),
    ("Newb30", "NewDb30"),
    ("Xx_warren_89", "Xx_warren_s89"),
    ("TTVKHAN_1Z23", "TTVKHAN_IZ23"),
    ("ninJUTSuULev_XD", "ninJuTsulLev_XD"),
])
def test_same_player_matches_ocr_variants(a, b):
    assert _same_player(a, b)


@pytest.mark.parametrize("a,b", [
    ("Sliderz", "RFW_Lolo20x"),
    ("huevoGuru", "FireflySonnet"),
    ("Antho", "Maxence"),
    ("Borz", "Newb30"),
    ("Medins34", "Chilio s7868"),
    ("Ritvik", ""),
])
def test_same_player_separates_distinct_names(a, b):
    assert not _same_player(a, b)


def test_merge_names_drops_ocr_variants_of_a_name_already_present():
    merged = _merge_names("Xx_warren_89", "Xx_warren_s89")
    assert merged == "Xx_warren_89"


def test_merge_names_checks_each_part_not_the_whole_string():
    """The regression behind 'A + B + A': a repeat was only compared to the
    entire accumulated label, so it never matched an earlier part."""
    assert _merge_names("MorelGlyph + Crazy_noodle", "MorelGlyph") == \
        "MorelGlyph + Crazy_noodle"
    assert _merge_names("MorelGlyph + Crazy_noodle", "Sliderz") == \
        "MorelGlyph + Crazy_noodle + Sliderz"


# ── Notice lag ──────────────────────────────────────────────────────────────────

def test_notice_lag_matches_the_measured_default():
    """At the default 2 samples/sec the measured gap was ~0.55s."""
    assert _notice_lag(2.0) == pytest.approx(0.55, abs=0.01)


def test_notice_lag_shrinks_as_sampling_gets_denser():
    """Only the sampling half depends on rate; the banner ramp is fixed."""
    assert _notice_lag(4.0) < _notice_lag(2.0) < _notice_lag(1.0)
    assert _notice_lag(1000.0) == pytest.approx(constants.BANNER_RAMP_SECONDS, abs=0.001)


def test_notice_lag_survives_a_nonsense_rate():
    assert _notice_lag(0.0) == constants.BANNER_RAMP_SECONDS
