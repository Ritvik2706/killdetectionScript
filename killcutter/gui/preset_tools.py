"""Contextual frame tools that apply only to a preset draft."""
import tkinter as tk
from tkinter import ttk

from . import theme as t
from .widgets import Preview, label


class PresetFrameTool(tk.Toplevel):
    def __init__(self, parent, image, *, mode, position, apply):
        super().__init__(parent)
        self.family = parent.family
        self.mode = mode
        self.selection = None
        self.apply_selection = apply
        colour = mode == 'color'
        self.title('Pick preset colour' if colour else 'Draw preset region')
        self.configure(bg=t.BG)
        self.geometry('900x620')
        self.minsize(540, 400)
        self.transient(parent)
        label(self, 'Click the colour to detect.' if colour else 'Drag around the signal to detect.',
              size=14, bold=True).pack(padx=18, pady=(16, 6))
        label(self, f'Frame {position} · Changes apply to this preset draft only.',
              color=t.MUTED).pack(padx=18, pady=(0, 8))
        self.preview = Preview(self, width=480, height=240,
                               on_pixel=self.select_pixel if colour else None)
        self.preview.pack(fill='both', expand=True, padx=18, pady=8)
        self.preview.set_image(image.copy())
        if not colour:
            self.preview.on_region = self.select_region
        self.summary = tk.StringVar(value='No colour selected' if colour else 'No region selected')
        label(self, textvariable=self.summary).pack(padx=18, pady=6)
        actions = tk.Frame(self, bg=t.BG)
        actions.pack(pady=(8, 16))
        ttk.Button(actions, text='Cancel', command=self.destroy).pack(side='left', padx=6)
        self.apply_button = ttk.Button(actions, text='Use colour' if colour else 'Use region',
                                       style='Primary.TButton', command=self.confirm)
        self.apply_button.pack(side='left', padx=6)
        self.apply_button.state(['disabled'])
        self.bind('<Escape>', lambda _: self.destroy())
        self.grab_set()

    def select_pixel(self, x, y, rgb):
        self.selection = '#%02X%02X%02X' % tuple(rgb[:3])
        self.summary.set(f'{self.selection} · RGB {rgb[0]}, {rgb[1]}, {rgb[2]} · X {x}, Y {y}')
        self.apply_button.state(['!disabled'])

    def select_region(self, region):
        self.selection = ', '.join(f'{value*100:.8f}' for value in region)
        self.summary.set('Region: ' + ', '.join(f'{value*100:.2f}%' for value in region))
        self.apply_button.state(['!disabled'])

    def confirm(self):
        if self.selection is not None:
            self.apply_selection(self.selection)
            self.destroy()
