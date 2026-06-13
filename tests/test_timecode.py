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


def test_ntsc_rate_corrects_integer_rates():
    assert tc.ntsc_rate(60) == 60 * 1000 / 1001
    assert tc.ntsc_rate(30) == 30 * 1000 / 1001
    assert tc.ntsc_rate(50) == 50          # 50 is not an NTSC base — unchanged


def test_is_drop_frame():
    assert tc.is_drop_frame(59.94) is True
    assert tc.is_drop_frame(29.97) is True
    assert tc.is_drop_frame(60) is False
    assert tc.is_drop_frame(24) is False


def test_seconds_to_timecode_at_5994():
    fps = tc.ntsc_rate(60)
    assert tc.seconds_to_timecode(0, fps) == "00:00:00:00"
    # one real second is ~60 frames at 59.94, rolling over the nominal-60 label
    assert tc.seconds_to_timecode(1.0, fps) == "00:00:01:00"
