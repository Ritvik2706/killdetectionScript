"""Tests for resolution-independent HUD geometry.

The critical property is that 1920x1080 resolves to exactly the measured
constants — the footage everything was tuned against must be bit-identical.
Beyond that, the banner is anchored to the top-right, so its distance from the
*right* edge is what scales, not an x coordinate from the left.
"""

import pytest

from killcutter import constants, hud


def test_reference_resolution_is_byte_identical_to_the_constants():
    h = hud.for_size(1920, 1080)
    assert h.region == constants.DEFAULT_REGION
    assert h.white == constants.TRIGGER_PIXEL_WHITE
    assert h.accent == constants.TRIGGER_PIXEL_ACCENT
    assert h.slot_pitch == constants.BANNER_SLOT_PITCH
    assert h.is_reference


@pytest.mark.parametrize("w,h,scale", [
    (1280, 720, 2 / 3),
    (2560, 1440, 4 / 3),
    (3840, 2160, 2.0),
])
def test_common_resolutions_scale_proportionally(w, h, scale):
    got = hud.for_size(w, h)
    assert got.scale == pytest.approx(scale)
    # distance from the right edge scales with the HUD
    ref_gap = 1920 - constants.TRIGGER_PIXEL_ACCENT[0]
    assert got.accent[0] == pytest.approx(w - ref_gap * scale, abs=1)
    assert got.accent[1] == pytest.approx(constants.TRIGGER_PIXEL_ACCENT[1] * scale,
                                          abs=1)


def test_ultrawide_keeps_the_banner_against_the_right_edge():
    """The bug this design avoids: a left-anchored x lands mid-screen at 21:9."""
    wide = hud.for_size(2560, 1080)
    ref_gap = 1920 - constants.TRIGGER_PIXEL_ACCENT[0]
    assert wide.accent[0] == 2560 - ref_gap          # same gap from the right
    assert wide.accent[0] > 2000                     # not stranded mid-picture
    assert wide.accent[1] == constants.TRIGGER_PIXEL_ACCENT[1]   # height unchanged


def test_every_resolved_pixel_stays_inside_the_frame():
    for w, h in [(1280, 720), (1920, 1080), (2560, 1080), (2560, 1440), (3840, 2160)]:
        got = hud.for_size(w, h)
        for x, y in (got.white, got.accent):
            assert 0 <= x < w and 0 <= y < h
        rx, ry, rw, rh = got.region
        assert 0 <= rx and rx + rw <= w
        assert 0 <= ry and ry + rh <= h


def test_explicit_region_override_is_taken_literally():
    """A hand-measured --region must not be silently rescaled."""
    got = hud.for_size(3840, 2160, region_override=(10, 20, 30, 40))
    assert got.region == (10, 20, 30, 40)


def test_nonsense_frame_size_falls_back_to_the_reference():
    assert hud.for_size(0, 0).region == constants.DEFAULT_REGION
