"""Desktop page layouts, separated from workflow orchestration.

Views bind controls to Application actions; processing remains in services.
"""
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from killcutter import config
from . import preferences
from . import theme as t
from .widgets import RoundedTreeview, AutoScrollbar, Card, Preview, ScrollForm, label


class Views:
    def _build_workspace(self):
        form = ScrollForm(self._page('workspace'), stretch=True)
        form.pack(fill='both', expand=True)
        page = form.body
        page.columnconfigure(0, weight=1)
        page.rowconfigure(0, weight=1)
        preview = Card(page)
        preview.grid(row=0, column=0, sticky='nsew', pady=(0, 14), padx=(0, 12))
        page.columnconfigure(1, minsize=250)
        header = tk.Frame(preview.content, bg=t.CARD)
        header.pack(fill='x', pady=(0, 12))
        label(header, 'FRAME PREVIEW', size=9, color=t.MUTED, bold=True).pack(side='left')
        label(header, textvariable=self.position_var, color=t.MUTED).pack(side='right')
        self.preview = Preview(preview.content, height=180, width=300)
        self.preview.pack(fill='both', expand=True)
        self.seek = ttk.Scale(preview.content, from_=0, to=1, command=self._seek_changed)
        self.seek.pack(fill='x', pady=(14, 8))
        source = label(preview.content, textvariable=self.source_var, color=t.MUTED, justify='left')
        source.pack(fill='x')
        source.bind('<Configure>', lambda e: source.configure(wraplength=max(100, e.width)))
        transport = tk.Frame(preview.content, bg=t.CARD)
        transport.pack(fill='x', pady=(8, 0))
        for title, delta in [('−5 s', -5), ('−1 frame', -1), ('+1 frame', 1), ('+5 s', 5)]:
            ttk.Button(transport, text=title, width=8,
                       command=lambda d=delta: self.step(d, frames=abs(d) == 1)).pack(side='left', padx=(0, 5))
        player_controls = tk.Frame(preview.content, bg=t.CARD)
        player_controls.pack(fill='x', pady=(8, 0))
        self.build_transport(player_controls)
        live = Card(page, padding=16)
        live.grid(row=0, column=1, sticky='nsew', pady=(0, 14))
        label(live.content, 'LIVE ANALYSIS', size=9, color=t.ACCENT, bold=True).pack(anchor='w')
        label(live.content, textvariable=self.live_count, size=22, bold=True).pack(anchor='w', pady=(12, 3))
        label(live.content, textvariable=self.live_detail, color=t.MUTED,
              wraplength=220, justify='left').pack(anchor='w', pady=(0, 12))
        label(live.content, textvariable=self.live_player, wraplength=210,
              justify='left', color=t.GREEN).pack(anchor='w', pady=(0, 10))
        self.live_table = RoundedTreeview(live.content, columns=('player',), show='tree', height=3,
                                      selectmode='browse')
        self.live_table.column('#0', width=85, minwidth=85, stretch=False)
        self.live_table.column('player', width=120, minwidth=90)
        self.live_table.configure(show='tree headings')
        self.live_table.heading('#0', text='TIME')
        self.live_table.heading('player', text='LABEL')
        self.live_table.pack(fill='both', expand=True)
        live_scroll = AutoScrollbar(live.content, orient='horizontal', command=self.live_table.xview)
        self.live_table.configure(xscrollcommand=live_scroll.set)
        live_scroll.pack(fill='x', pady=(t.px(6), 0))
        self.live_table.bind('<Double-1>', self.preview_live)
        self.live_table.bind('<<TreeviewSelect>>', self.describe_live)
        ttk.Checkbutton(live.content, text='Follow scan frames', variable=self.follow_scan).pack(anchor='w', pady=(10, 0))
        ttk.Button(live.content, text='Review highlights →', command=lambda: self.show('results')).pack(fill='x', pady=(8, 0))
        bottom = tk.Frame(page, bg=t.BG)
        bottom.grid(row=1, column=0, columnspan=2, sticky='ew')
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
        label(action.content, 'DETECTION PRESET', size=9, color=t.ACCENT, bold=True).pack(anchor='w')
        preset_row = tk.Frame(action.content, bg=t.CARD)
        preset_row.pack(fill='x', pady=(8, 0))
        self._preset_selector(preset_row).pack(side='left', fill='x', expand=True)
        ttk.Button(preset_row, text='Manage…', command=lambda: self.show('presets')).pack(side='right', padx=(8, 0))
        label(action.content, textvariable=self.analysis_title, size=16, bold=True).pack(anchor='w', pady=(8, 5))
        label(action.content, 'Scans the selected range locally.\nReview results before exporting.', color=t.MUTED, justify='left').pack(anchor='w')
        self.progress = ttk.Progressbar(action.content, maximum=100)
        self.progress.pack(fill='x', pady=(18, 12))
        controls = tk.Frame(action.content, bg=t.CARD)
        controls.pack(fill='x')
        self.scan_button = ttk.Button(controls, text='Analyze recording', style='CardPrimary.TButton', command=self.start_scan)
        self.scan_button.pack(side='left', fill='x', expand=True)
        self.cancel_button = ttk.Button(controls, text='Stop', command=self.stop_scan)
        self.cancel_button.pack(side='right', padx=(8, 0))

    def _build_results(self):
        page = self._page('results')
        bar = Card(page)
        bar.pack(fill='x', pady=(0, 14))
        self.results_summary = label(bar.content, 'No highlights yet', size=20, bold=True)
        self.results_summary.pack(anchor='w')
        label(bar.content, 'Load a saved EDL or analyze a recording, then select highlights to preview or export. Ctrl / Shift selects multiple rows.',
              color=t.MUTED, wraplength=720, justify='left').pack(anchor='w', pady=(6, 0))
        self.build_edl_selector(bar.content)
        search = tk.Frame(bar.content, bg=t.CARD)
        search.pack(fill='x', pady=(14, 0))
        label(search, 'Find label').pack(side='left', padx=(0, 10))
        self.search_entry = ttk.Entry(search, textvariable=self.search_var)
        self.search_entry.pack(side='left', fill='x', expand=True)
        ttk.Button(search, text='Clear', command=lambda: self.search_var.set('')).pack(side='left', padx=(8, 0))
        filters = self.trait_filters = tk.Frame(bar.content, bg=t.CARD)
        filters.pack(fill='x', pady=(12, 0))
        self.filter_buttons = {}
        for key, title in [('all', 'All kills'), ('real-player', 'Real players'),
                           ('bot', 'Bots'), ('unknown', 'Undetermined')]:
            button = ttk.Button(filters, text=title, command=lambda k=key: self.kill_filter.set(k))
            button.pack(side='left', padx=(0, 6))
            self.filter_buttons[key] = button
        self.filter_buttons['all'].state(['selected'])
        ttk.Button(filters, text='Reset filters', command=self.reset_result_filters).pack(side='right')
        self.unknown_check = ttk.Checkbutton(bar.content, text='Include undetermined kills',
                                            variable=self.keep_unknown)
        self.unknown_check.pack(anchor='w', pady=(8, 0))
        self.unknown_check.state(['disabled'])
        self.filter_hint_label = label(bar.content, textvariable=self.filter_hint, size=9, color=t.MUTED, wraplength=720, justify='left')
        self.filter_hint_label.pack(anchor='w', pady=(4, 0))
        label(bar.content, textvariable=self.selected_var, color=t.MUTED).pack(anchor='w', pady=(10, 0))
        actions = tk.Frame(page, bg=t.BG)
        trim = tk.Frame(page, bg=t.BG)
        trim.pack(side='bottom', fill='x', pady=(10, 0))
        actions.pack(side='bottom', fill='x', pady=(14, 0))
        well = Card(page)
        well.pack(fill='both', expand=True)
        self.table = RoundedTreeview(well.content, columns=('player', 'type', 'in', 'out', 'duration'), show='headings', selectmode='extended')
        for name, title, width in [('player', 'LABEL / MOMENT', 210), ('type', 'KILL TYPE', 140), ('in', 'IN', 125), ('out', 'OUT', 125), ('duration', 'DURATION', 100)]:
            self.table.heading(name, text=title, command=lambda c=name: self.sort_results(c))
            self.table.column(name, width=width, minwidth=70, anchor='w', stretch=True)
        scroll = AutoScrollbar(well.content, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.table.pack(fill='both', expand=True)
        self.table.bind('<<TreeviewSelect>>', lambda _: self._update_controls())
        self.table.bind('<Double-1>', lambda _: self.preview_result())
        self.table.bind('<Return>', lambda _: self.preview_result())
        self.table.bind('<Control-a>', self.select_all_results)
        self.table.bind('<Delete>', self.remove_selected)
        self.table.bind('<F2>', self.rename_selected)
        self.table.bind('<Control-c>', lambda _: self.copy_selection())
        self.table.tag_configure('alternate', background=t.ALTERNATE)
        self.result_buttons = []
        for title, command in [('Select all', self.select_all_results),
                               ('Preview', self.preview_result), ('Rename…', self.rename_selected),
                               ('Remove', self.remove_selected), ('Copy', self.copy_selection),
                               ('Timestamps', lambda: self.export_selection('timestamps')),
                               ('Export EDL', lambda: self.export_selection('edl')), ('Render MP4', lambda: self.export_selection('mp4'))]:
            button = ttk.Button(actions, text=title, command=command, style='Toolbar.TButton')
            self.result_buttons.append(button)
        def arrange_actions(event):
            buttons = self.result_buttons[:8]
            columns = 8 if sum(b.winfo_reqwidth() + 8 for b in buttons) <= event.width else 4
            for index, button in enumerate(buttons):
                button.grid(row=index // columns, column=index % columns,
                            sticky='ew', padx=(0, 6), pady=(0, 4))
            for column in range(8):
                actions.columnconfigure(column, weight=1 if column < columns else 0)
        actions.bind('<Configure>', arrange_actions)
        label(trim, 'NUDGE SELECTED', size=9, color=t.MUTED, bold=True).pack(side='left', padx=(0, 10))
        for title, seconds, edge in [('In −1s', -1, 'start'), ('In +1s', 1, 'start'),
                                     ('Out −1s', -1, 'end'), ('Out +1s', 1, 'end')]:
            button = ttk.Button(trim, text=title, style='Toolbar.TButton', width=8,
                                command=lambda s=seconds, e=edge: self.adjust_selected(s, edge=e))
            button.pack(side='left', padx=(0, 6))
            self.result_buttons.append(button)

    def _build_settings(self):
        form = ScrollForm(self._page('settings'))
        form.pack(fill='both', expand=True)
        self.setting_vars = {}
        defaults = Path.home() / 'Videos' / 'Killcutter'
        look = Card(form.body)
        look.pack(fill='x', pady=(0, 14))
        label(look.content, 'Appearance', size=20, bold=True).pack(anchor='w')
        label(look.content, 'Theme, accent and interface scale are stored on this machine and apply instantly.',
              color=t.MUTED).pack(anchor='w', pady=(5, 16))
        themes = tk.Frame(look.content, bg=t.CARD)
        themes.pack(fill='x')
        label(themes, 'Theme', width=19).pack(side='left')
        self.theme_buttons = {}
        for name in t.PALETTES:
            button = ttk.Button(themes, text=name, width=11,
                                command=lambda n=name: (self.theme_var.set(n), self.apply_appearance()))
            button.pack(side='left', padx=(0, 8))
            self.theme_buttons[name] = button
        accents = tk.Frame(look.content, bg=t.CARD)
        accents.pack(fill='x', pady=(14, 0))
        label(accents, 'Accent', width=19).pack(side='left')
        self.accent_swatches = {}
        for name, color in t.ACCENTS.items():
            swatch = tk.Frame(accents, bg=color, width=t.px(30), height=t.px(30),
                              highlightthickness=2, highlightbackground=t.CARD, cursor='hand2')
            swatch.pack(side='left', padx=(0, 8))
            swatch.pack_propagate(False)
            swatch.bind('<Button-1>', lambda _, c=color: (self.accent_var.set(c), self.apply_appearance()))
            self.accent_swatches[color] = swatch
        ttk.Button(accents, text='Custom…', command=self.choose_accent).pack(side='left', padx=(6, 0))
        scale_row = tk.Frame(look.content, bg=t.CARD)
        scale_row.pack(fill='x', pady=(16, 0))
        label(scale_row, 'Interface scale', width=19).pack(side='left')
        self.scale_label = label(scale_row, f'{self.prefs.scale:.0%}', width=6, color=t.ACCENT)
        self.scale_label.pack(side='right')
        slider = ttk.Scale(scale_row, from_=preferences.MIN_SCALE, to=preferences.MAX_SCALE,
                           variable=self.scale_var,
                           command=lambda v: self.scale_label.configure(text=f'{float(v):.0%}'))
        slider.pack(side='left', fill='x', expand=True, padx=(0, 12))
        # Restyling on release only: a full rebuild on every drag step would stutter.
        slider.bind('<ButtonRelease-1>', lambda _: self.apply_appearance())
        ttk.Checkbutton(look.content, text='Chime when an analysis finishes', variable=self.chime_var,
                        command=self.apply_appearance).pack(anchor='w', pady=(16, 0))
        ttk.Button(look.content, text='Reset appearance', command=self.reset_appearance).pack(anchor='w', pady=(12, 0))
        self._mark_appearance()
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
        for key, title, default in [('offset', 'Seconds before an event', 5), ('end_offset', 'Seconds after an event', 5),
                                     ('merge_gap', 'Merge events within (seconds)', 10), ('cooldown', 'Detection cooldown (seconds)', 3),
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
        sequence = tk.StringVar(value=config.section(self.cfg, 'export').get('name', 'Video Highlights'))
        self.setting_vars['export', 'name'] = sequence
        ttk.Entry(row, textvariable=sequence, width=24).pack(side='right')
        footer = Card(form.body)
        footer.pack(fill='x', pady=(0, 14))
        label(footer.content, 'Settings apply when saved. Existing CLI configuration is preserved.', color=t.MUTED).pack(anchor='w')
        label(footer.content, self.config_path, color=t.MUTED, wraplength=700, justify='left').pack(anchor='w', pady=(4, 12))
        ttk.Button(footer.content, text='Save settings', style='CardPrimary.TButton', command=self.save_settings).pack(side='left')
        ttk.Button(footer.content, text='Check environment', command=self.check_environment).pack(side='left', padx=10)
        ttk.Button(footer.content, text='Check for updates', command=self.check_updates).pack(side='left')
