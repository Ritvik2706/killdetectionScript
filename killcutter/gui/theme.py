"""Road Trip-inspired surfaces and typography, without a runtime dependency on it.

Palette roles are module globals so every widget can read ``theme.CARD`` at
build time. :func:`configure` rebinds them from a named palette plus the user's
accent and scale, and :func:`apply` rebuilds the ttk styles from whatever is
bound. Nothing here reads preferences directly: the shell passes values in.
"""
import tkinter.font as font
from tkinter import ttk
from PIL import Image, ImageTk
from .surfaces import rounded_surface

# Role names, in the order palettes declare them.
ROLES = ('BG', 'SIDEBAR', 'CARD', 'FIELD', 'BORDER', 'INK', 'MUTED', 'ALTERNATE', 'PREVIEW')

PALETTES = {
    'Midnight': ('#0E0E12', '#17171D', '#1C1C23', '#26262F', '#31313C', '#F2F2F7', '#98989F', '#22222B', '#101116'),
    'Graphite': ('#16181C', '#1E2127', '#24272E', '#2E323A', '#3A3F49', '#EDEFF3', '#9AA1AD', '#2A2E36', '#181B20'),
    'Daylight': ('#F4F5F7', '#FFFFFF', '#FFFFFF', '#ECEEF2', '#D6D9E0', '#16181D', '#5F646E', '#F0F2F5', '#E7E9ED'),
}

ACCENTS = {'Blue': '#0A84FF', 'Violet': '#7D5BED', 'Teal': '#22B8A6',
           'Amber': '#FF9F0A', 'Rose': '#FF375F', 'Lime': '#8CC63F'}

GREEN = '#30D158'
AMBER = '#FF9F0A'
SCALE = 1.0
FAMILY = 'DejaVu Sans'
_generation = 0


def _mix(a, b, weight):
    """Blend two ``#rrggbb`` colors; ``weight`` is how much of ``a`` to keep."""
    pair = [tuple(int(color[i:i+2], 16) for i in (1, 3, 5)) for color in (a, b)]
    return '#%02X%02X%02X' % tuple(round(x * weight + y * (1 - weight)) for x, y in zip(*pair))


def configure(palette=None, accent=None, scale=None):
    """Rebind the palette globals. Call before :func:`apply` or a restyle."""
    global SCALE, ACCENT, ACCENT_ACTIVE, SELECTED, ON_ACCENT
    colors = PALETTES.get(palette or 'Midnight', PALETTES['Midnight'])
    for role, color in zip(ROLES, colors):
        globals()[role] = color
    ACCENT = (accent or ACCENTS['Blue']).upper()
    if scale is not None:
        SCALE = scale
    ACCENT_ACTIVE = _mix(ACCENT, '#000000', .86)
    # The selected tint has to stay readable on both light and dark grounds.
    SELECTED = _mix(ACCENT, BG, .28 if palette != 'Daylight' else .18)
    ON_ACCENT = 'white' if _luminance(ACCENT) < .62 else '#101014'
    return palette or 'Midnight'


def _luminance(color):
    return sum(int(color[i:i+2], 16) / 255 * w for i, w in ((1, .299), (3, .587), (5, .114)))


def size(points):
    """Scale a point size, keeping the relative type hierarchy intact."""
    return max(6, round(points * SCALE))


def px(value):
    return max(1, round(value * SCALE))


def palette():
    """The current role colors, for remapping existing widgets on a restyle."""
    return {role: globals()[role] for role in ROLES}


def colors():
    """Palette roles plus the accent-derived colors, for a restyle remap."""
    return {role: globals()[role] for role in ROLES + ('ACCENT', 'ACCENT_ACTIVE', 'SELECTED', 'ON_ACCENT')}


configure()


