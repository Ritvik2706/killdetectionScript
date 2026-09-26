from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from killcutter import cli, config, outputs
from killcutter.errors import ConfigError, VideoError
from killcutter.models import Clip
from killcutter.ranges import parse_timestamp, resolve_range
from killcutter.ui import workspace


@pytest.mark.parametrize('value,expected', [('90', 90), ('01:30.5', 90.5), ('1:02:03', 3723), ('0', 0)])
def test_timestamp(value, expected):
    assert parse_timestamp(value) == expected


@pytest.mark.parametrize('value', ['nan', 'inf', '-1', '1:60', '1:2:60', '1:2:3:4', '1.5:20', ''])
def test_invalid_timestamp(value):
    with pytest.raises(ValueError):
        parse_timestamp(value)


@pytest.mark.parametrize('kwargs', [dict(start=-1), dict(start=100), dict(end=101), dict(end=0),
                                   dict(limit=0), dict(limit=-1), dict(end=20, limit=5), dict(start=float('nan'))])
def test_invalid_range(kwargs):
    with pytest.raises(ConfigError):
        resolve_range(100, **kwargs)


def test_range_clips_limit_and_preserves_source_time():
    assert resolve_range(100, 80, limit=60) == (80, 100)
    assert resolve_range(100, 20, end=70) == (20, 70)


def test_settings_save_preserves_unknown_data_and_escaping(tmp_path):
    target = tmp_path / 'config.toml'
    target.write_text('# keep\n[detect]\nrate = 2\nregion = [1, 2, 3, 4]\n[custom]\nhello = "world"\n')
    config.save_updates(target, {'detect': {'rate': 8, 'clips_dir': 'C:\\My "clips"'},
                                 'export': {'output_dir': '/tmp/edls'}})
    cfg, _ = config.load(target)
    assert cfg['detect']['region'] == [1, 2, 3, 4]
    assert cfg['detect']['clips_dir'] == 'C:\\My "clips"'
    assert cfg['detect']['rate'] == 8
    assert cfg['custom']['hello'] == 'world'
    assert '# keep' in target.read_text()


def test_settings_reject_malformed_without_overwriting(tmp_path):
    target = tmp_path / 'config.toml'
    target.write_text('[broken')
    with pytest.raises(ValueError):
        config.save_updates(target, {'detect': {'rate': 4}})
    assert target.read_text() == '[broken'


def test_settings_discard_does_not_write(monkeypatch, tmp_path):
    actions = iter([1, len(workspace._FIELDS) + 2])
    monkeypatch.setattr(workspace, 'choose', lambda *a: next(actions))
    monkeypatch.setattr(workspace, 'ask', lambda *a: 'changed')
    cfg = {'detect': {'rate': 4}}
    path = tmp_path / 'config.toml'
    assert workspace.settings(cfg, str(path)) == (cfg, str(path))
    assert cfg == {'detect': {'rate': 4}}
    assert not path.exists()


def test_output_options_and_timecodes():
    cfg = {'detect': {'timestamps_dir': '/tmp/times', 'clips_output_dir': '/tmp/mp4', 'render_clips': True},
           'export': {'output_dir': '/tmp/edl'}}
    parser = cli._build_parser(cfg, cli._global_flags())
    args = parser.parse_args(['detect', '--start', '1:00', '--end', '2:30', '--no-render-clips'])
    assert (args.start, args.end) == (60, 150)
    assert args.timestamps_dir == '/tmp/times'
    assert args.edl_dir == '/tmp/edl'
    assert args.clips_output_dir == '/tmp/mp4'
    assert not args.render_clips
    with pytest.raises(SystemExit):
        parser.parse_args(['detect', '--end', '90', '--limit', '10'])


def test_output_collisions_are_rejected(tmp_path):
    source = tmp_path / 'video.mp4'
    with pytest.raises(ConfigError):
        outputs.validate_paths([source], [source])
    with pytest.raises(ConfigError):
        outputs.validate_paths([source], [tmp_path / 'a', tmp_path / 'a'])


def test_renderer_paths_and_cleanup(monkeypatch, tmp_path):
    monkeypatch.setattr(outputs.shutil, 'which', lambda _: '/usr/bin/ffmpeg')
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        Path(args[-1]).write_bytes(b'video')
        return SimpleNamespace(returncode=0, stderr='')
    monkeypatch.setattr(outputs.subprocess, 'run', run)
    paths = outputs.render_clips('source with spaces.mkv', [Clip(60, 65)], tmp_path / 'clips')
    assert Path(paths[0]).read_bytes() == b'video'
    assert calls[0][calls[0].index('-ss') + 1] == '60'
    assert calls[0][calls[0].index('-t') + 1] == '5'
    monkeypatch.setattr(outputs.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stderr='codec failed'))
    with pytest.raises(VideoError, match='codec failed'):
        outputs.render_clips('source with spaces.mkv', [Clip(60, 65)], tmp_path / 'clips')
    assert list((tmp_path / 'clips').iterdir()) == [Path(paths[0])]
    assert Path(paths[0]).read_bytes() == b'video'


def test_guided_setup_keeps_explicit_output_and_range(monkeypatch):
    args = cli._build_parser({}, cli._global_flags()).parse_args([
        'detect', '--video', 'video.mkv', '--start', '10', '--end', '20',
        '--output', '/tmp/custom.txt', '--edl-output', '/tmp/custom.edl', '--dry-run'])
    monkeypatch.setattr(workspace.video, 'measure', lambda _: (60, 6000, 100))
    monkeypatch.setattr(workspace, 'choose', lambda *a: 0)
    assert workspace.scan_setup(args, {}) is args
    assert (args.start, args.end, args.limit) == (10, 20, None)
    assert args.output == '/tmp/custom.txt'
    assert args.edl_output == '/tmp/custom.edl'


