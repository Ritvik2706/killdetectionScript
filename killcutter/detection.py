"""Kill detection core.

CoD shows an "ENEMY DOWNED" banner in the top-right on a kill. OCR on every
frame would be far too slow, so each sampled frame is gated by two cheap pixel
checks (see :mod:`killcutter.constants`); only frames that pass are OCR'd, and
the OCR'd header then has to actually read "ENEMY DOWNED" before we count a
kill. That last step matters: teammate banners share the slot, the icon and the
accent colour, so pixels alone cannot tell them apart.

This module is presentation-free: it walks the video and reports progress and
events through a ``reporter`` object (see :mod:`killcutter.reporting`),
returning the list of :class:`~killcutter.models.Clip` it found. Anything that
prints lives in the reporter, so the algorithm stays testable and readable.
"""

import math
import difflib
import os
import re
import time
from dataclasses import dataclass

import cv2
import pytesseract

from killcutter import constants, hud as hud_mod, traits as traits_mod
from killcutter.errors import ConfigError, DependencyError, VideoError
from killcutter.models import Clip
from killcutter.presets import Preset
from killcutter.ranges import resolve_range


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
    preset: Preset | None = None       # None preserves the legacy Warzone CLI behavior
    traits: bool = True          # record per-kill traits (see killcutter.traits)


def validate(settings: DetectionSettings) -> None:
    """Reject settings that would silently produce nonsense."""
    if not math.isfinite(settings.rate) or settings.rate <= 0:
        raise ConfigError(f"--rate must be greater than 0 (got {settings.rate:g}).")
    if settings.rate > 60:
        raise ConfigError(f"--rate above 60 samples/sec is pointless (got "
                          f"{settings.rate:g}); choose 60 or fewer samples per second.")
    for name, value in (("--offset", settings.offset),
                        ("--end-offset", settings.end_offset),
                        ("--merge-gap", settings.merge_gap),
                        ("--cooldown", settings.cooldown)):
        if not math.isfinite(value) or value < 0:
            raise ConfigError(f"{name} cannot be negative (got {value:g}).")
    if len(settings.region) != 4 or any(v < 0 for v in settings.region):
        raise ConfigError(f"--region must be four non-negative numbers "
                          f"(got {tuple(settings.region)}).")
    if settings.region[2] <= 0 or settings.region[3] <= 0:
        raise ConfigError("--region width and height must be greater than 0.")


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
    layout: str = ""
    scan_start: float = 0.0
    scan_end: float = 0.0


# ── Pixel pre-checks ────────────────────────────────────────────────────────────

def _pixel(frame, coord):
    """Return ``(r, g, b)`` at ``coord``, or ``None`` if it is off-frame."""
    px, py = coord
    fh, fw = frame.shape[:2]
    if py >= fh or px >= fw:
        return None
    b, g, r = frame[py, px]
    return int(r), int(g), int(b)


def _pixel_is_white(frame, coord) -> bool:
    """True where the banner icon is: bright on every channel."""
    rgb = _pixel(frame, coord)
    if rgb is None:
        return False
    t = constants.BRIGHT_THRESHOLD
    return rgb[0] > t and rgb[1] > t and rgb[2] > t


def _pixel_is_accent(frame, coord) -> bool:
    """True on the banner's left accent bar — a saturated warm colour.

    Hue-agnostic on purpose: the bar was red before the Sept 2026 HUD restyle
    and is yellow after it, and both should keep working.
    """
    rgb = _pixel(frame, coord)
    if rgb is None:
        return False
    return rgb[0] > constants.ACCENT_MIN_RED and rgb[2] < constants.ACCENT_MAX_BLUE


def _banner_visible(frame, hud=None) -> bool:
    """Cheap gate: is *a* kill-shaped banner on screen? Confirmed later by OCR.

    ``hud`` carries the resolved pixel coordinates for this frame size; without
    one the 1920x1080 reference values are used.
    """
    white = hud.white if hud else constants.TRIGGER_PIXEL_WHITE
    accent = hud.accent if hud else constants.TRIGGER_PIXEL_ACCENT
    return _pixel_is_white(frame, white) and _pixel_is_accent(frame, accent)


