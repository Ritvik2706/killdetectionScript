"""Video-first preset setup with an isolated, asynchronous frame preview."""
from dataclasses import replace
from pathlib import Path
from queue import Empty
import tkinter as tk
from tkinter import ttk
from uuid import uuid4

from killcutter import presets
from killcutter.ranges import parse_timestamp
from killcutter.errors import ConfigError
from . import theme as t
from .services import Jobs, open_media
from .preset_precision import PresetPrecision
from .widgets import Card, Preview, ScrollForm, label

KINDS = {
    'text': ('Text recognition (OCR)', 'Draw an area around the text, read it with OCR, then choose the phrase to detect.'),
    'color': ('A colour appears', 'Draw the detection area, then pick a colour inside it.'),
    'motion': ('Movement', 'Draw a box around the area to watch. Camera movement also counts.'),
    'scene': ('Scene changes', 'Use the whole frame to find cuts, or draw a smaller area.'),
    'audio': ('Loud sounds', 'Detect sounds by volume. No picture selection is needed.'),
}


def timestamp(seconds):
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f'{int(hours):02}:{int(minutes):02}:{seconds:06.3f}'


class PresetWizard(PresetPrecision, tk.Toplevel):
    def __init__(self, parent, path, preset=None):
        super().__init__(parent)
        self.app = parent
        self.family = parent.family
        self.draft = preset or presets.Preset('recipe-' + uuid4().hex[:12], '', 'text')
        self.editing = preset is not None
        self.jobs = Jobs()
        self.media = None
        self.position = 0
        self.generation = 0
        self.seek_timer = None
        self.ready = False
        self.closed = False
        self.region = self.draft.region
        self.colour = self.draft.color
        self.colour_picked = self.editing
        self.step = 1
        self.title('Edit preset' if self.editing else 'Create a preset')
        self.configure(bg=t.BG)
        self.geometry(f'{min(1040, self.winfo_screenwidth()-60)}x{min(820, self.winfo_screenheight()-80)}')
        self.minsize(700, 580)
        self.transient(parent)
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self.bind('<Escape>', lambda _: self.destroy())
        self.heading = label(self, '2  Choose a frame', size=22, bold=True)
        self.heading.pack(anchor='w', padx=22, pady=(18, 4))
        label(self, 'Video selected  →  Choose a frame  →  Select pixels or an area & save', color=t.MUTED).pack(anchor='w', padx=22, pady=(0, 12))
        footer = tk.Frame(self, bg=t.BG)
        footer.pack(side='bottom', fill='x', padx=22, pady=(10, 18))
        self.next_button = ttk.Button(footer, text='Next: select area or pixels →', style='Primary.TButton', command=self.next_step)
        self.next_button.pack(side='right')
        self.back_button = ttk.Button(footer, text='Cancel', style='Toolbar.TButton', command=self.back)
        self.back_button.pack(side='left')
        self.message = tk.StringVar(value='Opening video…')
        notice = label(self, textvariable=self.message, color=t.MUTED, wraplength=900, justify='left')
        notice.pack(side='bottom', fill='x', padx=22)
        notice.bind('<Configure>', lambda e: notice.configure(wraplength=max(100, e.width)))
        self.frame_page = Card(self)
        self.frame_page.pack(fill='both', expand=True, padx=22)
        body = self.frame_page.content
        label(body, Path(path).name, bold=True).pack(anchor='w')
        label(body, 'Drag the timeline or enter a time to find a clear example.', color=t.MUTED).pack(anchor='w', pady=(4, 8))
        self.preview = Preview(body, height=220, width=400)
        self.preview.pack(fill='both', expand=True)
        self.seek = ttk.Scale(body, from_=0, to=1, command=self.request_frame)
        self.seek.pack(fill='x', pady=(10, 8))
        transport = tk.Frame(body, bg=t.CARD)
        transport.pack(fill='x')
        for title, amount in [('−5 s', -5), ('−1 frame', -1), ('+1 frame', 1), ('+5 s', 5)]:
            ttk.Button(transport, text=title, command=lambda a=amount: self.step_frame(a)).pack(side='left', padx=(0, 6))
        self.time_var = tk.StringVar(value='00:00:00.000')
        ttk.Button(transport, text='Go', command=self.go_to_time).pack(side='right')
        entry = ttk.Entry(transport, textvariable=self.time_var, width=15)
        entry.pack(side='right', padx=8)
        entry.bind('<Return>', lambda _: self.go_to_time())
        label(transport, 'Time').pack(side='right')
        self.setup_page = ScrollForm(self)
        self._build_setup()
        self.seek.state(['disabled'])
        self.next_button.state(['disabled'])
        self.jobs.submit('open', open_media, path)
        self.poll_timer = self.after(40, self.poll)
        self.grab_set()

    def _build_setup(self):
        card = Card(self.setup_page.body)
        card.pack(fill='both', expand=True)
        body = card.content
        label(body, 'What should we look for?', size=16, bold=True).pack(anchor='w')
        self.kind_var = tk.StringVar(value=KINDS[self.draft.detector][0])
        kind = ttk.Combobox(body, textvariable=self.kind_var, state='readonly', values=[v[0] for v in KINDS])
        kind.configure(postcommand=lambda: t.style_popdown(kind))
        kind.pack(fill='x', pady=(8, 6))
        kind.bind('<<ComboboxSelected>>', self.change_kind)
        self.instruction = tk.StringVar()
        label(body, textvariable=self.instruction, color=t.MUTED, wraplength=800, justify='left').pack(anchor='w', pady=(0, 8))
        self.selection_preview = Preview(body, width=400, height=230)
        self.selection_preview.pack(fill='x')
        tools = tk.Frame(body, bg=t.CARD)
        tools.pack(fill='x', pady=8)
        self.area_button = ttk.Button(tools, text='Draw detection area', command=lambda: self.set_tool('region'))
        self.area_button.pack(side='left', padx=(0, 6))
        self.colour_button = ttk.Button(tools, text='Pick a pixel colour', command=lambda: self.set_tool('color'))
        self.colour_button.pack(side='left', padx=(0, 6))
        self.full_button = ttk.Button(tools, text='Use whole frame', command=self.full_frame)
        self.full_button.pack(side='left')
        self.selection_summary = tk.StringVar()
        self.selection_summary_label = label(body, textvariable=self.selection_summary, color=t.ACCENT, wraplength=800)
        self.selection_summary_label.pack(anchor='w', pady=(0, 8))
        self.build_precision_tools(body)
        self.name_var = tk.StringVar(value=self.draft.name)
        label(body, 'Preset name', bold=True).pack(anchor='w')
        ttk.Entry(body, textvariable=self.name_var).pack(fill='x', pady=(4, 10))
        self.text_row = tk.Frame(body, bg=t.CARD)
        label(self.text_row, 'Words to find, for example “VICTORY”', bold=True).pack(anchor='w')
        self.text_var = tk.StringVar(value=self.draft.text)
        ttk.Entry(self.text_row, textvariable=self.text_var).pack(fill='x', pady=(4, 10))
        label(self.text_row, 'Matches a literal phrase, ignoring case and repeated spaces. No regular expressions.',
              color=t.MUTED, wraplength=780, justify='left').pack(anchor='w', pady=(0, 8))
        self.text_row.pack(fill='x')
        self.advanced_button = ttk.Button(body, text='Advanced settings ▸', command=self.toggle_advanced)
        self.advanced_button.pack(anchor='w', pady=8)
        self.advanced = tk.Frame(body, bg=t.CARD)
        self.advanced_vars = {}
        self.advanced_rows = {}
        for key, title, value in [('label', 'Name shown on detected clips', self.draft.label),
                                  ('tolerance', 'Colour / change tolerance (0–255)', self.draft.tolerance),
                                  ('coverage', 'Area that must match or change (%)', self.draft.coverage*100),
                                  ('audio_db', 'Minimum sound level (dBFS)', self.draft.audio_db)]:
            row = tk.Frame(self.advanced, bg=t.CARD)
            label(row, title).pack(side='left')
            var = tk.StringVar(value=str(value))
            ttk.Entry(row, textvariable=var, width=22).pack(side='right')
            self.advanced_vars[key] = var
            self.advanced_rows[key] = row
        label(body, 'Saving selects this preset for your next analysis. You can change it later.', color=t.MUTED,
              wraplength=800, justify='left').pack(anchor='w', pady=(10, 0))
        self.change_kind()

    @property
    def detector(self):
        return next(key for key, value in KINDS.items() if value[0] == self.kind_var.get())

    def change_kind(self, event=None):
        detector = self.detector
        if event and detector != self.draft.detector:
            self.advanced_vars['coverage'].set('60' if detector == 'scene' else '10')
        self.instruction.set(KINDS[detector][1])
        self.invalidate_ocr()
        self.ocr_panel.pack_forget()
        self.region_editor.pack_forget()
        if detector != 'audio':
            self.region_editor.pack(fill='x', after=self.selection_summary_label, pady=(0, 8))
        self.text_row.pack_forget()
        if detector == 'text':
            self.ocr_panel.pack(fill='x', after=self.region_editor, pady=(0, 10))
            self.text_row.pack(fill='x', before=self.advanced_button)
        self.colour_button.state(['!disabled'] if detector == 'color' else ['disabled'])
        for button in (self.area_button, self.full_button):
            button.state(['disabled'] if detector == 'audio' else ['!disabled'])
        self.set_tool('none' if detector == 'audio' else 'region')
        for key, row in self.advanced_rows.items():
            row.pack_forget()
            if key == 'label' or key == 'audio_db' and detector == 'audio' or key in ('tolerance', 'coverage') and detector in ('color', 'motion', 'scene'):
                row.pack(fill='x', pady=5)
        self.update_selection_summary()

    def set_tool(self, mode):
        self.selection_preview.on_region = self.select_region if mode == 'region' else None
        self.selection_preview.on_pixel = self.select_pixel if mode == 'color' else None
        self.selection_preview.drag_start = None
        for key, button in [('region', self.area_button), ('color', self.colour_button)]:
            button.state(['selected'] if mode == key else ['!selected'])
        if mode == 'color':
            self.instruction.set('Click the colour you want to detect in the picture below.')
        else:
            self.instruction.set(KINDS[self.detector][1])

    def select_region(self, region):
        self.region = region
        self.invalidate_ocr()
        self.sync_region_fields()
        self.selection_preview.region = region
        self.selection_preview.redraw()
        self.update_selection_summary()

    def full_frame(self):
        self.select_region((0, 0, 1, 1))

    def select_pixel(self, x, y, rgb):
        self.pixel_hint.set(f'Sampled pixel X {x}, Y {y} · RGB {rgb[0]}, {rgb[1]}, {rgb[2]} · #%02X%02X%02X' % tuple(rgb[:3]))
        self.colour = tuple(rgb[:3])
        self.colour_picked = True
        self.update_selection_summary()

    def update_selection_summary(self):
        area = 'Whole frame' if self.region == (0, 0, 1, 1) else 'Custom detection area selected'
        if self.media and self.detector != 'audio':
            x, y, w, h = replace(self.draft, region=self.region).box(self.media.width, self.media.height)
            area += f' · X {x}, Y {y} · {w} × {h} px'
        if self.detector == 'audio':
            area = 'Uses audio volume · adjust the minimum level in Advanced settings'
        elif self.detector == 'color':
            area += '  ·  ' + ('Colour #%02X%02X%02X' % self.colour if self.colour_picked else 'Pick a colour to continue')
        self.selection_summary.set(area)

    def toggle_advanced(self):
        visible = bool(self.advanced.winfo_manager())
        self.advanced.pack_forget()
        if not visible:
            self.advanced.pack(fill='x', after=self.advanced_button)
        self.advanced_button.configure(text='Advanced settings ▸' if visible else 'Advanced settings ▾')

    def request_frame(self, value):
        if self.media is None:
            return
        self.position = min(max(0, float(value)), max(0, self.media.duration-1/self.media.fps))
        self.invalidate_ocr()
        self.time_var.set(timestamp(self.position))
        self.ready = False
        self.next_button.state(['disabled'])
        self.message.set('Loading frame…')
        self.generation += 1
        if self.seek_timer:
            self.after_cancel(self.seek_timer)
        self.seek_timer = self.after(100, self._load_frame)

    def _load_frame(self):
        self.seek_timer = None
        self.jobs.preview(self.generation, self.media.path, self.position)

    def step_frame(self, amount):
        if self.media:
            value = self.position + (amount/self.media.fps if abs(amount) == 1 else amount)
            self.seek_to(value)

    def seek_to(self, value):
        self.seek.configure(command='')
        self.seek.set(min(max(0, value), max(0, self.media.duration-1/self.media.fps)))
        self.seek.configure(command=self.request_frame)
        self.request_frame(self.seek.get())

    def go_to_time(self):
        if not self.media:
            return
        try:
            value = parse_timestamp(self.time_var.get())
            if value >= self.media.duration:
                raise ValueError(f'Enter a time before {timestamp(self.media.duration)}.')
            self.seek_to(value)
        except ValueError as exc:
            self.message.set(str(exc))

    def poll(self):
        try:
            while True:
                kind, data, error = self.jobs.events.get_nowait()
                if isinstance(kind, tuple) and kind[0] == 'ocr':
                    self.receive_ocr(kind[1], data, error)
                    continue
                if isinstance(kind, tuple) and kind[1] != self.generation:
                    continue
                if error:
                    self.message.set('Could not load video: ' + error)
                    continue
                if kind == 'open':
                    self.media, frame = data
                    self.seek.configure(to=max(0, self.media.duration-1/self.media.fps))
                    self.seek.state(['!disabled'])
                else:
                    frame = data
                self.preview.set_image(frame)
                self.ready = True
                self.next_button.state(['!disabled'])
                self.message.set(f'Frame {timestamp(self.position)}  /  {timestamp(self.media.duration)}')
        except Empty:
            pass
        self.poll_timer = self.after(40, self.poll)

    def next_step(self):
        if self.step == 2:
            return self.save()
        if not self.ready:
            return
        self.frame_page.pack_forget()
        self.setup_page.pack(fill='both', expand=True, padx=22)
        self.selection_preview.set_image(self.preview.image.copy())
        self.selection_preview.region = self.region
        self.sync_region_fields()
        self.update_selection_summary()
        self.selection_preview.redraw()
        self.heading.configure(text='3  Select what to detect')
        self.next_button.configure(text='Save & use preset')
        self.back_button.configure(text='← Choose another frame')
        self.step = 2

    def back(self):
        if self.step == 1:
            return self.destroy()
        self.setup_page.pack_forget()
        self.frame_page.pack(fill='both', expand=True, padx=22)
        self.heading.configure(text='2  Choose a frame')
        self.next_button.configure(text='Next: select area or pixels →')
        self.back_button.configure(text='Cancel')
        self.step = 1

    def save(self):
        if not self.apply_region_fields():
            return
        try:
            if self.detector == 'color' and not self.colour_picked:
                raise ValueError('Choose “Pick a pixel colour”, then click a colour in the picture.')
            values = {k: v.get().strip() for k, v in self.advanced_vars.items()}
            preset = replace(self.draft, name=self.name_var.get().strip(), detector=self.detector,
                             text=self.text_var.get().strip(), region=self.region, color=self.colour,
                             label=values['label'], tolerance=int(values['tolerance']),
                             coverage=float(values['coverage'])/100, audio_db=float(values['audio_db']))
            preset.validate()
            self.app.preset_library.save(preset)
            self.app._refresh_presets(preset)
            self.app.status.set(f'Ready to analyze with {preset.name}.')
            self.destroy()
        except (ValueError, OSError, ConfigError) as exc:
            self.message.set(str(exc))

    def destroy(self):
        if not self.closed:
            self.closed = True
            if self.seek_timer:
                self.after_cancel(self.seek_timer)
            if hasattr(self, 'poll_timer'):
                self.after_cancel(self.poll_timer)
            self.jobs.close()
        super().destroy()
