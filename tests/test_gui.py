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


def test_gui_import_seek_settings_and_preset_colour(app, tmp_path):
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


def test_gui_presets_save_restore_and_result_capabilities(app):
    from killcutter import presets
    app.preset_library.save(presets.Preset('status-light', 'Status light', 'color', label='Light on'))
    app._refresh_presets(app.preset_library.items['status-light'])
    recipe = app.active_preset
    assert recipe.detector == 'color'
    assert presets.Library(app.config_path).items[recipe.id] == recipe
    assert app._settings().preset == recipe
    assert not app._settings().traits
    # Existing Warzone results keep their capabilities when the next recipe changes.
    assert app.state.player_traits
    app.state.player_traits = False
    app.state.preset_name = recipe.name
    app.state.clips = [Clip(1, 2, 'Light on')]
    app.kill_filter.set('bot')
    app.filter_results()
    assert app.table.get_children() == ('0',)
    assert 'type' not in app.table.cget('displaycolumns')
    assert not app.trait_filters.winfo_manager()
    app.state.player_traits = True
    app.reset_result_filters()
    assert 'type' in app.table.cget('displaycolumns')
    assert app.trait_filters.winfo_manager() == 'pack'


def test_gui_color_service_does_not_require_tesseract(app, monkeypatch):
    from killcutter import presets
    from killcutter.gui import services
    from killcutter.gui.state import Media
    recipe = presets.Preset('color-test', 'Colour test', 'color')
    app.active_preset = recipe
    monkeypatch.setattr(services.environment, 'configure_tesseract', lambda: pytest.fail('Colour needs no OCR'))
    monkeypatch.setattr(services.detection, 'detect', lambda *a, **kw: ([], True))
    assert services.analyze(app.jobs, Media('test.mp4', 30, 10, 640, 360), app._settings(), 0, 10) == ([], True)


def test_gui_partial_render_tracks_only_completed_files(app, monkeypatch, tmp_path):
    from killcutter.gui.state import Media
    from killcutter.gui import app as module
    app.state.media = Media(str(tmp_path / 'source.mp4'), 30, 10, 320, 180)
    app.state.clips = [Clip(1, 2, 'One'), Clip(3, 4, 'Two')]
    app.filter_results()
    app.select_all_results()
    monkeypatch.setattr(module.filedialog, 'askdirectory', lambda **kw: str(tmp_path))
    def render(source, clips, target, *, progress, cancelled):
        progress(1, 2, str(tmp_path / 'one.mp4'))
        app.jobs.cancel.set()
        return [str(tmp_path / 'one.mp4')]
    monkeypatch.setattr(module.outputs, 'render_clips', render)
    app.export_selection('mp4')
    pump(app, lambda: app.working is None)
    assert app.exported_ids == {'0'}
    assert not app.exported
    assert 'Export stopped' in app.status.get()


def test_gui_native_playback(app, tmp_path):
    if os.environ.get('KILLCUTTER_PLAYBACK_TESTS') != '1':
        pytest.skip('Opt-in native libmpv test on a display with audio/video support.')
    import cv2
    import numpy as np
    source = tmp_path / 'playback.avi'
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'MJPG'), 20, (320, 180))
    assert writer.isOpened()
    for i in range(60):
        writer.write(np.full((180, 320, 3), i*3, dtype=np.uint8))
    writer.release()
    app.deiconify()
    app.open_file(str(source))
    pump(app, lambda: app.working is None)
    app.toggle_playback()
    pump(app, lambda: app.state.position > .3, timeout=10)
    app.toggle_playback()
    assert app.player_paused
    app.set_volume(0)
    app.stop_playback()
    pump(app, lambda: app.player is None, timeout=10)


