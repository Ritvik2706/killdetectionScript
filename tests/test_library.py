from pathlib import Path

from killcutter.gui.library import scan_directory, relative_age


def test_inventory_matches_exact_exports_and_caches_metadata(tmp_path, monkeypatch):
    videos = tmp_path / 'videos'
    edls = tmp_path / 'edls'
    stamps = tmp_path / 'stamps'
    for folder in (videos, edls, stamps):
        folder.mkdir()
    for name in ('one.mp4', 'one_more.MKV', 'two.webm', 'bad.mov'):
        (videos / name).touch()
    (videos / 'ignore.txt').touch()
    (videos / 'directory.mp4').mkdir()
    (edls / 'one_highlights.edl').touch()
    (edls / 'two.edl').touch()
    (stamps / 'one_more_timestamps.txt').touch()
    calls = []
    def measure(path):
        calls.append(path)
        if Path(path).stem == 'bad':
            raise ValueError('Unreadable video')
        return 30, 1800, 60
    monkeypatch.setattr('killcutter.gui.library.video.measure', measure)
    rows, cache = scan_directory(videos, edls, stamps, {})
    by_name = {r.path.name: r for r in rows}
    assert len(rows) == 4
    assert by_name['one.mp4'].status == 'Done'
    assert by_name['two.webm'].status == 'Done'
    assert by_name['one_more.MKV'].status == 'Timestamps'
    assert by_name['bad.mov'].duration is None
    assert by_name['bad.mov'].status == 'Pending'
    (edls / 'one_highlights.edl').unlink()
    rows, cache = scan_directory(videos, edls, stamps, cache)
    assert len(calls) == 4
    assert next(r for r in rows if r.path.name == 'one.mp4').status == 'Pending'
    (videos / 'one.mp4').write_bytes(b'changed')
    scan_directory(videos, edls, stamps, cache)
    assert len(calls) == 5


def test_empty_inventory_and_missing_export_folders(tmp_path):
    assert scan_directory(tmp_path, tmp_path / 'edls', tmp_path / 'stamps', {}) == ([], {})


def test_relative_save_time():
    assert relative_age(100, 90) == 'Just now'
    assert relative_age(0, 60) == '1 min ago'
    assert relative_age(0, 7200) == '2 hours ago'
    assert relative_age(0, 86400 * 3) == '3 days ago'
