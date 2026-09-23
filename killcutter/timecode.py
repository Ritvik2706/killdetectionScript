"""Time and timecode formatting — pure functions, no I/O, easy to unit-test.

The NTSC handling here is the crux of keeping cuts from drifting: see
:func:`ntsc_rate` and :func:`seconds_to_timecode`.
"""


def format_clock(secs: float) -> str:
    """Seconds → ``M:SS.mmm`` (used for on-screen progress / kill markers)."""
    m, s = divmod(secs, 60)
    return f"{int(m)}:{s:06.3f}"


def format_duration(secs: float) -> str:
    """Seconds → ``H:MM:SS`` (or ``M:SS`` when under an hour)."""
    m, s = divmod(int(secs), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def format_eta(secs) -> str:
    """Seconds remaining → ``MM:SS``; ``--:--`` when unknown."""
    if secs is None or secs < 0:
        return "--:--"
    m, s = divmod(int(secs), 60)
    return f"{m:02}:{s:02}"


NTSC_BASES = (24, 30, 60, 120)


def resolve_fps(fps: float) -> float:
    """Snap a probed frame rate to the exact rate the media actually runs at.

    A recording is either a true integer rate (OBS writing 60/1) or an NTSC rate
    (60000/1001 = 59.94). Both reach us as floats carrying a little noise, so
    each is snapped to its exact value — and crucially, **never converted into
    the other**.

    This used to rewrite every ~60 fps rate as 59.94 unconditionally, on the
    assumption that Premiere always conforms to NTSC. For genuinely 60.000 fps
    footage that makes each timecode 0.1% short, which is invisible at the start
    of a recording and ruinous at the end: a cut lands 3.6s early at one hour,
    5.4s early at 90 minutes and 7.2s early at two hours — enough for a 10s
    highlight to finish before the kill it was built around. Author at the rate
    the media really is, and have the sequence match it.
    """
    for base in NTSC_BASES:
        if abs(fps - base) < 0.01:
            return float(base)                  # a true integer rate
        ntsc = base * 1000.0 / 1001.0
        if abs(fps - ntsc) < 0.05:
            return ntsc                         # genuinely NTSC, snap off noise
    return fps


def drift_seconds(authored_fps: float, media_fps: float, at_seconds: float) -> float:
    """How far a cut authored at ``authored_fps`` lands from where it belongs.

    Negative means early. This is the arithmetic behind the bug above, kept as a
    function so the export step can warn instead of silently drifting.
    """
    if media_fps <= 0:
        return 0.0
    return at_seconds * (authored_fps / media_fps) - at_seconds


def seconds_to_timecode(secs: float, fps: float) -> str:
    """Seconds → ``HH:MM:SS:FF`` non-drop timecode.

    ``fps`` is the media's real rate. The frame index is computed at that rate so
    the clip lands at the right wall-clock time, while labels roll over at the
    nominal integer rate — which is exactly how a non-drop timecode is read.
    """
    nominal = max(1, round(fps))
    total_frames = int(round(secs * fps))
    ff = total_frames % nominal
    total_secs = total_frames // nominal
    hh = total_secs // 3600
    mm = (total_secs % 3600) // 60
    ss = total_secs % 60
    return f"{hh:02}:{mm:02}:{ss:02}:{ff:02}"
