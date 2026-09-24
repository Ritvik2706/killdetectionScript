"""All terminal presentation for the pipeline.

The detection core talks to a :class:`ConsoleReporter` through a small set of
hooks; the rest are one-shot renderers the CLI calls directly. Keeping every
``print`` here means the core modules stay free of formatting concerns.
"""

import sys

from killcutter import ui
from killcutter.timecode import format_clock, format_duration, format_eta


# ── Generic status lines ────────────────────────────────────────────────────────

def error(message: str) -> None:
    print(ui.badge("ERROR", bg=ui.RED) + " " + ui.paint(message, ui.WHITE))


def banner(subtitle: str, config_path=None) -> None:
    print(ui.banner("KILLFEED AUTO-CUTTER", subtitle))
    if config_path:
        print("  " + ui.paint("config", ui.GREY) + " " + ui.paint(config_path, ui.DIM))


# ── Detection reporter ──────────────────────────────────────────────────────────

class ConsoleReporter:
    """Renders detection progress. In ``debug`` mode it prints per-sample lines
    instead of the live progress bar."""

    def __init__(self, debug: bool = False):
        self.debug = debug
        # The live bar redraws with \r, which turns into thousands of lines when
        # stdout is a pipe or a log file. Only animate it for a real terminal.
        self.animate = sys.stdout.isatty()

    def begin(self, meta) -> None:
        s = meta.settings
        rows = [
            ui.kv("Source", meta.source, val_color=ui.WHITE),
            ui.kv("Format", f"{meta.fps:.2f} fps   ·   {format_clock(meta.duration)}"
                            f"   ·   {meta.total_frames} frames"),
            ui.kv("Scan region", f"x={meta.region[0]}  y={meta.region[1]}  "
                                 f"w={meta.region[2]}  h={meta.region[3]}"
                                 + (f"   ·   {meta.layout}" if meta.layout else "")),
            ui.kv("Clip window", f"−{s.offset:g}s lead-in   +{s.end_offset:g}s tail"
                                 f"   ·   merge < {s.merge_gap:g}s"),
            ui.kv("Analyze range", f"{format_clock(meta.scan_start)} → "
                                      f"{format_clock(meta.scan_end or meta.duration)}"),
            ui.kv("Sampling", f"{s.rate:g}×/sec   ·   {meta.total_checks} checks"),
        ]
        if meta.dry_run:
            rows.append(ui.kv("Mode", "dry run — timestamps.txt will NOT be written",
                              val_color=ui.AMBER))
        print(ui.panel(rows, title="DETECTION", color=ui.TEAL))
        print()

    def frame(self, elapsed, triggered) -> None:
        if self.debug:
            mark = ui.paint("Y", ui.GREEN, bold=True) if triggered else ui.paint("n", ui.DIM)
            print(f"  {ui.paint(format_clock(elapsed), ui.GREY)}  triggered={mark}")

    def progress(self, done, total, elapsed, duration, kills, eta) -> None:
        if self.debug or not self.animate:
            return
        # CLEAR_LINE first, so a line that got shorter (terminal resized, a
        # suffix dropped) leaves no tail of the previous frame behind.
        print(ui.CLEAR_LINE + self._bar(done, total, elapsed, duration, kills, done, eta),
              end="\r", flush=True)

    def aborted(self, elapsed, duration, kills) -> None:
        pct = 100 * elapsed / duration if duration else 0
        print(ui.CLEAR_LINE + "  " + ui.badge("STOPPED", fg=ui.INK, bg=ui.AMBER) + " "
              + ui.paint(f"Scan interrupted at {format_clock(elapsed)} "
                         f"({pct:.0f}% of the file).", ui.WHITE))
        print("  " + ui.paint(f"Keeping the {kills} clip{'s' if kills != 1 else ''} "
                              "found so far.", ui.DIM))

    def kill(self, index, at, clip) -> None:
        print(
            ui.CLEAR_LINE
            + ui.badge(f"KILL #{index}", bg=ui.GREEN) + " "
            + ui.paint(format_clock(at), ui.LIME, bold=True)
            + f"  {ui.paint('→', ui.DIM)}  "
            + ui.paint(f"{format_clock(clip.start)} – {format_clock(clip.end)}", ui.WHITE)
            + ui.paint(f"   {clip.name}", ui.TEAL)
        )

    def extended(self, clip) -> None:
        print(
            ui.CLEAR_LINE
            + ui.badge("EXTENDED", fg=ui.INK, bg=ui.AMBER) + " "
            + ui.paint(f"{format_clock(clip.start)} – {format_clock(clip.end)}", ui.WHITE)
            + ui.paint(f"   {clip.name}", ui.GREY)
        )

    # The bar is redrawn with \r, which only returns to the start of the final
    # screen row. A line wider than the terminal therefore wraps and leaves its
    # previous rows behind, turning the live bar into a wall of scrolling text —
    # so the line is fitted to the terminal instead of being a fixed width.
    MAX_BAR = 32
    MIN_BAR = 6

    @classmethod
    def _bar(cls, done, total, elapsed, duration, kills, tick, eta, width=None):
        pct = done / max(total, 1)
        spin = ui.spinner_frame(tick)
        pct_s = ui.paint(f"{pct * 100:5.1f}%", ui.WHITE, bold=True)
        if kills:
            tally = ui.badge(f"{kills} KILL{'S' if kills != 1 else ''}", bg=ui.GREEN)
        else:
            tally = ui.paint("0 kills", ui.DIM)

        # (drop_rank, text) — lowest rank is given up first when space is tight.
        # The ETA goes before the clock, and the kill tally is kept longest.
        suffixes = [
            (1, "  " + ui.paint(f"{format_clock(elapsed)} / {format_clock(duration)}",
                                ui.GREY)),
            (0, "  " + ui.paint(f"ETA {format_eta(eta)}", ui.DIM)),
            (2, "  " + tally),
        ]

        avail = (ui.term_width() if width is None else width) - 1
        fixed = 2 + ui.visible_len(spin) + 1 + 1 + ui.visible_len(pct_s)

        def suffix_width():
            return sum(ui.visible_len(t) for _, t in suffixes)

        while suffixes and fixed + suffix_width() + cls.MIN_BAR > avail:
            suffixes.remove(min(suffixes, key=lambda s: s[0]))

        bar_w = max(cls.MIN_BAR,
                    min(cls.MAX_BAR, avail - fixed - suffix_width()))
        bar = ui.gradient_bar(pct, bar_w)
        return f"  {spin} {bar} {pct_s}" + "".join(t for _, t in suffixes)


