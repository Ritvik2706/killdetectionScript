"""Road Trip-inspired surfaces and typography, without a runtime dependency on it."""
import tkinter.font as font
from tkinter import ttk
from PIL import Image, ImageTk
from .surfaces import rounded_surface

BG = '#0E0E12'
SIDEBAR = '#17171D'
CARD = '#1C1C23'
FIELD = '#26262F'
BORDER = '#31313C'
INK = '#F2F2F7'
MUTED = '#98989F'
ACCENT = '#0A84FF'
SELECTED = '#183452'
GREEN = '#30D158'
AMBER = '#FF9F0A'


def apply(root):
    family = 'Segoe UI' if 'Segoe UI' in font.families(root) else 'DejaVu Sans'
    for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont'):
        font.nametofont(name).configure(family=family, size=10)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background=BG, foreground=INK, font=(family, 10))
    style.configure('TFrame', background=BG)
    style.configure('Card.TFrame', background=CARD)
    style.configure('TLabel', background=BG, foreground=INK)
    style.configure('Card.TLabel', background=CARD)
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('TButton', background=FIELD, foreground=INK, borderwidth=0, padding=(15, 10), focusthickness=1, focuscolor=ACCENT)
    style.map('TButton', background=[('active', BORDER), ('disabled', CARD)], foreground=[('disabled', MUTED)])
    style.configure('Primary.TButton', background=ACCENT, foreground='white')
    style.map('Primary.TButton', background=[('active', '#0071E3'), ('disabled', FIELD)])
    style.configure('Nav.TButton', background=SIDEBAR, anchor='w', padding=(18, 13))
    style.map('Nav.TButton', background=[('selected', SELECTED), ('active', FIELD)])
    style.configure('TEntry', fieldbackground=FIELD, foreground=INK, insertcolor=INK, bordercolor=BORDER, lightcolor=FIELD, darkcolor=FIELD, padding=9)
    style.configure('TCheckbutton', background=CARD, foreground=INK, padding=4)
    style.map('TCheckbutton', background=[('active', CARD)])
    style.configure('Horizontal.TScale', background=ACCENT, troughcolor=FIELD, sliderlength=16, bordercolor=FIELD, lightcolor=ACCENT, darkcolor=ACCENT)
    style.configure('Horizontal.TProgressbar', background=ACCENT, troughcolor=FIELD, borderwidth=0, bordercolor=FIELD, lightcolor=ACCENT, darkcolor=ACCENT)
    style.configure('Treeview', background=CARD, fieldbackground=CARD, foreground=INK, rowheight=38, borderwidth=0)
    style.map('Treeview', background=[('selected', SELECTED)], foreground=[('selected', INK)])
    style.configure('Treeview.Heading', background=FIELD, foreground=MUTED, padding=10, relief='flat')
    style.configure('Vertical.TScrollbar', background=BORDER, troughcolor=BG, borderwidth=0, arrowsize=12, arrowcolor=MUTED, bordercolor=BG, lightcolor=BORDER, darkcolor=BORDER)
    # Image elements retain ttk's focus, keyboard, disabled and invoke behavior.
    root.surface_images = []
    for name, fill, hover, behind in [('TButton', FIELD, BORDER, CARD),
                                      ('Toolbar.TButton', FIELD, BORDER, BG),
                                      ('Primary.TButton', ACCENT, '#0071E3', BG),
                                      ('CardPrimary.TButton', ACCENT, '#0071E3', CARD),
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
    style.configure('CardPrimary.TButton', foreground='white')
    style.configure('Nav.TButton', padding=(12, 12))
    style.configure('Treeview', bordercolor=CARD, lightcolor=CARD, darkcolor=CARD)
    style.layout('Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])
    style.configure('Horizontal.TScrollbar', background=BORDER, troughcolor=CARD,
                    bordercolor=CARD, lightcolor=BORDER, darkcolor=BORDER, arrowcolor=MUTED,
                    arrowsize=10)
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
