"""Background work and adapters. Workers exchange data, never Tk objects."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from queue import Queue
from threading import Event
import time

import cv2
from PIL import Image

from killcutter import detection, environment, video
from killcutter.errors import VideoError
from .state import Media


def read_frame(path, seconds=0):
    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            raise VideoError(f"Could not open {path}")
        cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
        ok, frame = cap.read()
        if not ok:
            raise VideoError("Could not decode this frame. Try seeking slightly earlier.")
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    finally:
        cap.release()


def open_media(path):
    fps, _, duration = video.measure(path)
    if fps <= 0 or duration <= 0:
        raise VideoError("This file does not contain a readable video stream.")
    image = read_frame(path)
    return Media(path, fps, duration, image.width, image.height), image


class Jobs:
    """One processing job and one independent preview lane."""
    def __init__(self):
        self.events = Queue()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='killcutter-job')
        self.preview_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='killcutter-preview')
        self.library_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='killcutter-library')
        self.cancel = Event()
        self.future = None
        self.preview_future = None
        self.closed = False

    @property
    def busy(self):
        return self.future is not None and not self.future.done()

    def submit(self, kind, function, *args):
        if self.busy:
            return False
        self.cancel.clear()
        self.future = self.pool.submit(self._run, kind, function, args)
        return True

    def preview(self, generation, path, seconds):
        if self.preview_future:
            self.preview_future.cancel()
        self.preview_future = self.preview_pool.submit(self._run, ('frame', generation, seconds), read_frame, (path, seconds))

    def _run(self, kind, function, args):
        try:
            result = function(*args)
            if not self.closed:
                self.events.put((kind, result, None))
        except Exception as exc:
            if not self.closed:
                self.events.put((kind, None, str(exc)))

    def close(self):
        self.closed = True
        self.cancel.set()
        self.library_pool.shutdown(wait=False, cancel_futures=True)
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.preview_pool.shutdown(wait=False, cancel_futures=True)


class Reporter:
    def __init__(self, events):
        self.events = events
        self.last = 0
        self.start = 0
        self.last_frame = 0
        self.index = 0

    def begin(self, meta):
        self.start = meta.scan_start

    def frame(self, elapsed, triggered):
        now = time.monotonic()
        if now - self.last_frame >= .5:
            self.last_frame = now
            self.events.put(('scan_position', (elapsed, triggered), None))

    def kill(self, index, at, clip):
        self.index = index - 1
        self.events.put(('highlight', (self.index, at, replace(clip, traits=dict(clip.traits)), False), None))

    def extended(self, clip):
        self.events.put(('highlight', (self.index, clip.end, replace(clip, traits=dict(clip.traits)), True), None))

    def aborted(self, *args):
        pass

    def progress(self, done, total, elapsed, end, kills, eta):
        now = time.monotonic()
        if now - self.last >= .1:
            self.last = now
            fraction = (elapsed - self.start) / max(.001, end - self.start)
            self.events.put(('progress', (max(0, min(1, fraction)), kills, eta), None))


def analyze(jobs, media, settings, start, end, region_override=None):
    if (settings.preset is None or settings.preset.needs_ocr) and not environment.configure_tesseract():
        from killcutter.errors import DependencyError
        raise DependencyError("Tesseract OCR was not found. Install it and check Environment in Settings.")
    return detection.detect(media.path, settings, Reporter(jobs.events), start=start, end=end,
                            cancelled=jobs.cancel.is_set, region_override=region_override)


def inspect_region_text(image, region):
    """Read exactly the ROI used by text detection, off the Tk thread."""
    import numpy as np
    from killcutter.presets import Preset
    from killcutter.errors import DependencyError
    if not environment.configure_tesseract():
        raise DependencyError('Tesseract OCR was not found. Install Tesseract or set KILLCUTTER_TESSERACT to its executable.')
    x, y, w, h = Preset('preview', 'Preview', region=region).box(*image.size)
    roi = cv2.cvtColor(np.asarray(image.crop((x, y, x+w, y+h)).convert('RGB')), cv2.COLOR_RGB2BGR)
    return '\n'.join(detection._ocr_lines(roi, timeout=15))
