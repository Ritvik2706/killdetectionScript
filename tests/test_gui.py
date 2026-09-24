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


def test_reporter_emits_snapshot_and_merge_events():
    from queue import Queue
    reporter = Reporter(Queue())
    clip = Clip(10, 15, 'Alpha')
    reporter.kill(1, 12, clip)
    clip.name = 'Alpha, Beta'
    reporter.extended(clip)
    first = reporter.events.get_nowait()
    second = reporter.events.get_nowait()
    assert first == ('highlight', (0, 12, Clip(10, 15, 'Alpha'), False), None)
    assert second == ('highlight', (0, 15, clip, True), None)
    assert first[1][2] is not clip


def test_reporter_throttles_position_events(monkeypatch):
    from queue import Queue
    from killcutter.gui import services
    monkeypatch.setattr(services.time, 'monotonic', lambda: 10)
    reporter = Reporter(Queue())
    for at in range(100):
        reporter.frame(at, False)
    assert reporter.events.qsize() == 1
    assert reporter.events.get_nowait() == ('scan_position', (0, False), None)


def test_gui_live_merge_search_sort_and_copy(app):
    app.working = 'scan'
    app.jobs.events.put(('highlight', (0, 12, Clip(10, 15, 'Alpha'), False), None))
    app.jobs.events.put(('highlight', (0, 18, Clip(10, 23, 'Alpha, Beta'), True), None))
    app.jobs.events.put(('highlight', (1, 32, Clip(30, 35, 'Gamma'), False), None))
    pump(app, lambda: len(app.state.clips) == 2)
    assert app.working == 'scan'
    assert app.live_table.item('0', 'values') == ('Alpha, Beta',)
    assert len(app.live_table.get_children()) == 2
    assert app.table.set('0', 'out') == '00:00:23.000'
    app.working = None
    app.search_var.set('BETA')
    assert app.table.get_children() == ('0',)
    app.select_all_results()
    app.copy_selection()
    assert app.clipboard_get() == '10.000 23.000 Alpha, Beta\n'
    app.search_var.set('')
    app.sort_results('duration')
    assert app.table.get_children() == ('1', '0')
    app.table.selection_set('1')
    app.sort_results('duration')
    assert app.table.selection() == ('1',)
    assert not app.exported


def test_gui_scan_error_retains_live_results(app, monkeypatch):
    errors = []
    monkeypatch.setattr(app, 'error', lambda *args: errors.append(args))
    app.working = 'scan'
    app.jobs.events.put(('highlight', (0, 12, Clip(10, 15, 'Alpha'), False), None))
    app.jobs.events.put(('scan', None, 'Decoder failed'))
    pump(app, lambda: app.working is None)
    assert app.state.clips == [Clip(10, 15, 'Alpha')]
    assert 'retained' in app.results_summary.cget('text')
    app.table.selection_set('0')
    app._update_controls()
    assert not app.result_buttons[1].instate(['disabled'])
    assert errors


def test_preferences_reject_unusable_values():
    from killcutter.gui import preferences, theme
    cfg = {'gui': {'theme': 'Neon', 'accent': 'not-a-colour', 'scale': 9, 'chime': 'yes',
                   'geometry': 'huge', 'page': 'nowhere', 'recents': ['a.mkv', 7, 'b.mkv']}}
    prefs = preferences.load(cfg)
    assert prefs.theme in theme.PALETTES and prefs.accent == theme.ACCENTS['Blue']
    assert prefs.scale == preferences.MAX_SCALE  # clamped, not rejected
    assert prefs.chime is True and prefs.geometry == '' and prefs.page == 'workspace'
    assert prefs.recents == ('a.mkv', 'b.mkv')
    good = preferences.load({'gui': {'theme': 'Daylight', 'accent': '#22b8a6', 'scale': 1.25,
                                     'chime': False, 'geometry': '1200x800+10+10', 'page': 'results'}})
    assert good.appearance == ('Daylight', '#22B8A6', 1.25)
    assert good.chime is False and good.page == 'results'


def test_recents_promote_without_duplicates():
    from killcutter.gui import preferences
    prefs = preferences.Preferences()
    for path in ('a.mkv', 'b.mkv', 'a.mkv'):
        prefs = preferences.remember(prefs, path)
    assert prefs.recents == ('a.mkv', 'b.mkv')
    for index in range(preferences.RECENT_LIMIT + 3):
        prefs = preferences.remember(prefs, f'{index}.mkv')
    assert len(prefs.recents) == preferences.RECENT_LIMIT


def test_palette_roles_are_complete_and_accents_readable():
    from killcutter.gui import theme
    for name, colors in theme.PALETTES.items():
        assert len(colors) == len(theme.ROLES), name
    for accent in theme.ACCENTS.values():
        theme.configure('Midnight', accent, 1.0)
        assert theme.ON_ACCENT in ('white', '#101014')
        assert theme.SELECTED != theme.BG  # a selected row must stay visible
    theme.configure()


