"""General video detectors behind the same scan/report/export contract as Warzone."""
import os
import time

import cv2
import numpy as np

from .errors import VideoError
from .models import Clip
from .ranges import resolve_range


def matches(frame, preset):
    from .detection import _ocr_lines
    x, y, w, h = preset.box(frame.shape[1], frame.shape[0])
    roi = frame[y:y+h, x:x+w]
    if preset.detector == 'text':
        # Case and whitespace insensitive literal phrase matching, not regex/code.
        observed = ' '.join(' '.join(_ocr_lines(roi)).casefold().split())
        return ' '.join(preset.text.casefold().split()) in observed
    if preset.detector == 'color':
        rgb = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB).astype(np.int16)
        distance = np.abs(rgb - np.asarray(preset.color, dtype=np.int16))
        return float(np.mean(np.all(distance <= preset.tolerance, axis=2))) >= preset.coverage
    raise ValueError(f'Unsupported general detector: {preset.detector}')


class FrameMatcher:
    """Keep temporal evidence isolated to one scan, never in a saved recipe."""
    def __init__(self, preset):
        self.preset = preset
        self.previous = None

    def matches(self, frame):
        preset = self.preset
        if preset.detector not in ('motion', 'scene'):
            return matches(frame, preset)
        x, y, w, h = preset.box(frame.shape[1], frame.shape[0])
        gray = cv2.cvtColor(frame[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        previous, self.previous = self.previous, gray
        if previous is None:
            return False
        difference = cv2.absdiff(gray, previous)
        return float(np.mean(difference > preset.tolerance)) >= preset.coverage


def detect(path, settings, reporter, *, start=0, limit=None, end=None, cancelled=None, dry_run=False):
    from .detection import DetectionMeta, _measure_duration, _samples
    preset = settings.preset.validate()
    if not os.path.isfile(path):
        raise VideoError(f'No such file: {path}')
    cap = cv2.VideoCapture(path)
    clips = []
    completed = True
    elapsed = start
    stop = start
    stream = None
    try:
        if not cap.isOpened():
            raise VideoError(f'Could not open: {path}')
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps <= 0:
            raise VideoError('Could not read the video frame rate.')
        duration = _measure_duration(cap, total_frames, fps)
        start, stop = resolve_range(duration, start, limit, end)
        width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if min(width, height) <= 0:
            raise VideoError('Could not read the video dimensions.')
        box = preset.box(width, height)
        checks = int((stop-start)*settings.rate)+1
        reporter.begin(DetectionMeta(os.path.basename(path), fps, duration, total_frames,
                                    box, settings, checks, dry_run, preset.name, start, stop))
        if start:
            cap.set(cv2.CAP_PROP_POS_MSEC, start*1000)
        previous = False
        matcher = FrameMatcher(preset)
        last_event = float('-inf')
        wall = time.monotonic()
        if preset.detector == 'audio':
            from .audio_detection import samples as audio_samples
            stream = audio_samples(path, start, stop, settings.rate, cancelled)
        else:
            stream = _samples(cap, duration, 1/settings.rate)
        for done, (elapsed, frame) in enumerate(stream, 1):
            if cancelled and cancelled():
                raise KeyboardInterrupt
            if elapsed < start:
                continue
            if elapsed >= stop:
                break
            active = frame >= preset.audio_db if preset.detector == 'audio' else matcher.matches(frame)
            reporter.frame(elapsed, active)
            # A sustained match is one event; it must disappear before rearming.
            if active and (not previous or preset.detector == 'scene') and elapsed-last_event > settings.cooldown:
                clip = Clip(max(start, elapsed-settings.offset), min(stop, elapsed+settings.end_offset), preset.label)
                if clips and elapsed-last_event <= settings.merge_gap:
                    clip.start = clips[-1].start
                    clips[-1] = clip
                    reporter.extended(clip)
                else:
                    clips.append(clip)
                    reporter.kill(len(clips), elapsed, clip)  # legacy reporter callback
                last_event = elapsed
            if settings.preview and preset.detector != 'audio':
                x, y, w, h = preset.box(frame.shape[1], frame.shape[0])
                cv2.imshow('Detection region', frame[y:y+h, x:x+w])
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    raise KeyboardInterrupt
            previous = active
            fraction = (elapsed-start)/(stop-start)
            spent = time.monotonic()-wall
            eta = spent/fraction-spent if fraction > .001 else None
            reporter.progress(done, checks, elapsed, stop, len(clips), eta)
    except KeyboardInterrupt:
        completed = False
        reporter.aborted(elapsed, stop, len(clips))
    finally:
        if stream is not None:
            stream.close()
        cap.release()
        if settings.preview:
            cv2.destroyAllWindows()
    return clips, completed
