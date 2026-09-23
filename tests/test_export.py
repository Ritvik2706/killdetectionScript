from killcutter import export
from killcutter.export import ExportPlan
from killcutter.models import Clip


def test_read_timestamps(tmp_path):
    p = tmp_path / "timestamps.txt"
    p.write_text("1.000 6.500 ShadowFox\n10.0 15.0\n# bad line\n2.0\n")
    clips = export.read_timestamps(str(p))
    assert len(clips) == 2
    assert clips[0] == Clip(1.0, 6.5, "ShadowFox")
    assert clips[1].name == "???"          # no name column -> placeholder


def _plan(clips, **kw):
    return ExportPlan(
        clips=clips, sequence_name=kw.get("name", "Kill Highlights"),
        video_basename=kw.get("base", "clip.mkv"), fps=kw.get("fps", 60.0),
        is_drop=kw.get("is_drop", False), out_path="out.edl",
        fps_note="", fps_warning="", total_seconds=sum(c.duration for c in clips),
    )


def test_build_edl_header_and_events():
    edl = export.build_edl(_plan([Clip(1.0, 6.0, "Fox"), Clip(20.0, 25.0, "???")]))
    lines = edl.splitlines()
    assert lines[0] == "TITLE: Kill Highlights"
    assert lines[1] == "FCM: NON-DROP FRAME"
    assert "001  CLIP" in edl and "002  CLIP" in edl
    assert "* FROM CLIP NAME: clip.mkv" in edl
    assert "* COMMENT: Fox" in edl
    # placeholder names are not emitted as comments
    assert "* COMMENT: ???" not in edl


def test_build_edl_source_timecodes_do_not_drift_late_in_a_long_file():
    """A kill two hours in must be cut at two hours, not 7s before it."""
    edl = export.build_edl(_plan([Clip(7200.0, 7210.0, "Fox")], fps=60.0))
    assert "02:00:00:00 02:00:10:00" in edl


def test_build_edl_records_are_contiguous():
    edl = export.build_edl(_plan([Clip(0.0, 2.0, "a"), Clip(100.0, 105.0, "b")]))
    # second clip records right after the first (2s), regardless of source time
    assert "00:00:00:00 00:00:02:00" in edl   # first record in/out
    assert "00:00:02:00 00:00:07:00" in edl   # second record in/out