# ── One-shot result / export renderers ──────────────────────────────────────────

def detection_results(clips) -> None:
    """Print the rule + RESULTS panel (or a 'no kills' note)."""
    print(ui.CLEAR_LINE + ui.rule(ui.DIM))
    if not clips:
        print("  " + ui.badge("DONE", bg=ui.AMBER) + " "
              + ui.paint("No kills detected.", ui.WHITE))
        print("  " + ui.paint("Run 'killcutter diagnose' to see which check is failing.",
                              ui.DIM))
        return

    rows = []
    for idx, clip in enumerate(clips, 1):
        rows.append(
            ui.paint(f"#{idx:<3}", ui.TEAL, bold=True) + " "
            + ui.paint(f"{format_clock(clip.start)} – {format_clock(clip.end)}", ui.WHITE)
            + "  " + ui.paint(f"[{format_clock(clip.duration)}]", ui.AMBER)
            + "  " + ui.paint(clip.name, ui.GREY)
        )
    total = sum(c.duration for c in clips)
    summary = (ui.paint(f"{len(clips)} clip{'s' if len(clips) != 1 else ''} detected",
                        ui.GREEN, bold=True)
               + ui.paint(f"   ·   total footage {format_clock(total)}", ui.GREY))
    print(ui.panel([summary, ""] + rows, title="RESULTS", color=ui.GREEN))


def timestamps_saved(path) -> None:
    print("\n  " + ui.badge("SAVED", bg=ui.CYAN) + " " + ui.paint(path, ui.WHITE))


def dry_run_note() -> None:
    print("\n  " + ui.badge("DRY RUN", bg=ui.AMBER) + " " + ui.paint("No file written.", ui.WHITE))


def export_handoff() -> None:
    print("\n" + ui.rule(ui.DIM))
    print("  " + ui.paint("↳ handing off to highlight export", ui.PURPLE, italic=True))


