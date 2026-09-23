"""Command-line interface: ``killcutter <command>``.

Commands:
    detect      scan a video for kills, then auto-build the highlight EDL
    export      build a highlight EDL from an existing timestamps.txt
    calibrate   re-find the scan region / trigger pixel on a frame
    doctor      check this machine has everything killcutter needs
    diagnose    check the HUD constants against a clip when detection stops working

Global flags (before or after the command): --config, --write-config,
--no-color, --version. Config values seed argparse defaults; explicit flags win.
"""

import argparse
import os
import sys

from killcutter import (__version__, config, detection, environment, export,
                        reporting, video)
from killcutter import ui
from killcutter.ranges import parse_timestamp
from killcutter import outputs
from killcutter.constants import DEFAULT_CLIPS_DIR, DEFAULT_REGION
from killcutter.detection import DetectionSettings
from killcutter.errors import KillcutterError, NoClipsError


# ── Parser construction ─────────────────────────────────────────────────────────

def _global_flags() -> argparse.ArgumentParser:
    """Flags shared by the top-level parser and every subcommand."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--config", metavar="PATH", help="Load settings from this TOML file")
    p.add_argument("--no-color", action="store_true", dest="no_color",
                   help="Disable ANSI colour output")
    return p


def _build_parser(cfg, common) -> argparse.ArgumentParser:
    d = config.section(cfg, "detect")
    e = config.section(cfg, "export")
    cfg_region = tuple(d["region"]) if d.get("region") else None

    parser = argparse.ArgumentParser(
        prog="killcutter",
        description="Detect CoD kills and build a Premiere-ready highlight EDL.",
        parents=[common],
    )
    parser.add_argument("--version", action="version",
                        version=f"Killfeed Auto-Cutter {__version__}")
    parser.add_argument("--write-config", nargs="?", const="", metavar="PATH",
                        dest="write_config",
                        help="Write a starter config (default: user config dir) and exit")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # detect ---------------------------------------------------------------
    pd = sub.add_parser("detect", parents=[common],
                        help="Scan a video for kills, then build the highlight EDL")
    pd.add_argument("--video", help="Path to video (omit to pick from the clips folder)")
    pd.add_argument("--region", nargs=4, type=int, metavar=("X", "Y", "W", "H"),
                    default=cfg_region, help=f"Scan region override (default: {DEFAULT_REGION})")
    pd.add_argument("--offset", type=float, default=d.get("offset", 5),
                    help="Seconds before kill to cut (default: 5)")
    pd.add_argument("--end-offset", type=float, default=d.get("end_offset", 5),
                    dest="end_offset", help="Seconds after kill to cut (default: 5)")
    pd.add_argument("--merge-gap", type=float, default=d.get("merge_gap", 10.0),
                    dest="merge_gap",
                    help="Merge kills within this many seconds into one clip (default: 10)")
    pd.add_argument("--cooldown", type=float, default=d.get("cooldown", 3.0),
                    help="Min seconds between detections (default: 3)")
    pd.add_argument("--rate", type=float, default=d.get("rate", 4),
                    help="Frame samples per second (default: 4)")
    pd.add_argument("--start", type=parse_timestamp, default=0.0,
                    help="Skip to this many seconds in before scanning (default: 0)")
    window = pd.add_mutually_exclusive_group()
    window.add_argument("--end", type=parse_timestamp, help="Stop at source time (seconds or HH:MM:SS)")
    pd.add_argument("--interactive", action="store_true", help="Open guided scan setup")
    window.add_argument("--limit", type=parse_timestamp,
                    help="Only scan this many seconds of footage (default: all)")
    pd.add_argument("--timestamps-dir", default=d.get("timestamps_dir", ""),
                    help="Folder for recording-specific timestamp files")
    pd.add_argument("--edl-dir", default=e.get("output_dir", ""), help="Folder for EDL files")
    pd.add_argument("--edl-output", help="Explicit EDL filename (overrides --edl-dir)")
    pd.add_argument("--clips-output-dir", default=d.get("clips_output_dir", "highlights"),
                    help="Folder for rendered MP4 highlights")
    pd.add_argument("--render-clips", action=argparse.BooleanOptionalAction,
                    default=d.get("render_clips", False), help="Render MP4 highlights with FFmpeg")
    pd.add_argument("--output", default=None,
                    help="Where to write detected clips (default: timestamps.txt)")
    pd.add_argument("--preview", action="store_true",
                    help="Show the scan region live with OCR result (for tuning)")
    pd.add_argument("--debug", action="store_true",
                    help="Print trigger result + timestamp for every sample")
    pd.add_argument("--dry-run", action="store_true", dest="dry_run",
                    help="Print detected clips without writing timestamps.txt")
    pd.add_argument("--no-export", action="store_true", dest="no_export",
                    default=not d.get("export", True),
                    help="Skip the automatic highlight-export step")

    # export ---------------------------------------------------------------
    px = sub.add_parser("export", parents=[common],
                        help="Build a highlight EDL from an existing timestamps.txt")
    px.add_argument("--video", help="Source video (omit to pick from the clips folder)")
    px.add_argument("--timestamps", default="timestamps.txt",
                    help="timestamps.txt from detect (default: timestamps.txt)")
    px.add_argument("--edl-dir", default=e.get("output_dir", ""), help="Folder for EDL files")
    px.add_argument("--output", help="Output EDL path (default: <video_stem>_highlights.edl)")
    px.add_argument("--name", default=e.get("name", "Kill Highlights"),
                    help="Sequence name shown in Premiere (default: 'Kill Highlights')")
    px.add_argument("--fps", type=float, default=e.get("fps"),
                    help="Authoring fps; MUST match your Premiere sequence (e.g. 59.94)")

    # diagnose -------------------------------------------------------------
    pg = sub.add_parser("diagnose", parents=[common],
                        help="Check the HUD constants against a clip")
    pg.add_argument("--video", help="Video to check (omit to pick from the clips folder)")
    pg.add_argument("--region", nargs=4, type=int, metavar=("X", "Y", "W", "H"),
                    default=cfg_region, help=f"Scan region override (default: {DEFAULT_REGION})")
    pg.add_argument("--start", type=float,
                    help="Where to start scanning, seconds (default: 10%% into the file)")
    pg.add_argument("--span", type=float, default=600.0,
                    help="How many seconds of footage to sample (default: 600)")
    pg.add_argument("--rate", type=float, default=d.get("rate", 4),
                    help="Frame samples per second (default: 4)")

    sub.add_parser("ui", parents=[common], help="Open the interactive workspace")
    sub.add_parser("settings", parents=[common], help="Edit and save default settings")

    # doctor ---------------------------------------------------------------
    sub.add_parser("doctor", parents=[common],
                   help="Check this machine has everything killcutter needs")

    # calibrate ------------------------------------------------------------
    pc = sub.add_parser("calibrate", parents=[common],
                        help="Re-find the scan region / trigger pixel on a frame")
    pc.add_argument("--video", help="Video to calibrate against (omit to pick)")
    pc.add_argument("--pixel", action="store_true",
                    help="Pick a trigger pixel instead of the region")
    pc.add_argument("--region", nargs=4, type=int, metavar=("X", "Y", "W", "H"),
                    default=cfg_region, help="Region to zoom into for --pixel")
    pc.add_argument("--seek", type=float, default=30.0,
                    help="Timestamp (seconds) of the frame to show (default: 30)")
    return parser


def _clips_dir(cfg) -> str:
    return os.path.expanduser(config.section(cfg, "detect").get("clips_dir") or DEFAULT_CLIPS_DIR)


# ── Commands ────────────────────────────────────────────────────────────────────

def cmd_detect(args, cfg, cfg_path) -> int:
    if args.interactive:
        from killcutter.ui.workspace import scan_setup
        args.no_export = args.no_export or not config.section(cfg, "detect").get("export", True)
        args = scan_setup(args, cfg)
        if args is None:
            return 0
    reporting.banner("kill scan", cfg_path)
    video_path = args.video or video.pick(_clips_dir(cfg))
    args.output = args.output or (outputs.destination(video_path, args.timestamps_dir, "_timestamps.txt")
                                  if args.timestamps_dir else "timestamps.txt")
    args.edl_output = args.edl_output or outputs.destination(video_path, args.edl_dir, "_highlights.edl")
    if not args.dry_run:
        destinations = [args.output] + ([args.edl_output] if not args.no_export else [])
        outputs.validate_paths([video_path], destinations)
        args.output = outputs.prepare_file(args.output)
        if not args.no_export:
            args.edl_output = outputs.prepare_file(args.edl_output)
        if args.render_clips:
            import shutil
            if not shutil.which("ffmpeg"):
                from killcutter.errors import DependencyError
                raise DependencyError("Rendering video clips requires FFmpeg on PATH.")
    override = tuple(args.region) if args.region else None

    settings = DetectionSettings(
        region=override or DEFAULT_REGION, offset=args.offset,
        end_offset=args.end_offset, merge_gap=args.merge_gap,
        cooldown=args.cooldown, rate=args.rate,
        preview=args.preview, debug=args.debug,
    )
    reporter = reporting.ConsoleReporter(debug=args.debug)
    clips, completed = detection.detect(video_path, settings, reporter,
                                        dry_run=args.dry_run,
                                        region_override=override,
                                        start=args.start, limit=args.limit, end=args.end)

    reporting.detection_results(clips)
    if not clips:
        return 0 if completed else 130
    if args.dry_run:
        reporting.dry_run_note()
        return 0 if completed else 130

    _write_timestamps(args.output, clips)
    reporting.timestamps_saved(args.output)
    if not completed:
        reporting.partial_note(args.output)

    auto_export = not args.no_export and completed
    if auto_export:
        reporting.export_handoff()
        e = config.section(cfg, "export")
        _do_export(video_path, args.output, name=e.get("name", "Kill Highlights"), fps=e.get("fps"), output=args.edl_output)
    elif not completed:
        reporting.export_skipped(args.output)
        return 130
    if args.render_clips and completed:
        outputs.render_clips(video_path, clips, args.clips_output_dir,
                             progress=lambda i, n, p: print(ui.paint(f"  Rendered {i}/{n} · {p}", ui.GREEN)))
    return 0


def _write_timestamps(path, clips) -> None:
    """Write clips atomically, so an interrupted write cannot truncate the file."""
    outputs.atomic_text(path, "".join(
        f"{clip.start:.3f} {clip.end:.3f} {clip.name}\n" for clip in clips))



def cmd_doctor(args, cfg, cfg_path) -> int:
    reporting.banner("doctor", cfg_path)
    results = environment.check(clips_dir=_clips_dir(cfg), config_path=cfg_path)
    reporting.doctor(results)
    return 1 if environment.blocking_failures(results) else 0


def cmd_export(args, cfg, cfg_path) -> int:
    reporting.banner("highlight export", cfg_path)
    video_path = args.video or video.pick(_clips_dir(cfg))
    _do_export(video_path, args.timestamps,
               name=args.name, fps=args.fps, output=args.output or
               outputs.destination(video_path, args.edl_dir, "_highlights.edl"))
    return 0


def _do_export(video_path, timestamps_path, *, name="Kill Highlights", fps=None, output=None):
    clips = export.read_timestamps(timestamps_path)
    if not clips:
        raise NoClipsError(f"No clips found in {timestamps_path}")
    plan = export.plan(video_path, clips, fps_override=fps, name=name, output=output)
    outputs.validate_paths([video_path, timestamps_path], [plan.out_path])
    plan.out_path = outputs.prepare_file(plan.out_path)
    reporting.export_plan(plan)
    export.write_edl(plan)
    reporting.export_saved(plan)


def cmd_diagnose(args, cfg, cfg_path) -> int:
    from killcutter import diagnose as diagnose_mod
    reporting.banner("diagnose", cfg_path)
    video_path = args.video or video.pick(_clips_dir(cfg))
    region = tuple(args.region) if args.region else DEFAULT_REGION
    report = diagnose_mod.diagnose(
        video_path, region, start=args.start, span=args.span, rate=args.rate,
        reporter=reporting.ConsoleReporter(),
    )
    print(ui.CLEAR_LINE, end="")
    reporting.diagnosis(report)
    return 0 if not report.problems else 1


def cmd_calibrate(args, cfg, cfg_path) -> int:
    from killcutter import calibration
    reporting.banner("calibrate", cfg_path)
    video_path = args.video or video.pick(_clips_dir(cfg))
    if args.region:
        region = tuple(args.region)
    else:
        from killcutter import hud as hud_mod
        w, h = video.frame_size(video_path)
        region = hud_mod.for_size(w, h).region
    if args.pixel:
        calibration.calibrate_pixel(video_path, args.seek, region)
    else:
        calibration.calibrate_region(video_path, args.seek)
    return 0


_COMMANDS = {"detect": cmd_detect, "export": cmd_export,
             "calibrate": cmd_calibrate, "diagnose": cmd_diagnose,
             "doctor": cmd_doctor}


# ── Entry point ─────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Pre-parse the flags that shape setup before the full parser exists.
    common = _global_flags()
    pre = argparse.ArgumentParser(add_help=False, parents=[common])
    pre.add_argument("--write-config", nargs="?", const="", dest="write_config")
    known, _ = pre.parse_known_args(argv)

    if known.no_color:
        ui.set_color(False)
    if known.write_config is not None:
        config.write_default(known.write_config or None)
        return 0

    environment.configure_tesseract()
    cfg, cfg_path = config.load(known.config)
    if config.section(cfg, "ui").get("color") is False:
        ui.set_color(False)

    parser = _build_parser(cfg, common)
    args = parser.parse_args(argv)
    if not args.command:
        if sys.stdin.isatty() and sys.stdout.isatty():
            args.command = "ui"
        else:
            parser.print_help()
            return 0

    try:
        if args.command == "settings":
            from killcutter.ui.workspace import settings
            settings(cfg, cfg_path or known.config)
            return 0
        if args.command == "ui":
            from killcutter.ui.workspace import home
            return home(cfg, cfg_path or known.config,
                        lambda current: _build_parser(current, common), _COMMANDS, no_color=known.no_color)
        return _COMMANDS[args.command](args, cfg, cfg_path)
    except (KillcutterError, OSError) as exc:
        reporting.error(str(exc))
        return 1
    except KeyboardInterrupt:
        reporting.interrupted()
        return 130


def run() -> None:
    """Console-script wrapper that turns the int return into an exit code."""
    raise SystemExit(main())
