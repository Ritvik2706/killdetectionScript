"""Sequential queue worker; exports never replace existing files."""
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from killcutter import export, outputs
from .services import analyze, open_media


class BatchEvents:
    def __init__(self, events):
        self.events = events

    def put(self, event):
        kind, data, error = event
        if kind == 'progress':
            self.events.put(('batch_progress', data, error))


class BatchContext:
    def __init__(self, jobs):
        self.cancel = jobs.cancel
        self.events = BatchEvents(jobs.events)


def analyze_queued(jobs, path, settings, region, edl_dir, timestamps_dir, sequence, fps):
    result = {'clips': [], 'media': None, 'edl': None, 'timestamps': None, 'status': 'Failed', 'error': None}
    try:
        if jobs.cancel.is_set():
            result['status'] = 'Stopped'
            return result
        media, _ = open_media(path)
        result['media'] = media
        clips, completed = analyze(BatchContext(jobs), media, settings, 0, media.duration, region)
        result['clips'] = clips
        result['status'] = 'Done' if completed else 'Stopped'
        if clips or completed:
            suffix = datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8]
            stem = Path(path).stem + ('_highlights_' if completed else '_partial_') + suffix
            stamp = str(Path(timestamps_dir) / (stem + '_timestamps.txt'))
            edl = str(Path(edl_dir) / (stem + '.edl'))
            outputs.validate_paths([path], [stamp, edl])
            outputs.atomic_text(stamp, export.format_timestamps(clips))
            result['timestamps'] = stamp
            plan = export.plan(path, clips, fps_override=fps, name=sequence, output=edl)
            export.write_edl(plan)
            result['edl'] = edl
    except Exception as exc:
        result['status'] = 'Failed'
        result['error'] = str(exc)
    return result