def test_scaling_keeps_the_type_hierarchy():
    from killcutter.gui import theme
    theme.configure(scale=1.5)
    assert theme.size(10) == 15 and theme.size(21) > theme.size(10) and theme.px(38) == 57
    theme.configure(scale=1.0)
    assert theme.size(10) == 10


def test_gui_appearance_applies_and_persists(app):
    from killcutter.gui import preferences, theme
    from killcutter import config
    app.theme_var.set('Daylight')
    app.accent_var.set('#22B8A6')
    app.scale_var.set(1.2)
    app.chime_var.set(False)
    app.apply_appearance()
    app.update()
    assert theme.BG == theme.PALETTES['Daylight'][0]
    assert app.rail_card.content.cget('bg') == theme.SIDEBAR
    assert app.preview.cget('bg') == theme.PREVIEW
    assert app.theme_buttons['Daylight'].cget('style') == 'CardPrimary.TButton'
    # Accent-tinted labels follow the new accent, not just the palette roles.
    assert app.scale_label.cget('fg') == '#22B8A6'
    assert app.scale_label.cget('font').split()[-2] == str(theme.size(10))
    saved = preferences.load(config.load(app.config_path)[0])
    assert saved.appearance == ('Daylight', '#22B8A6', 1.2) and saved.chime is False
    app.reset_appearance()
    assert app.prefs.appearance == preferences.Preferences().appearance


def test_gui_remove_undo_rename_and_nudge(app, tmp_path, monkeypatch):
    from killcutter.gui.state import Media
    from tkinter import simpledialog
    app.state.media = Media(str(tmp_path / 'source.mkv'), 30, 120, 1920, 1080)
    app.state.clips = [Clip(10, 15, 'Alpha'), Clip(20, 25, 'Beta'), Clip(30, 35, 'Gamma')]
    app.state.completed = True
    app.exported_ids = {'0', '1', '2'}
    app.filter_results()
    app.table.selection_set('1')
    app.remove_selected()
    assert [c.name for c in app.state.clips] == ['Alpha', 'Gamma']
    assert app.exported_ids == {'0', '1'}  # Gamma keeps its exported mark at its new index
    assert app.live_table.item('1', 'values') == ('Gamma',)
    app.undo_remove()
    assert [c.name for c in app.state.clips] == ['Alpha', 'Beta', 'Gamma']
    assert not app.exported
    app.table.selection_set('0')
    monkeypatch.setattr(simpledialog, 'askstring', lambda *a, **k: '  Delta  ')
    app.rename_selected()
    assert app.state.clips[0].name == 'Delta'
    app.table.selection_set('0')
    app.adjust_selected(-2, edge='start')
    app.adjust_selected(3, edge='end')
    assert app.state.clips[0] == Clip(8, 18, 'Delta')
    app.adjust_selected(-999, edge='start')
    assert app.state.clips[0].start == 0  # clamped to the recording, never past the out point


def test_gui_recent_recordings_menu(app, tmp_path):
    from killcutter.gui import preferences
    present, missing = tmp_path / 'kept.mkv', tmp_path / 'gone.mkv'
    present.touch()
    app.prefs = preferences.remember(preferences.remember(app.prefs, str(missing)), str(present))
    menu = app.recent_menu()
    assert menu.entrycget(0, 'label') == 'kept.mkv'
    assert menu.entrycget(1, 'label').endswith('(missing)')
    assert str(menu.entrycget(1, 'state')) == 'disabled'
    app.clear_recents()
    assert app.recent_menu().entrycget(0, 'label') == 'No recent recordings yet'


def test_gui_kill_filters_preserve_clips_and_limit_selection(app):
    app.state.clips = [Clip(1, 3, 'Alpha', {'real-player': True}),
                       Clip(4, 6, 'Beta', {'real-player': False}),
                       Clip(7, 9, 'Gamma')]
    app.filter_results()
    app.select_all_results()
    app.kill_filter.set('real-player')
    assert app.table.get_children() == ('0', '2')
    assert set(app.table.selection()) == {'0', '2'}
    app.keep_unknown.set(False)
    assert app.table.get_children() == ('0',)
    app.kill_filter.set('bot')
    assert app.table.get_children() == ('1',)
    assert not app.table.selection()
    app.keep_unknown.set(True)
    assert app.table.get_children() == ('1', '2')
    app.kill_filter.set('unknown')
    assert app.table.get_children() == ('2',)
    assert app.table.set('2', 'type') == 'Undetermined'
    app.search_var.set('Alpha')
    assert not app.table.get_children()
    assert 'No matching' in app.filter_hint.get()
    app.reset_result_filters()
    assert app.table.get_children() == ('0', '1', '2')
    assert len(app.state.clips) == 3
    app.sort_results('type')
    assert app.table.get_children() == ('1', '0', '2')
