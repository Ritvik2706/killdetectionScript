"""Small libmpv client. Native decoding, audio and A/V synchronization stay in mpv.

The API calls run on a dedicated thread. Tk only receives position/status data.
"""
import ctypes as C
from ctypes.util import find_library
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import os
import time

from killcutter.errors import DependencyError


class EndFile(C.Structure):
    _fields_ = [('reason', C.c_int), ('error', C.c_int)]


class Event(C.Structure):
    _fields_ = [('event_id', C.c_int), ('error', C.c_int),
                ('reply_userdata', C.c_uint64), ('data', C.c_void_p)]


def library_path():
    return os.environ.get('KILLCUTTER_MPV') or find_library('mpv') or ('mpv-2.dll' if os.name == 'nt' else 'libmpv.so.2')


class NativePlayer:
    def __init__(self, window, start=0, end=None):
        try:
            self.lib = C.CDLL(library_path())
        except OSError as exc:
            raise DependencyError('Audio/video playback needs libmpv. Install mpv (Linux) or set '
                                  'KILLCUTTER_MPV to mpv-2.dll (Windows). Frame inspection still works.') from exc
        signatures = {
            'mpv_create': ([], C.c_void_p),
            'mpv_initialize': ([C.c_void_p], C.c_int),
            'mpv_set_option_string': ([C.c_void_p, C.c_char_p, C.c_char_p], C.c_int),
            'mpv_command': ([C.c_void_p, C.POINTER(C.c_char_p)], C.c_int),
            'mpv_get_property_string': ([C.c_void_p, C.c_char_p], C.c_void_p),
            'mpv_free': ([C.c_void_p], None),
            'mpv_wait_event': ([C.c_void_p, C.c_double], C.POINTER(Event)),
            'mpv_terminate_destroy': ([C.c_void_p], None),
            'mpv_error_string': ([C.c_int], C.c_char_p),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.lib, name)
            fn.argtypes, fn.restype = args, result
        self.handle = self.lib.mpv_create()
        if not self.handle:
            raise RuntimeError('Could not create the video player.')
        try:
            for key, value in {'wid': str(window), 'config': 'no', 'terminal': 'no',
                               'input-default-bindings': 'no', 'input-vo-keyboard': 'no',
                               'osc': 'no', 'keep-open': 'yes', 'idle': 'yes',
                               'start': str(start), 'end': str(end) if end is not None else 'none'}.items():
                self.check(self.lib.mpv_set_option_string(self.handle, key.encode(), value.encode()))
            self.check(self.lib.mpv_initialize(self.handle))
        except Exception:
            self.close()
            raise

    def check(self, code):
        if code < 0:
            raise RuntimeError(self.lib.mpv_error_string(code).decode())

    def command(self, *args):
        encoded = [str(a).encode('utf-8') for a in args] + [None]
        self.check(self.lib.mpv_command(self.handle, (C.c_char_p * len(encoded))(*encoded)))

    def property(self, name):
        value = self.lib.mpv_get_property_string(self.handle, name.encode())
        if not value:
            return None
        try:
            return C.string_at(value).decode('utf-8')
        finally:
            self.lib.mpv_free(value)

    def events(self):
        for _ in range(100):
            event = self.lib.mpv_wait_event(self.handle, 0).contents
            if not event.event_id:
                break
            if event.error < 0:
                self.check(event.error)
            if event.event_id == 7 and event.data:  # MPV_EVENT_END_FILE
                result = C.cast(event.data, C.POINTER(EndFile)).contents
                if result.reason == 4:  # MPV_END_FILE_REASON_ERROR
                    self.check(result.error)
                    raise RuntimeError('The media player could not decode this recording.')

    def close(self):
        if self.handle:
            self.lib.mpv_terminate_destroy(self.handle)
            self.handle = None


class Playback:
    """All native player calls are serialized in a single worker thread."""
    def __init__(self, events, window, path, start, end, volume=80):
        self.events = events
        self.commands = Queue()
        self.thread = Thread(target=self._run, args=(window, path, start, end, volume), daemon=True)
        self.thread.start()

    def command(self, *args):
        self.commands.put(args)

    def close(self):
        self.command('close')

    def _run(self, window, path, start, end, volume):
        player = None
        try:
            player = NativePlayer(window, start, end)
            player.command('set', 'volume', volume)
            player.command('loadfile', str(Path(path).resolve()), 'replace')
            started = time.monotonic()
            loaded = False
            while True:
                try:
                    command = self.commands.get(timeout=.05)
                    if command[0] == 'close':
                        break
                    player.command(*command)
                except Empty:
                    pass
                player.events()
                position = player.property('time-pos')
                if position is not None:
                    loaded = True
                    self.events.put((('playback', self), (float(position), player.property('pause') == 'yes'), None))
                if not loaded and time.monotonic() - started > 15:
                    raise RuntimeError('Timed out opening the recording for playback.')
                if player.property('eof-reached') == 'yes':
                    break
        except Exception as exc:
            self.events.put((('playback_error', self), None, str(exc)))
        finally:
            if player:
                player.close()
            self.events.put((('playback_done', self), None, None))
