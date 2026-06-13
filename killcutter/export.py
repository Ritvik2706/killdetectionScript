"""Highlight export: read timestamps, plan the reel, render an EDL.

Pure data-in/data-out so it can be unit-tested without a video or a terminal.
The CLI handles all the printing.
"""

import os
import re
from dataclasses import dataclass

from killcutter import video
from killcutter.errors import VideoError
from killcutter.models import Clip
from killcutter.timecode import ntsc_rate, is_drop_frame, seconds_to_timecode


def read_timestamps(path) -> list:
    """Parse a ``timestamps.txt`` (``start end name...`` per line) into clips."""
    clips = []
    with open(path) as f:
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
    ntsc_note: str        # "" unless the rate was NTSC-corrected
    total_seconds: float


def plan(video_path, clips, *, fps_override=None, name="Kill Highlights", output=None) -> ExportPlan:
    """Resolve the authoring fps, output path and drop-frame mode for a reel."""
    raw_fps, _ = video.probe(video_path)
    if raw_fps <= 0:
        raise VideoError(f"Could not read frame rate (got {raw_fps}). Is the file valid?")

    # Author at the rate Premiere conforms to. An explicit --fps wins; otherwise
    # NTSC-correct the reported rate (60 -> 59.94) so cuts don't drift.
    fps = fps_override if fps_override else ntsc_rate(raw_fps)
    ntsc_note = ""
    if not fps_override and abs(fps - raw_fps) > 0.005:
        ntsc_note = f"{raw_fps:.3f} → {fps:.3f} (NTSC corrected)"

    basename = os.path.basename(video_path)
    stem = os.path.splitext(basename)[0]
    return ExportPlan(
        clips=clips,
        sequence_name=name,
        video_basename=basename,
        fps=fps,
        is_drop=is_drop_frame(fps),
        out_path=output or f"{stem}_highlights.edl",
        ntsc_note=ntsc_note,
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
    with open(plan.out_path, "w") as f:
        f.write(build_edl(plan))
    return plan.out_path
