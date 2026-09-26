"""One identity asset for the sidebar, Tk windows, and desktop packaging."""
from pathlib import Path
from PIL import Image, ImageTk

ASSETS = Path(__file__).with_name('assets')


def icon_image(size):
    with Image.open(ASSETS / 'killcutter.png') as source:
        return source.convert('RGBA').resize((size, size), Image.Resampling.LANCZOS)


def photo(master, size):
    return ImageTk.PhotoImage(icon_image(size), master=master)


def install_window_icons(root):
    # Tk needs live references; default=True also applies to future dialogs.
    root.app_icons = [photo(root, size) for size in (16, 32, 48, 64, 128, 256)]
    root.iconphoto(True, *root.app_icons)