def export_plan(plan) -> None:
    """Print the EXPORT summary + CLIPS panels for an export plan."""
    n = len(plan.clips)
    info = [
        ui.kv("Source", plan.video_basename, val_color=ui.WHITE),
        ui.kv("Frame rate", f"{plan.fps:.3f} fps   ·   "
                            f"{'drop' if plan.is_drop else 'non-drop'} frame"),
    ]
    if plan.fps_note:
        info.append(ui.kv("Rate", plan.fps_note, val_color=ui.AMBER))
    info.append(ui.kv("Reel", f"{n} clip{'s' if n != 1 else ''}   ·   "
                              f"{format_duration(plan.total_seconds)} total"))
    info.append(ui.kv("Output", plan.out_path, val_color=ui.WHITE))
    print(ui.panel(info, title="EXPORT", color=ui.PURPLE))
    if plan.fps_warning:
        print("  " + ui.badge("CHECK FPS", fg=ui.INK, bg=ui.AMBER) + " "
              + ui.paint(plan.fps_warning, ui.WHITE))
    print()

    rows = []
    for idx, clip in enumerate(plan.clips, 1):
        rows.append(
            ui.paint(f"#{idx:<3}", ui.TEAL, bold=True) + " "
            + ui.paint(f"{format_duration(clip.start)} – {format_duration(clip.end)}", ui.WHITE)
            + "  " + ui.paint(f"[{format_duration(clip.duration)}]", ui.AMBER)
            + "  " + ui.paint(clip.name, ui.GREY)
        )
    print(ui.panel(rows, title="CLIPS", color=ui.CYAN))


def export_saved(plan) -> None:
    drop = "drop" if plan.is_drop else "non-drop"
    print("\n  " + ui.badge("SAVED", bg=ui.GREEN) + " " + ui.paint(plan.out_path, ui.WHITE))
    print("  " + ui.paint("Premiere Pro:", ui.GREY)
          + ui.paint(f"  File ▸ Import ▸ {plan.out_path}", ui.WHITE))
    print("  " + ui.badge("IMPORTANT", fg=ui.INK, bg=ui.AMBER) + " "
          + ui.paint(f"Sequence MUST be {plan.fps:.3f} fps ({drop} frame), "
                     "or cuts will drift.", ui.WHITE))


def interrupted() -> None:
    print(ui.paint("\n  Interrupted.", ui.DIM))


# ── Diagnosis renderer ──────────────────────────────────────────────────────────

def _swatch(rgb) -> str:
    """Name a colour roughly, so 'red → yellow' jumps out of the report."""
    r, g, b = rgb
    if r < 60 and g < 60 and b < 60:
        return "dark"
    if g > 180 and r > 180:
        return "yellow"
    if r > 150 and g < 80:
        return "red"
    if r > 150 and g < 150:
        return "orange"
    return "other"


