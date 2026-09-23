"""Desktop contracts plus opt-in tests that require an actual graphical display."""
import os
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from killcutter.gui.state import image_rect, source_pixel
from killcutter.gui.services import Jobs, Reporter
from killcutter.models import Clip


def test_letterboxed_coordinate_mapping():
    assert image_rect(1920, 1080, 1000, 1000) == (0, 219, 1000, 562)
    assert source_pixel(500, 500, 1920, 1080, 1000, 1000) == (960, 540)
    assert source_pixel(500, 100, 1920, 1080, 1000, 1000) is None
    assert source_pixel(1000, 500, 1920, 1080, 1000, 1000) is None
    assert source_pixel(0, 0, 0, 0, 100, 100) is None


def test_jobs_return_data_and_errors_without_touching_ui():
    jobs = Jobs()
    try:
        jobs.submit('success', lambda: 42)
        jobs.future.result(timeout=2)
        assert jobs.events.get_nowait() == ('success', 42, None)
        def fail():
            raise ValueError('bad video')
        jobs.submit('failure', fail)
        jobs.future.result(timeout=2)
        assert jobs.events.get_nowait() == ('failure', None, 'bad video')
    finally:
        jobs.close()


def test_reporter_progress_uses_selected_range():
    from queue import Queue
    reporter = Reporter(Queue())
    reporter.begin(Mock(scan_start=60))
    reporter.progress(40, 80, 70, 80, 3, 2)
    assert reporter.events.get_nowait() == ('progress', (.5, 3, 2), None)


def test_cooperative_cancellation_preserves_partial_results(monkeypatch, tmp_path):
    import numpy as np
    from killcutter import detection
    source = tmp_path / 'video.mkv'
    source.touch()
    cap = Mock()
    cap.get.return_value = 60
    monkeypatch.setattr(detection.cv2, 'VideoCapture', lambda _: cap)
    monkeypatch.setattr(detection, '_measure_duration', lambda *a: 100)
    monkeypatch.setattr(detection, '_samples', lambda *a: iter([
        (20, np.zeros((60, 60, 3), dtype=np.uint8)),
        (21, np.zeros((60, 60, 3), dtype=np.uint8)),
    ]))
    monkeypatch.setattr(detection, '_banner_visible', lambda *a: True)
    monkeypatch.setattr(detection, 'read_banner', lambda *a: (True, 'Player'))
    cancelled = iter([False, True])
    reporter = Mock()
    clips, completed = detection.detect(str(source), detection.DetectionSettings((0, 0, 10, 10)),
                                         reporter, start=20, end=30, cancelled=lambda: next(cancelled))
    assert not completed
    assert len(clips) == 1
    reporter.aborted.assert_called_once()
    cap.release.assert_called_once()


@pytest.fixture
def app(tmp_path, monkeypatch):
    if os.environ.get('KILLCUTTER_GUI_TESTS') != '1':
        pytest.skip('Set KILLCUTTER_GUI_TESTS=1 on a graphical desktop or under Xvfb.')
    from killcutter.gui.app import Application
    from tkinter import messagebox
    monkeypatch.setattr(messagebox, 'showerror', lambda title, message, **kwargs: pytest.fail(f'{title}: {message}'))
    root = Application(config_path=str(tmp_path / 'config.toml'))
    root.withdraw()
    root.update()
    yield root
    root.working = None
    root.exported = True
    root.close()


def pump(app, condition, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.update()
        if condition():
            return
        time.sleep(.01)
    pytest.fail('GUI operation did not finish')


def test_gui_import_seek_settings_and_inspection(app, tmp_path):
    import cv2
    import numpy as np
    path = tmp_path / 'sample.mp4'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 30, (320, 180))
    assert writer.isOpened()
    for _ in range(90):
        writer.write(np.zeros((180, 320, 3), dtype=np.uint8))
    writer.release()
    app.open_file(str(path))
    pump(app, lambda: app.state.media is not None and app.working is None)
    assert app.preview.image.size == (320, 180)
    app._seek_changed(1)
    pump(app, lambda: app.frame_time == 1)
    app.mark_in()
    assert app._range()[0] == 1
    app.inspect_pixel(12, 34, (10, 20, 30))
    assert app.sample['rgb'] == [10, 20, 30]
    assert app.sample['time_seconds'] == 1
    app.setting_vars['detect', 'rate'].set('8')
    assert app._settings().rate == 4  # unsaved edits do not affect scans
    app.save_settings()
    assert app._settings().rate == 8
    assert Path(app.config_path).is_file()


def test_gui_scan_results_export_selected(app, monkeypatch, tmp_path):
    from killcutter.gui.state import Media
    from killcutter.gui import app as module
    app.state.media = Media(str(tmp_path / 'source.mkv'), 30, 60, 1920, 1080)
    app.full_range()
    monkeypatch.setattr(module, 'analyze', lambda *a: ([Clip(10, 15, 'One'), Clip(20, 25, 'Two')], True))
    app.start_scan()
    pump(app, lambda: app.working is None)
    assert len(app.table.get_children()) == 2
    app.table.selection_set('1')
    target = tmp_path / 'selected.txt'
    monkeypatch.setattr(module.filedialog, 'asksaveasfilename', lambda **kw: str(target))
    app.export_selection('timestamps')
    pump(app, lambda: app.working is None)
    assert target.read_text() == '20.000 25.000 Two\n'
    assert not app.exported  # unselected highlights still need an export


def test_gui_partial_scan_keeps_reviewable_results(app, monkeypatch, tmp_path):
    from killcutter.gui.state import Media
    from killcutter.gui import app as module
    app.state.media = Media(str(tmp_path / 'source.mkv'), 30, 60, 1920, 1080)
    app.full_range()
    monkeypatch.setattr(module, 'analyze', lambda *a: ([Clip(10, 15, 'One')], False))
    app.start_scan()
    pump(app, lambda: app.working is None)
    assert 'Partial results' in app.results_summary.cget('text')
    assert app.table.selection() == ('0',)


def test_desktop_utf8_output_roundtrip(tmp_path):
    from killcutter import config, export, outputs
    path = tmp_path / 'settings.toml'
    config.save_updates(path, {'detect': {'clips_dir': 'C:/Vidéos/録画'}})
    config.save_updates(path, {'detect': {'rate': 8}})
    cfg, _ = config.load(path)
    assert cfg['detect']['clips_dir'] == 'C:/Vidéos/録画'
    timestamps = tmp_path / 'timestamps.txt'
    outputs.atomic_text(timestamps, '10.000 15.000 joueur_é\n')
    assert export.read_timestamps(timestamps) == [Clip(10, 15, 'joueur_é')]
