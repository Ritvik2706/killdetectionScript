import pytest

from killcutter import timecode as tc


def test_format_clock():
    assert tc.format_clock(0) == "0:00.000"
    assert tc.format_clock(75.5) == "1:15.500"


def test_format_duration():
    assert tc.format_duration(59) == "0:59"
    assert tc.format_duration(75) == "1:15"
    assert tc.format_duration(3725) == "1:02:05"


def test_format_eta_unknown():
    assert tc.format_eta(None) == "--:--"
    assert tc.format_eta(-1) == "--:--"
    assert tc.format_eta(65) == "01:05"


def test_resolve_fps_keeps_true_integer_rates():
    """OBS writes 60/1. Rewriting that as 59.94 is what drifted long exports."""
    assert tc.resolve_fps(60.0) == 60.0
    assert tc.resolve_fps(30.0) == 30.0
    assert tc.resolve_fps(59.999) == 60.0     # float noise from the probe
    assert tc.resolve_fps(50.0) == 50.0       # not an NTSC base at all


def test_resolve_fps_snaps_genuine_ntsc_rates():
    assert tc.resolve_fps(59.94) == 60 * 1000 / 1001
    assert tc.resolve_fps(29.97) == 30 * 1000 / 1001
    assert tc.resolve_fps(23.976) == 24 * 1000 / 1001


def test_resolve_fps_never_converts_between_the_two_families():
    for rate in (24.0, 30.0, 60.0, 120.0):
        assert tc.resolve_fps(rate) == rate
    for base in tc.NTSC_BASES:
        ntsc = base * 1000.0 / 1001.0
        assert tc.resolve_fps(ntsc) == ntsc


def test_seconds_to_timecode_is_exact_at_60fps():
    assert tc.seconds_to_timecode(0, 60.0) == "00:00:00:00"
    assert tc.seconds_to_timecode(1.0, 60.0) == "00:00:01:00"
    assert tc.seconds_to_timecode(5400.0, 60.0) == "01:30:00:00"
    assert tc.seconds_to_timecode(7200.0, 60.0) == "02:00:00:00"


def test_timecode_round_trips_without_drift_over_hours():
    """The regression: a cut two hours in must not land seconds early."""
    for secs in (60, 600, 3600, 5400, 7200, 14958):
        tc_str = tc.seconds_to_timecode(secs, 60.0)
        hh, mm, ss, ff = (int(x) for x in tc_str.split(":"))
        lands = (((hh * 3600 + mm * 60 + ss) * 60) + ff) / 60.0
        assert abs(lands - secs) < 0.02


def test_drift_seconds_quantifies_a_rate_mismatch():
    ntsc = 60 * 1000.0 / 1001.0
    # authoring 60fps media at 59.94 pulls cuts earlier as the file goes on
    assert tc.drift_seconds(ntsc, 60.0, 5400) == pytest.approx(-5.4, abs=0.1)
    assert tc.drift_seconds(ntsc, 60.0, 7200) == pytest.approx(-7.2, abs=0.1)
    assert tc.drift_seconds(60.0, 60.0, 7200) == 0.0
