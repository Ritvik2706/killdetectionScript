"""Desktop page layouts, separated from workflow orchestration.

Views bind controls to Application actions; processing remains in services.
"""
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from killcutter import config
from . import theme as t
from .widgets import Card, Preview, ScrollForm, label


class Views:
    def _build_workspace(self):
        page = self._page('workspace')
        page.columnconfigure(0, weight=1)
        page.rowconfigure(0, weight=1)
        preview = Card(page)
        preview.grid(row=0, column=0, sticky='nsew', pady=(0, 14))
        header = tk.Frame(preview.content, bg=t.CARD)
        header.pack(fill='x', pady=(0, 12))
        label(header, 'FRAME PREVIEW', size=9, color=t.MUTED, bold=True).pack(side='left')
        label(header, textvariable=self.position_var, color=t.MUTED).pack(side='right')
        self.preview = Preview(preview.content, height=260)
        self.preview.pack(fill='both', expand=True)
        self.seek = ttk.Scale(preview.content, from_=0, to=1, command=self._seek_changed)
        self.seek.pack(fill='x', pady=(14, 8))
        label(preview.content, textvariable=self.source_var, color=t.MUTED).pack(anchor='w')
        bottom = tk.Frame(page, bg=t.BG)
        bottom.grid(row=1, column=0, sticky='ew')
        bottom.columnconfigure(0, weight=3)
        bottom.columnconfigure(1, weight=2)
        selection = Card(bottom)
        selection.grid(row=0, column=0, sticky='nsew', padx=(0, 12))
        label(selection.content, 'ANALYSIS RANGE', size=9, color=t.MUTED, bold=True).pack(anchor='w', pady=(0, 12))
        row = tk.Frame(selection.content, bg=t.CARD)
        row.pack(fill='x')
        for title, variable, setter in [('IN', self.start_var, self.mark_in), ('OUT', self.end_var, self.mark_out)]:
            col = tk.Frame(row, bg=t.CARD)
            col.pack(side='left', fill='x', expand=True, padx=(0, 12))
            label(col, title, size=9, color=t.MUTED).pack(anchor='w', pady=(0, 5))
            ttk.Entry(col, textvariable=variable, width=15).pack(fill='x')
            ttk.Button(col, text='Use current frame', command=setter).pack(fill='x', pady=(8, 0))
        label(selection.content, textvariable=self.selection_var, size=9, color=t.MUTED).pack(anchor='w', pady=(12, 0))
        ttk.Button(selection.content, text='Reset to full recording', command=self.full_range).pack(anchor='w', pady=(10, 0))
        action = Card(bottom)
        action.grid(row=0, column=1, sticky='nsew')
        label(action.content, 'ENEMY DOWNED', size=9, color=t.ACCENT, bold=True).pack(anchor='w')
        label(action.content, 'Find the action.', size=19, bold=True).pack(anchor='w', pady=(8, 5))
        label(action.content, 'Scans the selected range locally.\nReview results before exporting.', color=t.MUTED, justify='left').pack(anchor='w')
        self.progress = ttk.Progressbar(action.content, maximum=100)
        self.progress.pack(fill='x', pady=(18, 12))
        controls = tk.Frame(action.content, bg=t.CARD)
        controls.pack(fill='x')
        self.scan_button = ttk.Button(controls, text='Analyze recording', style='Primary.TButton', command=self.start_scan)
        self.scan_button.pack(side='left', fill='x', expand=True)
        self.cancel_button = ttk.Button(controls, text='Stop', command=self.stop_scan)
        self.cancel_button.pack(side='right', padx=(8, 0))

    def _build_results(self):
        page = self._page('results')
        bar = Card(page)
        bar.pack(fill='x', pady=(0, 14))
        self.results_summary = label(bar.content, 'No highlights yet', size=20, bold=True)
        self.results_summary.pack(anchor='w')
        label(bar.content, 'Analyze a recording, then select rows to preview or export. Ctrl / Shift selects multiple rows.',
              color=t.MUTED, wraplength=720, justify='left').pack(anchor='w', pady=(6, 0))
        well = Card(page)
        well.pack(fill='both', expand=True)
        self.table = ttk.Treeview(well.content, columns=('player', 'in', 'out', 'duration'), show='headings', selectmode='extended')
        for name, title, width in [('player', 'PLAYER / MOMENT', 260), ('in', 'IN', 150), ('out', 'OUT', 150), ('duration', 'DURATION', 100)]:
            self.table.heading(name, text=title)
            self.table.column(name, width=width, minwidth=70, anchor='w', stretch=True)
        scroll = ttk.Scrollbar(well.content, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.table.pack(fill='both', expand=True)
        self.table.bind('<<TreeviewSelect>>', lambda _: self._update_controls())
        self.table.bind('<Double-1>', lambda _: self.preview_result())
        actions = tk.Frame(page, bg=t.BG)
        actions.pack(fill='x', pady=(14, 0))
        self.result_buttons = []
        for title, command in [('Select all', lambda: self.table.selection_set(self.table.get_children())),
                               ('Preview', self.preview_result), ('Timestamps', lambda: self.export_selection('timestamps')),
                               ('Export EDL', lambda: self.export_selection('edl')), ('Render MP4', lambda: self.export_selection('mp4'))]:
            button = ttk.Button(actions, text=title, command=command)
            button.pack(side='left', padx=(0, 8))
            self.result_buttons.append(button)

    def _build_inspector(self):
        page = self._page('inspector')
        card = Card(page)
        card.pack(fill='both', expand=True, pady=(0, 14))
        label(card.content, 'SOURCE FRAME  /  CLICK A PIXEL', color=t.MUTED, size=9, bold=True).pack(anchor='w', pady=(0, 12))
        self.inspector = Preview(card.content, on_pixel=self.inspect_pixel, height=300)
        self.inspector.pack(fill='both', expand=True)
        info = Card(page)
        info.pack(fill='x')
        self.pixel_info = label(info.content, 'No pixel selected', size=18, bold=True)
        self.pixel_info.pack(anchor='w')
        label(info.content, 'Seek in Recording, then click a pixel here. Coordinates use the original video resolution.\nInspection is a calibration building block; saved samples do not change detection yet.',
              color=t.MUTED, justify='left', wraplength=760).pack(anchor='w', pady=(8, 12))
        self.save_sample_button = ttk.Button(info.content, text='Save pixel sample…', command=self.save_sample)
        self.save_sample_button.pack(anchor='w')

    def _build_settings(self):
        form = ScrollForm(self._page('settings'))
        form.pack(fill='both', expand=True)
        self.setting_vars = {}
        defaults = Path.home() / 'Videos' / 'Killcutter'
        folders = Card(form.body)
        folders.pack(fill='x', pady=(0, 14))
        label(folders.content, 'A place for everything.', size=20, bold=True).pack(anchor='w')
        label(folders.content, 'Choose independent locations for your recordings and exports.', color=t.MUTED).pack(anchor='w', pady=(5, 16))
        for section, key, title, default in [
            ('detect', 'clips_dir', 'Recordings', str(Path.home() / 'Videos')),
            ('detect', 'timestamps_dir', 'Timestamps', str(defaults / 'Timestamps')),
            ('export', 'output_dir', 'EDL files', str(defaults / 'EDL')),
            ('detect', 'clips_output_dir', 'Rendered MP4 clips', str(defaults / 'Clips')),
        ]:
            row = tk.Frame(folders.content, bg=t.CARD)
            row.pack(fill='x', pady=6)
            label(row, title, width=19).pack(side='left')
            value = config.section(self.cfg, section).get(key) or default
            variable = tk.StringVar(value=value)
            self.setting_vars[section, key] = variable
            ttk.Entry(row, textvariable=variable).pack(side='left', fill='x', expand=True, padx=(0, 8))
            ttk.Button(row, text='Browse…', command=lambda v=variable: self.pick_folder(v)).pack(side='right')
        options = Card(form.body)
        options.pack(fill='x', pady=(0, 14))
        label(options.content, 'Detection defaults', size=20, bold=True).pack(anchor='w', pady=(0, 12))
        for key, title, default in [('offset', 'Seconds before a kill', 5), ('end_offset', 'Seconds after a kill', 5),
                                     ('merge_gap', 'Merge kills within (seconds)', 10), ('cooldown', 'Detection cooldown (seconds)', 3),
                                     ('rate', 'Samples per second', 4)]:
            row = tk.Frame(options.content, bg=t.CARD)
            row.pack(fill='x', pady=5)
            label(row, title).pack(side='left')
            variable = tk.StringVar(value=str(config.section(self.cfg, 'detect').get(key, default)))
            self.setting_vars['detect', key] = variable
            ttk.Entry(row, textvariable=variable, width=12).pack(side='right')
        row = tk.Frame(options.content, bg=t.CARD)
        row.pack(fill='x', pady=5)
        label(row, 'Premiere sequence name').pack(side='left')
        sequence = tk.StringVar(value=config.section(self.cfg, 'export').get('name', 'Kill Highlights'))
        self.setting_vars['export', 'name'] = sequence
        ttk.Entry(row, textvariable=sequence, width=24).pack(side='right')
        footer = Card(form.body)
        footer.pack(fill='x', pady=(0, 14))
        label(footer.content, 'Settings apply when saved. Existing CLI configuration is preserved.', color=t.MUTED).pack(anchor='w')
        label(footer.content, self.config_path, color=t.MUTED, wraplength=700, justify='left').pack(anchor='w', pady=(4, 12))
        ttk.Button(footer.content, text='Save settings', style='Primary.TButton', command=self.save_settings).pack(side='left')
        ttk.Button(footer.content, text='Check environment', command=self.check_environment).pack(side='left', padx=10)