def diagnosis(report) -> None:
    """Print the DIAGNOSIS panels for a :class:`killcutter.diagnose.Diagnosis`."""
    from killcutter import constants

    size = f"{report.width}x{report.height}"
    size_ok = (report.width, report.height) == (1920, 1080)
    scanned = f"{format_clock(report.scan_start)} → " \
              f"{format_clock(report.scan_start + report.scan_span)}"
    info = [
        ui.kv("Source", report.source, val_color=ui.WHITE),
        ui.kv("Format", f"{size}   ·   {report.fps:.2f} fps   ·   "
                        f"{format_clock(report.duration)}",
              val_color=ui.WHITE if size_ok else ui.AMBER),
        ui.kv("Scanned", f"{scanned}   ·   {report.sampled} samples"),
        ui.kv("Scan region", f"x={report.region[0]}  y={report.region[1]}  "
                             f"w={report.region[2]}  h={report.region[3]}"),
        ui.kv("HUD layout", report.layout or "1920x1080 reference layout"),
    ]
    print(ui.panel(info, title="DIAGNOSIS", color=ui.TEAL))
    print()

    def stage(label, hits, coord=None):
        pct = 100 * hits / max(report.sampled, 1)
        colour = ui.GREEN if hits else ui.RED
        where = ui.paint(f"  {coord}", ui.DIM) if coord else ""
        return (ui.paint(f"{label:<22}", ui.GREY)
                + ui.paint(f"{hits:5d} frames", colour, bold=True)
                + ui.paint(f"  ({pct:4.1f}%)", ui.DIM) + where)

    rows = [
        stage("white pixel", report.white_hits, report.white_pixel),
        stage("accent pixel", report.accent_hits, report.accent_pixel),
        stage("both (OCR runs)", report.gated),
        stage("header confirmed", report.kills),
    ]
    rows += ["", ui.paint("ELIMINATED strip", ui.GREY)
             + ui.paint(f"  x={report.eliminated_region[0]} y={report.eliminated_region[1]} "
                        f"w={report.eliminated_region[2]} h={report.eliminated_region[3]}", ui.DIM),
             stage("name line seen", report.eliminated_seen),
             stage("with # (real player)", report.eliminated_hashed)]
    if report.accent_samples:
        med = tuple(int(sum(c[i] for c in report.accent_samples)
                        / len(report.accent_samples)) for i in range(3))
        rows += ["", ui.paint("accent colour seen      ", ui.GREY)
                 + ui.paint(f"RGB{med}", ui.WHITE)
                 + ui.paint(f"  ({_swatch(med)})", ui.AMBER)]
    print(ui.panel(rows, title="PIPELINE", color=ui.CYAN))

    if report.headers:
        print()
        hrows = []
        for h in report.headers[:12]:
            mark = (ui.paint("✓", ui.GREEN, bold=True) if h.accepted
                    else ui.paint("·", ui.DIM))
            hrows.append(
                f"{mark} " + ui.paint(f"{h.count:4d}x", ui.AMBER) + "  "
                + ui.paint(f"{h.header[:28]:28s}",
                           ui.WHITE if h.accepted else ui.GREY)
                + ui.paint(f"  RGB{h.accent} {_swatch(h.accent)}", ui.DIM))
        print(ui.panel(hrows, title="BANNERS SEEN", color=ui.PURPLE))

    print()
    problems = report.problems
    if not problems:
        print("  " + ui.badge("HEALTHY", bg=ui.GREEN) + " "
              + ui.paint(f"Detected {report.kills} confirmed kill frames — "
                         "the HUD constants still match this footage.", ui.WHITE))
    else:
        for p in problems:
            print("  " + ui.badge("PROBLEM", bg=ui.RED) + " " + ui.paint(p, ui.WHITE))


# ── Doctor renderer ─────────────────────────────────────────────────────────────

def doctor(results) -> None:
    """Print the environment check table from :func:`killcutter.environment.check`."""
    rows = []
    for c in results:
        if c.ok:
            mark = ui.paint("✓", ui.GREEN, bold=True)
            label = ui.paint(f"{c.name:<16}", ui.WHITE)
        else:
            mark = ui.paint("✗", ui.RED, bold=True)
            label = ui.paint(f"{c.name:<16}", ui.RED, bold=True)
        rows.append(f"{mark} {label}{ui.paint(c.detail, ui.GREY)}")
        if c.fix and not c.ok:
            rows.append(f"  {ui.paint('↳ ' + c.fix, ui.AMBER)}")
        elif c.fix:
            rows.append(f"  {ui.paint('↳ ' + c.fix, ui.DIM)}")
    print(ui.panel(rows, title="ENVIRONMENT", color=ui.TEAL))
    print()

    from killcutter.environment import blocking_failures
    bad = blocking_failures(results)
    if not bad:
        print("  " + ui.badge("READY", bg=ui.GREEN) + " "
              + ui.paint("Everything killcutter needs is installed.", ui.WHITE))
    else:
        names = ", ".join(c.name for c in bad)
        print("  " + ui.badge("BLOCKED", bg=ui.RED) + " "
              + ui.paint(f"Cannot run until this is fixed: {names}", ui.WHITE))


def export_skipped(timestamps_path) -> None:
    """After an interrupted scan, don't silently build a reel from half a file."""
    print("\n  " + ui.paint("Export skipped because the scan was stopped. "
                            "Build the EDL anyway with:", ui.DIM))
    print("  " + ui.paint(f"killcutter export --timestamps {timestamps_path}", ui.WHITE))


def partial_note(path) -> None:
    print("  " + ui.paint("Scan was interrupted, so this file covers only the part "
                          "that was scanned.", ui.DIM))


# ── Traits ──────────────────────────────────────────────────────────────────────

