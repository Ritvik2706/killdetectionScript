"""Desktop shell and workflows. All widget access stays on the Tk thread."""
from dataclasses import replace
from pathlib import Path
from queue import Empty
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from killcutter import config, constants, detection, environment, export, outputs, traits
from killcutter.ranges import parse_timestamp, resolve_range
from . import branding, preferences, theme as t
from .services import Jobs, analyze, open_media
from .state import Workspace
from .widgets import Card, Preview, label
from .views import Views
from .library_views import LibraryViews
from .edl_views import EdlViews
from .queue_views import QueueViews
from .preset_views import PresetViews
from .playback_views import PlaybackViews


def clock(seconds):
    hours, rest = divmod(max(0, seconds), 3600)
    minutes, seconds = divmod(rest, 60)
    return f'{int(hours):02}:{int(minutes):02}:{seconds:06.3f}'


class Application(QueueViews, EdlViews, LibraryViews, PlaybackViews, PresetViews, Views, tk.Tk):
    def __init__(self, *, config_path=None):
        super().__init__(className="KillcutterStudio")
        self.withdraw()
        self.title('Killcutter Studio')
        branding.install_window_icons(self)
        self.cfg, loaded_path = config.load(config_path)
        self.config_path = loaded_path or config_path or config.user_config_path()
        self.prefs = preferences.load(self.cfg)
        t.configure(*self.prefs.appearance)
        self.configure(bg=t.BG)
        self.family = t.apply(self)
        self.minsize(t.px(940), t.px(660))
        width, height = min(t.px(1360), self.winfo_screenwidth()-60), min(t.px(880), self.winfo_screenheight()-80)
        self.geometry(self.prefs.geometry or f'{max(t.px(940), width)}x{max(t.px(660), height)}')
        self.state = Workspace()
        self.jobs = Jobs()
        self.working = None
        self.init_queue()
        self.generation = 0
        self.seek_timer = None
        self.frame_time = 0
        self.exported = True
        self.exported_ids = set()
        self.exporting_ids = set()
        self.analysis_title = tk.StringVar(value='Ready to analyze.')
        self.live_player = tk.StringVar(value='Waiting for detections')
        self.live_count = tk.StringVar(value='0 highlights')
        self.live_detail = tk.StringVar(value='Detected labels and moments appear here during analysis.')
        self.follow_scan = tk.BooleanVar(value=True)
        self.search_var = tk.StringVar()
        self.kill_filter = tk.StringVar(value='all')
        self.keep_unknown = tk.BooleanVar(value=True)
        self.filter_hint = tk.StringVar(value='Filter highlights without rescanning. Only selected rows are exported.')
        self.selected_var = tk.StringVar(value='No highlights selected')
        self.result_sort = ('in', False)
        self.removed = []
        self.theme_var = tk.StringVar(value=self.prefs.theme)
        self.accent_var = tk.StringVar(value=self.prefs.accent)
        self.scale_var = tk.DoubleVar(value=self.prefs.scale)
        self.chime_var = tk.BooleanVar(value=self.prefs.chime)
        self.last_follow = 0
        self.scan_started = 0
        self.scan_position = 0
        self.status = tk.StringVar(value='Ready when you are. Open a recording to get started.')
        self.start_var = tk.StringVar(value='00:00:00.000')
        self.end_var = tk.StringVar(value='00:00:00.000')
        self.position_var = tk.StringVar(value='00:00:00.000')
        self.source_var = tk.StringVar(value='No recording loaded')
        self.selection_var = tk.StringVar(value='Choose your in and out points')
        self._init_presets()
        self._build_shell()
        self._build_workspace()
        self._build_results()
        self._build_settings()
        self._build_presets()
        self.saved_values = {key: variable.get() for key, variable in self.setting_vars.items()}
        self._build_library()
        self.show(self.prefs.page)
        self.start_var.trace_add('write', lambda *_: self._range_summary())
        self.end_var.trace_add('write', lambda *_: self._range_summary())
        for variable in (self.search_var, self.kill_filter, self.keep_unknown):
            variable.trace_add('write', lambda *_: self.filter_results())
        self.bind('<space>', self.toggle_playback)
        self.bind('<Control-o>', lambda _: self.open_file())
        self.bind('<Control-Return>', lambda _: self.start_scan())
        self.bind('<Control-f>', self.focus_search)
        self.bind('<Escape>', lambda _: self.stop_scan() if self.working in ('scan', 'render', 'batch') else None)
        self.bind('<F1>', lambda _: self.show_shortcuts())
        self.bind('<Control-question>', lambda _: self.show_shortcuts())
        self.bind('<Control-z>', lambda _: self.undo_remove())
        for number, page in enumerate(('workspace', 'results', 'presets', 'settings'), 1):
            self.bind(f'<Control-Key-{number}>', lambda _, p=page: self.show(p))
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.poll_timer = self.after(75, self._poll)
        self._update_controls()
        self.deiconify()

    def _build_shell(self):
        rail_card = Card(self, padding=8, role='SIDEBAR', width=t.px(214))
        rail_card.pack(side='left', fill='y', padx=(12, 0), pady=12)
        rail_card.pack_propagate(False)
        self.rail_card = rail_card
        rail = rail_card.content
        self.brand = tk.Canvas(rail, width=t.px(42), height=t.px(42), bg=t.SIDEBAR, highlightthickness=0)
        self.brand.pack(anchor='w', padx=22, pady=(26, 12))
        self._draw_brand()
        label(rail, 'Killcutter', size=21, bold=True).pack(anchor='w', padx=22)
        label(rail, 'S T U D I O', size=9, color=t.MUTED).pack(anchor='w', padx=24, pady=(4, 32))
        label(rail, 'WORKSPACE', size=9, color=t.MUTED, bold=True).pack(anchor='w', padx=24, pady=(0, 10))
        self.nav = {}
        self.pages = {}
        for key, title in [('workspace', '01   Recording'), ('results', '02   Highlights'),
                           ('presets', '03   Presets'), ('settings', '04   Settings')]:
            button = ttk.Button(rail, text=title, style='Nav.TButton', command=lambda k=key: self.show(k))
            button.pack(fill='x', padx=2, pady=3)
            self.nav[key] = button
        label(rail, 'LOCAL PROCESSING\nYour footage stays yours.\n\nCtrl+O  Open recording\nCtrl+Enter  Analyze\nF1  All shortcuts', size=9, color=t.MUTED,
              justify='left').pack(side='bottom', anchor='w', padx=22, pady=26)
        main = tk.Frame(self, bg=t.BG)
        main.pack(side='left', fill='both', expand=True, padx=26, pady=(22, 14))
        self.header = tk.Frame(main, bg=t.BG)
        self.header.pack(fill='x', pady=(0, 22))
        self.open_button = ttk.Button(self.header, text='Open recording   ↗', style='Primary.TButton', command=self.open_file)
        self.open_button.pack(side='right', padx=(16, 0))
        self.recent_button = ttk.Button(self.header, text='Recent ▾', style='Toolbar.TButton', command=self.show_recents)
        self.recent_button.pack(side='right')
        self.queue_button = ttk.Button(self.header, text='Queue (0)', style='Toolbar.TButton', command=self.show_analysis_queue)
        self.queue_button.pack(side='right', padx=(0, 8))
        self.heading = label(self.header, '', size=26, bold=True)
        self.heading.pack(anchor='w')
        self.subtitle = label(self.header, textvariable=self.active_preset_text, color=t.ACCENT, bold=True)
        self.subtitle.pack(anchor='w', pady=(5, 0))
        self.header.bind('<Configure>', self._header_resize)
        self.host = tk.Frame(main, bg=t.BG)
        self.host.pack(fill='both', expand=True)
        self.host.rowconfigure(0, weight=1)
        self.host.columnconfigure(0, weight=1)
        footer = tk.Frame(main, bg=t.BG)
        footer.pack(fill='x', pady=(12, 0))
        self.status_label = label(footer, textvariable=self.status, color=t.MUTED)
        self.status_label.pack(fill='x')
        footer.bind('<Configure>', lambda e: self.status_label.configure(wraplength=max(200, e.width)))

    def _draw_brand(self):
        size = t.px(48)
        self.brand.configure(width=size, height=size, bg=t.SIDEBAR)
        self.brand.delete('all')
        self.brand_photo = branding.photo(self, size)
        self.brand.create_image(size/2, size/2, image=self.brand_photo)

    def _header_resize(self, event):
        available = max(180, event.width - self.open_button.winfo_reqwidth()
                        - self.recent_button.winfo_reqwidth() - self.queue_button.winfo_reqwidth() - 40)
        self.heading.configure(wraplength=available, justify='left')
        self.subtitle.configure(wraplength=available, justify='left')

    def _page(self, key):
        page = tk.Frame(self.host, bg=t.BG)
        page.grid(row=0, column=0, sticky='nsew')
        self.pages[key] = page
        return page

    def show(self, key):
        if key != 'workspace' and hasattr(self, 'player'):
            self.stop_playback()
        titles = {
            'workspace': ('Recording', 'Select a recording. Set your range. Find the highlights.'),
            'results': ('Your highlights.', 'Review your detections and export the moments worth keeping.'),
            'presets': ('Detection presets', 'Choose what to detect. Create a preset from a video.'),
            'settings': ('Make it yours.', 'Saved defaults for your workflow, folders, and detection.'),
        }
        self.current_page = key
        self.prefs = replace(self.prefs, page=key)
        self.heading.configure(text=titles[key][0])
        self.pages[key].tkraise()
        for name, button in self.nav.items():
            button.state(['selected'] if name == key else ['!selected'])

    def _folder(self, section, key):
        return str(Path(self.saved_values[section, key]).expanduser())

    def pick_folder(self, variable):
        result = filedialog.askdirectory(parent=self, title='Choose folder', initialdir=variable.get() or str(Path.home()))
        if result:
            variable.set(result)

    def _settings(self, draft=False):
        values = {key: float(self.setting_vars['detect', key].get() if draft else self.saved_values['detect', key]) for key in ('offset', 'end_offset', 'merge_gap', 'cooldown', 'rate')}
        settings = detection.DetectionSettings(region=constants.DEFAULT_REGION, preset=self.active_preset,
                                               traits=self.active_preset.has_player_traits, **values)
        detection.validate(settings)
        return settings

    def save_settings(self):
        try:
            self._settings(draft=True)
            updates = {}
            for (section, key), variable in self.setting_vars.items():
                value = variable.get().strip()
                if section == 'detect' and key in ('offset', 'end_offset', 'merge_gap', 'cooldown', 'rate'):
                    value = float(value)
                elif not value:
                    raise ValueError('Folder locations and sequence name cannot be empty.')
                updates.setdefault(section, {})[key] = value
            config.save_updates(self.config_path, updates)
            self.cfg, _ = config.load(self.config_path)
            previous_folder = self._folder('detect', 'clips_dir')
            self.saved_values = {key: variable.get().strip() for key, variable in self.setting_vars.items()}
            if self.library_folder.get() == previous_folder:
                self.library_folder.set(self._folder('detect', 'clips_dir'))
            self.refresh_library()
            self.status.set('Settings saved. Your next scan will use these defaults.')
        except Exception as exc:
            self.error('Could not save settings', str(exc))

    def open_file(self, path=None):
        if self.working:
            return
        if not path:
            self.show_recording_picker()
            return
        if self.state.clips and not self.exported and not messagebox.askyesno('Open another recording?', 'Current highlights have not been exported. Replace this workspace?', parent=self.recording_picker if self.library_visible else self):
            return
        if self.library_visible:
            self.close_recording_picker()
        if self.seek_timer:
            self.after_cancel(self.seek_timer)
            self.seek_timer = None
        self.generation += 1
        resolved = str(Path(path).resolve())
        self.prefs = preferences.remember(self.prefs, resolved)
        self._save_preferences()
        self._begin('open', 'Opening recording…')
        self.jobs.submit('open', open_media, resolved)
        return True

    def _begin(self, kind, message):
        self.stop_playback()
        self.working = kind
        self.status.set(message)
        self._update_controls()

    def _update_controls(self):
        busy, loaded = bool(self.working), self.state.media is not None
        self.update_preset_actions()
        self.render_queue()
        for selector in self.preset_selectors:
            selector.configure(state='disabled' if busy else 'readonly')
        self.edl_selector.configure(state='readonly' if loaded and not busy else 'disabled')
        for button in self.edl_buttons:
            button.state(['!disabled'] if loaded and not busy else ['disabled'])
        self.open_button.state(['disabled'] if busy else ['!disabled'])
        self.play_button.state(['!disabled'] if loaded and not busy else ['disabled'])
        self.scan_button.state(['!disabled'] if loaded and not busy else ['disabled'])
        self.cancel_button.state(['!disabled'] if self.working in ('scan', 'render', 'batch') else ['disabled'])
        self.seek.state(['!disabled'] if loaded and not busy else ['disabled'])
        selected = [self.state.clips[int(i)] for i in self.table.selection() if int(i) < len(self.state.clips)]
        self.selected_var.set(f'{len(self.table.get_children())} of {len(self.state.clips)} shown · {len(selected)} selected  ·  {clock(sum(c.duration for c in selected))} total duration')
        for index, button in enumerate(self.result_buttons):
            has_rows = bool(self.table.get_children() if index == 0 else self.table.selection())
            button.state(['!disabled'] if has_rows and not busy else ['disabled'])

    def _seek_changed(self, value):
        if not self.state.media or self.working:
            return
        seconds = float(value)
        if self.player and not self.player_stopping:
            self.player.command('seek', seconds, 'absolute+exact')
            return
        self.state.position = seconds
        self.position_var.set(clock(seconds))
        self.generation += 1
        if self.seek_timer:
            self.after_cancel(self.seek_timer)
        self.seek_timer = self.after(120, lambda: self._request_frame(seconds))

    def _request_frame(self, seconds):
        self.seek_timer = None
        if self.state.media and not self.working:
            self.jobs.preview(self.generation, self.state.media.path, seconds)

    def mark_in(self):
        if self.state.media and not self.working:
            self.start_var.set(clock(self.state.position))

    def mark_out(self):
        if self.state.media and not self.working:
            self.end_var.set(clock(min(self.state.media.duration, self.state.position + 1 / self.state.media.fps)))

    def full_range(self):
        if self.state.media and not self.working:
            self.start_var.set(clock(0))
            self.end_var.set(clock(self.state.media.duration))

    def _range_summary(self):
        if not self.state.media:
            return
        try:
            start, end = self._range()
            self.selection_var.set(f'{clock(end-start)} selected  ·  {(end-start)/self.state.media.duration:.0%} of recording')
        except Exception:
            self.selection_var.set('Enter a valid range within the recording.')

    def _range(self):
        # Display rounding must not put the end a fraction beyond the container.
        start, end = parse_timestamp(self.start_var.get()), parse_timestamp(self.end_var.get())
        if abs(end - self.state.media.duration) < .001:
            end = self.state.media.duration
        return resolve_range(self.state.media.duration, start, end=end)

    def start_scan(self):
        if not self.state.media or self.working:
            return
        try:
            settings = self._settings()
            start, end = self._range()
        except Exception as exc:
            self.error('Check scan settings', str(exc))
            return
        if self.state.clips and not self.exported and not messagebox.askyesno('Replace highlights?', 'Analyze again and replace the current unexported results?', parent=self):
            return
        self.generation += 1
        self.reset_edl()
        self.state.clips = []
        self.state.completed = False
        self.state.preset = self.active_preset
        self.state.preset_id = self.active_preset.id
        self.state.preset_name = self.active_preset.name
        self.state.player_traits = self.active_preset.has_player_traits
        self.kill_filter.set('all')
        self.filter_results()
        self.exported_ids.clear()
        self.exported = True
        self.table.delete(*self.table.get_children())
        self.live_table.delete(*self.live_table.get_children())
        self.search_var.set('')
        self.live_count.set('0 highlights')
        self.live_player.set('Waiting for detections')
        self.analysis_title.set('Analyzing…')
        self.live_detail.set(f'Running {self.active_preset.name}…')
        self.results_summary.configure(text='Analysis in progress')
        self.scan_started = time.monotonic()
        self.scan_position = start
        self.last_follow = 0
        self.show('workspace')
        self.progress['value'] = 0
        self._begin('scan', 'Analyzing locally… You can stop and keep partial results.')
        self.jobs.submit('scan', analyze, self.jobs, self.state.media, settings, start, end,
                         config.section(self.cfg, "detect").get("region") if self.active_preset.has_player_traits else None)

    def stop_scan(self):
        if self.working == 'batch':
            self.stop_queue()
            return
        if self.working not in ('scan', 'render'):
            return
        self.jobs.cancel.set()
        if self.working == 'render':
            self.status.set('Stopping export… Completed files will be kept.')
            self.cancel_button.state(['disabled'])
            return
        self.status.set('Stopping after the current sample… Your detected highlights will be kept.')
        self.cancel_button.state(['disabled'])

    def _set_frame(self, image):
        self.preview.set_image(image)
        self.frame_time = self.state.position
        self._update_controls()

    def _poll(self):
        try:
            for _ in range(100):
                kind, data, error = self.jobs.events.get_nowait()
                if isinstance(kind, tuple):
                    if kind[0] == 'library':
                        self.receive_library(kind[1], data, error)
                        continue
                    if kind[0].startswith('playback'):
                        self.playback_event(kind, data, error)
                        continue
                    if kind[1] == self.generation:
                        if error:
                            self.status.set(error)
                        else:
                            self.state.position = kind[2]
                            self.position_var.set(clock(kind[2]))
                            self._set_frame(data)
                    continue
                if kind == 'batch_progress':
                    fraction, count, eta = data
                    self.status.set(f'Queue · {Path(self.analysis_queue[self.queue_active]["path"]).name} · {fraction:.0%} · {count} highlights')
                    continue
                if kind == 'batch':
                    self.receive_batch(data, error)
                    continue
                if kind == 'render_progress':
                    index, total, path = data
                    self.exported_ids.add(self.render_ids[index - 1])
                    self.exported = len(self.exported_ids) == len(self.state.clips)
                    self.progress['value'] = index / total * 100
                    if not self.jobs.cancel.is_set():
                        self.status.set(f'Exported {index} of {total} clips · {Path(path).name}')
                    continue
                if kind == 'scan_position':
                    self.scan_position, triggered = data
                    if self.working == 'scan' and self.follow_scan.get() and time.monotonic() - self.last_follow >= 1:
                        self.last_follow = time.monotonic()
                        self.state.position = self.scan_position
                        self.position_var.set(clock(self.scan_position))
                        self.seek.set(self.scan_position)
                        self.jobs.preview(self.generation, self.state.media.path, self.scan_position)
                    continue
                if kind == 'highlight':
                    index, at, clip, merged = data
                    if index == len(self.state.clips):
                        self.state.clips.append(clip)
                    elif 0 <= index < len(self.state.clips):
                        self.state.clips[index] = clip
                    self.exported = False
                    iid = str(index)
                    values = (clip.name,)
                    if self.live_table.exists(iid):
                        self.live_table.item(iid, values=values)
                    else:
                        self.live_table.insert('', 'end', iid=iid, text=clock(at).split('.')[0], values=values)
                    self.live_table.see(iid)
                    self.live_player.set(clip.name)
                    self.live_count.set(f"{len(self.state.clips)} highlight{'s' if len(self.state.clips) != 1 else ''}")
                    self.results_summary.configure(text=f'Live · {len(self.state.clips)} highlights')
                    self.filter_results()
                    continue
                if kind == 'progress':
                    fraction, count, eta = data
                    self.progress['value'] = fraction * 100
                    remaining = f'  ·  about {int(eta)}s remaining' if eta is not None else ''
                    elapsed = max(0, time.monotonic() - self.scan_started)
                    self.live_detail.set(f'{fraction:.0%} scanned · {int(elapsed)}s elapsed\nAt {clock(self.scan_position)}{remaining}')
                    if not self.jobs.cancel.is_set():
                        self.status.set(f'Analyzing  {fraction:.0%}  ·  {count} highlights{remaining}')
                    continue
                self.working = None
                if kind == 'scan':
                    self.analysis_title.set('Analysis interrupted' if error else 'Ready to analyze.')
                if error:
                    if kind == 'scan':
                        self.results_summary.configure(text=f'Interrupted · {len(self.state.clips)} highlights retained')
                        self.live_detail.set('Analysis interrupted. Detected highlights are available for review.')
                    self.error('Operation could not finish', error)
                elif kind == 'open':
                    media, image = data
                    self.state = Workspace(media=media)
                    self.reset_edl()
                    self.edl_choices = []
                    self.edl_selector.configure(values=())
                    self.removed = []
                    self.exported = True
                    self.exported_ids.clear()
                    self.table.delete(*self.table.get_children())
                    self.results_summary.configure(text='No highlights yet')
                    self.live_table.delete(*self.live_table.get_children())
                    self.live_count.set('0 highlights')
                    self.live_player.set('Waiting for detections')
                    self.analysis_title.set('Ready to analyze.')
                    self.live_detail.set('Ready. Detected labels will appear during analysis.')
                    self.progress['value'] = 0
                    self.search_var.set('')
                    self.source_var.set(f'{media.name}   ·   {media.width} × {media.height}   ·   {media.fps:g} fps')
                    self.seek.configure(to=max(0, media.duration - 1/media.fps))
                    self.seek.set(0)
                    self.full_range()
                    self._set_frame(image)
                    self.show('workspace')
                    self.status.set('Recording loaded. Scrub to a frame, choose your range, then analyze.')
                    if getattr(self, 'queue_review', None):
                        self.apply_queue_review()
                    else:
                        self.load_edl(automatic=True)
                elif kind == 'edl':
                    self.receive_edl(data)
                elif kind == 'scan':
                    self.state.clips, self.state.completed = data
                    self.exported = not bool(self.state.clips)
                    self.exported_ids.clear()
                    self.filter_results()
                    self.table.selection_set(self.table.get_children())
                    total = sum(c.duration for c in self.state.clips)
                    prefix = '' if self.state.completed else 'Partial results · '
                    self.results_summary.configure(text=f'{prefix}{len(self.state.clips)} highlights  /  {clock(total)}')
                    self.live_count.set(f"{len(self.state.clips)} highlight{'s' if len(self.state.clips) != 1 else ''}")
                    self.live_detail.set('Analysis complete. Review and export your highlights.' if self.state.completed else 'Stopped. Your partial results are ready to review.')
                    if self.state.completed:
                        self.progress['value'] = 100
                    if self.prefs.chime:
                        self.bell()
                    self.status.set(('Scan finished. Select highlights to export.' if self.state.completed else 'Scan stopped. Partial highlights are ready to export.') if self.state.clips else 'No highlights found in this range. Check the preset, its region, or try another section.')
                    self.show('results')
                elif kind == 'render':
                    complete = len(data) == len(self.render_ids)
                    self.status.set(f'{"Export complete" if complete else "Export stopped"} · {len(data)} of {len(self.render_ids)} files saved.')
                    self.show('results')
                elif kind == 'export':
                    self.exported_ids.update(self.exporting_ids)
                    self.exported = len(self.exported_ids) == len(self.state.clips)
                    self.status.set(f'Export complete · {data}')
                    self.refresh_library()
                    if self.export_kind == 'edl':
                        if self.exported:
                            self.load_edl(data, automatic=True)
                        else:
                            if data not in self.edl_choices:
                                self.edl_choices.insert(0, data)
                                self.edl_selector.configure(values=self.edl_choices)
                            self.edl_note.set('Selected highlights saved to EDL; remaining unsaved highlights are still shown.')
                elif kind == 'updates':
                    message, url = data
                    self.status.set(message)
                    if messagebox.askyesno('Software updates', message + '\n\nOpen the official releases page?', parent=self):
                        import webbrowser
                        webbrowser.open(url)
                elif kind == 'environment':
                    self._environment_dialog(data)
                self._update_controls()
        except Empty:
            pass
        self.poll_timer = self.after(75, self._poll)

    def step(self, amount, *, frames=False):
        if not self.state.media or self.working:
            return
        delta = amount / self.state.media.fps if frames else amount
        position = min(max(0, self.state.position + delta),
                       self.state.media.duration - 1 / self.state.media.fps)
        self.seek.set(position)
        self._seek_changed(position)

    def focus_search(self, event=None):
        self.show('results')
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, 'end')
        return 'break'

    def select_all_results(self, event=None):
        self.table.selection_set(self.table.get_children())
        return 'break'

    def reset_result_filters(self):
        self.search_var.set('')
        self.kill_filter.set('all')
        self.keep_unknown.set(True)

    @staticmethod
    def kill_type(clip):
        return {True: 'Real player', False: 'Bot', None: 'Undetermined'}[clip.traits.get('real-player')]

    def filter_results(self):
        selected = set(self.table.selection())
        self.table.delete(*self.table.get_children())
        query = self.search_var.get().strip().casefold()
        mode = self.kill_filter.get() if self.state.player_traits else 'all'
        self.table.configure(displaycolumns=('player', 'type', 'in', 'out', 'duration') if self.state.player_traits else ('player', 'in', 'out', 'duration'))
        if self.state.player_traits:
            self.unknown_check.pack(anchor='w', pady=(8, 0), before=self.filter_hint_label)
            self.trait_filters.pack(fill='x', pady=(12, 0), before=self.unknown_check)
        else:
            self.trait_filters.pack_forget()
            self.unknown_check.pack_forget()
        for key, button in self.filter_buttons.items():
            button.state(['selected'] if key == mode else ['!selected'])
        self.unknown_check.state(['!disabled'] if mode in ('real-player', 'bot') else ['disabled'])
        column, reverse = self.result_sort
        keys = {'type': lambda pair: self.kill_type(pair[1]), 'player': lambda pair: pair[1].name.casefold(), 'in': lambda pair: pair[1].start,
                'out': lambda pair: pair[1].end, 'duration': lambda pair: pair[1].duration}
        row = 0
        for i, clip in sorted(enumerate(self.state.clips), key=keys[column], reverse=reverse):
            if query and query not in clip.name.casefold():
                continue
            if mode == 'unknown' and clip.traits.get('real-player') is not None:
                continue
            if mode in ('real-player', 'bot') and not traits.matches(clip, require=(mode,), keep_unknown=self.keep_unknown.get()):
                continue
            self.table.insert('', 'end', iid=str(i),
                              values=(clip.name, self.kill_type(clip), clock(clip.start), clock(clip.end), f'{clip.duration:.2f}s'),
                              tags=('alternate',) if row % 2 else ())
            row += 1
            if str(i) in selected:
                self.table.selection_add(str(i))
        self.filter_hint.set('No matching highlights. Try another filter or reset filters.' if self.state.clips and not row
                             else 'Undetermined = insufficient evidence. Mixed clips count as real player if any kill is confirmed.')
        if not self.state.player_traits:
            self.filter_hint.set(f'Analyzed with {self.state.preset_name}. Search or select events to export.')
        self._update_controls()

    def sort_results(self, column):
        previous, descending = self.result_sort
        self.result_sort = (column, not descending if column == previous else False)
        for name, title in [('player', 'LABEL / MOMENT'), ('type', 'KILL TYPE'), ('in', 'IN'), ('out', 'OUT'), ('duration', 'DURATION')]:
            arrow = (' ↓' if self.result_sort[1] else ' ↑') if name == column else ''
            self.table.heading(name, text=title + arrow)
        self.filter_results()

    def copy_selection(self):
        clips = [self.state.clips[int(i)] for i in sorted(self.table.selection(), key=int)]
        if not clips:
            return
        self.clipboard_clear()
        self.clipboard_append(export.format_timestamps(clips))
        self.status.set(f'Copied {len(clips)} highlight timestamps to the clipboard.')

    def describe_live(self, event=None):
        selection = self.live_table.selection()
        if selection:
            self.live_player.set(self.state.clips[int(selection[0])].name)

    def preview_live(self, event=None):
        selection = self.live_table.selection()
        if selection and not self.working:
            self.reset_result_filters()
            self.table.selection_set(selection[0])
            self.preview_result()

    def preview_result(self):
        if not self.table.selection() or self.working:
            return
        clip = self.state.clips[int(self.table.selection()[0])]
        self.show('workspace')
        self.seek.set(clip.start)
        self._seek_changed(clip.start)

    def export_selection(self, kind):
        if not self.table.selection() or self.working:
            return
        clips = [self.state.clips[int(i)] for i in sorted(self.table.selection(), key=int)]
        media = self.state.media
        if kind == 'mp4':
            target = filedialog.askdirectory(parent=self, title='Save rendered highlights', initialdir=self._folder('detect', 'clips_output_dir'))
            if not target:
                return
            existing = [Path(target) / f'{Path(media.path).stem}_highlight_{i:03}.mp4' for i in range(1, len(clips)+1)]
            if any(p.exists() for p in existing) and not messagebox.askyesno('Replace MP4 files?', 'Some numbered highlights already exist in this folder. Replace them?', parent=self):
                return
        else:
            suffix = '_highlights.edl' if kind == 'edl' else '_timestamps.txt'
            folder = self._folder('export', 'output_dir') if kind == 'edl' else self._folder('detect', 'timestamps_dir')
            if kind == 'edl' and self.edl_path:
                folder = str(Path(self.edl_path).parent)
            target = filedialog.asksaveasfilename(parent=self, title='Export selected highlights', initialdir=folder,
                                                 initialfile=Path(self.edl_path).name if kind == 'edl' and self.edl_path else Path(media.path).stem + suffix, defaultextension=Path(suffix).suffix)
            if not target:
                return
        sequence = self.saved_values['export', 'name']
        fps = config.section(self.cfg, 'export').get('fps')
        def save():
            if kind == 'mp4':
                return outputs.render_clips(media.path, clips, target,
                    cancelled=self.jobs.cancel.is_set,
                    progress=lambda *args: self.jobs.events.put(('render_progress', args, None)))
            else:
                outputs.validate_paths([media.path], [target])
                if kind == 'edl':
                    plan = export.plan(media.path, clips, name=sequence, fps_override=fps, output=target)
                    export.write_edl(plan)
                else:
                    outputs.atomic_text(target, export.format_timestamps(clips))
            return target
        self.export_kind = kind
        self.exporting_ids = set(self.table.selection())
        self.render_ids = sorted(self.exporting_ids, key=int)
        job = 'render' if kind == 'mp4' else 'export'
        if kind == 'mp4':
            self.show('workspace')
            self.progress['value'] = 0
        self._begin(job, 'Exporting selected highlights… Press Escape or Stop to cancel MP4 rendering.')
        self.jobs.submit(job, save)

    def check_updates(self):
        if self.working:
            return
        from . import updates
        self._begin('updates', 'Checking official releases…')
        self.jobs.submit('updates', updates.check)

    def check_environment(self):
        if self.working:
            return
        self._begin('environment', 'Checking local dependencies…')
        self.jobs.submit('environment', environment.check, self._folder('detect', 'clips_dir'), self.config_path)

    def _environment_dialog(self, checks):
        import shutil
        dialog = tk.Toplevel(self)
        dialog.title('Environment · Killcutter')
        dialog.configure(bg=t.BG)
        dialog.geometry('720x500')
        dialog.transient(self)
        from .playback import library_path
        import ctypes
        try:
            ctypes.CDLL(library_path())
            playback_ok = True
        except OSError:
            playback_ok = False
        checks.append(environment.Check('Audio/video playback', playback_ok, 'libmpv available' if playback_ok else 'Install libmpv or set KILLCUTTER_MPV to its library path', required=False))
        checks.append(environment.Check('FFmpeg', bool(shutil.which('ffmpeg')), shutil.which('ffmpeg') or 'Not found · required for MP4 rendering and audio detection', required=False))
        text = tk.Text(dialog, bg=t.CARD, fg=t.INK, relief='flat', padx=20, pady=20, wrap='word', font=(self.family, 11))
        scrollbar = ttk.Scrollbar(dialog, command=text.yview)
        scrollbar.pack(side='right', fill='y')
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(fill='both', expand=True, padx=16, pady=16)
        for check in checks:
            text.insert('end', f'{"✓" if check.ok else "!"}  {check.name}\n{check.detail}\n{check.fix}\n\n')
        text.configure(state='disabled')
        ttk.Button(dialog, text='Done', command=dialog.destroy).pack(pady=(0, 16))
        dialog.bind('<Escape>', lambda _: dialog.destroy())

    # ----- appearance, session and recents -------------------------------

    def _widgets(self, kind, parent=None):
        """Every descendant of ``parent`` that is an instance of ``kind``."""
        found = []
        for child in (parent or self).winfo_children():
            if isinstance(child, kind):
                found.append(child)
            found.extend(self._widgets(kind, child))
        return found

    def apply_appearance(self, *, persist=True):
        """Restyle the live window from the appearance controls."""
        before = t.colors()
        try:
            scale = round(float(self.scale_var.get()), 2)
        except (tk.TclError, ValueError):
            scale = self.prefs.scale
        self.prefs = replace(self.prefs, theme=self.theme_var.get(), accent=self.accent_var.get(),
                             scale=scale, chime=bool(self.chime_var.get()))
        t.configure(*self.prefs.appearance)
        self.family = t.apply(self)
        mapping = {old: new for old, new in zip(before.values(), t.colors().values()) if old != new}
        self.configure(bg=t.BG)
        t.recolor(self, mapping, self.family)
        for card in self._widgets(Card):
            card.refresh()
        for preview in self._widgets(Preview):
            preview.refresh()
        self._draw_brand()
        self.rail_card.configure(width=t.px(214))
        self.minsize(t.px(940), t.px(660))
        self.table.tag_configure('alternate', background=t.ALTERNATE)
        self.filter_results()
        self._mark_appearance()
        self.scale_label.configure(text=f'{self.prefs.scale:.0%}')
        if persist:
            self._save_preferences()
            self.status.set(f'Appearance saved · {self.prefs.theme} · {self.prefs.scale:.0%}')

    def _mark_appearance(self):
        """Show which theme and accent are active."""
        for name, button in self.theme_buttons.items():
            button.configure(style='CardPrimary.TButton' if name == self.prefs.theme else 'TButton')
        for color, swatch in self.accent_swatches.items():
            swatch.configure(highlightbackground=t.INK if color == self.prefs.accent else t.CARD,
                             width=t.px(30), height=t.px(30))

    def choose_accent(self):
        from tkinter import colorchooser
        chosen = colorchooser.askcolor(color=self.accent_var.get(), parent=self, title='Accent colour')[1]
        if chosen:
            self.accent_var.set(chosen.upper())
            self.apply_appearance()

    def reset_appearance(self):
        defaults = preferences.Preferences()
        self.theme_var.set(defaults.theme)
        self.accent_var.set(defaults.accent)
        self.scale_var.set(defaults.scale)
        self.chime_var.set(defaults.chime)
        self.apply_appearance()

    def _save_preferences(self):
        try:
            preferences.save(self.config_path, self.prefs)
            self.cfg, _ = config.load(self.config_path)
        except Exception as exc:
            self.status.set(f'Could not save preferences: {exc}')

    def show_recents(self):
        menu = self.recent_menu()
        menu.tk_popup(self.recent_button.winfo_rootx(),
                      self.recent_button.winfo_rooty() + self.recent_button.winfo_height())

    def recent_menu(self):
        menu = tk.Menu(self, tearoff=0, bg=t.CARD, fg=t.INK, activebackground=t.SELECTED,
                       activeforeground=t.INK, bd=0, activeborderwidth=0)
        if not self.prefs.recents:
            menu.add_command(label='No recent recordings yet', state='disabled')
        for path in self.prefs.recents:
            exists = Path(path).is_file()
            menu.add_command(label=Path(path).name if exists else f'{Path(path).name}  (missing)',
                             state='normal' if exists and not self.working else 'disabled',
                             command=lambda p=path: self.open_file(p))
        menu.add_separator()
        menu.add_command(label='Clear list', command=self.clear_recents,
                         state='normal' if self.prefs.recents else 'disabled')
        return menu

    def clear_recents(self):
        self.prefs = replace(self.prefs, recents=())
        self._save_preferences()
        self.status.set('Recent recordings cleared.')

    def show_shortcuts(self):
        rows = [('Space', 'Play or pause video with audio (Recording)'), ('Ctrl+O', 'Open a recording'), ('Ctrl+Enter', 'Analyze the selected range'),
                ('Esc', 'Stop analysis, keeping partial results'),
                ('Ctrl+1 … Ctrl+4', 'Recording / Highlights / Presets / Settings'),
                ('Ctrl+F', 'Search highlights by label'),
                ('Ctrl+A', 'Select all visible highlights (in the table)'),
                ('Enter', 'Preview the selected highlight'),
                ('F2', 'Rename the selected highlight'),
                ('Delete', 'Remove the selected highlights'),
                ('Ctrl+Z', 'Undo the last removal'),
                ('Ctrl+C', 'Copy selected timestamps'),
                ('F1', 'This list')]
        dialog = tk.Toplevel(self)
        dialog.title('Keyboard shortcuts · Killcutter')
        dialog.configure(bg=t.BG)
        dialog.transient(self)
        card = Card(dialog)
        card.pack(fill='both', expand=True, padx=16, pady=16)
        label(card.content, 'Keyboard shortcuts', size=18, bold=True).pack(anchor='w', pady=(0, 14))
        for keys, description in rows:
            row = tk.Frame(card.content, bg=t.CARD)
            row.pack(fill='x', pady=3)
            label(row, keys, color=t.ACCENT, width=18).pack(side='left')
            label(row, description, color=t.MUTED).pack(side='left')
        ttk.Button(card.content, text='Done', command=dialog.destroy).pack(anchor='w', pady=(16, 0))
        dialog.bind('<Escape>', lambda _: dialog.destroy())
        dialog.update_idletasks()
        dialog.geometry(f'+{self.winfo_rootx()+80}+{self.winfo_rooty()+70}')

    # ----- editing the highlight list ------------------------------------

    def _selected_indexes(self):
        return sorted(int(i) for i in self.table.selection())

    def _relabel(self, keep):
        """Keep export bookkeeping aligned after the clip list is re-indexed."""
        self.exported_ids = {str(new) for new, old in enumerate(keep) if str(old) in self.exported_ids}

    def remove_selected(self, event=None):
        if self.working or not self.table.selection():
            return 'break'
        doomed = self._selected_indexes()
        self.removed = [(i, self.state.clips[i]) for i in doomed]
        keep = [i for i in range(len(self.state.clips)) if i not in set(doomed)]
        self._relabel(keep)
        self.state.clips = [self.state.clips[i] for i in keep]
        self.exported = not self.state.clips or self.exported_ids == {str(i) for i in range(len(self.state.clips))}
        self._after_edit(f"Removed {len(doomed)} highlight{'s' if len(doomed) != 1 else ''}. Ctrl+Z restores them.")
        return 'break'

    def undo_remove(self):
        if self.working or not self.removed:
            return
        clips = list(self.state.clips)
        for index, clip in self.removed:
            clips.insert(min(index, len(clips)), clip)
        self.state.clips = clips
        self.exported_ids.clear()
        self.exported = False
        restored = len(self.removed)
        self.removed = []
        self._after_edit(f"Restored {restored} highlight{'s' if restored != 1 else ''}.")

    def rename_selected(self, event=None):
        from tkinter import simpledialog
        selection = self._selected_indexes()
        if self.working or not selection:
            return 'break'
        clip = self.state.clips[selection[0]]
        name = simpledialog.askstring('Rename highlight', 'Player or moment:', initialvalue=clip.name, parent=self)
        if name and name.strip():
            clip.name = name.strip()
            self.exported_ids.discard(str(selection[0]))
            self.exported = False
            self._after_edit(f'Renamed to {clip.name}.')
        return 'break'

    def adjust_selected(self, seconds, *, edge):
        """Nudge the in or out point of every selected highlight."""
        selection = self._selected_indexes()
        if self.working or not selection or not self.state.media:
            return
        limit = self.state.media.duration
        for index in selection:
            clip = self.state.clips[index]
            if edge == 'start':
                clip.start = min(max(0, clip.start + seconds), clip.end - .1)
            else:
                clip.end = max(min(limit, clip.end + seconds), clip.start + .1)
            self.exported_ids.discard(str(index))
        self.exported = False
        self._after_edit(f"{'Start' if edge == 'start' else 'End'} nudged {seconds:+g}s on {len(selection)} highlight(s).")

    def _after_edit(self, message):
        keep = set(self.table.selection())
        self._sync_live()
        self.filter_results()
        for iid in keep:
            if self.table.exists(iid):
                self.table.selection_add(iid)
        total = sum(c.duration for c in self.state.clips)
        prefix = '' if self.state.completed else 'Partial results · '
        self.results_summary.configure(text=f'{prefix}{len(self.state.clips)} highlights  /  {clock(total)}'
                                       if self.state.clips else 'No highlights')
        self.status.set(message)

    def _sync_live(self):
        """Rebuild the live list so its rows keep matching the clip indexes."""
        self.live_table.delete(*self.live_table.get_children())
        for index, clip in enumerate(self.state.clips):
            self.live_table.insert('', 'end', iid=str(index), text=clock(clip.start).split('.')[0], values=(clip.name,))
        self.live_count.set(f"{len(self.state.clips)} highlight{'s' if len(self.state.clips) != 1 else ''}")

    def error(self, title, message):
        self.status.set(message)
        messagebox.showerror(title, message, parent=self)

    def close(self):
        if self.player:
            self.stop_playback()
            self.after(100, self.close)
            return
        if self.working:
            if self.working in ('scan', 'render', 'batch'):
                if messagebox.askyesno('Stop current operation?', 'Stop and keep this window open to review completed work?', parent=self):
                    self.stop_scan()
            else:
                messagebox.showinfo('Work in progress', 'Wait for the current operation to finish before closing.', parent=self)
            return
        if self.state.clips and not self.exported and not messagebox.askyesno('Close without exporting?', 'Your highlights have not been exported. Close this workspace?', parent=self):
            return
        self.prefs = replace(self.prefs, geometry=self.winfo_geometry(), page=self.current_page)
        self._save_preferences()
        if self.seek_timer:
            self.after_cancel(self.seek_timer)
        self.after_cancel(self.library_tick)
        self.after_cancel(self.poll_timer)
        self.jobs.close()
        self.destroy()
