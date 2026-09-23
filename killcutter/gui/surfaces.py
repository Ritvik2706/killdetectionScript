"""Antialiased rounded surfaces shared by cards and native ttk controls."""
from functools import lru_cache
from PIL import Image, ImageDraw


@lru_cache(maxsize=64)
def _tile(radius, fill, outline):
    size = radius * 2 + 2
    image = Image.new('RGBA', (size * 4, size * 4))
    ImageDraw.Draw(image).rounded_rectangle(
        (0, 0, size * 4 - 1, size * 4 - 1), radius=radius * 4,
        fill=fill, outline=outline, width=4)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def rounded_surface(width, height, radius, fill, outline=None):
    """Assemble corners at native size so resizing large cards stays cheap."""
    width, height = max(2, width), max(2, height)
    radius = max(1, min(radius, (width - 1) // 2, (height - 1) // 2))
    tile = _tile(radius, fill, outline)
    size = tile.width
    image = Image.new('RGBA', (width, height), fill)
    for left, top in ((True, True), (False, True), (True, False), (False, False)):
        x, y = (0 if left else size-radius), (0 if top else size-radius)
        image.paste(tile.crop((x, y, x+radius, y+radius)),
                    (0 if left else width-radius, 0 if top else height-radius))
    if outline:
        draw = ImageDraw.Draw(image)
        draw.line((radius, 0, width-radius-1, 0), fill=outline)
        draw.line((radius, height-1, width-radius-1, height-1), fill=outline)
        draw.line((0, radius, 0, height-radius-1), fill=outline)
        draw.line((width-1, radius, width-1, height-radius-1), fill=outline)
    return image
