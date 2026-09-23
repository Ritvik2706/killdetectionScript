"""Desktop shell and workflows. All widget access stays on the Tk thread."""
from pathlib import Path
from queue import Empty
import json
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from killcutter import config, constants, detection, environment, export, outputs
from killcutter.ranges import parse_timestamp, resolve_range
from . import theme as t
from .services import Jobs, analyze, open_media
from .state import Workspace
from .widgets import Card, label
from .views import Views


def clock(seconds):
    hours, rest = divmod(max(0, seconds), 3600)
    minutes, seconds = divmod(rest, 60)
    return f'{int(hours):02}:{int(minutes):02}:{seconds:06.3f}'


class Application(Views, tk.Tk):
    def __init__(self, *, config_path=None):
        super().__init__()
        self.withdraw()
        self.title('Killcutter Studio')
        self.configure(bg=t.BG)
        self.family = t.apply(self)
        self.minsize(980, 680)
        width, height = min(1360, self.winfo_screenwidth()-60), min(880, self.winfo_screenheight()-80)
        self.geometry(f'{max(980, width)}x{max(680, height)}')
        self.cfg, loaded_path = config.load(config_path)
        self.config_path = loaded_path or config_path or config.user_config_path()
        self.state = Workspace()
        self.jobs = Jobs()
        self.working = None
        self.generation = 0
        self.seek_timer = None
        self.frame_time = 0
        self.sample = None
        self.exported = True
        self.exported_ids = set()
        self.exporting_ids = set()
        self.analysis_title = tk.StringVar(value='Ready to analyze.')
        self.live_player = tk.StringVar(value='Waiting for detections')
        self.live_count = tk.StringVar(value='0 highlights')
        self.live_detail = tk.StringVar(value='Player names and moments appear here as they are detected.')
        self.follow_scan = tk.BooleanVar(value=True)
        self.search_var = tk.StringVar()
        self.selected_var = tk.StringVar(value='No highlights selected')
        self.result_sort = ('in', False)
        self.last_follow = 0
        self.scan_started = 0
        self.scan_position = 0
        self.status = tk.StringVar(value='Ready when you are. Open a recording to get started.')
        self.start_var = tk.StringVar(value='00:00:00.000')
        self.end_var = tk.StringVar(value='00:00:00.000')
        self.position_var = tk.StringVar(value='00:00:00.000')
        self.source_var = tk.StringVar(value='No recording loaded')
        self.selection_var = tk.StringVar(value='Choose your in and out points')
        self._build_shell()
        self._build_workspace()
        self._build_results()
        self._build_inspector()
        self._build_settings()
        self.saved_values = {key: variable.get() for key, variable in self.setting_vars.items()}
        self.show('workspace')
        self.start_var.trace_add('write', lambda *_: self._range_summary())
        self.end_var.trace_add('write', lambda *_: self._range_summary())
        self.search_var.trace_add('write', lambda *_: self.filter_results())
        self.bind('<Control-o>', lambda _: self.open_file())
        self.bind('<Control-Return>', lambda _: self.start_scan())
        self.bind('<Control-f>', self.focus_search)
        self.bind('<Escape>', lambda _: self.stop_scan() if self.working == 'scan' else None)
        for number, page in enumerate(('workspace', 'results', 'inspector', 'settings'), 1):
            self.bind(f'<Control-Key-{number}>', lambda _, p=page: self.show(p))
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.poll_timer = self.after(75, self._poll)
        self._update_controls()
        self.deiconify()

    def _build_shell(self):
        rail_card = Card(self, padding=8, color=t.SIDEBAR, width=206)
        rail_card.pack(side='left', fill='y', padx=(12, 0), pady=12)
        rail_card.pack_propagate(False)
        rail = rail_card.content
        brand = tk.Canvas(rail, width=42, height=42, bg=t.SIDEBAR, highlightthickness=0)
        brand.pack(anchor='w', padx=22, pady=(26, 12))
        brand.create_rectangle(2, 2, 40, 40, fill=t.ACCENT, outline='')
        brand.create_polygon(14, 10, 14, 32, 31, 21, fill='white')
        label(rail, 'Killcutter', size=21, bold=True).pack(anchor='w', padx=22)
        label(rail, 'S T U D I O', size=9, color=t.MUTED).pack(anchor='w', padx=24, pady=(4, 32))
        label(rail, 'WORKSPACE', size=9, color=t.MUTED, bold=True).pack(anchor='w', padx=24, pady=(0, 10))
        self.nav = {}
        self.pages = {}
        for key, title in [('workspace', '01   Recording'), ('results', '02   Highlights'),
                           ('inspector', '03   Frame inspector'), ('settings', '04   Settings')]:
            button = ttk.Button(rail, text=title, style='Nav.TButton', command=lambda k=key: self.show(k))
            button.pack(fill='x', padx=2, pady=3)
            self.nav[key] = button
        label(rail, 'LOCAL PROCESSING\nYour footage stays yours.\n\nCtrl+O  Open recording\nCtrl+Enter  Analyze\nEsc  Stop analysis', size=9, color=t.MUTED,
              justify='left').pack(side='bottom', anchor='w', padx=22, pady=26)
        main = tk.Frame(self, bg=t.BG)
        main.pack(side='left', fill='both', expand=True, padx=26, pady=(22, 14))
        self.header = tk.Frame(main, bg=t.BG)
        self.header.pack(fill='x', pady=(0, 22))
        self.open_button = ttk.Button(self.header, text='Open recording   ↗', style='Primary.TButton', command=self.open_file)
        self.open_button.pack(side='right', padx=(16, 0))
        self.heading = label(self.header, '', size=26, bold=True)
        self.heading.pack(anchor='w')
        self.subtitle = label(self.header, '', color=t.MUTED)
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

    def _header_resize(self, event):
        available = max(180, event.width - self.open_button.winfo_reqwidth() - 30)
        self.heading.configure(wraplength=available, justify='left')
        self.subtitle.configure(wraplength=available, justify='left')

    def _page(self, key):
        page = tk.Frame(self.host, bg=t.BG)
        page.grid(row=0, column=0, sticky='nsew')
        self.pages[key] = page
        return page

    def show(self, key):
        titles = {
            'workspace': ('Recording', 'Select a recording. Set your range. Find the highlights.'),
            'results': ('Your highlights.', 'Review your detections and export the moments worth keeping.'),
            'inspector': ('A closer look.', 'Inspect source pixels precisely. Build your next detection profile.'),
            'settings': ('Make it yours.', 'Saved defaults for your workflow, folders, and detection.'),
        }
        self.current_page = key
        self.heading.configure(text=titles[key][0])
        self.subtitle.configure(text=titles[key][1])
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
        settings = detection.DetectionSettings(region=constants.DEFAULT_REGION, **values)
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
            self.saved_values = {key: variable.get().strip() for key, variable in self.setting_vars.items()}
            self.status.set('Settings saved. Your next scan will use these defaults.')
        except Exception as exc:
            self.error('Could not save settings', str(exc))

    def open_file(self, path=None):
        if self.working:
            return
        if self.state.clips and not self.exported and not messagebox.askyesno('Open another recording?', 'Current highlights have not been exported. Replace this workspace?', parent=self):
            return
        path = path or filedialog.askopenfilename(parent=self, title='Open recording',
                                                  initialdir=self._folder('detect', 'clips_dir'),
                                                  filetypes=[('Video recordings', '*.mp4 *.mkv *.mov *.avi *.webm *.m4v'), ('All files', '*')])
        if not path:
            return
        if self.seek_timer:
            self.after_cancel(self.seek_timer)
            self.seek_timer = None
        self.generation += 1
        self._begin('open', 'Opening recording…')
        self.jobs.submit('open', open_media, str(Path(path).resolve()))

    def _begin(self, kind, message):
        self.working = kind
        self.status.set(message)
        self._update_controls()

    def _update_controls(self):
        busy, loaded = bool(self.working), self.state.media is not None
        self.open_button.state(['disabled'] if busy else ['!disabled'])
        self.scan_button.state(['!disabled'] if loaded and not busy else ['disabled'])
        self.cancel_button.state(['!disabled'] if self.working == 'scan' else ['disabled'])
        self.seek.state(['!disabled'] if loaded and not busy else ['disabled'])
        self.save_sample_button.state(['!disabled'] if self.sample and not busy else ['disabled'])
        selected = [self.state.clips[int(i)] for i in self.table.selection() if int(i) < len(self.state.clips)]
        self.selected_var.set(f'{len(self.table.get_children())} shown · {len(selected)} selected  ·  {clock(sum(c.duration for c in selected))} total duration')
        for index, button in enumerate(self.result_buttons):
            has_rows = bool(self.table.get_children() if index == 0 else self.table.selection())
            button.state(['!disabled'] if has_rows and not busy else ['disabled'])

    def _seek_changed(self, value):
        if not self.state.media or self.working:
            return
        seconds = float(value)
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
        self.state.clips = []
        self.state.completed = False
        self.exported_ids.clear()
        self.exported = True
        self.table.delete(*self.table.get_children())
        self.live_table.delete(*self.live_table.get_children())
        self.search_var.set('')
        self.live_count.set('0 highlights')
        self.live_player.set('Waiting for detections')
        self.analysis_title.set('Analyzing…')
        self.live_detail.set('Looking for the ENEMY DOWNED banner…')
        self.results_summary.configure(text='Analysis in progress')
        self.scan_started = time.monotonic()
        self.scan_position = start
        self.last_follow = 0
        self.show('workspace')
        self.progress['value'] = 0
        self._begin('scan', 'Analyzing locally… You can stop and keep partial results.')
        self.jobs.submit('scan', analyze, self.jobs, self.state.media, settings, start, end,
                         config.section(self.cfg, "detect").get("region"))

    def stop_scan(self):
        if self.working != 'scan':
            return
        self.jobs.cancel.set()
        self.status.set('Stopping after the current sample… Your detected highlights will be kept.')
        self.cancel_button.state(['disabled'])

    def _set_frame(self, image):
        self.preview.set_image(image)
        self.inspector.set_image(image)
        self.frame_time = self.state.position
        self.sample = None
        self.pixel_info.configure(text='No pixel selected')
        self._update_controls()

    def _poll(self):
        try:
            for _ in range(100):
                kind, data, error = self.jobs.events.get_nowait()
                if isinstance(kind, tuple):
                    if kind[1] == self.generation:
                        if error:
                            self.status.set(error)
                        else:
                            self.state.position = kind[2]
                            self.position_var.set(clock(kind[2]))
                            self._set_frame(data)
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
                    self.exported = True
                    self.exported_ids.clear()
                    self.table.delete(*self.table.get_children())
                    self.results_summary.configure(text='No highlights yet')
                    self.live_table.delete(*self.live_table.get_children())
                    self.live_count.set('0 highlights')
                    self.live_player.set('Waiting for detections')
                    self.analysis_title.set('Ready to analyze.')
                    self.live_detail.set('Ready. Player names will appear during analysis.')
                    self.progress['value'] = 0
                    self.search_var.set('')
                    self.source_var.set(f'{media.name}   ·   {media.width} × {media.height}   ·   {media.fps:g} fps')
                    self.seek.configure(to=max(0, media.duration - 1/media.fps))
                    self.seek.set(0)
                    self.full_range()
                    self._set_frame(image)
                    self.show('workspace')
                    self.status.set('Recording loaded. Scrub to a frame, choose your range, then analyze.')
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
                    self.status.set(('Scan finished. Select highlights to export.' if self.state.completed else 'Scan stopped. Partial highlights are ready to export.') if self.state.clips else 'No highlights found in this range. Check the HUD layout or try another section.')
                    self.show('results')
                elif kind == 'export':
                    self.exported_ids.update(self.exporting_ids)
                    self.exported = len(self.exported_ids) == len(self.state.clips)
                    self.status.set(f'Export complete · {data}')
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

    def filter_results(self):
        selected = set(self.table.selection())
        self.table.delete(*self.table.get_children())
        query = self.search_var.get().strip().casefold()
        column, reverse = self.result_sort
        keys = {'player': lambda pair: pair[1].name.casefold(), 'in': lambda pair: pair[1].start,
                'out': lambda pair: pair[1].end, 'duration': lambda pair: pair[1].duration}
        for row, (i, clip) in enumerate(sorted(enumerate(self.state.clips), key=keys[column], reverse=reverse)):
            if query and query not in clip.name.casefold():
                continue
            self.table.insert('', 'end', iid=str(i),
                              values=(clip.name, clock(clip.start), clock(clip.end), f'{clip.duration:.2f}s'),
                              tags=('alternate',) if row % 2 else ())
            if str(i) in selected:
                self.table.selection_add(str(i))
        self._update_controls()

    def sort_results(self, column):
        previous, descending = self.result_sort
        self.result_sort = (column, not descending if column == previous else False)
        for name, title in [('player', 'PLAYER / MOMENT'), ('in', 'IN'), ('out', 'OUT'), ('duration', 'DURATION')]:
            arrow = (' ↓' if self.result_sort[1] else ' ↑') if name == column else ''
            self.table.heading(name, text=title + arrow)
        self.filter_results()

    def copy_selection(self):
        clips = [self.state.clips[int(i)] for i in sorted(self.table.selection(), key=int)]
        if not clips:
            return
        self.clipboard_clear()
        self.clipboard_append(''.join(f'{c.start:.3f} {c.end:.3f} {c.name}\n' for c in clips))
        self.status.set(f'Copied {len(clips)} highlight timestamps to the clipboard.')

    def describe_live(self, event=None):
        selection = self.live_table.selection()
        if selection:
            self.live_player.set(self.state.clips[int(selection[0])].name)

    def preview_live(self, event=None):
        selection = self.live_table.selection()
        if selection and not self.working:
            self.search_var.set('')
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
            target = filedialog.asksaveasfilename(parent=self, title='Export selected highlights', initialdir=folder,
                                                 initialfile=Path(media.path).stem + suffix, defaultextension=Path(suffix).suffix)
            if not target:
                return
        sequence = self.saved_values['export', 'name']
        fps = config.section(self.cfg, 'export').get('fps')
        def save():
            if kind == 'mp4':
                outputs.render_clips(media.path, clips, target)
            else:
                outputs.validate_paths([media.path], [target])
                if kind == 'edl':
                    plan = export.plan(media.path, clips, name=sequence, fps_override=fps, output=target)
                    export.write_edl(plan)
                else:
                    outputs.atomic_text(target, ''.join(f'{c.start:.3f} {c.end:.3f} {c.name}\n' for c in clips))
            return target
        self.exporting_ids = set(self.table.selection())
        self._begin('export', 'Exporting selected highlights… MP4 encoding can take a while.')
        self.jobs.submit('export', save)

    def inspect_pixel(self, x, y, rgb):
        if not self.state.media:
            return
        self.sample = {'version': 1, 'source': self.state.media.path, 'time_seconds': self.frame_time,
                       'frame_width': self.state.media.width, 'frame_height': self.state.media.height,
                       'x': x, 'y': y, 'rgb': list(rgb)}
        self.pixel_info.configure(text=f'X {x}   /   Y {y}     ·     RGB {rgb[0]}, {rgb[1]}, {rgb[2]}')
        self._update_controls()

    def save_sample(self):
        if not self.sample:
            return
        path = filedialog.asksaveasfilename(parent=self, title='Save pixel sample', defaultextension='.json', initialfile='pixel-sample.json')
        if path:
            try:
                outputs.validate_paths([self.state.media.path], [path])
                outputs.atomic_text(path, json.dumps(self.sample, indent=2) + '\n')
                self.status.set(f'Pixel sample saved · {path}')
            except Exception as exc:
                self.error('Could not save sample', str(exc))

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
        checks.append(environment.Check('FFmpeg', bool(shutil.which('ffmpeg')), shutil.which('ffmpeg') or 'Not found · required only for MP4 rendering', required=False))
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

    def error(self, title, message):
        self.status.set(message)
        messagebox.showerror(title, message, parent=self)

    def close(self):
        if self.working:
            if self.working == 'scan':
                if messagebox.askyesno('Stop analysis?', 'Stop the scan and keep this window open to review partial highlights?', parent=self):
                    self.stop_scan()
            else:
                messagebox.showinfo('Work in progress', 'Wait for the current operation to finish before closing.', parent=self)
            return
        if self.state.clips and not self.exported and not messagebox.askyesno('Close without exporting?', 'Your highlights have not been exported. Close this workspace?', parent=self):
            return
        if self.seek_timer:
            self.after_cancel(self.seek_timer)
        self.after_cancel(self.poll_timer)
        self.jobs.close()
        self.destroy()
