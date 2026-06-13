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


def ntsc_rate(fps: float) -> float:
    """Map an OBS/camera-reported rate to the real NTSC rate Premiere conforms to.

    OpenCV reports ~60 fps footage as exactly 60.0, but Premiere imports the EDL
    into a 59.94 fps (60000/1001) sequence. Authoring at 60 while Premiere plays
    at 59.94 drifts every clip later by ~0.09% of its timecode — seconds deep
    into a long recording. Authoring at the same 59.94 makes the drift zero.
    """
    for base in (24, 30, 60, 120):
        if abs(fps - base) < 0.05:
            return base * 1000.0 / 1001.0
    return fps


def is_drop_frame(fps: float) -> bool:
    """29.97 and 59.94 use drop-frame timecode; everything else is non-drop."""
    return abs(fps - round(fps)) > 0.005 and round(fps) in (30, 60)


def seconds_to_timecode(secs: float, fps: float) -> str:
    """Seconds → ``HH:MM:SS:FF`` non-drop timecode.

    ``fps`` is the real playback rate (e.g. 59.94): the frame index is computed
    at that rate so the clip lands at the right wall-clock time, while labels
    roll over at the nominal integer rate (60) — how Premiere reads non-drop
    timecode for a 59.94 sequence.
    """
    nominal = max(1, round(fps))
    total_frames = int(round(secs * fps))
    ff = total_frames % nominal
    total_secs = total_frames // nominal
    hh = total_secs // 3600
    mm = (total_secs % 3600) // 60
    ss = total_secs % 60
    return f"{hh:02}:{mm:02}:{ss:02}:{ff:02}"
