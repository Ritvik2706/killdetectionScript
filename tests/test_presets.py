"""Preset persistence and real, game-independent event detection."""
from dataclasses import replace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from killcutter import detection, generic_detection, presets
from killcutter.errors import ConfigError


def test_library_round_trip_and_builtin_protection(tmp_path):
    library = presets.Library(tmp_path / 'config.toml')
    recipe = presets.Preset('red', 'Red indicator', 'color', region=(.1, .2, .3, .4))
    library.save(recipe)
    restored = presets.Library(tmp_path / 'config.toml')
    assert restored.items['red'] == recipe
    assert restored.items['warzone'] == presets.WARZONE
    with pytest.raises(ConfigError):
        library.save(presets.WARZONE)
    (library.folder / 'broken.json').write_text('[]')
    restored = presets.Library(tmp_path / 'config.toml')
    assert len(restored.errors) == 1
    assert restored.items['red'] == recipe


@pytest.mark.parametrize('changes', [
    {'version': 2}, {'region': (0, 0, 0, 1)}, {'region': (.9, 0, .5, 1)},
    {'region': (float('nan'), 0, 1, 1)}, {'coverage': 0}, {'coverage': float('nan')},
    {'color': (256, 0, 0)}, {'tolerance': -1}, {'detector': 'python'}, {'id': '../escape'},
])
def test_invalid_recipes_rejected(changes):
    with pytest.raises(ConfigError):
        replace(presets.Preset('red', 'Red', 'color'), **changes).validate()


