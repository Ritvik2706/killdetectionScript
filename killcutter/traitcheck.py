"""Check a trait against real footage before trusting it.

A trait probe is only as good as the threshold behind it, and a threshold tuned
on a couple of screenshots is a guess. This module samples a recording, runs one
trait's probe over every sample, and — with ``--dump`` — writes each crop it
judged to disk next to its verdict, so the answers can be checked by eye instead
of taken on faith.

``python -m killcutter traits --video clip.mp4 --dump /tmp/hash``
"""

import os
from dataclasses import dataclass, field

import cv2

from killcutter import hud as hud_mod
from killcutter.errors import VideoError


@dataclass
class TraitReport:
    source: str
    trait: str
    region: tuple
    layout: str
    scan_start: float
    scan_span: float
    sampled: int = 0
    yes: int = 0
    no: int = 0
    unknown: int = 0
    dump_dir: str = ""
    examples: list = field(default_factory=list)   # (seconds, verdict) for the panel
    hit_scores: list = field(default_factory=list)   # match scores on confirmed frames
    miss_scores: list = field(default_factory=list)  # best score on rejected frames

    @property
    def decided(self) -> int:
        return self.yes + self.no

    @property
    def headroom(self):
        """How far the weakest accepted frame sat above the cutoff.

        This is the number that says whether a threshold is safe on *your*
        footage. A weakest hit barely above the cutoff means the next slightly
        worse recording starts getting marked as a bot.
        """
        if not self.hit_scores:
            return None
        from killcutter.traits import HASH_MATCH_MIN
        return min(self.hit_scores) - HASH_MATCH_MIN


def sample(video_path, trait, *, start=0.0, span=600.0, rate=1.0, dump_dir=None) -> TraitReport:
    """Run ``trait``'s probe across a slice of ``video_path``.

    Sampling is deliberately coarse (1/s by default): the point is to collect a
    spread of crops to review, not to reproduce a detection run.
    """
    if not os.path.exists(video_path):
        raise VideoError(f"No such file: {video_path}")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise VideoError(f"Could not open: {video_path}")
    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        hud = hud_mod.for_size(width, height)
        x, y, w, h = getattr(hud, trait.region)
        report = TraitReport(source=os.path.basename(video_path), trait=trait.name,
                             region=(x, y, w, h), layout=hud_mod.describe(hud),
                             scan_start=start, scan_span=span,
                             dump_dir=dump_dir or "")
        if dump_dir:
            os.makedirs(dump_dir, exist_ok=True)

        if start:
            cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)
        step = 1.0 / rate if rate > 0 else 1.0
        next_at = start
        while True:
            if not cap.grab():
                break
            elapsed = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if elapsed >= start + span:
                break
            if elapsed + 1e-9 < next_at:
                continue
            ok, frame = cap.retrieve()
            if not ok:
                break
            next_at = elapsed + step
            roi = frame[y:y + h, x:x + w]
            verdict = trait.probe(roi, hud.scale)
            _record_score(report, trait, roi, hud.scale, verdict)
            report.sampled += 1
            if verdict is None:
                report.unknown += 1
            elif verdict:
                report.yes += 1
            else:
                report.no += 1
            # Only decided frames are worth reviewing; "unknown" almost always
            # just means the line was not on screen, and there would be
            # thousands of those.
            if verdict is not None:
                report.examples.append((elapsed, verdict))
                if dump_dir:
                    label = "yes" if verdict else "no"
                    cv2.imwrite(os.path.join(
                        dump_dir, f"{label}_{elapsed:08.2f}.png"), roi)
        return report
    finally:
        cap.release()


def _record_score(report, trait, roi, scale, verdict) -> None:
    """Note the raw match score behind a verdict, for the headroom readout.

    Only meaningful for traits that work by template matching; anything else
    simply contributes nothing.
    """
    if verdict is None or trait.name != "real-player":
        return
    from killcutter import traits as traits_mod
    mask = traits_mod.name_mask(roi)
    score, _, confirmed = traits_mod.find_hash(mask, scale)
    (report.hit_scores if confirmed else report.miss_scores).append(score)
