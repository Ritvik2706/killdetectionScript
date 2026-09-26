from pathlib import Path
import os
import pytest
from killcutter.export import ExportPlan, build_edl
from killcutter.models import Clip
from killcutter.gui.state import Media
from killcutter.gui.edl import read_edl, load_saved


def write_edl(path, media, clips):
    plan = ExportPlan(clips, 'Test', Path(media.path).name, media.fps, False, str(path), '', '', 0)
    path.write_text(build_edl(plan))


@pytest.mark.parametrize('fps', [30, 60, 60000/1001])
def test_roundtrip_source_timestamps_and_names(tmp_path, fps):
    media = Media('/videos/session.mp4', fps, 8000, 1920, 1080)
    path = tmp_path / 'custom.edl'
    clips = [Clip(120.123, 140.234, 'Player One', {'real-player': True}), Clip(7200, 7210, 'Player Two')]
    write_edl(path, media, clips)
    loaded = read_edl(path, media)
    for a, b in zip(clips, loaded):
        assert a.name == b.name
        assert a.traits == b.traits
        assert a.start == pytest.approx(b.start, abs=1/fps)
        assert a.end == pytest.approx(b.end, abs=1/fps)


def test_latest_matching_edl_and_external_changes(tmp_path):
    media = Media('/videos/session.mp4', 30, 500, 1920, 1080)
    old, new, other = [tmp_path / n for n in ('old.edl', 'new.edl', 'unrelated.edl')]
    write_edl(old, media, [Clip(10, 20, 'Old')])
    write_edl(new, media, [Clip(30, 40, 'New')])
    os.utime(old, (1, 1))
    write_edl(other, Media('other.mp4', 30, 500, 1, 1), [Clip(1, 2)])
    paths, target, clips, error = load_saved(tmp_path, media)
    assert target == str(new)
    assert len(paths) == 2 and error is None
    assert clips[0].name == 'New'
    write_edl(new, media, [Clip(50, 60, 'Edited externally')])
    assert load_saved(tmp_path, media, new)[2][0].name == 'Edited externally'
    assert load_saved(tmp_path, media, old)[2][0].name == 'Old'
    assert load_saved(tmp_path, media, other)[3]


def test_unsupported_or_broken_edl_has_no_partial_results(tmp_path):
    media = Media('session.mp4', 30, 500, 1, 1)
    path = tmp_path / 'session_highlights.edl'
    write_edl(path, media, [Clip(1, 2)])
    original = path.read_text()
    for text in (original.replace('NON-DROP FRAME', 'DROP FRAME'),
                 original.replace('B     C', 'B     D'),
                 original + '\n002 malformed event',
                 original.replace('00:00:01:00', '00:00:99:00')):
        path.write_text(text)
        assert load_saved(tmp_path, media)[2] is None
        assert load_saved(tmp_path, media)[3]
