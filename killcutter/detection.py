"""Kill detection core.

CoD shows an "ENEMY DOWNED" banner in the top-right on a kill. OCR on every
frame would be far too slow, so each sampled frame is gated by two cheap pixel
checks (a white pixel on the banner text, a red pixel on its accent); only
matching frames are OCR'd to read the player name.

This module is presentation-free: it walks the video and reports progress and
events through a ``reporter`` object (see :mod:`killcutter.reporting`),
returning the list of :class:`~killcutter.models.Clip` it found. Anything that
prints lives in the reporter, so the algorithm stays testable and readable.
"""

import os
import time
from dataclasses import dataclass

import cv2
import pytesseract

from killcutter import constants
from killcutter.errors import VideoError
from killcutter.models import Clip


@dataclass
class DetectionSettings:
    region: tuple
    offset: float = 5.0          # seconds before the kill for the clip start
    end_offset: float = 5.0      # seconds after the kill for the clip end
    merge_gap: float = 10.0      # merge kills closer than this into one clip
    cooldown: float = 3.0        # min seconds between detections
    rate: float = 2.0            # frame samples per second
    preview: bool = False
    debug: bool = False


@dataclass
class DetectionMeta:
    source: str
    fps: float
    duration: float
    total_frames: int
    region: tuple
    settings: DetectionSettings
    total_checks: int
    dry_run: bool


# ── Pixel pre-checks ────────────────────────────────────────────────────────────

def _pixel_is_white(frame, coord) -> bool:
    px, py = coord
    fh, fw = frame.shape[:2]
    if py >= fh or px >= fw:
        return False
    b, g, r = frame[py, px]
    t = constants.BRIGHT_THRESHOLD
    return int(b) > t and int(g) > t and int(r) > t


def _pixel_is_red(frame, coord) -> bool:
    px, py = coord
    fh, fw = frame.shape[:2]
    if py >= fh or px >= fw:
        return False
    b, g, r = frame[py, px]
    t = constants.RED_THRESHOLD
    return int(r) > t and int(g) < t and int(b) < t


def _banner_visible(frame) -> bool:
    return (_pixel_is_white(frame, constants.TRIGGER_PIXEL_WHITE)
            and _pixel_is_red(frame, constants.TRIGGER_PIXEL_RED))


# ── OCR + name merging ──────────────────────────────────────────────────────────

def _read_player_name(roi) -> str:
    """Return the player name from the banner ROI via OCR (or "" if unsure)."""
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, thresh = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    text = pytesseract.image_to_string(thresh, config=constants.TESSERACT_CONFIG).strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[-1] if len(lines) >= 2 else ""


def _merge_names(prev_name: str, new_name: str) -> str:
    """Combine player names for a merged clip; discard '???' when possible."""
    if not new_name or new_name == "???":
        return prev_name
    if not prev_name or prev_name == "???":
        return new_name
    if new_name == prev_name:
        return prev_name
    return f"{prev_name} + {new_name}"


# ── Duration ────────────────────────────────────────────────────────────────────

def _measure_duration(cap, total_frames, fps) -> float:
    """Prefer container timestamps over frame_count/fps.

    CAP_PROP_FPS is unreliable for VFR game recordings (OBS, capture cards),
    which makes frame-number time estimates drift by seconds over a long clip —
    the shrinking-offset bug. The last frame's POS_MSEC is the real duration.
    """
    cap.set(cv2.CAP_PROP_POS_AVI_RATIO, 1.0)
    end_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    return end_ms / 1000.0 if end_ms > 0 else total_frames / fps


# ── Main entry ──────────────────────────────────────────────────────────────────

def detect(video_path, settings: DetectionSettings, reporter, *, dry_run=False) -> list:
    """Scan ``video_path`` and return the detected :class:`Clip` list.

    Raises :class:`VideoError` if the file can't be opened or has no frame rate.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise VideoError(f"Could not open: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps <= 0:
        cap.release()
        raise VideoError(f"Could not read frame rate (got {fps}). Is the file valid?")

    duration = _measure_duration(cap, total_frames, fps)
    check_interval = 1.0 / settings.rate
    total_checks = int(duration / check_interval) + 1

    meta = DetectionMeta(
        source=os.path.basename(video_path), fps=fps, duration=duration,
        total_frames=total_frames, region=settings.region, settings=settings,
        total_checks=total_checks, dry_run=dry_run,
    )
    reporter.begin(meta)

    x, y, w, h = settings.region
    clips: list = []
    last_kill = -(settings.cooldown + 1)
    player = ""   # most recent OCR result — shown in preview during cooldown frames
    start_wall = time.time()

    try:
        for i in range(total_checks):
            elapsed = i * check_interval
            if elapsed >= duration:
                break
            cap.set(cv2.CAP_PROP_POS_MSEC, elapsed * 1000.0)
            ok, frame = cap.read()
            if not ok:
                continue

            triggered = _banner_visible(frame)
            reporter.frame(elapsed, triggered)

            frac = (i + 1) / max(total_checks, 1)
            spent = time.time() - start_wall
            eta = (spent / frac - spent) if frac > 0.001 else None

            if not triggered:
                reporter.progress(i + 1, total_checks, elapsed, duration, len(clips), eta)
                continue

            fh, fw = frame.shape[:2]
            roi = frame[min(y, fh - 1):min(y + h, fh), min(x, fw - 1):min(x + w, fw)]

            if (elapsed - last_kill) > settings.cooldown:
                cut_end = min(duration, elapsed + settings.end_offset)
                player = _read_player_name(roi)
                name = player or "???"

                if clips and (elapsed - last_kill) <= settings.merge_gap:
                    prev = clips[-1]
                    clips[-1] = Clip(prev.start, cut_end, _merge_names(prev.name, name))
                    reporter.extended(clips[-1])
                else:
                    clips.append(Clip(max(0.0, elapsed - settings.offset), cut_end, name))
                    reporter.kill(len(clips), elapsed, clips[-1])
                last_kill = elapsed

            if settings.preview and _preview(roi, player):
                break

            reporter.progress(i + 1, total_checks, elapsed, duration, len(clips), eta)
    finally:
        cap.release()
        if settings.preview:
            cv2.destroyAllWindows()

    return clips


def _preview(roi, player) -> bool:
    """Show the live banner ROI; return True if the user pressed Q to stop."""
    display = roi.copy()
    cv2.putText(display, f"DOWNED: {player}" if player else "DOWNED",
                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.imshow("Banner region", display)
    return cv2.waitKey(1) & 0xFF == ord("q")