# ── OCR + name merging ──────────────────────────────────────────────────────────

def _ocr_lines(roi, *, timeout=0) -> list:
    """OCR the banner ROI and return its non-empty lines, in order."""
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, thresh = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    try:
        text = pytesseract.image_to_string(thresh, config=constants.TESSERACT_CONFIG, timeout=timeout)
    except (pytesseract.TesseractNotFoundError, OSError) as exc:
        from killcutter import environment
        raise DependencyError(
            "Tesseract OCR is required to read player names but could not be "
            f"run ({exc}).\n  Install it with:  {environment.install_hint()}\n"
            "  Or set KILLCUTTER_TESSERACT to the binary's full path."
        ) from exc
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _letters(text: str) -> str:
    return re.sub(r"[^A-Z]", "", text.upper())


def _is_kill_header(header: str) -> bool:
    """True if ``header`` reads "ENEMY DOWNED" rather than a teammate banner.

    OCR mangles these constantly ("ENEMY DOVWNED", "TEAMMATE DOW|"), so match
    fuzzily — but require the kill header to be a *better* match than any of the
    look-alikes, which is what keeps "TEAMMATE DOWN" out.
    """
    letters = _letters(header)
    if not letters:
        return False

    def ratio(target):
        return difflib.SequenceMatcher(None, letters, _letters(target)).ratio()

    kill = ratio(constants.BANNER_HEADER)
    if kill < constants.HEADER_MIN_RATIO:
        return False
    return all(kill > ratio(other) for other in constants.REJECTED_HEADERS)


def read_banner(roi):
    """Return ``(is_kill, player_name)`` for a banner ROI.

    ``player_name`` is the line under the header, or ``""`` when OCR could not
    make one out.
    """
    lines = _ocr_lines(roi)
    if not lines or not _is_kill_header(lines[0]):
        return False, ""
    return True, lines[1] if len(lines) >= 2 else ""


def _fold_name(name: str) -> str:
    """Normalise a name for comparison, folding characters OCR mixes up."""
    folded = "".join(constants.NAME_CONFUSABLES.get(c, c) for c in name.lower())
    return re.sub(r"[^a-z0-9]", "", folded)


def _same_player(a: str, b: str) -> bool:
    """True if two OCR readings are probably the same player."""
    fa, fb = _fold_name(a), _fold_name(b)
    if not fa or not fb:
        return False
    return difflib.SequenceMatcher(None, fa, fb).ratio() >= constants.NAME_MATCH_RATIO


def _notice_lag(rate: float) -> float:
    """How long after a kill we actually notice it, in seconds.

    The banner sweeps in before it reaches the trigger pixel, and we only sample
    every ``1 / rate`` seconds — so on average we are half an interval late on
    top of the ramp. Subtracting this puts the recorded time on the kill itself
    instead of on the moment we spotted its banner.
    """
    sampling = 0.5 / rate if rate > 0 else 0.0
    return constants.BANNER_RAMP_SECONDS + sampling


def _merge_names(prev_name: str, new_name: str) -> str:
    """Combine player names for a merged clip; discard '???' when possible."""
    if not new_name or new_name == "???":
        return prev_name
    if not prev_name or prev_name == "???":
        return new_name
    if any(_same_player(part, new_name) for part in prev_name.split(" + ")):
        return prev_name
    return f"{prev_name} + {new_name}"


# ── Trait observation ───────────────────────────────────────────────────────────

def _observe(pending, frame, hud) -> None:
    """Run every registered trait probe for the clips still inside their window.

    Called on every sampled frame, not just triggered ones: the evidence a trait
    looks for (the ELIMINATED line, say) usually shows up *after* the banner
    that got us here, and often when no banner is up at all.
    """
    if not pending:
        return
    crops = {}
    for observation in pending:
        for trait in traits_mod.REGISTRY.values():
            box = crops.get(trait.region)
            if box is None:
                box = crops[trait.region] = _crop(frame, getattr(hud, trait.region))
            observation.note(trait.name, trait.probe(box, hud.scale))


