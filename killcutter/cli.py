"""Command-line interface: ``killcutter <command>``.

Commands:
    detect      scan a video for kills, then auto-build the highlight EDL
    export      build a highlight EDL from an existing timestamps.txt
    calibrate   re-find the scan region / trigger pixel on a frame

Global flags (before or after the command): --config, --write-config,
--no-color, --version. Config values seed argparse defaults; explicit flags win.
"""

import argparse
import sys

from killcutter import __version__, config, detection, export, reporting, video
from killcutter import ui
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
    pd.add_argument("--rate", type=float, default=d.get("rate", 2),
                    help="Frame samples per second (default: 2)")
    pd.add_argument("--output", default="timestamps.txt",
                    help="Where to write detected clips (default: timestamps.txt)")
    pd.add_argument("--preview", action="store_true",
                    help="Show the scan region live with OCR result (for tuning)")
    pd.add_argument("--debug", action="store_true",
                    help="Print trigger result + timestamp for every sample")
    pd.add_argument("--dry-run", action="store_true", dest="dry_run",
                    help="Print detected clips without writing timestamps.txt")
    pd.add_argument("--no-export", action="store_true", dest="no_export",
                    help="Skip the automatic highlight-export step")

    # export ---------------------------------------------------------------
    px = sub.add_parser("export", parents=[common],
                        help="Build a highlight EDL from an existing timestamps.txt")
    px.add_argument("--video", help="Source video (omit to pick from the clips folder)")
    px.add_argument("--timestamps", default="timestamps.txt",
                    help="timestamps.txt from detect (default: timestamps.txt)")
    px.add_argument("--output", help="Output EDL path (default: <video_stem>_highlights.edl)")
    px.add_argument("--name", default=e.get("name", "Kill Highlights"),
                    help="Sequence name shown in Premiere (default: 'Kill Highlights')")
    px.add_argument("--fps", type=float, default=e.get("fps"),
                    help="Authoring fps; MUST match your Premiere sequence (e.g. 59.94)")

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
    return config.section(cfg, "detect").get("clips_dir") or DEFAULT_CLIPS_DIR


# ── Commands ────────────────────────────────────────────────────────────────────

def cmd_detect(args, cfg, cfg_path) -> int:
    reporting.banner("kill scan", cfg_path)
    video_path = args.video or video.pick(_clips_dir(cfg))
    region = tuple(args.region) if args.region else DEFAULT_REGION

    settings = DetectionSettings(
        region=region, offset=args.offset, end_offset=args.end_offset,
        merge_gap=args.merge_gap, cooldown=args.cooldown, rate=args.rate,
        preview=args.preview, debug=args.debug,
    )
    reporter = reporting.ConsoleReporter(debug=args.debug)
    clips = detection.detect(video_path, settings, reporter, dry_run=args.dry_run)

    reporting.detection_results(clips)
    if not clips:
        return 0
    if args.dry_run:
        reporting.dry_run_note()
        return 0

    with open(args.output, "w") as f:
        for clip in clips:
            f.write(f"{clip.start:.3f} {clip.end:.3f} {clip.name}\n")
    reporting.timestamps_saved(args.output)

    auto_export = config.section(cfg, "detect").get("export", True) and not args.no_export
    if auto_export:
        reporting.export_handoff()
        _do_export(video_path, args.output)
    return 0


def cmd_export(args, cfg, cfg_path) -> int:
    reporting.banner("highlight export", cfg_path)
    video_path = args.video or video.pick(_clips_dir(cfg))
    _do_export(video_path, args.timestamps,
               name=args.name, fps=args.fps, output=args.output)
    return 0


def _do_export(video_path, timestamps_path, *, name="Kill Highlights", fps=None, output=None):
    clips = export.read_timestamps(timestamps_path)
    if not clips:
        raise NoClipsError(f"No clips found in {timestamps_path}")
    plan = export.plan(video_path, clips, fps_override=fps, name=name, output=output)
    reporting.export_plan(plan)
    export.write_edl(plan)
    reporting.export_saved(plan)


def cmd_calibrate(args, cfg, cfg_path) -> int:
    from killcutter import calibration
    reporting.banner("calibrate", cfg_path)
    video_path = args.video or video.pick(_clips_dir(cfg))
    region = tuple(args.region) if args.region else DEFAULT_REGION
    if args.pixel:
        calibration.calibrate_pixel(video_path, args.seek, region)
    else:
        calibration.calibrate_region(video_path, args.seek)
    return 0


_COMMANDS = {"detect": cmd_detect, "export": cmd_export, "calibrate": cmd_calibrate}


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

    cfg, cfg_path = config.load(known.config)
    if config.section(cfg, "ui").get("color") is False:
        ui.set_color(False)

    parser = _build_parser(cfg, common)
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    try:
        return _COMMANDS[args.command](args, cfg, cfg_path)
    except KillcutterError as exc:
        reporting.error(str(exc))
        return 1
    except KeyboardInterrupt:
        reporting.interrupted()
        return 130


def run() -> None:
    """Console-script wrapper that turns the int return into an exit code."""
    raise SystemExit(main())
