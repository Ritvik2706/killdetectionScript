"""Where the killfeed banner sits, for any resolution.

The constants in :mod:`killcutter.constants` were measured on 1920x1080. Rather
than hard-code them, this module stores the banner's geometry the way the game
actually lays it out — anchored to the **top-right corner**, scaled with the
vertical resolution — and resolves it for whatever frame we are handed.

Anchoring to the right edge (instead of scaling an x coordinate from the left)
is what makes ultrawide work: on a 2560x1080 screen the HUD still hugs the right
edge, so a left-anchored coordinate would land in the middle of the picture.

At 1920x1080 every value here resolves to exactly the measured constant, so the
footage this was tuned against is unaffected.
"""

from dataclasses import dataclass

from killcutter import constants

REFERENCE_WIDTH = 1920
REFERENCE_HEIGHT = 1080


def _right_offset(x: int) -> int:
    return REFERENCE_WIDTH - x


@dataclass(frozen=True)
class Hud:
    """Resolved banner geometry for one frame size."""

    region: tuple          # (x, y, w, h) of the text block we OCR
    eliminated: tuple      # (x, y, w, h) of the bottom-centre ELIMINATED line
    white: tuple           # (x, y) bright pixel on the banner icon
    accent: tuple          # (x, y) on the left accent bar
    slot_pitch: int        # vertical distance between stacked banners
    scale: float           # 1.0 at 1080p

    @property
    def is_reference(self) -> bool:
        return abs(self.scale - 1.0) < 1e-9


def for_size(width: int, height: int, region_override=None) -> Hud:
    """Resolve the banner geometry for a ``width`` x ``height`` frame.

    ``region_override`` (from ``--region``) is taken literally — if someone has
    measured a region by hand, scaling it underneath them would be wrong.
    """
    if width <= 0 or height <= 0:
        width, height = REFERENCE_WIDTH, REFERENCE_HEIGHT
    scale = height / REFERENCE_HEIGHT

    def x_from_right(ref_x: int) -> int:
        return int(round(width - _right_offset(ref_x) * scale))

    def scaled(v: int) -> int:
        return int(round(v * scale))

    rx, ry, rw, rh = constants.DEFAULT_REGION
    region = (tuple(region_override) if region_override
              else (x_from_right(rx), scaled(ry), scaled(rw), scaled(rh)))

    # The ELIMINATED line sits near the centre of the screen rather than against
    # an edge, so it scales from the left like the picture does.
    ex, ey, ew, eh = constants.ELIMINATED_REGION
    eliminated = (int(round(ex * width / REFERENCE_WIDTH)),
                  scaled(ey), int(round(ew * width / REFERENCE_WIDTH)), scaled(eh))

    return Hud(
        region=region,
        eliminated=eliminated,
        white=(x_from_right(constants.TRIGGER_PIXEL_WHITE[0]),
               scaled(constants.TRIGGER_PIXEL_WHITE[1])),
        accent=(x_from_right(constants.TRIGGER_PIXEL_ACCENT[0]),
                scaled(constants.TRIGGER_PIXEL_ACCENT[1])),
        slot_pitch=scaled(constants.BANNER_SLOT_PITCH),
        scale=scale,
    )


def describe(hud: Hud) -> str:
    """One-line summary for the diagnose / detect panels."""
    if hud.is_reference:
        return "1920x1080 reference layout"
    return f"scaled x{hud.scale:.3f} from the 1920x1080 reference"