def _crop(frame, box):
    """Clamp ``box`` to the frame and return that view (possibly empty)."""
    x, y, w, h = box
    fh, fw = frame.shape[:2]
    return frame[min(y, fh):min(y + h, fh), min(x, fw):min(x + w, fw)]


def _retire(pending, clips, elapsed, *, force=False) -> None:
    """Write resolved traits onto their clips once their window has passed."""
    for observation in list(pending):
        if force or elapsed >= observation.until:
            if observation.clip_index < len(clips):
                clip = clips[observation.clip_index]
                clip.traits = traits_mod.merge(clip.traits, observation.resolve())
            pending.remove(observation)


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


# ── Frame sampling ──────────────────────────────────────────────────────────────

def _samples(cap, duration, check_interval):
    """Yield ``(elapsed_seconds, frame)`` at roughly ``check_interval`` apart.

    Walks the file sequentially and uses ``grab()`` to skip past frames we do
    not want, decoding fully only for the ones we sample. Seeking per sample
    instead (``set(CAP_PROP_POS_MSEC)``) forces a keyframe seek and a re-decode
    of most of the GOP every time, which measured ~3x slower on OBS captures.

    Times still come from the container (``CAP_PROP_POS_MSEC``), so VFR footage
    does not drift.
    """
    next_at = 0.0
    while True:
        if not cap.grab():
            return
        elapsed = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        if duration and elapsed >= duration:
            return
        if elapsed + 1e-9 < next_at:
            continue
        ok, frame = cap.retrieve()
        if not ok:
            return
        yield elapsed, frame
        # Anchor to the frame we actually got, so a long GOP cannot make us
        # fall behind and sample faster than requested forever after.
        next_at = elapsed + check_interval


# ── Main entry ──────────────────────────────────────────────────────────────────

