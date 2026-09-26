"""Responsive directory browser with a separate background inventory lane."""
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog

from killcutter.timecode import format_duration
from . import theme as t
from .library import scan_directory, relative_age
from .widgets import RoundedTreeview, Card, AutoScrollbar, label


class LibraryViews:
    def _build_library(self):
        self.library_visible = False
        self.library_rows = []
        self.library_cache = {}
        self.library_future = None
        self.library_generation = 0
        self.library_sort = ('modified', True)
        self.library_folder = tk.StringVar(value=self._folder('detect', 'clips_dir'))
        self.library_search = tk.StringVar()
        self.library_filter = tk.StringVar(value='All')
        self.library_summary = tk.StringVar(value='Choose a folder to browse recordings.')
        self.library_detail = tk.StringVar(value='Double-click a recording to preview and analyze it.')
        dialog = self.recording_picker = tk.Toplevel(self)
        dialog.withdraw()
        dialog.title('Choose a recording · Killcutter')
        dialog.configure(bg=t.BG)
        dialog.protocol('WM_DELETE_WINDOW', self.close_recording_picker)
        dialog.bind('<Escape>', lambda _: self.close_recording_picker())
        page = tk.Frame(dialog, bg=t.BG, padx=20, pady=20)
        page.pack(fill='both', expand=True)
        self.picker_heading = label(page, 'Choose a recording', size=22, bold=True)
        self.picker_heading.pack(anchor='w')
        self.picker_description = label(page, '', color=t.MUTED, wraplength=800, justify='left')
        self.picker_description.pack(anchor='w', pady=(5, 16))
        actions = tk.Frame(page, bg=t.BG)
        actions.pack(side='bottom', fill='x', pady=(16, 0))
        self.library_open_button = ttk.Button(actions, text='Open recording',
            style='Primary.TButton', command=self.open_library_recording)
        self.library_open_button.pack(side='right')
        self.library_queue_button = ttk.Button(actions, text='Add to analysis queue', command=self.enqueue_recordings)
        self.library_queue_button.pack(side='right', padx=8)
        self.library_open_button.state(['disabled'])
        self.picker_current_button = ttk.Button(actions, text='Use current recording', command=self.pick_current_recording)
        ttk.Button(actions, text='Cancel', command=self.close_recording_picker).pack(side='right', padx=(0, 10))
        top = Card(page)
        top.pack(fill='x', pady=(0, 12))
        folders = tk.Frame(top.content, bg=t.CARD)
        folders.pack(fill='x')
        ttk.Entry(folders, textvariable=self.library_folder).pack(side='left', fill='x', expand=True)
        ttk.Button(folders, text='Browse…', command=self.choose_library_folder).pack(side='left', padx=6)
        ttk.Button(folders, text='Refresh', command=self.refresh_library).pack(side='left')
        ttk.Button(folders, text='Configured folder', command=self.reset_library_folder).pack(side='left', padx=(6, 0))
        label(top.content, 'Done = matching EDL present · Timestamps = saved detections only · Folder contents only',
              color=t.MUTED, wraplength=680, justify='left').pack(anchor='w', pady=8)
        filters = tk.Frame(top.content, bg=t.CARD)
        filters.pack(fill='x')
        label(filters, 'Search').pack(side='left', padx=(0, 8))
        self.library_search_entry = ttk.Entry(filters, textvariable=self.library_search)
        self.library_search_entry.pack(side='left', fill='x', expand=True)
        ttk.Combobox(filters, textvariable=self.library_filter, values=('All', 'Pending', 'Timestamps', 'Done'),
                     state='readonly', width=13).pack(side='left', padx=8)
        label(top.content, textvariable=self.library_summary, color=t.MUTED).pack(anchor='w', pady=(8, 0))
        bottom = Card(page)
        bottom.pack(side='bottom', fill='x', pady=(12, 0))
        label(bottom.content, textvariable=self.library_detail, wraplength=680, justify='left', color=t.MUTED).pack(anchor='w')
        well = Card(page)
        well.pack(fill='both', expand=True)
        table = self.library_table = RoundedTreeview(well.content, columns=('name', 'status', 'duration', 'modified', 'size'), show='headings', selectmode='browse')
        for key, title, width in [('name', 'RECORDING', 280), ('status', 'STATUS', 100), ('duration', 'LENGTH', 90), ('modified', 'LAST SAVED', 120), ('size', 'SIZE', 85)]:
            table.heading(key, text=title, command=lambda k=key: self.sort_library(k))
            table.column(key, width=width, minwidth=70, stretch=key == 'name')
        vertical = AutoScrollbar(well.content, orient='vertical', command=table.yview)
        vertical.pack(side='right', fill='y')
        horizontal = AutoScrollbar(well.content, orient='horizontal', command=table.xview)
        horizontal.pack(side='bottom', fill='x')
        table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        table.pack(fill='both', expand=True)
        table.bind('<Double-1>', self.open_library_recording)
        table.bind('<Return>', self.open_library_recording)
        table.bind('<<TreeviewSelect>>', self.describe_library_recording)
        for variable in (self.library_search, self.library_filter):
            variable.trace_add('write', lambda *_: self.render_library())
        self.library_tick = self.after(30000, self.tick_library)

    def show_recording_picker(self, *, on_select=None, preset_name=None):
        dialog = self.recording_picker
        if self.library_visible:
            dialog.lift()
            return
        self.picker_on_select = on_select
        creating = on_select is not None
        title = ('Edit preset · choose a sample video' if preset_name else 'New preset · choose a sample video') if creating else 'Choose a recording'
        dialog.title(title + ' · Killcutter')
        self.picker_heading.configure(text=title)
        self.picker_description.configure(text=(
            'Create a detector from an example in your footage.\n'
            '1  Choose a video here  →  2  Find a frame  →  3  Select an area or pixel colour and save.'
            if creating else 'Open one recording, or use Ctrl / Shift to select several and add them to the analysis queue.'))
        self.library_open_button.configure(text='Choose frame →' if creating else 'Open recording')
        self.library_table.configure(selectmode='browse' if creating else 'extended')
        self.library_table.selection_remove(self.library_table.selection())
        self.library_queue_button.pack_forget()
        if not creating:
            self.library_queue_button.pack(side='right', padx=8)
        self.describe_library_recording()
        self.picker_current_button.pack_forget()
        if creating and self.state.media:
            self.picker_current_button.configure(text=f'Use current: {self.state.media.name[:35]}')
            self.picker_current_button.pack(side='left')
        self.library_search.set('')
        self.library_filter.set('All')
        self.stop_playback()
        self.picker_previous_focus = self.focus_get()
        self.update_idletasks()
        width = min(t.px(980), self.winfo_screenwidth() - 40)
        height = min(t.px(720), self.winfo_screenheight() - 80)
        x = max(0, min(self.winfo_rootx() + (self.winfo_width() - width) // 2,
                       self.winfo_screenwidth() - width))
        y = max(0, min(self.winfo_rooty() + (self.winfo_height() - height) // 2,
                       self.winfo_screenheight() - height))
        dialog.geometry(f'{width}x{height}+{x}+{y}')
        dialog.minsize(min(width, t.px(760)), min(height, t.px(540)))
        dialog.transient(self)
        self.library_visible = True
        dialog.deiconify()
        dialog.lift()
        dialog.grab_set()
        self.library_search_entry.focus_set()
        self.refresh_library()

    def close_recording_picker(self):
        self.library_visible = False
        self.picker_on_select = None
        self.recording_picker.grab_release()
        self.recording_picker.withdraw()
        previous = getattr(self, 'picker_previous_focus', None)
        if previous is not None and previous.winfo_exists():
            previous.focus_set()
        return 'break'

    def tick_library(self):
        if self.library_visible:
            self.refresh_library()
        self.library_tick = self.after(30000, self.tick_library)

    def choose_library_folder(self):
        path = filedialog.askdirectory(parent=self.recording_picker, initialdir=self.library_folder.get(), title='Browse recordings')
        if path:
            self.library_folder.set(path)
            self.refresh_library()

    def reset_library_folder(self):
        self.library_folder.set(self._folder('detect', 'clips_dir'))
        self.refresh_library()

    def refresh_library(self):
        if not self.library_visible:
            return
        self.library_generation += 1
        if self.library_future:
            self.library_future.cancel()
        self.library_summary.set('Reading directory and video metadata…')
        self.library_future = self.jobs.library_pool.submit(
            self.jobs._run, ('library', self.library_generation), scan_directory,
            (self.library_folder.get(), self._folder('export', 'output_dir'),
             self._folder('detect', 'timestamps_dir'), self.library_cache))

    def receive_library(self, generation, data, error):
        if generation != self.library_generation:
            return
        if error:
            self.library_rows = []
            self.render_library()
            self.library_summary.set(f'Could not read directory: {error}')
        else:
            self.library_rows, self.library_cache = data
            self.render_library()

    def sort_library(self, key):
        previous, reverse = self.library_sort
        self.library_sort = (key, not reverse if previous == key else key in ('modified', 'size', 'duration'))
        self.render_library()

    def render_library(self):
        selection = self.library_table.selection()
        selected = selection
        self.library_table.delete(*self.library_table.get_children())
        query, status = self.library_search.get().casefold(), self.library_filter.get()
        rows = [r for r in self.library_rows if query in r.path.name.casefold() and (status == 'All' or status == r.status)]
        key, reverse = self.library_sort
        def value(row):
            return row.path.name.casefold() if key == 'name' else (getattr(row, key) or 0)
        for row in sorted(rows, key=value, reverse=reverse):
            self.library_table.insert('', 'end', iid=str(row.path), values=(row.path.name, row.status,
                format_duration(row.duration) if row.duration else 'Unavailable', relative_age(row.modified),
                f'{row.size / 1024 ** 2:,.1f} MB'))
        remaining = [path for path in selected if self.library_table.exists(path)]
        if remaining:
            self.library_table.selection_set(remaining)
        else:
            self.library_detail.set('Double-click a recording to preview and analyze it.')
        self.describe_library_recording()
        done = sum(r.status == 'Done' for r in self.library_rows)
        self.library_summary.set(f'{len(rows)} of {len(self.library_rows)} recordings · {done} done · {len(self.library_rows) - done} without EDL' if self.library_rows else 'No videos found in this folder.')

    def describe_library_recording(self, event=None):
        selected = self.library_table.selection()
        row = next((r for r in self.library_rows if selected and str(r.path) == selected[0]), None)
        self.library_open_button.state(['!disabled'] if len(selected) == 1 else ['disabled'])
        self.library_queue_button.state(['!disabled'] if selected else ['disabled'])
        if len(selected) > 1:
            self.library_detail.set(f'{len(selected)} videos selected · Add to analysis queue to review and start full-video analysis.')
            return
        if row:
            self.library_detail.set(f'{row.path}\nLast saved: {datetime.fromtimestamp(row.modified):%Y-%m-%d %H:%M:%S}\nEDL: {row.edl or "Not found"}\nTimestamps: {row.timestamps or "Not found"}')

    def pick_current_recording(self):
        if self.state.media:
            return self.accept_picker_recording(self.state.media.path)

    def accept_picker_recording(self, path):
        callback = getattr(self, 'picker_on_select', None)
        if callback:
            self.close_recording_picker()
            return callback(path)
        return self.open_file(path)

    def open_library_recording(self, event=None):
        selected = self.library_table.selection()
        if len(selected) == 1:
            return self.accept_picker_recording(selected[0])