def test_gui_dragged_region_maps_to_source(app):
    from types import SimpleNamespace
    from PIL import Image
    from killcutter.gui.widgets import Preview
    canvas = Preview(app, width=400, height=400)
    canvas.pack()
    app.deiconify()
    app.update()
    canvas.set_image(Image.new('RGB', (800, 400)))
    regions = []
    canvas.on_region = regions.append
    width, height = canvas.winfo_width(), canvas.winfo_height()
    from killcutter.gui.state import image_rect
    x, y, w, h = image_rect(800, 400, width, height)
    canvas._click(SimpleNamespace(x=x+w//4, y=y+h//4))
    canvas._end_region(SimpleNamespace(x=x+3*w//4, y=y+3*h//4))
    assert len(regions) == 1
    assert regions[0] == pytest.approx((.25, .25, .5, .5), abs=.015)
    canvas.destroy()


def test_gui_presets_have_one_editor_and_safe_management_actions(app, monkeypatch):
    from killcutter.presets import Preset
    from tkinter import simpledialog, messagebox
    assert not hasattr(app, 'advanced_editor')
    assert app.preset_edit_button.instate(['disabled'])
    built_in = app.preset_menu()
    assert built_in.entrycget(0, 'state') == 'disabled'
    assert built_in.entrycget(4, 'state') == 'disabled'
    built_in.destroy()
    original = Preset('my-text', 'My text', 'text', text='Victory')
    app.preset_library.save(original)
    app._refresh_presets(original)
    assert app.preset_edit_button.instate(['!disabled'])
    assert 'Victory' in app.preset_summary.get()
    app.duplicate_preset()
    duplicate = app.active_preset
    assert duplicate.id != original.id
    assert duplicate.text == original.text
    assert duplicate.name == 'My text (copy)'
    monkeypatch.setattr(simpledialog, 'askstring', lambda *a, **kw: 'Renamed copy')
    app.rename_preset()
    assert app.active_preset.name == 'Renamed copy'
    assert app.preset_library.items[original.id] == original
    monkeypatch.setattr(messagebox, 'askyesno', lambda *a, **kw: False)
    app.delete_preset()
    assert duplicate.id in app.preset_library.items
    monkeypatch.setattr(messagebox, 'askyesno', lambda *a, **kw: True)
    app.delete_preset()
    assert duplicate.id not in app.preset_library.items
    assert app.active_preset.id == 'warzone'
    app.working = 'scan'
    app._update_controls()
    assert app.preset_new_button.instate(['disabled'])


def test_old_inspector_preference_migrates_to_presets():
    from killcutter.gui.preferences import load
    assert load({'gui': {'page': 'inspector'}}).page == 'presets'


@pytest.fixture
def preset_wizard(app, monkeypatch):
    from PIL import Image
    from killcutter.gui import preset_wizard as wizard, services
    from killcutter.gui.state import Media
    from tkinter import filedialog
    monkeypatch.setattr(filedialog, 'askopenfilename', lambda **kwargs: '/tmp/example.mp4')
    monkeypatch.setattr(wizard, 'open_media', lambda path: (
        Media(path, 30, 60, 320, 180), Image.new('RGB', (320, 180), '#123456')))
    monkeypatch.setattr(services, 'read_frame', lambda path, seconds: Image.new('RGB', (320, 180), '#345678'))
    app.create_preset()
    assert app.library_visible
    assert 'sample video' in app.picker_heading.cget('text')
    dialog = app.accept_picker_recording('/tmp/example.mp4')
    assert not app.library_visible
    pump(app, lambda: dialog.ready)
    yield dialog
    if dialog.winfo_exists():
        dialog.destroy()


def test_gui_guided_preset_seek_select_save(app, preset_wizard):
    from killcutter import presets
    dialog = preset_wizard
    previous = app.active_preset
    dialog.time_var.set('00:12.500')
    dialog.go_to_time()
    assert not dialog.ready
    assert dialog.next_button.instate(['disabled'])
    pump(app, lambda: dialog.ready)
    assert dialog.position == 12.5
    dialog.step_frame(1)
    pump(app, lambda: dialog.ready)
    assert dialog.position == pytest.approx(12.5 + 1/30)
    dialog.next_step()
    assert dialog.step == 2
    assert app.active_preset == previous
    dialog.kind_var.set('A colour appears')
    dialog.change_kind()
    dialog.select_region((.1, .2, .3, .4))
    dialog.name_var.set('My indicator')
    dialog.save()
    assert 'Pick a pixel colour' in dialog.message.get()
    dialog.select_pixel(4, 5, (18, 52, 86))
    dialog.back()
    dialog.next_step()
    assert dialog.region == (.1, .2, .3, .4)
    dialog.save()
    recipe = app.active_preset
    assert recipe.name == 'My indicator'
    assert recipe.region == (.1, .2, .3, .4)
    assert recipe.color == (18, 52, 86)
    assert app._settings().preset == recipe
    assert recipe.name in app.active_preset_text.get()
    assert presets.Library(app.config_path).items[recipe.id] == recipe
    assert app.state.media is None  # the sample video does not replace the recording


def test_gui_guided_preset_validation_and_cancel(app, preset_wizard):
    dialog = preset_wizard
    previous = app.active_preset
    dialog.time_var.set('nonsense')
    dialog.go_to_time()
    assert 'Use seconds' in dialog.message.get()
    dialog.time_var.set('01:00')
    dialog.go_to_time()
    assert 'before' in dialog.message.get()
    dialog.next_step()
    dialog.save()
    assert 'name' in dialog.message.get()
    dialog.name_var.set('Text signal')
    dialog.save()
    assert 'phrase' in dialog.message.get()
    dialog.kind_var.set('Loud sounds')
    dialog.change_kind()
    assert dialog.area_button.instate(['disabled'])
    assert dialog.selection_preview.on_region is None
    assert dialog.selection_preview.on_pixel is None
    dialog.destroy()
    assert app.active_preset == previous
    assert len(app.preset_library.items) == 1


def test_gui_new_preset_cancel_file_picker_leaves_state(app, monkeypatch):
    from tkinter import filedialog
    monkeypatch.setattr(filedialog, 'askopenfilename', lambda **kwargs: pytest.fail('Unexpected native video picker'))
    previous = app.active_preset
    assert app.create_preset() is None
    assert app.library_visible
    app.close_recording_picker()
    assert app.grab_current() is None
    assert app.active_preset == previous
    assert not hasattr(app, 'advanced_editor')


def test_gui_controls_follow_theme_and_keep_native_interaction(app):
    from tkinter import ttk
    from killcutter.gui import theme
    combo = app.preset_selectors[0]
    theme.style_popdown(combo)
    popup = str(app.tk.call('ttk::combobox::PopdownWindow', str(combo)))
    for palette in ('Daylight', 'Graphite', 'Midnight'):
        app.theme_var.set(palette)
        app.apply_appearance(persist=False)
        assert app.tk.call(popup + '.f.l', 'cget', '-background') == theme.FIELD
        assert app.tk.call(popup + '.f.l', 'cget', '-selectbackground') == theme.SELECTED
        style = ttk.Style(app)
        assert style.lookup('TCombobox', 'foreground', ('disabled', 'readonly')) == theme.MUTED
        assert 'Themed.downarrow' in str(style.layout('TCombobox'))
        assert 'Scrollbar.thumb' in str(style.layout('Vertical.TScrollbar'))
    # Exercise native hit testing and drag bindings, not just style declarations.
    window = __import__('tkinter').Toplevel(app)
    window.geometry('400x180')
    scale = ttk.Scale(window, from_=0, to=100)
    scale.pack(fill='x', padx=20, pady=20)
    scroll = ttk.Scrollbar(window, orient='horizontal')
    scroll.pack(fill='x', padx=20)
    scroll.set(.2, .5)
    app.update()
    assert 'slider' in scale.identify(*map(int, scale.coords(0)))
    start = tuple(map(int, scale.coords(0)))
    end = tuple(map(int, scale.coords(80)))
    scale.event_generate('<ButtonPress-1>', x=start[0], y=start[1])
    scale.event_generate('<B1-Motion>', x=end[0], y=end[1])
    scale.event_generate('<ButtonRelease-1>', x=end[0], y=end[1])
    assert 75 < scale.get() < 85
    assert 'thumb' in scroll.identify(int(scroll.winfo_width()*.35), scroll.winfo_height()//2)
    window.destroy()


def test_gui_preview_reuses_frame_when_drawing_selection(app, monkeypatch):
    from PIL import Image
    source = Image.new('RGB', (3840, 2160), '#123456')
    app.update_idletasks()
    app.preview.set_image(source)
    original = app.preview.photo
    resize = Mock(wraps=source.resize)
    monkeypatch.setattr(source, 'resize', resize)
    for width in (.2, .3, .4):
        app.preview.region = (.1, .1, width, .2)
        app.preview.redraw()
    resize.assert_not_called()
    assert app.preview.photo is original
    app.preview.set_image(Image.new('RGB', (3840, 2160), '#654321'))
    assert app.preview.photo is not original


def test_gui_scroll_form_only_scrolls_overflowing_content(app):
    import tkinter as tk
    from types import SimpleNamespace
    from killcutter.gui.widgets import AutoScrollbar, ScrollForm

    window = tk.Toplevel(app)
    window.overrideredirect(True)
    window.geometry('420x300')
    form = ScrollForm(window)
    form.pack(fill='both', expand=True)
    content = tk.Frame(form.body, width=200, height=100)
    content.pack(fill='x')
    app.update()
    bar = next(child for child in form.winfo_children() if isinstance(child, AutoScrollbar))
    assert not bar.winfo_manager()
    form._wheel(SimpleNamespace(num=5, delta=0))
    assert form.canvas.yview() == (0.0, 1.0)

    content.configure(height=700)
    app.update()
    assert bar.winfo_manager() == 'pack'
    assert bar.winfo_x() - (form.canvas.winfo_x() + form.canvas.winfo_width()) >= 10
    form.canvas.yview_moveto(1)
    app.update()
    assert form.canvas.yview()[0] > 0

    content.configure(height=100)
    app.update()
    assert not bar.winfo_manager()
    assert form.canvas.yview() == (0.0, 1.0)
    window.destroy()


def test_gui_library_browses_filters_and_opens(app, tmp_path, monkeypatch):
    from killcutter.gui.library import Recording
    source = tmp_path / 'recording.mp4'
    source.touch()
    edl = tmp_path / 'recording_highlights.edl'
    edl.touch()
    monkeypatch.setattr('killcutter.gui.library_views.scan_directory',
                        lambda *args: ([Recording(source, 1024, time.time() - 3600, 90, edl, None)], {}))
    app.open_file()
    pump(app, lambda: bool(app.library_table.get_children()))
    assert app.library_table.item(str(source), 'values')[1] == 'Done'
    app.library_filter.set('Pending')
    assert not app.library_table.get_children()
    app.library_filter.set('All')
    app.library_search.set('missing')
    assert not app.library_table.get_children()
    app.library_search.set('recording')
    app.library_table.selection_set(str(source))
    app.describe_library_recording()
    assert str(edl) in app.library_detail.get()
    opened = []
    monkeypatch.setattr(app, 'open_file', opened.append)
    app.open_library_recording()
    assert opened == [str(source)]
    app.receive_library(app.library_generation - 1, ([], {}), None)
    assert app.library_table.get_children()


def test_gui_open_recording_uses_metadata_picker_before_replacing_workspace(app, monkeypatch):
    from tkinter import filedialog, messagebox
    monkeypatch.setattr(filedialog, 'askopenfilename', lambda **kwargs: pytest.fail('Native picker opened'))
    monkeypatch.setattr(messagebox, 'askyesno', lambda *args, **kwargs: pytest.fail('Prompted before a video was selected'))
    app.state.clips = [Clip(0, 1, 'Unsaved')]
    app.exported = False
    app.show('results')
    app.open_button.invoke()
    assert app.current_page == 'results'
    assert app.library_visible
    assert app.grab_current() == app.recording_picker
    assert 'library' not in app.nav
    assert app.state.clips[0].name == 'Unsaved'
    assert app.working is None
    app.close_recording_picker()
    assert not app.library_visible
    assert app.grab_current() is None
    assert app.current_page == 'results'


def test_gui_picker_closes_only_when_recording_is_accepted(app, tmp_path, monkeypatch):
    from tkinter import messagebox
    app.state.clips = [Clip(0, 1, 'Unsaved')]
    app.exported = False
    app.open_file()
    monkeypatch.setattr(messagebox, 'askyesno', lambda *args, **kwargs: False)
    source = str(tmp_path / 'chosen.mp4')
    app.open_file(source)
    assert app.library_visible
    assert app.working is None
    monkeypatch.setattr(messagebox, 'askyesno', lambda *args, **kwargs: True)
    submit = Mock()
    monkeypatch.setattr(app.jobs, 'submit', submit)
    app.open_file(source)
    assert not app.library_visible
    assert app.grab_current() is None
    assert app.working == 'open'
    assert submit.call_args.args[0] == 'open'
    assert submit.call_args.args[2] == source


def test_gui_loads_latest_edl_switches_and_keeps_results_on_error(app, tmp_path, monkeypatch):
    from PIL import Image
    from killcutter.gui.state import Media
    from killcutter.export import ExportPlan, build_edl
    media = Media(str(tmp_path / 'session.mp4'), 30, 100, 320, 180)
    monkeypatch.setattr('killcutter.gui.app.open_media', lambda path: (media, Image.new('RGB', (320, 180))))
    app.saved_values['export', 'output_dir'] = str(tmp_path)
    old, new = tmp_path / 'old.edl', tmp_path / 'new.edl'
    for path, start, name in [(old, 10, 'Old player'), (new, 30, 'New player')]:
        path.write_text(build_edl(ExportPlan([Clip(start, start + 5, name)], 'Test', 'session.mp4', 30, False, str(path), '', '', 5)))
    os.utime(old, (1, 1))
    app.open_file(media.path)
    pump(app, lambda: app.working is None and app.edl_path == str(new))
    assert app.state.clips[0].name == 'New player'
    assert app.state.clips[0].start == 30
    app.edl_selector.current(app.edl_choices.index(str(old)))
    app.choose_saved_edl()
    pump(app, lambda: app.working is None)
    assert app.edl_path == str(old)
    assert app.state.clips[0].name == 'Old player'
    old.write_text('broken EDL')
    app.load_edl(str(old))
    pump(app, lambda: app.working is None)
    assert app.state.clips[0].name == 'Old player'
    assert 'Could not load' in app.edl_note.get()
    app.state.clips[0].name = 'Unsaved edit'
    app.exported = False
    monkeypatch.setattr('tkinter.messagebox.askyesno', lambda *args, **kwargs: False)
    app.load_edl(str(new))
    assert app.state.clips[0].name == 'Unsaved edit'
    assert app.edl_path == str(old)


def test_gui_preset_sample_uses_current_video_without_replacing_workspace(app, monkeypatch):
    from killcutter.gui.state import Media
    from killcutter.gui import preset_wizard
    from tkinter import filedialog
    app.state.media = Media('/tmp/current.mp4', 30, 60, 320, 180)
    app.state.clips = [Clip(10, 15, 'Keep this highlight')]
    app.exported = False
    app.show('presets')
    launched = []
    monkeypatch.setattr(preset_wizard, 'PresetWizard', lambda parent, path, preset=None: launched.append((path, preset)))
    monkeypatch.setattr(filedialog, 'askopenfilename', lambda **kwargs: pytest.fail('Unexpected native video picker'))
    app.create_preset()
    assert app.library_open_button.cget('text') == 'Choose frame →'
    assert app.picker_current_button.winfo_manager() == 'pack'
    app.picker_current_button.invoke()
    assert launched == [('/tmp/current.mp4', None)]
    assert app.current_page == 'presets'
    assert app.state.clips[0].name == 'Keep this highlight'
    assert not app.exported
    assert not app.library_visible
    app.open_file()
    assert app.picker_heading.cget('text') == 'Choose a recording'
    assert app.library_open_button.cget('text') == 'Open recording'
    assert not app.picker_current_button.winfo_manager()
    app.close_recording_picker()


def test_gui_preset_ocr_reads_precise_area_and_rejects_stale_results(app, preset_wizard, monkeypatch):
    dialog = preset_wizard
    dialog.next_step()
    assert dialog.kind_var.get() == 'Text recognition (OCR)'
    for key, value in zip(('X', 'Y', 'Width', 'Height'), (20, 10, 80, 40)):
        dialog.region_fields[key].set(str(value))
    assert dialog.apply_region_fields()
    assert dialog.crop_preview.image.size == (80, 40)
    calls = []
    def inspect(image, region):
        calls.append((image.size, region))
        return 'VICTORY\nPlayer One'
    monkeypatch.setattr('killcutter.gui.preset_precision.inspect_region_text', inspect)
    dialog.inspect_ocr()
    pump(app, lambda: not dialog.ocr_pending)
    assert calls == [((320, 180), dialog.region)]
    assert 'Player One' in dialog.ocr_output.get('1.0', 'end')
    dialog.use_ocr_text()
    assert dialog.text_var.get() == 'VICTORY Player One'
    previous = dialog.inspection_generation
    dialog.select_region((0, 0, .5, .5))
    dialog.receive_ocr(previous, 'Stale OCR text', None)
    assert dialog.ocr_text == ''
    assert dialog.use_ocr_button.instate(['disabled'])
    dialog.region_fields['Width'].set('9999')
    before = dialog.region
    assert not dialog.apply_region_fields()
    assert dialog.region == before
    dialog.region_fields['Width'].set('160')
    assert dialog.apply_region_fields()
    dialog.inspect_ocr()
    pump(app, lambda: not dialog.ocr_pending)
    dialog.receive_ocr(dialog.inspection_generation, None, 'Tesseract missing')
    assert 'Tesseract missing' in dialog.ocr_status.get()


def test_gui_multiple_videos_run_sequentially_and_preserve_workspace(app, monkeypatch):
    from killcutter.gui.library import Recording
    from killcutter.gui.state import Media
    from pathlib import Path
    paths = [Path('/tmp/first.mp4'), Path('/tmp/second.mp4')]
    monkeypatch.setattr('killcutter.gui.library_views.scan_directory', lambda *args: (
        [Recording(p, 100, 0, 60, None, None) for p in paths], {}))
    original = app.state
    original.clips = [Clip(1, 2, 'Unsaved workspace')]
    app.exported = False
    calls = []
    def run(jobs, path, *args):
        calls.append(path)
        return {'status': 'Done', 'clips': [], 'edl': None, 'timestamps': None,
                'media': Media(path, 30, 60, 1, 1), 'error': None}
    monkeypatch.setattr('killcutter.gui.queue_views.analyze_queued', run)
    app.open_file()
    pump(app, lambda: len(app.library_table.get_children()) == 2)
    app.library_table.selection_set([str(p) for p in paths])
    app.describe_library_recording()
    assert app.library_open_button.instate(['disabled'])
    assert app.library_queue_button.instate(['!disabled'])
    app.enqueue_recordings()
    assert len(app.analysis_queue) == 2
    assert not calls
    app.start_queue()
    pump(app, lambda: not app.queue_running)
    assert calls == [str(p) for p in paths]
    assert all(row['status'] == 'Done' for row in app.analysis_queue)
    assert app.state is original
    assert app.state.clips[0].name == 'Unsaved workspace'
    assert not app.exported


def test_gui_queue_stop_leaves_pending_videos_and_continues_after_failure(app, monkeypatch):
    from threading import Event
    entered = Event()
    def run(jobs, path, *args):
        if path == '/tmp/first.mp4':
            entered.set()
            jobs.cancel.wait(3)
            return {'status': 'Stopped', 'clips': [], 'error': None}
        return {'status': 'Failed', 'clips': [], 'error': 'Unreadable video'}
    monkeypatch.setattr('killcutter.gui.queue_views.analyze_queued', run)
    app.analysis_queue = [{'path': p, 'status': 'Pending', 'result': None}
                          for p in ('/tmp/first.mp4', '/tmp/second.mp4', '/tmp/third.mp4')]
    app.show_analysis_queue()
    app.start_queue()
    pump(app, entered.is_set)
    app.stop_queue()
    pump(app, lambda: not app.queue_running)
    assert [r['status'] for r in app.analysis_queue] == ['Stopped', 'Pending', 'Pending']
    app.start_queue()
    pump(app, lambda: not app.queue_running)
    assert [r['status'] for r in app.analysis_queue] == ['Stopped', 'Failed', 'Failed']
