"""Video discovery, metadata probing, and the interactive clip picker.

Shared by both the detect and export commands so footage selection looks and
behaves identically everywhere.
"""

import os
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

import cv2

from killcutter import ui
from killcutter.constants import VIDEO_EXTENSIONS
from killcutter.errors import VideoError
from killcutter.timecode import format_duration


@dataclass
class VideoFile:
    name: str
    path: str
    duration: str   # pre-formatted label, e.g. "1:24:05"
    mtime: float


def probe(path) -> tuple:
    """Return ``(fps, total_frames)`` for a video, without decoding it fully."""
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return fps, frames


def measure(path) -> tuple:
    """Return ``(fps, total_frames, duration_seconds)``.

    Duration comes from the container's own timestamps rather than
    ``frames / fps``, so the two can be compared against each other — that
    cross-check is what catches a frame rate the file is lying about.
    """
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise VideoError(f"Could not open: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_AVI_RATIO, 1.0)
    end_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
    cap.release()
    if end_ms > 0:
        duration = end_ms / 1000.0
    else:
        duration = frames / fps if fps > 0 else 0.0
    return fps, frames, duration


def frame_size(path) -> tuple:
    """Return ``(width, height)`` for a video, or the 1080p reference if unknown."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise VideoError(f"Could not open: {path}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return (w, h) if w > 0 and h > 0 else (1920, 1080)


def measured_fps(frames: int, duration: float):
    """Frame rate implied by the container, or ``None`` if it cannot be known."""
    if frames <= 1 or duration <= 0:
        return None
    # The last frame's timestamp marks its start, so the span covers frames-1.
    return (frames - 1) / duration


def _duration_label(path) -> str:
    fps, frames = probe(path)
    return format_duration(frames / fps) if fps > 0 and frames > 0 else "?"


def list_clips(clips_dir) -> list:
    """Newest-first list of playable clips in ``clips_dir`` with metadata."""
    clips_dir = os.path.expanduser(clips_dir)
    if not os.path.isdir(clips_dir):
        raise VideoError(f"Clips folder not found: {clips_dir}")

    names = sorted(
        (f for f in os.listdir(clips_dir)
         if os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS),
        key=lambda f: os.path.getmtime(os.path.join(clips_dir, f)),
        reverse=True,
    )
    if not names:
        raise VideoError(f"No video files found in {clips_dir}")

    paths = [os.path.join(clips_dir, n) for n in names]
    with ThreadPoolExecutor() as pool:
        durations = list(pool.map(_duration_label, paths))
    return [
        VideoFile(n, p, d, os.path.getmtime(p))
        for n, p, d in zip(names, paths, durations)
    ]


def _render_row(clip: VideoFile, active: bool, idx: int) -> str:
    """One picker row: pointer · number · duration · age · name."""
    pointer = ui.paint("▌ ", ui.LIME, bold=True) if active else "  "
    num = ui.paint(f"{idx:>3}", ui.TEAL if active else ui.DIM, bold=active)
    dur = ui.paint(f"{clip.duration:>8}", ui.AMBER if active else ui.GREY)
    age = ui.paint(f"{ui.rel_time(clip.mtime):>9}", ui.DIM)
    name = ui.paint(clip.name, ui.WHITE if active else ui.GREY, bold=active)
    return f"{pointer}{num}  {dur}  {age}   {name}"


def pick(clips_dir) -> str:
    """Open the interactive picker and return the chosen video's path.

    Exits the process cleanly on cancel (raises ``SystemExit(0)``).
    """
    clips = list_clips(clips_dir)
    choice = ui.select(
        clips, _render_row,
        title=f"SELECT CLIP  ·  {clips_dir}",
        filter_text=lambda c: c.name,
    )
    if choice is None:
        print(ui.paint("  Cancelled.", ui.DIM))
        raise SystemExit(0)
    return clips[choice].path
