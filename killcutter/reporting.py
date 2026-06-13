"""All terminal presentation for the pipeline.

The detection core talks to a :class:`ConsoleReporter` through a small set of
hooks; the rest are one-shot renderers the CLI calls directly. Keeping every
``print`` here means the core modules stay free of formatting concerns.
"""

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

    def begin(self, meta) -> None:
        s = meta.settings
        rows = [
            ui.kv("Source", meta.source, val_color=ui.WHITE),
            ui.kv("Format", f"{meta.fps:.2f} fps   ·   {format_clock(meta.duration)}"
                            f"   ·   {meta.total_frames} frames"),
            ui.kv("Scan region", f"x={meta.region[0]}  y={meta.region[1]}  "
                                 f"w={meta.region[2]}  h={meta.region[3]}"),
            ui.kv("Clip window", f"−{s.offset:g}s lead-in   +{s.end_offset:g}s tail"
                                 f"   ·   merge < {s.merge_gap:g}s"),
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
        if self.debug:
            return
        print(self._bar(done, total, elapsed, duration, kills, done, eta),
              end="\r", flush=True)

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

    @staticmethod
    def _bar(done, total, elapsed, duration, kills, tick, eta, width=32):
        pct = done / max(total, 1)
        spin = ui.spinner_frame(tick)
        bar = ui.gradient_bar(pct, width)
        pct_s = ui.paint(f"{pct * 100:5.1f}%", ui.WHITE, bold=True)
        clock = ui.paint(f"{format_clock(elapsed)} / {format_clock(duration)}", ui.GREY)
        eta_s = ui.paint(f"ETA {format_eta(eta)}", ui.DIM)
        if kills:
            tally = "  " + ui.badge(f"{kills} KILL{'S' if kills != 1 else ''}", bg=ui.GREEN)
        else:
            tally = "  " + ui.paint("0 kills", ui.DIM)
        return f"  {spin} {bar} {pct_s}  {clock}  {eta_s}{tally}"


# ── One-shot result / export renderers ──────────────────────────────────────────

def detection_results(clips) -> None:
    """Print the rule + RESULTS panel (or a 'no kills' note)."""
    print(ui.CLEAR_LINE + ui.rule(ui.DIM))
    if not clips:
        print("  " + ui.badge("DONE", bg=ui.AMBER) + " "
              + ui.paint("No kills detected.", ui.WHITE)
              + ui.paint("  Try tuning the region / trigger pixels with calibrate.", ui.DIM))
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
    if plan.ntsc_note:
        info.append(ui.kv("NTSC", plan.ntsc_note, val_color=ui.AMBER))
    info.append(ui.kv("Reel", f"{n} clip{'s' if n != 1 else ''}   ·   "
                              f"{format_duration(plan.total_seconds)} total"))
    info.append(ui.kv("Output", plan.out_path, val_color=ui.WHITE))
    print(ui.panel(info, title="EXPORT", color=ui.PURPLE))
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
