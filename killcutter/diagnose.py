"""Check the HUD assumptions in :mod:`killcutter.constants` against real footage.

When a game update restyles the killfeed, ``detect`` simply stops finding kills
and gives no clue why. This module samples a stretch of video and reports which
stage is failing — the white pixel, the accent pixel, or the OCR header match —
plus every banner header it actually saw and the accent colour it was drawn in.

That is usually enough to tell "the HUD moved" from "the HUD changed colour"
from "OCR has gone bad", which are three very different fixes.

Presentation-free, like :mod:`killcutter.detection`: returns a
:class:`Diagnosis` for :mod:`killcutter.reporting` to render.
"""

import os
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import cv2

from killcutter import constants, hud as hud_mod
from killcutter.detection import (_banner_visible, _is_kill_header, _ocr_lines,
                                  _measure_duration, _pixel, _pixel_is_accent,
                                  _pixel_is_white, _samples)
from killcutter.errors import VideoError

EXPECTED_SIZE = (1920, 1080)


@dataclass
class HeaderStat:
    """One distinct banner header OCR saw, and how it was drawn."""

    header: str
    count: int
    accent: tuple          # median (r, g, b) of the accent pixel
    accepted: bool         # did it pass the kill-header match?


@dataclass
class Diagnosis:
    source: str
    width: int
    height: int
    fps: float
    duration: float
    region: tuple
    scan_start: float
    scan_span: float
    sampled: int = 0
    white_hits: int = 0
    accent_hits: int = 0
    gated: int = 0
    kills: int = 0
    headers: list = field(default_factory=list)
    accent_samples: list = field(default_factory=list)
    layout: str = ""
    white_pixel: tuple = constants.TRIGGER_PIXEL_WHITE
    accent_pixel: tuple = constants.TRIGGER_PIXEL_ACCENT

    @property
    def problems(self) -> list:
        """Human-readable diagnoses, most likely cause first. Empty means healthy."""
        out = []
        if (self.width, self.height) != EXPECTED_SIZE and not self.kills:
            out.append(
                f"Footage is {self.width}x{self.height}; the HUD geometry was scaled "
                f"from the {EXPECTED_SIZE[0]}x{EXPECTED_SIZE[1]} reference. If nothing "
                "below matched, the scaling is probably wrong for this layout — "
                "re-run 'calibrate' and set [detect] region in your config.")
        if not self.sampled:
            out.append("No frames were sampled — the video could not be read.")
            return out
        if self.kills:
            return out

        if not self.accent_hits:
            out.append(
                f"The accent pixel {self.accent_pixel} never showed a warm "
                "colour. The banner has probably moved — re-run 'calibrate'.")
        elif not self.white_hits:
            out.append(
                f"The accent pixel fired but the white pixel {self.white_pixel} "
                "never did. The banner icon moved or changed colour — re-run "
                "'calibrate --pixel'.")
        elif not self.gated:
            out.append(
                "Both trigger pixels fired, but never on the same frame. They are "
                "probably no longer on the same banner — re-run 'calibrate'.")
        elif not self.headers:
            out.append(
                "Frames passed the pixel gate but OCR read nothing from the scan region. "
                f"The region {self.region} is likely wrong — re-run 'calibrate'.")
        else:
            seen = ", ".join(repr(h.header) for h in self.headers[:4])
            out.append(
                f"Frames passed the pixel gate, but no header matched "
                f"{constants.BANNER_HEADER!r}. Headers seen: {seen}. Either the wording "
                "changed (update BANNER_HEADER) or the gate is firing on other banners.")
        return out


def diagnose(video_path, region=None, *, start=None, span=600.0, rate=2.0,
             reporter=None) -> Diagnosis:
    """Sample ``span`` seconds of ``video_path`` and report on the HUD gates.

    ``start`` defaults to 10% into the file, which skips menus and warm-up and
    usually lands in live gameplay.
    """
    override = tuple(region) if region else None

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise VideoError(f"Could not open: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps <= 0:
        cap.release()
        raise VideoError(f"Could not read frame rate (got {fps}). Is the file valid?")

    duration = _measure_duration(cap, total_frames, fps)
    if start is None:
        start = duration * 0.1
    start = max(0.0, min(start, max(0.0, duration - 1)))
    span = min(span, max(0.0, duration - start))

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    hud = hud_mod.for_size(width, height, override)
    region = hud.region

    report = Diagnosis(
        source=os.path.basename(video_path),
        width=width, height=height,
        fps=fps, duration=duration, region=region,
        scan_start=start, scan_span=span,
        layout=hud_mod.describe(hud),
        white_pixel=hud.white, accent_pixel=hud.accent,
    )

    counts = Counter()
    accepted = {}
    accents = defaultdict(list)
    x, y, w, h = region
    end_at = start + span

    try:
        if start:
            cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)
        for elapsed, frame in _samples(cap, duration, 1.0 / rate):
            if elapsed >= end_at:
                break
            report.sampled += 1
            if reporter is not None:
                reporter.progress(report.sampled, int(span * rate) + 1,
                                  elapsed, end_at, report.kills, None)

            white = _pixel_is_white(frame, hud.white)
            accent = _pixel_is_accent(frame, hud.accent)
            report.white_hits += white
            report.accent_hits += accent
            if accent:
                rgb = _pixel(frame, hud.accent)
                if rgb:
                    report.accent_samples.append(rgb)
            if not (white and accent):
                continue

            report.gated += 1
            fh, fw = frame.shape[:2]
            roi = frame[min(y, fh - 1):min(y + h, fh), min(x, fw - 1):min(x + w, fw)]
            lines = _ocr_lines(roi)
            if not lines:
                continue
            head = lines[0]
            counts[head] += 1
            ok = _is_kill_header(head)
            accepted[head] = ok
            report.kills += ok
            rgb = _pixel(frame, hud.accent)
            if rgb:
                accents[head].append(rgb)
    finally:
        cap.release()

    report.headers = [
        HeaderStat(header=head, count=n, accepted=accepted[head],
                   accent=_median_rgb(accents[head]))
        for head, n in counts.most_common()
    ]
    return report


def _median_rgb(samples) -> tuple:
    if not samples:
        return (0, 0, 0)
    return tuple(int(statistics.median(c[i] for c in samples)) for i in range(3))
