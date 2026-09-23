"""Desktop domain state and image-coordinate mapping, independent of Tk."""
from dataclasses import dataclass, field
from pathlib import Path
from killcutter.models import Clip


@dataclass(frozen=True)
class Media:
    path: str
    fps: float
    duration: float
    width: int
    height: int

    @property
    def name(self):
        return Path(self.path).name


@dataclass
class Workspace:
    media: Media | None = None
    clips: list[Clip] = field(default_factory=list)
    completed: bool = False
    position: float = 0


def image_rect(source_width, source_height, width, height):
    """Letterbox geometry shared by rendering and pointer mapping."""
    if min(source_width, source_height, width, height) <= 0:
        return 0, 0, 0, 0
    scale = min(width / source_width, height / source_height)
    w, h = max(1, int(source_width * scale)), max(1, int(source_height * scale))
    return (width - w) // 2, (height - h) // 2, w, h


def source_pixel(x, y, source_width, source_height, width, height):
    left, top, w, h = image_rect(source_width, source_height, width, height)
    if not w or not h or not (left <= x < left + w and top <= y < top + h):
        return None
    return min(source_width - 1, int((x - left) * source_width / w)), min(source_height - 1, int((y - top) * source_height / h))
