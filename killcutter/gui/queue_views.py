"""Reviewable analysis queue, independent of the current recording workspace."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from killcutter import config
from .batch import analyze_queued
from .widgets import RoundedTreeview, label
from . import theme as t


class QueueViews:
    def init_queue(self):
        self.analysis_queue = []
        self.queue_running = False
        self.queue_stop_requested = False
        self.queue_window = None
        self.queue_active = None

    def enqueue_recordings(self):
        paths = self.library_table.selection()
        if not paths:
            return
        existing = {r['path'] for r in self.analysis_queue if r['status'] in ('Pending', 'Analyzing')}
        for path in paths:
            if path not in existing:
                self.analysis_queue.append({'path': path, 'status': 'Pending', 'result': None})
                existing.add(path)
        self.close_recording_picker()
        self.show_analysis_queue()

    def show_analysis_queue(self):
        if self.queue_window is not None and self.queue_window.winfo_exists():
            self.queue_window.lift()
            self.render_queue()
            return
        dialog = self.queue_window = tk.Toplevel(self)
        dialog.title('Analysis queue · Killcutter')
        dialog.configure(bg=t.CARD)
        dialog.geometry('880x520')
        dialog.minsize(660, 400)
        dialog.transient(self)
        label(dialog, 'Analysis queue', size=22, bold=True).pack(anchor='w', padx=20, pady=(20, 6))
        self.queue_description = tk.StringVar()
        label(dialog, textvariable=self.queue_description, color=t.MUTED, wraplength=800, justify='left').pack(anchor='w', padx=20, pady=(0, 12))
        self.queue_table = RoundedTreeview(dialog, columns=('video', 'status'), show='headings', selectmode='extended')
        self.queue_table.heading('video', text='VIDEO')
        self.queue_table.heading('status', text='STATUS')
        self.queue_table.column('video', width=500)
        self.queue_table.column('status', width=170)
        self.queue_table.pack(fill='both', expand=True, padx=20)
        self.queue_detail = tk.StringVar(value='Select a row for saved files or error details.')
        label(dialog, textvariable=self.queue_detail, color=t.MUTED, wraplength=800, justify='left').pack(fill='x', padx=20, pady=10)
        self.queue_table.bind('<<TreeviewSelect>>', self.describe_queue)
        actions = tk.Frame(dialog, bg=t.CARD)
        actions.pack(fill='x', padx=20, pady=(0, 20))
        self.queue_start = ttk.Button(actions, text='Start queue', command=self.start_queue, style='CardPrimary.TButton')
        self.queue_start.pack(side='left')
        self.queue_stop = ttk.Button(actions, text='Stop queue', command=self.stop_queue)
        self.queue_stop.pack(side='left', padx=8)
        ttk.Button(actions, text='Remove pending', command=self.remove_pending).pack(side='left')
        ttk.Button(actions, text='Review results', command=self.review_queue_result).pack(side='right')
        self.render_queue()

    def render_queue(self):
        self.queue_button.configure(text=f'Queue ({sum(r["status"] == "Pending" for r in self.analysis_queue)})')
        if self.queue_window is None or not self.queue_window.winfo_exists():
            return
        selected = self.queue_table.selection()
        self.queue_table.delete(*self.queue_table.get_children())
        for index, row in enumerate(self.analysis_queue):
            self.queue_table.insert('', 'end', iid=str(index), values=(Path(row['path']).name, row['status']))
        self.queue_table.selection_set([i for i in selected if self.queue_table.exists(i)])
        self.queue_start.state(['disabled'] if self.working or self.queue_running or not any(r['status'] == 'Pending' for r in self.analysis_queue) else ['!disabled'])
        self.queue_stop.state(['!disabled'] if self.queue_running else ['disabled'])
        preset = self.queue_settings.preset.name if self.queue_running else self.active_preset.name
        self.queue_description.set(f'Preset: {preset}\nFull videos, one at a time. EDLs and timestamps save to configured folders with unique filenames. Your current workspace is kept.')

    def describe_queue(self, event=None):
        selected = self.queue_table.selection()
        if not selected:
            return
        row = self.analysis_queue[int(selected[0])]
        result = row['result'] or {}
        self.queue_detail.set(row['path'] + '\n' + (result.get('error') or '\n'.join(
            str(result[k]) for k in ('edl', 'timestamps') if result.get(k)) or row['status']))

    def remove_pending(self):
        selected = {int(i) for i in self.queue_table.selection()}
        # Keep indices stable while a job is running.
        for i in selected:
            if self.analysis_queue[i]['status'] == 'Pending':
                self.analysis_queue[i]['status'] = 'Removed'
        self.render_queue()

    def start_queue(self):
        if self.working or self.queue_running:
            return
        try:
            self.queue_settings = self._settings()
        except Exception as exc:
            self.error('Check analysis settings', str(exc))
            return
        self.queue_region = config.section(self.cfg, 'detect').get('region') if self.active_preset.has_player_traits else None
        self.queue_outputs = (self._folder('export', 'output_dir'), self._folder('detect', 'timestamps_dir'),
                              self.saved_values['export', 'name'], config.section(self.cfg, 'export').get('fps'))
        self.queue_running = True
        self.queue_stop_requested = False
        self.next_queue_item()

    def next_queue_item(self):
        pending = next((i for i, r in enumerate(self.analysis_queue) if r['status'] == 'Pending'), None)
        if self.queue_stop_requested or pending is None:
            self.queue_running = False
            self.queue_active = None
            self.working = None
            self.status.set('Queue stopped. Pending videos can be started later.' if self.queue_stop_requested else 'Analysis queue finished. Open the queue to review results.')
            self._update_controls()
            self.render_queue()
            self.refresh_library()
            return
        self.queue_active = pending
        row = self.analysis_queue[pending]
        row['status'] = 'Analyzing'
        self._begin('batch', f'Analyzing queued video: {Path(row["path"]).name}')
        self.jobs.submit('batch', analyze_queued, self.jobs, row['path'], self.queue_settings,
                         self.queue_region, *self.queue_outputs)
        self.render_queue()

    def stop_queue(self):
        if self.queue_running:
            self.queue_stop_requested = True
            self.jobs.cancel.set()
            self.status.set('Stopping queue… Completed exports and partial results will be kept.')

    def receive_batch(self, data, error):
        row = self.analysis_queue[self.queue_active]
        row['result'] = data or {'error': error, 'clips': []}
        row['status'] = data['status'] if data else 'Failed'
        self.next_queue_item()

    def review_queue_result(self):
        if self.working:
            return
        selected = self.queue_table.selection()
        if not selected:
            return
        row = self.analysis_queue[int(selected[0])]
        result = row['result'] or {}
        if result.get('media') and (result.get('edl') or result.get('clips')):
            if self.open_file(row['path']):
                self.queue_review = result

    def apply_queue_review(self):
        result = self.queue_review
        self.queue_review = None
        path = result.get('edl')
        self.receive_edl(([path] if path else [], path or 'Unsaved queue results', result['clips'], None))
        if not path:
            self.reset_edl()
            self.exported = False
        self.show('results')