def trait_list(traits) -> None:
    """Print every registered trait and how to ask for it."""
    rows = []
    for trait in traits:
        rows.append(ui.paint(f"{trait.name:<16}", ui.TEAL, bold=True)
                    + ui.paint(trait.summary, ui.WHITE))
        if trait.negative_name:
            rows.append(ui.paint(f"{'':<16}", ui.GREY)
                        + ui.paint(f"negate with: {trait.negative_name}", ui.DIM))
        if trait.detail:
            rows.append(ui.paint(f"{'':<16}", ui.GREY) + ui.paint(trait.detail, ui.GREY))
        rows.append("")
    rows += [ui.paint("  killcutter detect --exclude bot", ui.WHITE),
             ui.paint("  killcutter export --require real-player", ui.WHITE)]
    print(ui.panel(rows, title="TRAITS", color=ui.TEAL))


def traits_filtered(dropped, require, exclude, keep_unknown) -> None:
    """Say what the trait filters removed, and why, so it is never silent."""
    asked = ", ".join([f"require {t}" for t in require]
                      + [f"exclude {t}" for t in exclude])
    n = len(dropped)
    print("  " + ui.badge("FILTERED", fg=ui.INK, bg=ui.AMBER) + " "
          + ui.paint(f"{n} clip{'s' if n != 1 else ''} dropped  ({asked})", ui.WHITE))
    if keep_unknown:
        print("  " + ui.paint("Clips whose traits could not be determined were kept; "
                              "pass --drop-unknown to remove those too.", ui.DIM))
    for clip in dropped[:8]:
        print("    " + ui.paint(f"{format_duration(clip.start)} – "
                                f"{format_duration(clip.end)}", ui.GREY)
              + "  " + ui.paint(clip.name, ui.DIM))
    if n > 8:
        print("    " + ui.paint(f"… and {n - 8} more", ui.DIM))
    print()


def trait_report(report) -> None:
    """Print the sampling result from ``killcutter traits --video``."""
    info = [
        ui.kv("Source", report.source, val_color=ui.WHITE),
        ui.kv("Trait", report.trait, val_color=ui.WHITE),
        ui.kv("Region", f"x={report.region[0]}  y={report.region[1]}  "
                        f"w={report.region[2]}  h={report.region[3]}"),
        ui.kv("HUD layout", report.layout),
        ui.kv("Scanned", f"{format_clock(report.scan_start)} → "
                         f"{format_clock(report.scan_start + report.scan_span)}"
                         f"   ·   {report.sampled} samples"),
    ]
    print(ui.panel(info, title="TRAIT CHECK", color=ui.TEAL))
    print()

    def row(label, count, colour):
        pct = 100 * count / max(report.sampled, 1)
        return (ui.paint(f"{label:<22}", ui.GREY)
                + ui.paint(f"{count:5d} frames", colour, bold=True)
                + ui.paint(f"  ({pct:4.1f}%)", ui.DIM))

    rows = [row("yes", report.yes, ui.GREEN),
            row("no", report.no, ui.AMBER),
            row("not on screen", report.unknown, ui.GREY)]
    if report.hit_scores:
        head = report.headroom
        colour = ui.GREEN if head is None or head >= 0.05 else ui.AMBER
        rows += ["", ui.paint("match score (hits)    ", ui.GREY)
                 + ui.paint(f"{min(report.hit_scores):.2f} – {max(report.hit_scores):.2f}",
                            ui.WHITE),
                 ui.paint("headroom over cutoff  ", ui.GREY)
                 + ui.paint(f"{head:+.2f}", colour, bold=True)]
    if report.miss_scores:
        rows.append(ui.paint("best score (rejected) ", ui.GREY)
                    + ui.paint(f"{max(report.miss_scores):.2f}", ui.WHITE))
    if report.dump_dir:
        rows += ["", ui.paint("crops written to        ", ui.GREY)
                 + ui.paint(report.dump_dir, ui.WHITE)]
    print(ui.panel(rows, title="VERDICTS", color=ui.CYAN))
    head = report.headroom
    if head is not None and head < 0.05:
        print("\n  " + ui.badge("THIN MARGIN", fg=ui.INK, bg=ui.AMBER) + " "
              + ui.paint(f"The weakest confirmed frame cleared the cutoff by only "
                         f"{head:+.2f}. Slightly worse footage would start reading "
                         "real players as bots — send this report before trusting "
                         "'--exclude bot' on a whole session.", ui.WHITE))
    if not report.decided:
        print("\n  " + ui.badge("CHECK", fg=ui.INK, bg=ui.AMBER) + " "
              + ui.paint("The trait's evidence never appeared. Either this slice of "
                         "footage has none, or the region has moved — try a different "
                         "--start, then 'killcutter calibrate'.", ui.WHITE))