def detect(video_path, settings: DetectionSettings, reporter, *, dry_run=False,
           region_override=None, start=0.0, limit=None, end=None, cancelled=None):
    """Scan ``video_path``; return ``(clips, completed)``.

    ``completed`` is False when the user interrupted the scan, in which case the
    clips found so far are still returned — a two-hour scan should never throw
    away its work because you pressed Ctrl-C near the end.

    ``cancelled`` is an optional zero-argument callback for desktop workers.
    When it returns True at a sample boundary, partial clips are returned.

    Raises :class:`VideoError` if the file can't be opened or has no frame rate.
    """
    validate(settings)
    if settings.preset is not None:
        settings.preset.validate()
        if settings.preset.detector != 'warzone':
            from .generic_detection import detect as detect_general
            return detect_general(video_path, settings, reporter, dry_run=dry_run,
                                  start=start, limit=limit, end=end, cancelled=cancelled)
    if not os.path.exists(video_path):
        raise VideoError(f"No such file: {video_path}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise VideoError(
            f"Could not open: {video_path}\n"
            "  The file may be corrupt, still being written, or in a codec "
            "this OpenCV build cannot read.")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps <= 0:
        cap.release()
        raise VideoError(f"Could not read frame rate (got {fps}). Is the file valid?")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    hud = hud_mod.for_size(width, height, region_override)
    settings.region = hud.region

    duration = _measure_duration(cap, total_frames, fps)
    try:
        start, scan_end = resolve_range(duration, start, limit, end)
    except ConfigError:
        cap.release()
        raise
    check_interval = 1.0 / settings.rate
    total_checks = int(max(0.0, scan_end - start) / check_interval) + 1

    meta = DetectionMeta(
        source=os.path.basename(video_path), fps=fps, duration=duration,
        total_frames=total_frames, region=settings.region, settings=settings,
        total_checks=total_checks, dry_run=dry_run,
        layout=hud_mod.describe(hud), scan_start=start, scan_end=scan_end,
    )
    reporter.begin(meta)

    x, y, w, h = settings.region
    clips: list = []
    last_kill = -(settings.cooldown + 1)
    last_name = ""      # player from the last counted kill, for re-read detection
    banner_cleared = True   # has the banner gone away since that kill?
    player = ""   # most recent OCR result — shown in preview during cooldown frames
    pending: list = []   # trait evidence still being gathered, per clip
    start_wall = time.time()
    done = 0
    completed = True

    try:
        if start:
            cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)
        for elapsed, frame in _samples(cap, duration, check_interval):
            if cancelled is not None and cancelled():
                raise KeyboardInterrupt
            if elapsed < start:
                continue
            if elapsed >= scan_end:
                break
            done += 1
            if settings.traits:
                _observe(pending, frame, hud)
                _retire(pending, clips, elapsed)
            triggered = _banner_visible(frame, hud)
            reporter.frame(elapsed, triggered)

            span = scan_end - start
            frac = min((elapsed - start) / span, 1.0) if span > 0 else 0.0
            spent = time.time() - start_wall
            eta = (spent / frac - spent) if frac > 0.001 else None

            if not triggered:
                banner_cleared = True
                reporter.progress(done, total_checks, elapsed, scan_end, len(clips), eta)
                continue

            fh, fw = frame.shape[:2]
            roi = frame[min(y, fh - 1):min(y + h, fh), min(x, fw - 1):min(x + w, fw)]

            if (elapsed - last_kill) > settings.cooldown:
                is_kill, name_text = read_banner(roi)
                if is_kill:
                    player = name_text
                    name = player or "???"

                    # A banner lingers ~4s, outliving the cooldown, so the same
                    # one can be read twice. It is only a new kill if the banner
                    # dropped in between, or a different player is on it now.
                    reread = not banner_cleared and (name == last_name
                                                     or _same_player(name, last_name))
                    if not reread:
                        # ``elapsed`` is when we *noticed*; the kill landed a
                        # little earlier (see BANNER_RAMP_SECONDS). Cut around
                        # the kill, so --offset means what it says.
                        kill_at = max(start, elapsed - _notice_lag(settings.rate))
                        cut_end = min(scan_end, kill_at + settings.end_offset)
                        if clips and (elapsed - last_kill) <= settings.merge_gap:
                            prev = clips[-1]
                            clips[-1] = Clip(prev.start, cut_end,
                                             _merge_names(prev.name, name),
                                             dict(prev.traits))
                            reporter.extended(clips[-1])
                        else:
                            clips.append(
                                Clip(max(start, kill_at - settings.offset), cut_end, name))
                            reporter.kill(len(clips), kill_at, clips[-1])
                        if settings.traits:
                            _open_window(pending, len(clips) - 1, elapsed)
                        last_kill = elapsed
                        last_name = name
                        banner_cleared = False

            if settings.preview and _preview(roi, player):
                completed = False
                reporter.aborted(elapsed, scan_end, len(clips))
                break

            reporter.progress(done, total_checks, elapsed, scan_end, len(clips), eta)
    except KeyboardInterrupt:
        # Keep what we found. The CLI writes it and says the scan was partial.
        completed = False
        reporter.aborted(elapsed if done else start, scan_end, len(clips))
    finally:
        cap.release()
        if settings.preview:
            cv2.destroyAllWindows()

    # Windows still open when the scan ended (or was interrupted) resolve on
    # whatever evidence they did gather, rather than being thrown away.
    _retire(pending, clips, 0.0, force=True)
    return clips, completed


def _preview(roi, player) -> bool:
    """Show the live banner ROI; return True if the user pressed Q to stop."""
    display = roi.copy()
    cv2.putText(display, f"DOWNED: {player}" if player else "DOWNED",
                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.imshow("Banner region", display)
    return cv2.waitKey(1) & 0xFF == ord("q")


def _open_window(pending, clip_index, elapsed) -> None:
    """Start (or extend) the trait-evidence window for ``clip_index``."""
    for observation in pending:
        if observation.clip_index == clip_index:
            observation.until = elapsed + traits_mod.WINDOW_SECONDS
            return
    pending.append(traits_mod.Observation(
        clip_index=clip_index, until=elapsed + traits_mod.WINDOW_SECONDS))