def test_detect_routes_every_output_and_export_setting(monkeypatch, tmp_path):
    cfg = {'export': {'name': 'My sequence', 'fps': 30, 'output_dir': str(tmp_path / 'edls')},
           'detect': {'timestamps_dir': str(tmp_path / 'times'), 'clips_output_dir': str(tmp_path / 'mp4')}}
    args = cli._build_parser(cfg, cli._global_flags()).parse_args(['detect', '--video', 'game.mkv', '--render-clips'])
    detect = Mock(return_value=([Clip(10, 15, 'Player')], True))
    monkeypatch.setattr(cli.detection, 'detect', detect)
    exporter = Mock()
    renderer = Mock()
    monkeypatch.setattr(cli, '_do_export', exporter)
    monkeypatch.setattr(outputs, 'render_clips', renderer)
    monkeypatch.setattr(outputs.shutil, 'which', lambda _: '/usr/bin/ffmpeg')
    assert cli.cmd_detect(args, cfg, None) == 0
    assert (tmp_path / 'times/game_timestamps.txt').read_text() == '10.000 15.000 Player\n'
    assert exporter.call_args.kwargs == {'name': 'My sequence', 'fps': 30, 'output': str(tmp_path / 'edls/game_highlights.edl')}
    assert renderer.call_args.args[2] == str(tmp_path / 'mp4')


def test_dry_run_creates_no_output_directories(monkeypatch, tmp_path):
    args = cli._build_parser({}, cli._global_flags()).parse_args([
        'detect', '--video', 'game.mkv', '--timestamps-dir', str(tmp_path / 'times'),
        '--edl-dir', str(tmp_path / 'edls'), '--dry-run', '--render-clips'])
    monkeypatch.setattr(cli.detection, 'detect', Mock(return_value=([Clip(10, 15)], True)))
    assert cli.cmd_detect(args, {}, None) == 0
    assert list(tmp_path.iterdir()) == []


def test_interrupted_scan_saves_timestamps_without_export(monkeypatch, tmp_path):
    args = cli._build_parser({}, cli._global_flags()).parse_args([
        'detect', '--video', 'game.mkv', '--timestamps-dir', str(tmp_path), '--render-clips'])
    monkeypatch.setattr(cli.detection, 'detect', Mock(return_value=([Clip(10, 15)], False)))
    monkeypatch.setattr(outputs.shutil, 'which', lambda _: '/usr/bin/ffmpeg')
    exporter, renderer = Mock(), Mock()
    monkeypatch.setattr(cli, '_do_export', exporter)
    monkeypatch.setattr(outputs, 'render_clips', renderer)
    assert cli.cmd_detect(args, {}, None) == 130
    assert (tmp_path / 'game_timestamps.txt').exists()
    exporter.assert_not_called()
    renderer.assert_not_called()


def test_detection_ignores_frames_before_start_and_bounds_highlights(monkeypatch, tmp_path):
    import numpy as np
    from killcutter import detection
    source = tmp_path / 'video.mkv'
    source.touch()
    cap = Mock()
    cap.get.return_value = 60
    monkeypatch.setattr(detection.cv2, 'VideoCapture', lambda _: cap)
    monkeypatch.setattr(detection, '_measure_duration', lambda *a: 100)
    monkeypatch.setattr(detection, '_samples', lambda *a: iter([
        (5, np.zeros((60, 60, 3), dtype=np.uint8)),
        (20, np.zeros((60, 60, 3), dtype=np.uint8)),
        (30, np.zeros((60, 60, 3), dtype=np.uint8)),
    ]))
    monkeypatch.setattr(detection, '_banner_visible', lambda *a: True)
    monkeypatch.setattr(detection, 'read_banner', lambda *a: (True, 'Player'))
    reporter = Mock()
    clips, complete = detection.detect(str(source), detection.DetectionSettings((0, 0, 10, 10), end_offset=50),
                                        reporter, start=20, end=30)
    assert complete
    assert clips == [Clip(20, 30, 'Player')]
    reporter.frame.assert_called_once_with(20, True)
    cap.release.assert_called_once()


def test_cancellable_renderer_preserves_previous_output(monkeypatch, tmp_path):
    monkeypatch.setattr(outputs.shutil, 'which', lambda _: '/usr/bin/ffmpeg')
    target = tmp_path / 'source_highlight_001.mp4'
    target.write_bytes(b'previous complete output')
    monkeypatch.setattr(outputs, '_run_cancellable', lambda *args: None)
    assert outputs.render_clips('source.mkv', [Clip(1, 3)], tmp_path, cancelled=lambda: False) == []
    assert target.read_bytes() == b'previous complete output'
    assert list(tmp_path.iterdir()) == [target]


def test_cancellable_process_is_terminated_and_reaped(monkeypatch):
    process = Mock()
    process.poll.return_value = -15
    monkeypatch.setattr(outputs.subprocess, 'Popen', lambda *a, **kw: process)
    assert outputs._run_cancellable(['ffmpeg'], lambda: True) is None
    process.terminate.assert_called_once()
    process.communicate.assert_called_once_with(timeout=2)
