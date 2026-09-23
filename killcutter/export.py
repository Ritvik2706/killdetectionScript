"""Highlight export: read timestamps, plan the reel, render an EDL.

Pure data-in/data-out so it can be unit-tested without a video or a terminal.
The CLI handles all the printing.
"""

import os
import re
from dataclasses import dataclass

from killcutter import video, outputs
from killcutter.errors import VideoError
from killcutter.models import Clip
from killcutter.timecode import drift_seconds, resolve_fps, seconds_to_timecode


def read_timestamps(path) -> list:
    """Parse a ``timestamps.txt`` (``start end name...`` per line) into clips."""
    clips = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            try:
                start, end = float(parts[0]), float(parts[1])
            except ValueError:
                continue
            name = " ".join(parts[2:]) if len(parts) >= 3 else "???"
            clips.append(Clip(start, end, name))
    return clips


@dataclass
class ExportPlan:
    clips: list
    sequence_name: str
    video_basename: str
    fps: float
    is_drop: bool
    out_path: str
    fps_note: str         # "" unless the probed rate needed snapping
    fps_warning: str      # "" unless the authored rate disagrees with the media
    total_seconds: float


def plan(video_path, clips, *, fps_override=None, name="Kill Highlights", output=None) -> ExportPlan:
    """Resolve the authoring fps, output path and drop-frame mode for a reel."""
    raw_fps, frames, duration = video.measure(video_path)
    if raw_fps <= 0:
        raise VideoError(f"Could not read frame rate (got {raw_fps}). Is the file valid?")

    # Author at the rate the media actually runs at. An explicit --fps wins.
    fps = fps_override if fps_override else resolve_fps(raw_fps)
    fps_note = ""
    if not fps_override and abs(fps - raw_fps) > 0.0005:
        fps_note = f"{raw_fps:.5f} → {fps:.3f} (snapped to the exact rate)"

    # Cross-check the authored rate against the container itself. A rate that is
    # off by even 0.1% is invisible in the first minutes and pushes cuts seconds
    # early by the end of a long recording, so say so rather than drift quietly.
    fps_warning = ""
    actual = video.measured_fps(frames, duration)
    if actual and abs(fps - actual) / actual > 0.0005:
        last = max((c.end for c in clips), default=0.0)
        off = drift_seconds(fps, actual, last)
        fps_warning = (f"authoring at {fps:.3f} but the file measures "
                       f"{actual:.3f} fps — the last cut lands {off:+.1f}s off. "
                       f"Override with --fps {actual:.3f} if that is wrong.")

    basename = os.path.basename(video_path)
    stem = os.path.splitext(basename)[0]
    return ExportPlan(
        clips=clips,
        sequence_name=name,
        video_basename=basename,
        fps=fps,
        # Timecodes are authored non-drop, so the EDL must declare non-drop.
        # Drop-frame only relabels frames; claiming it while emitting non-drop
        # labels makes Premiere read every cut at the wrong frame.
        is_drop=False,
        out_path=output or f"{stem}_highlights.edl",
        fps_note=fps_note,
        fps_warning=fps_warning,
        total_seconds=sum(c.duration for c in clips),
    )


def build_edl(plan: ExportPlan) -> str:
    """Render the plan as an EDL string. One event per clip; track 'B' = A/V."""
    fcm = "DROP FRAME" if plan.is_drop else "NON-DROP FRAME"
    # EDL reel names max out at 8 chars; Premiere relinks via FROM CLIP NAME.
    reel = re.sub(r"[^A-Za-z0-9]", "", os.path.splitext(plan.video_basename)[0])[:8].upper() or "AX"

    lines = [f"TITLE: {plan.sequence_name}", f"FCM: {fcm}", ""]
    rec_pos = 0.0
    for i, clip in enumerate(plan.clips):
        src_in = seconds_to_timecode(clip.start, plan.fps)
        src_out = seconds_to_timecode(clip.end, plan.fps)
        rec_in = seconds_to_timecode(rec_pos, plan.fps)
        rec_out = seconds_to_timecode(rec_pos + clip.duration, plan.fps)

        lines.append(
            f"{i + 1:03d}  {reel:<8} B     C        "
            f"{src_in} {src_out} {rec_in} {rec_out}"
        )
        lines.append(f"* FROM CLIP NAME: {plan.video_basename}")
        if clip.name and clip.name != "???":
            lines.append(f"* COMMENT: {clip.name}")
        lines.append("")
        rec_pos += clip.duration

    return "\n".join(lines)


def write_edl(plan: ExportPlan) -> str:
    """Write the EDL to ``plan.out_path`` and return that path."""
    outputs.atomic_text(plan.out_path, build_edl(plan))
    return plan.out_path
