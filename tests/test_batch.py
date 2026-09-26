from types import SimpleNamespace
from threading import Event
from queue import Queue
from PIL import Image
from killcutter.gui import batch
from killcutter.gui.state import Media
from killcutter.models import Clip
from killcutter.export import ExportPlan


def test_batch_exports_unique_files_and_retains_clips_if_save_fails(tmp_path, monkeypatch):
    media = Media(str(tmp_path / 'video.mp4'), 30, 60, 320, 180)
    clips = [Clip(10, 15, 'Player')]
    monkeypatch.setattr(batch, 'open_media', lambda path: (media, Image.new('RGB', (2, 2))))
    monkeypatch.setattr(batch, 'analyze', lambda *args: (clips, True))
    monkeypatch.setattr(batch.export, 'plan', lambda path, clips, **kw: ExportPlan(clips, 'Test', 'video.mp4', 30, False, kw['output'], '', '', 5))
    jobs = SimpleNamespace(cancel=Event(), events=Queue())
    args = (jobs, media.path, None, None, str(tmp_path), str(tmp_path), 'Test', None)
    first = batch.analyze_queued(*args)
    second = batch.analyze_queued(*args)
    assert first['status'] == second['status'] == 'Done'
    assert first['edl'] != second['edl']
    assert first['timestamps'] != second['timestamps']
    def fail(*args):
        raise OSError('Disk full')
    monkeypatch.setattr(batch.export, 'write_edl', fail)
    failed = batch.analyze_queued(*args)
    assert failed['status'] == 'Failed'
    assert failed['clips'] == clips
    assert failed['timestamps']
    assert failed['error'] == 'Disk full'
    jobs.cancel.set()
    assert batch.analyze_queued(*args)['status'] == 'Stopped'