def apply(root):
    """Build the ttk styles for the bound palette; safe to call repeatedly."""
    global _generation, FAMILY
    family = FAMILY = 'Segoe UI' if 'Segoe UI' in font.families(root) else 'DejaVu Sans'
    for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont'):
        font.nametofont(name).configure(family=family, size=size(10))
    style = ttk.Style(root)
    # A fresh theme each time: element names may only be created once per theme.
    _generation += 1
    name = f'killcutter{_generation}'
    style.theme_create(name, parent='clam')
    style.theme_use(name)
    base = (family, size(10))
    style.configure('.', background=BG, foreground=INK, font=base)
    style.configure('TFrame', background=BG)
    style.configure('Card.TFrame', background=CARD)
    style.configure('TLabel', background=BG, foreground=INK)
    style.configure('Card.TLabel', background=CARD)
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('TButton', background=FIELD, foreground=INK, borderwidth=0, padding=(px(15), px(10)), focusthickness=1, focuscolor=ACCENT)
    style.map('TButton', background=[('active', BORDER), ('disabled', CARD)], foreground=[('disabled', MUTED)])
    style.configure('Primary.TButton', background=ACCENT, foreground=ON_ACCENT)
    style.map('Primary.TButton', background=[('active', ACCENT_ACTIVE), ('disabled', FIELD)])
    style.configure('Nav.TButton', background=SIDEBAR, anchor='w', padding=(px(18), px(13)))
    style.map('Nav.TButton', background=[('selected', SELECTED), ('active', FIELD)])
    style.configure('TEntry', fieldbackground=FIELD, foreground=INK, insertcolor=INK, bordercolor=BORDER, lightcolor=FIELD, darkcolor=FIELD, padding=px(9))
    style.configure('TCheckbutton', background=CARD, foreground=INK, padding=px(4),
                    indicatorbackground=FIELD, indicatorforeground=ON_ACCENT,
                    indicatormargin=px(4), focuscolor=ACCENT, borderwidth=0)
    style.map('TCheckbutton', background=[('active', CARD)],
              indicatorbackground=[('selected', ACCENT), ('active', BORDER)])
    style.configure('Horizontal.TScale', background=ACCENT, troughcolor=FIELD, sliderlength=px(16), bordercolor=FIELD, lightcolor=ACCENT, darkcolor=ACCENT)
    style.configure('Horizontal.TProgressbar', background=ACCENT, troughcolor=FIELD, borderwidth=0, bordercolor=FIELD, lightcolor=ACCENT, darkcolor=ACCENT)
    style.configure('Treeview', background=CARD, fieldbackground=CARD, foreground=INK, rowheight=px(38), borderwidth=0, font=base)
    style.map('Treeview', background=[('selected', SELECTED)], foreground=[('selected', INK)])
    style.configure('Treeview.Heading', background=FIELD, foreground=MUTED, padding=px(10), relief='flat', font=(family, size(10)))
    style.configure('Vertical.TScrollbar', background=BORDER, troughcolor=BG, borderwidth=0, arrowsize=px(12), arrowcolor=MUTED, bordercolor=BG, lightcolor=BORDER, darkcolor=BORDER)
    # Image elements retain ttk's focus, keyboard, disabled and invoke behavior.
    root.surface_images = []
    for name, fill, hover, behind in [('TButton', FIELD, BORDER, CARD),
                                      ('Toolbar.TButton', FIELD, BORDER, BG),
                                      ('Primary.TButton', ACCENT, ACCENT_ACTIVE, BG),
                                      ('CardPrimary.TButton', ACCENT, ACCENT_ACTIVE, CARD),
                                      ('Nav.TButton', SIDEBAR, FIELD, SIDEBAR)]:
        photos = []
        for color, outline in [(fill, None), (hover, None), (FIELD, None),
                               (fill, ACCENT), (SELECTED, None)]:
            surface = rounded_surface(32, 32, 12, color, outline)
            backdrop = Image.new('RGBA', surface.size, behind)
            backdrop.alpha_composite(surface)
            photo = ImageTk.PhotoImage(backdrop, master=root)
            photos.append(photo)
        root.surface_images.extend(photos)
        element = name + '.rounded'
        style.element_create(element, 'image', photos[0],
                             ('disabled', photos[2]), ('focus', photos[3]),
                             ('selected', photos[4]), ('active', photos[1]),
                             border=13, padding=0, sticky='nsew')
        style.layout(name, [(element, {'sticky': 'nsew', 'children': [
            ('Button.padding', {'sticky': 'nsew', 'children': [
                ('Button.label', {'sticky': 'nsew'})]})]})])
    style.configure('CardPrimary.TButton', foreground=ON_ACCENT)
    style.configure('Nav.TButton', padding=(px(12), px(12)))
    style.configure('Treeview', bordercolor=CARD, lightcolor=CARD, darkcolor=CARD)
    style.layout('Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])
    style.configure('Horizontal.TScrollbar', background=BORDER, troughcolor=CARD,
                    bordercolor=CARD, lightcolor=BORDER, darkcolor=BORDER, arrowcolor=MUTED,
                    arrowsize=px(10))
    style.map('Horizontal.TScale', bordercolor=[('disabled', FIELD)],
              lightcolor=[('disabled', FIELD)], darkcolor=[('disabled', FIELD)],
              background=[('disabled', BORDER)])
    # Rounded fields keep the native text-selection and caret behavior.
    fields = []
    for outline in (BORDER, ACCENT):
        surface = rounded_surface(28, 28, 9, FIELD, outline)
        backdrop = Image.new('RGBA', surface.size, CARD)
        backdrop.alpha_composite(surface)
        fields.append(ImageTk.PhotoImage(backdrop, master=root))
    root.surface_images.extend(fields)
    style.element_create('Rounded.field', 'image', fields[0], ('focus', fields[1]),
                         border=10, padding=0, sticky='nsew')
    style.layout('TEntry', [('Rounded.field', {'sticky': 'nsew', 'children': [
        ('Entry.padding', {'sticky': 'nsew', 'children': [('Entry.textarea', {'sticky': 'nsew'})]})]})])
    return family


def recolor(widget, mapping, family):
    """Re-point plain Tk widgets at the new palette after a theme change.

    Only colors that came from the previous palette are replaced, so deliberate
    one-off colors (a status accent, a swatch) survive untouched.
    """
    for option in ('bg', 'fg', 'highlightbackground', 'insertbackground', 'selectbackground'):
        try:
            current = str(widget.cget(option))
        except Exception:
            continue
        if current in mapping:
            widget.configure(**{option: mapping[current]})
    base = getattr(widget, 'base_size', None)
    if base is not None:
        widget.configure(font=(family, size(base), 'bold' if getattr(widget, 'base_bold', False) else 'normal'))
    for child in widget.winfo_children():
        recolor(child, mapping, family)
