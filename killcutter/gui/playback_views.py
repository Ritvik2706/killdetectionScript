"""Transport controls for the embedded native player."""
import tkinter as tk
from tkinter import ttk

from . import theme as t
from .playback import Playback


class PlaybackViews:
    def build_transport(self, parent):
        self.player = None
        self.player_paused = False
        self.player_stopping = False
        self.volume = tk.DoubleVar(value=80)
        self.play_button = ttk.Button(parent, text='Play', command=self.toggle_playback)
        self.play_button.pack(side='left', padx=(0, 6))
        ttk.Button(parent, text='Stop', command=self.stop_playback).pack(side='left', padx=(0, 6))
        ttk.Label(parent, text='Volume', style='Card.TLabel').pack(side='left', padx=(8, 4))
        ttk.Scale(parent, from_=0, to=100, variable=self.volume,
                  command=self.set_volume).pack(side='left', fill='x', expand=True)
        self.play_surface = tk.Frame(self.preview, bg=t.PREVIEW)
        self.play_surface.place_forget()

    def set_volume(self, value):
        if self.player:
            self.player.command('set', 'volume', float(value))

    def toggle_playback(self, event=None):
        if event is not None and isinstance(event.widget, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox, ttk.Button, ttk.Checkbutton, ttk.Scale)):
            return
        if self.player_stopping or self.working or not self.state.media or self.current_page != 'workspace':
            return
        if self.player:
            self.player_paused = not self.player_paused
            self.player.command('set', 'pause', 'yes' if self.player_paused else 'no')
            self.play_button.configure(text='Resume' if self.player_paused else 'Pause')
        else:
            self.play_range(self.state.position, self.state.media.duration)
        return 'break'

    def play_range(self, start, end):
        if self.player or self.working:
            return
        if start >= end - .05:
            start = 0
        self.generation += 1
        self.play_surface.place(x=0, y=0, relwidth=1, relheight=1)
        self.play_surface.lift()
        self.update_idletasks()
        self.player_paused = False
        self.play_button.configure(text='Pause')
        self.player = Playback(self.jobs.events, self.play_surface.winfo_id(),
                               self.state.media.path, start, end, self.volume.get())

    def stop_playback(self):
        if self.player and not self.player_stopping:
            self.player_stopping = True
            self.player.close()
            self.play_button.configure(text='Play')
            # Keep the native surface alive until mpv has destroyed its child window.
            self.status.set('Stopping playback…')

    def playback_event(self, kind, data, error):
        event, source = kind
        if event == 'playback_done':
            if self.player is source:
                self.player = None
                self.player_stopping = False
            if self.player is None:
                self.play_surface.place_forget()
                self.play_button.configure(text='Play')
                if self.state.media and not self.working:
                    self._request_frame(self.state.position)
        elif source is self.player and not self.player_stopping:
            if error:
                self.status.set(f'Playback unavailable: {error}')
            elif event == 'playback':
                position, paused = data
                self.state.position = min(position, self.state.media.duration)
                from .app import clock
                self.position_var.set(clock(self.state.position))
                # Setting the slider must not trigger another seek.
                self.seek.configure(command='')
                self.seek.set(self.state.position)
                self.seek.configure(command=self._seek_changed)
