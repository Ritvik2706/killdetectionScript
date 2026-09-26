"""Saved EDL selection for the Highlights workspace."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .edl import load_saved
from .widgets import label
from . import theme as t


class EdlViews:
    def build_edl_selector(self, parent):
        self.edl_path = None
        self.edl_choices = []
        self.edl_var = tk.StringVar(value='Current analysis (not saved as EDL)')
        self.edl_note = tk.StringVar(value='Open a recording to load its newest matching EDL.')
        row = tk.Frame(parent, bg=t.CARD)
        row.pack(fill='x', pady=(12, 0))
        label(row, 'EDL').pack(side='left', padx=(0, 8))
        self.edl_selector = ttk.Combobox(row, textvariable=self.edl_var, state='readonly')
        self.edl_selector.pack(side='left', fill='x', expand=True)
        self.edl_selector.bind('<<ComboboxSelected>>', self.choose_saved_edl)
        self.edl_buttons = []
        for title, action in [('Browse…', self.browse_edl), ('Latest', lambda: self.load_edl()),
                              ('Reload', lambda: self.load_edl(self.edl_path))]:
            button = ttk.Button(row, text=title, command=action)
            button.pack(side='left', padx=(6, 0))
            self.edl_buttons.append(button)
        label(parent, textvariable=self.edl_note, color=t.MUTED, wraplength=700, justify='left').pack(anchor='w', pady=(5, 0))

    def reset_edl(self):
        self.edl_path = None
        self.edl_var.set('Current analysis (not saved as EDL)')
        self.edl_note.set('Showing current analysis. Export EDL to save these highlights.')

    def choose_saved_edl(self, event=None):
        index = self.edl_selector.current()
        if 0 <= index < len(self.edl_choices):
            target = self.edl_choices[index]
            self.edl_var.set(self.edl_path or 'Current analysis (not saved as EDL)')
            self.load_edl(target)

    def browse_edl(self):
        if self.working or not self.state.media:
            return
        path = filedialog.askopenfilename(parent=self, title='Choose highlight EDL',
            initialdir=self._folder('export', 'output_dir'), filetypes=[('EDL files', '*.edl')])
        if path:
            self.load_edl(path)

    def load_edl(self, path=None, *, automatic=False):
        if self.working or not self.state.media:
            return
        if not automatic and self.state.clips and not self.exported:
            if not messagebox.askyesno('Replace highlights?', 'Replace the current unsaved highlights with the selected EDL?', parent=self):
                return
        self._begin('edl', 'Loading saved highlights…')
        self.jobs.submit('edl', load_saved, self._folder('export', 'output_dir'), self.state.media, path)

    def receive_edl(self, data):
        paths, path, clips, error = data
        self.edl_choices = paths
        self.edl_selector.configure(values=paths)
        if error:
            self.edl_note.set(f'Could not load {Path(path).name}: {error}')
            self.status.set('EDL could not be loaded. Current highlights were kept.')
            return
        if path is None:
            self.edl_note.set('No matching EDL found. Analyze this recording or browse for an EDL.')
            self.status.set('No saved EDL found for this recording.')
            return
        self.edl_path = path
        self.edl_var.set(path)
        self.state.clips = clips
        self.state.completed = True
        self.state.player_traits = any('real-player' in clip.traits for clip in clips)
        self.removed = []
        self.exported = True
        self.exported_ids = {str(i) for i in range(len(clips))}
        self.reset_result_filters()
        self.filter_results()
        self.table.selection_set(self.table.get_children())
        self.results_summary.configure(text=f'{len(clips)} saved highlights')
        self.live_table.delete(*self.live_table.get_children())
        self.edl_note.set('Loaded source timestamps and labels from EDL. Edit highlights, then Export EDL to save changes.')
        self.status.set(f'Loaded {len(clips)} highlights from {Path(path).name}.')