def test_scaled_color_region_and_coverage():
    recipe = presets.Preset('red', 'Red', 'color', region=(.5, .5, .5, .5), coverage=.5)
    for size in (40, 80):
        frame = np.zeros((size, size, 3), dtype=np.uint8)
        frame[size//2:, size//2:] = (0, 0, 255)
        assert generic_detection.matches(frame, recipe)
        assert not generic_detection.matches(frame, replace(recipe, region=(0, 0, .5, .5)))
    assert recipe.box(80, 40) == (40, 20, 40, 20)


def test_literal_text_matching_is_not_warzone_specific(monkeypatch):
    monkeypatch.setattr(detection, '_ocr_lines', lambda roi: ['GOAL', '  SCORED  '])
    frame = np.zeros((40, 40, 3), dtype=np.uint8)
    assert generic_detection.matches(frame, presets.Preset('goal', 'Goal', text='goal scored'))
    assert not generic_detection.matches(frame, presets.Preset('goal', 'Goal', text='ENEMY DOWNED'))


@pytest.fixture
def indicator_video(tmp_path):
    path = tmp_path / 'indicator.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (80, 60))
    assert writer.isOpened()
    for i in range(60):
        frame = np.zeros((60, 80, 3), dtype=np.uint8)
        if 10 <= i < 20 or 35 <= i < 45:
            frame[:] = (0, 0, 255)
        writer.write(frame)
    writer.release()
    return path


def test_general_scan_detects_transitions_without_warzone_or_ocr(indicator_video, monkeypatch):
    monkeypatch.setattr(detection, '_banner_visible', lambda *a: pytest.fail('Warzone gate used'))
    monkeypatch.setattr(detection, '_ocr_lines', lambda *a: pytest.fail('OCR used for colour'))
    recipe = presets.Preset('red', 'Red indicator', 'color', coverage=.8, label='Indicator on')
    settings = detection.DetectionSettings((0, 0, 1, 1), preset=recipe, rate=10, offset=.2,
                                           end_offset=.3, cooldown=.1, merge_gap=0)
    reporter = Mock()
    clips, completed = detection.detect(str(indicator_video), settings, reporter)
    assert completed and len(clips) == 2
    assert [c.name for c in clips] == ['Indicator on', 'Indicator on']
    assert clips[0].start == pytest.approx(.8, abs=.11)
    assert clips[1].start == pytest.approx(3.3, abs=.11)
    assert all(not c.traits for c in clips)
    assert reporter.kill.call_count == 2
    settings.merge_gap = 4
    merged, _ = detection.detect(str(indicator_video), settings, Mock())
    assert len(merged) == 1
    assert merged[0].start == clips[0].start and merged[0].end == clips[1].end


def test_general_scan_cancel_keeps_events(indicator_video):
    reporter = Mock()
    settings = detection.DetectionSettings((0, 0, 1, 1), preset=presets.Preset('red', 'Red', 'color'), rate=10)
    clips, completed = detection.detect(str(indicator_video), settings, reporter,
                                       cancelled=lambda: reporter.kill.called)
    assert not completed and len(clips) == 1
    reporter.aborted.assert_called_once()


def test_motion_and_scene_compare_consecutive_samples():
    dark = np.zeros((40, 40, 3), dtype=np.uint8)
    light = np.full((40, 40, 3), 255, dtype=np.uint8)
    for detector in ('motion', 'scene'):
        matcher = generic_detection.FrameMatcher(presets.Preset('change', 'Change', detector, coverage=.5))
        assert not matcher.matches(dark)
        assert not matcher.matches(dark)
        assert matcher.matches(light)
        assert not matcher.matches(light)
        assert matcher.matches(dark)


def test_library_delete_preserves_builtin(tmp_path):
    library = presets.Library(tmp_path / 'config.toml')
    library.save(presets.Preset('red', 'Red', 'color'))
    library.delete('red')
    assert list(presets.Library(tmp_path / 'config.toml').items) == ['warzone']
    with pytest.raises(ConfigError):
        library.delete('warzone')


def test_cli_accepts_general_preset(indicator_video, tmp_path):
    from killcutter import cli, export
    recipe = tmp_path / 'recipe.json'
    presets.save(recipe, presets.Preset('red', 'Red', 'color', label='Indicator'))
    target = tmp_path / 'moments.txt'
    assert cli.main(['detect', '--video', str(indicator_video), '--preset', str(recipe),
                     '--output', str(target), '--no-export', '--merge-gap', '0', '--cooldown', '0']) == 0
    assert len(export.read_timestamps(target)) == 2


def test_audio_sampling_and_cancellation(tmp_path):
    import shutil
    import wave
    from killcutter.audio_detection import samples
    if not shutil.which('ffmpeg'):
        pytest.skip('FFmpeg required for real audio integration')
    source = tmp_path / 'levels.wav'
    pcm = np.concatenate([np.zeros(8000), np.sin(np.arange(8000)*.2)*16000, np.zeros(8000)]).astype('<i2')
    with wave.open(str(source), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(pcm.tobytes())
    levels = list(samples(str(source), 0, 3, 4))
    assert len(levels) == 12
    assert levels[0][1] < -90
    assert -12 < levels[5][1] < -8
    assert levels[8][1] < -90
    stream = samples(str(source), 0, 3, 4, cancelled=lambda: True)
    with pytest.raises(KeyboardInterrupt):
        next(stream)


def test_audio_preset_runs_through_shared_scan(indicator_video, tmp_path):
    import shutil
    import subprocess
    import wave
    if not shutil.which('ffmpeg'):
        pytest.skip('FFmpeg required')
    sound = tmp_path / 'sound.wav'
    values = np.concatenate([np.zeros(8000), np.sin(np.arange(8000)*.2)*16000, np.zeros(8000)]).astype('<i2')
    with wave.open(str(sound), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(values.tobytes())
    video = tmp_path / 'with-audio.mkv'
    result = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(indicator_video), '-i', str(sound),
                             '-map', '0:v:0', '-map', '1:a:0', '-c', 'copy', '-shortest', str(video)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    recipe = presets.Preset('loud', 'Loud sound', 'audio', label='Sound starts', audio_db=-24)
    settings = detection.DetectionSettings((0, 0, 1, 1), preset=recipe, rate=4,
                                           offset=.1, end_offset=.2, cooldown=0, merge_gap=0)
    clips, completed = detection.detect(str(video), settings, Mock())
    assert completed and len(clips) == 1
    assert clips[0].name == 'Sound starts'
    assert clips[0].start == pytest.approx(.9, abs=.05)


def test_pixel_area_roundtrip_does_not_add_or_drop_boundary_pixels():
    from killcutter.presets import Preset
    for width, height in ((320, 180), (1920, 1080), (3840, 2160)):
        for x in (0, 2, 31, width - 100):
            preset = Preset('precise', 'Precise', region=(x/width, 10/height, 100/width, 50/height))
            assert preset.box(width, height) == (x, 10, 100, 50)


def test_ocr_inspection_uses_detector_crop_and_timeout(monkeypatch):
    import numpy as np
    from PIL import Image
    from killcutter.gui import services
    image = Image.new('RGB', (320, 180), (10, 20, 30))
    monkeypatch.setattr(services.environment, 'configure_tesseract', lambda: True)
    def ocr(roi, *, timeout):
        assert roi.shape == (50, 100, 3)
        assert np.array_equal(roi[0, 0], [30, 20, 10])
        assert timeout == 15
        return ['VICTORY', 'Player']
    monkeypatch.setattr(services.detection, '_ocr_lines', ocr)
    assert services.inspect_region_text(image, (2/320, 10/180, 100/320, 50/180)) == 'VICTORY\nPlayer'
