"""Precise region editing and asynchronous OCR inspection for preset drafts."""
from dataclasses import replace
import tkinter as tk
from tkinter import ttk

from . import theme as t
from .widgets import Preview, label
from .services import inspect_region_text


class PresetPrecision:
    def build_precision_tools(self, body):
        self.inspection_generation = 0
        self.ocr_pending = False
        self.ocr_text = ''
        self.region_fields = {}
        self.region_editor = tk.Frame(body, bg=t.CARD)
        self.region_editor.pack(fill='x', pady=(0, 8))
        label(self.region_editor, 'Source pixels', color=t.MUTED).pack(side='left', padx=(0, 8))
        for name in ('X', 'Y', 'Width', 'Height'):
            label(self.region_editor, name).pack(side='left', padx=(0, 4))
            var = tk.StringVar(value='0')
            entry = ttk.Entry(self.region_editor, textvariable=var, width=6)
            entry.pack(side='left', padx=(0, 8))
            entry.bind('<Return>', lambda _: self.apply_region_fields())
            self.region_fields[name] = var
        ttk.Button(self.region_editor, text='Apply area', command=self.apply_region_fields).pack(side='left')
        self.pixel_hint = tk.StringVar(value='Coordinates start at the top-left of the original video.')
        label(body, textvariable=self.pixel_hint, color=t.MUTED, wraplength=780).pack(anchor='w', pady=(0, 8))
        self.ocr_panel = tk.Frame(body, bg=t.CARD)
        self.ocr_panel.pack(fill='x', pady=(0, 10))
        controls = tk.Frame(self.ocr_panel, bg=t.CARD)
        controls.pack(fill='x')
        self.ocr_button = ttk.Button(controls, text='Read selected area (OCR)', command=self.inspect_ocr)
        self.ocr_button.pack(side='left')
        self.use_ocr_button = ttk.Button(controls, text='Use read text as phrase', command=self.use_ocr_text)
        self.use_ocr_button.pack(side='left', padx=8)
        self.use_ocr_button.state(['disabled'])
        self.ocr_status = tk.StringVar(value='Read this area to check which words OCR can see before saving.')
        label(self.ocr_panel, textvariable=self.ocr_status, color=t.MUTED, wraplength=780, justify='left').pack(anchor='w', pady=6)
        self.crop_preview = Preview(self.ocr_panel, height=110, width=400)
        self.crop_preview.pack(fill='x', pady=(0, 6))
        self.ocr_output = tk.Text(self.ocr_panel, height=3, wrap='word', bg=t.FIELD, fg=t.INK,
                                  insertbackground=t.INK, relief='flat', padx=8, pady=6)
        self.ocr_output.pack(fill='x')
        self.ocr_output.configure(state='disabled')

    def sync_region_fields(self):
        if not self.media:
            return
        box = replace(self.draft, region=self.region).box(self.media.width, self.media.height)
        for var, value in zip(self.region_fields.values(), box):
            var.set(str(value))
        self.region_field_snapshot = tuple(var.get() for var in self.region_fields.values())
        self.pixel_hint.set(f'{self.media.width} × {self.media.height} source · X/Y start at 0 · Area {box[2]} × {box[3]} px')
        self.update_crop()

    def apply_region_fields(self):
        if not self.media or self.detector == 'audio':
            return True
        current = tuple(var.get() for var in self.region_fields.values())
        if current == getattr(self, 'region_field_snapshot', None):
            return True
        try:
            x, y, w, h = map(int, current)
            width, height = self.media.width, self.media.height
            if x < 0 or y < 0 or w <= 0 or h <= 0 or x+w > width or y+h > height:
                raise ValueError('Area must fit inside the source frame and have a positive width and height.')
            self.select_region((x/width, y/height, w/width, h/height))
            return True
        except ValueError as exc:
            self.message.set(f'Invalid pixel area: {exc}')
            return False

    def update_crop(self):
        image = self.selection_preview.image
        if image is None:
            return
        x, y, w, h = replace(self.draft, region=self.region).box(*image.size)
        self.crop_preview.set_image(image.crop((x, y, x+w, y+h)))

    def invalidate_ocr(self):
        self.inspection_generation += 1
        self.ocr_text = ''
        self.use_ocr_button.state(['disabled'])
        self.ocr_output.configure(state='normal')
        self.ocr_output.delete('1.0', 'end')
        self.ocr_output.configure(state='disabled')
        self.ocr_status.set('Area or frame changed. Read the selected area to check the text.')

    def inspect_ocr(self):
        if self.ocr_pending or self.selection_preview.image is None or not self.apply_region_fields():
            return
        if self.jobs.busy:
            return
        self.invalidate_ocr()
        self.ocr_pending = True
        self.ocr_button.state(['disabled'])
        self.ocr_status.set('Reading the selected area…')
        self.jobs.submit(('ocr', self.inspection_generation), inspect_region_text,
                         self.selection_preview.image.copy(), self.region)

    def receive_ocr(self, generation, data, error):
        self.ocr_pending = False
        self.ocr_button.state(['!disabled'])
        if generation != self.inspection_generation:
            return
        if error:
            self.ocr_text = ''
            self.use_ocr_button.state(['disabled'])
            self.ocr_status.set('OCR could not run: ' + error)
            return
        self.ocr_text = data
        self.ocr_output.configure(state='normal')
        self.ocr_output.insert('1.0', data)
        self.ocr_output.configure(state='disabled')
        self.use_ocr_button.state(['!disabled'] if data.strip() else ['disabled'])
        phrase = ' '.join(self.text_var.get().casefold().split())
        match = bool(phrase and phrase in ' '.join(data.casefold().split()))
        self.ocr_status.set(('Text found · current phrase matches.' if match else 'Text found. Check the readout, then enter or use a phrase.') if data.strip() else 'No text found. Try a tighter area or a clearer frame.')

    def use_ocr_text(self):
        if self.ocr_text:
            self.text_var.set(' '.join(self.ocr_text.split()))
