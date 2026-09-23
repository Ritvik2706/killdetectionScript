"""Interactive workspace and scan setup, built on the standard-library picker."""
from copy import deepcopy
from pathlib import Path
import math

from killcutter import config, ui, video, reporting, outputs, environment
from killcutter.ui import keys, screens, ansi
from killcutter.errors import KillcutterError
from killcutter.constants import DEFAULT_CLIPS_DIR
from killcutter.ranges import parse_timestamp, resolve_range


def choose(title, rows, initial=0):
    def render(row, active, index):
        marker = "›" if active else " "
        width = max(1, ui.term_width() - 12)
        label = row if len(row) <= width else row[:width - 1] + "…"
        return ui.paint(f" {marker} {index:>2}  {label}",
                        ui.WHITE if active else ui.GREY, bold=active)
    return ui.select(rows, render, title=title, initial=initial)


def ask(label, current, convert=str):
    """Editable prompt. Blank keeps the value; /cancel returns without changes."""
    if keys.supports_raw_input():
        return screens.edit(label, current, convert)
    while True:
        try:
            raw = input(f"  {label} [{current}] › ").strip()
            if not raw or raw == "/cancel":
                return current
            if raw == "/clear" and convert is str:
                return ""
            return convert(raw)
        except ValueError as exc:
            print(ui.paint(f"  {exc}", ui.AMBER))
        except EOFError:
            return current


def number(raw, *, positive=False, maximum=None):
    value = float(raw)
    if (not math.isfinite(value) or value < 0 or (positive and value == 0)
            or (maximum is not None and value > maximum)):
        raise ValueError(f"Enter a {'positive' if positive else 'non-negative'} number"
                         + (f" up to {maximum}." if maximum else "."))
    return value


def stamp(seconds):
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{int(hours):02}:{int(minutes):02}:{secs:06.3f}".rstrip("0").rstrip(".")


_FIELDS = [
    ("detect", "clips_dir", "Recordings folder", "", str),
    ("detect", "timestamps_dir", "Timestamps folder", "", str),
    ("export", "output_dir", "EDL folder", "", str),
    ("detect", "clips_output_dir", "Rendered MP4 folder", "highlights", str),
    ("detect", "render_clips", "Render MP4 clips · requires FFmpeg", False, bool),
    ("detect", "offset", "Lead-in · seconds before kill", 5, number),
    ("detect", "end_offset", "Tail · seconds after kill", 5, number),
    ("detect", "merge_gap", "Merge nearby kills · seconds", 10, number),
    ("detect", "cooldown", "Detection cooldown · seconds", 3, number),
    ("detect", "rate", "Samples per second · up to 60", 4,
     lambda raw: number(raw, positive=True, maximum=60)),
    ("detect", "export", "Automatically export EDL", True, bool),
    ("export", "name", "Premiere sequence name", "Kill Highlights", str),
    ("ui", "color", "Terminal color", True, bool),
]


def settings(cfg, cfg_path=None):
    """Edit a draft; save explicitly or discard without touching the file."""
    draft = deepcopy(cfg)
    target = cfg_path or config.user_config_path()
    cursor = 0
    while True:
        rows = []
        for section, key, label, default, convert in _FIELDS:
            value = config.section(draft, section).get(key, default)
            empty = "Auto-detect" if key == "clips_dir" else "Current directory"
            display = ("On" if value else "Off") if convert is bool else (value or empty)
            rows.append(f"{label}   {display}")
        action = choose(f"SETTINGS · {target}", rows + [
            "Save settings", "Reset editable settings to defaults", "Discard and go back"], cursor)
        cursor = action or 0
        if action is None or action == len(rows) + 2:
            return cfg, cfg_path
        if action == len(rows) + 1:
            for section, key, _, default, _ in _FIELDS:
                draft.setdefault(section, {})[key] = default
        elif action == len(rows):
            updates = {}
            for section, key, _, default, _ in _FIELDS:
                updates.setdefault(section, {})[key] = config.section(draft, section).get(key, default)
            try:
                path = config.save_updates(target, updates)
            except (OSError, ValueError) as exc:
                screens.page("COULD NOT SAVE", [str(exc), "", f"Destination: {target}"],
                             subtitle="Your draft is still available. Choose another location or try again.")
                continue
            screens.page("SETTINGS SAVED", [ui.paint("✓ Your defaults are saved.", ui.GREEN), "", path],
                         subtitle="New scans will use these settings.")
            return config.load(path)
        else:
            section, key, label, default, convert = _FIELDS[action]
            value = config.section(draft, section).get(key, default)
            draft.setdefault(section, {})[key] = (not value if convert is bool else
                                                  ask(label, value, convert))


def scan_setup(args, cfg):
    """Return configured argparse args, or None on cancellation."""
    if not args.video:
        action = choose("NEW SCAN · select source", ["Browse recordings folder", "Enter video path", "Back"])
        if action is None or action == 2:
            return None
        if action == 0:
            clips = video.list_clips(config.section(cfg, "detect").get("clips_dir")
                                     or DEFAULT_CLIPS_DIR)
            selected = ui.select(clips, video._render_row, title="NEW SCAN · recordings",
                                 filter_text=lambda c: c.name)
            if selected is None:
                return None
            args.video = clips[selected].path
        else:
            args.video = ask("Video path", "")
            if not args.video:
                return None
    args.video = str(Path(args.video).expanduser())
    fps, _, duration = video.measure(args.video)
    start, end = resolve_range(duration, args.start, args.limit, args.end)
    args.output = args.output or outputs.destination(args.video, args.timestamps_dir, "_timestamps.txt")
    args.edl_output = args.edl_output or outputs.destination(args.video, args.edl_dir, "_highlights.edl")
    cursor = 0
    while True:
        selected = end - start
        title = f"SCAN SETUP · {Path(args.video).name} · {stamp(selected)} selected"
        options = [
            ("start", "Start analysis"),
            ("range_start", f"Range start   {stamp(start)}"),
            ("range_end", f"Range end     {stamp(end)}"),
            ("full", f"Use full recording   {stamp(duration)}"),
            ("padding", f"Lead-in / tail   {args.offset:g}s / {args.end_offset:g}s"),
            ("rate", f"Sampling   {args.rate:g} per second"),
            ("timestamps", f"Timestamps output   {args.output}"),
            ("export", f"Export EDL   {'Off' if args.no_export else 'On'}"),
            ("dry_run", f"Dry run   {'On' if args.dry_run else 'Off'}"),
            ("preview", f"Live banner preview   {'On' if args.preview else 'Off'}"),
            ("edl", f"EDL output   {args.edl_output}"),
            ("render", f"Render MP4 clips   {'On' if args.render_clips else 'Off'}"),
            ("clips_dir", f"MP4 output folder   {args.clips_output_dir}"),
            ("summary", "Review scan summary"), ("back", "Back"),
        ]
        index = choose(title, [label for _, label in options], cursor)
        cursor = index or 0
        action = options[index][0] if index is not None else "back"
        if action == "back":
            return None
        if action in ("start", "summary"):
            cells = max(10, min(50, ui.term_width() - 12))
            timeline = ''.join('━' if start / duration <= i / cells < end / duration else '─'
                               for i in range(cells))
            summary = [
                ui.kv("Source", Path(args.video).name),
                ui.kv("Video", f"{stamp(duration)} · {fps:g} fps"),
                ui.kv("Range", f"{stamp(start)} → {stamp(end)}"),
                ui.paint(timeline, ui.TEAL),
                ui.kv("Analyze", f"{stamp(selected)} · {selected / duration:.0%} of recording"),
                ui.kv("Timestamps", "Dry run (no files)" if args.dry_run else args.output),
                ui.kv("EDL", "Off" if args.no_export or args.dry_run else args.edl_output),
                ui.kv("MP4 clips", args.clips_output_dir if args.render_clips and not args.dry_run else "Off"),
                "Highlights stay inside the selected range; times refer to the source.",
            ]
            if action == "summary":
                screens.page("SCAN SUMMARY", summary, subtitle="Review your range and output destinations.")
                continue
            if not args.dry_run:
                output_files = [Path(args.output).expanduser()]
                if not args.no_export:
                    output_files.append(Path(args.edl_output).expanduser())
                if args.render_clips:
                    output_files.extend(Path(args.clips_output_dir).expanduser().glob(
                        Path(args.video).stem + "_highlight_*.mp4"))
                existing = [str(p) for p in output_files if p.exists()]
                if existing and choose("OUTPUT EXISTS · " + ", ".join(existing),
                                       ["Back to setup", "Replace existing outputs"]) != 1:
                    continue
            args.start, args.end, args.limit = start, end, None
            return args
        if action in ("range_start", "range_end"):
            value = ask("Time · seconds / MM:SS / HH:MM:SS", start if action == "range_start" else end,
                        parse_timestamp)
            try:
                start, end = resolve_range(duration, value if action == "range_start" else start,
                                           end=value if action == "range_end" else end)
            except KillcutterError as exc:
                screens.page("INVALID RANGE", [str(exc)], subtitle="Your previous range is unchanged.")
        elif action == "full":
            start, end = 0, duration
        elif action == "padding":
            args.offset = ask("Seconds before kill", args.offset, number)
            args.end_offset = ask("Seconds after kill", args.end_offset, number)
        elif action == "rate":
            args.rate = ask("Samples per second", args.rate,
                            lambda raw: number(raw, positive=True, maximum=60))
        elif action == "timestamps":
            args.output = str(Path(ask("Timestamps output path", args.output)).expanduser())
        elif action == "export":
            args.no_export = not args.no_export
        elif action == "dry_run":
            args.dry_run = not args.dry_run
        elif action == "preview":
            args.preview = not args.preview
        elif action == "edl":
            args.edl_output = str(Path(ask("EDL output path", args.edl_output)).expanduser())
        elif action == "render":
            args.render_clips = not args.render_clips
        elif action == "clips_dir":
            args.clips_output_dir = str(Path(ask("MP4 output folder", args.clips_output_dir)).expanduser())


def _setup_lines(checks):
    """The 'here is what you must do' block, or [] when nothing is missing."""
    steps = environment.setup_steps(checks)
    if not steps:
        return []
    lines = ["", ui.paint("SETUP · RUN THESE COMMANDS", ui.TEAL, bold=True), "",
             ui.paint(f"Detected {environment.platform_family()}. "
                      "Copy each line into a terminal, then press r to re-check.",
                      ui.GREY), ""]
    for label, command in steps:
        lines.append(ui.paint(f"   {label}", ui.WHITE, bold=True))
        lines.append(ui.paint(f"   $ {command}", ui.LIME))
    if environment.pip_is_blocked():
        lines.extend(["", ui.paint(
            "   This Python refuses 'pip install' (managed by your distro), so the "
            "commands above use your package manager. A virtualenv or pipx works too.",
            ui.GREY)])
    return lines


def environment_page(cfg, cfg_path):
    while True:
        screens.clear()
        if keys.supports_raw_input():
            screens.draw("ENVIRONMENT", "Checking your machine…", [], ui.paint("Please wait", ui.GREY))
        folder = str(Path(config.section(cfg, "detect").get("clips_dir") or DEFAULT_CLIPS_DIR).expanduser())
        checks = environment.check(clips_dir=folder, config_path=cfg_path)
        import shutil
        ffmpeg = shutil.which("ffmpeg")
        checks.append(environment.Check("FFmpeg", bool(ffmpeg), ffmpeg or "Not installed",
                                        "Optional · needed only to render MP4 clips", required=False))
        failures = environment.blocking_failures(checks)
        lines = [ui.badge("ACTION NEEDED" if failures else "READY", bg=ui.AMBER if failures else ui.GREEN),
                 "Fix the required dependencies below." if failures else "Your machine is ready to analyze recordings.",
                 "", ui.paint("DEPENDENCIES & LOCATIONS", ui.TEAL, bold=True), ""]
        for check in checks:
            tone = ui.GREEN if check.ok else (ui.RED if check.required else ui.AMBER)
            mark = "✓" if check.ok else "!"
            lines.append(ui.paint(f"{mark}  {check.name:<17}", tone, bold=True)
                         + ui.paint(check.detail, ui.WHITE))
            if check.fix:
                fix = "Open Settings to customize your defaults." if check.name == "Config" else check.fix
                lines.append(ui.paint("   " + fix, ui.GREY))
        lines.extend(_setup_lines(checks))
        action = screens.page("SETUP & ENVIRONMENT", lines,
                              subtitle="Dependencies, recording locations, and optional tools.",
                              actions=[("r", "re-check"), ("s", "settings")])
        if action == "r":
            continue
        return action


def run_job(command, args, cfg, cfg_path):
    """Keep live command output in the workspace, then offer a scrollable result."""
    import sys
    from contextlib import redirect_stdout

    class Transcript:
        def __init__(self, terminal):
            self.terminal = terminal
            self.parts = []

        def write(self, value):
            # Progress redraws should not swamp the final result page.
            if "\r" not in value:
                self.parts.append(value)
            return self.terminal.write(value)

        def flush(self):
            self.terminal.flush()

        def isatty(self):
            return self.terminal.isatty()

    screens.clear()
    transcript = Transcript(sys.stdout)
    with redirect_stdout(transcript):
        status = command(args, cfg, cfg_path)
    lines = []
    for line in ''.join(transcript.parts).splitlines():
        plain = ansi._ANSI_RE.sub('', line)
        if plain.startswith(('╭', '╰', '─')):
            continue
        lines.append(line.strip('│ '))
    screens.page("RESULTS", lines, subtitle="Stopped · partial results preserved" if status == 130 else "Finished · review your results below.")
    return status


def home(cfg, cfg_path, parser_factory, commands, *, no_color=False):
    with screens.session():
        return _home(cfg, cfg_path, parser_factory, commands, no_color=no_color)


def _home(cfg, cfg_path, parser_factory, commands, *, no_color=False):
    # A missing dependency is not worth discovering halfway through a scan, so
    # open the setup page first when the machine cannot run one yet.
    if environment.blocking_failures(environment.check()):
        environment_page(cfg, cfg_path)
    cursor = 0
    while True:
        action = choose("KILLCUTTER · recording → highlights", [
            "New scan        Select a recording and analysis range",
            "Settings        Detection, export and appearance",
            "Setup           Check dependencies and recordings folder",
            "Help            Workflow and keyboard shortcuts",
            "Export EDL      Build from an existing timestamps file",
            "Quit",
        ], cursor)
        cursor = action or 0
        if action is None or action == 5:
            return 0
        try:
            if action == 2:
                if environment_page(cfg, cfg_path) == "s":
                    action = 1
                else:
                    continue
            if action == 1:
                cfg, cfg_path = settings(cfg, cfg_path)
                from killcutter.ui.ansi import _supports_color
                ui.set_color(_supports_color() and not no_color and
                             config.section(cfg, "ui").get("color", True))
            elif action == 4:
                args = parser_factory(cfg).parse_args(["export"])
                args.video = ask("Source video path", "")
                if not args.video:
                    continue
                args.video = str(Path(args.video).expanduser())
                args.timestamps = str(Path(ask("Timestamps file", "timestamps.txt")).expanduser())
                args.output = ask("EDL output", outputs.destination(args.video, args.edl_dir, "_highlights.edl"))
                if Path(args.output).expanduser().exists() and choose("EDL EXISTS", ["Back", "Replace existing EDL"]) != 1:
                    continue
                run_job(commands["export"], args, cfg, cfg_path)
            elif action == 3:
                screens.page("HELP", [
                    ui.paint("FROM RECORDING TO HIGHLIGHTS", ui.TEAL, bold=True), "",
                    ui.paint("01  Choose your recording", ui.WHITE, bold=True),
                    "    New scan → browse your recordings or enter a video path.", "",
                    ui.paint("02  Set your range", ui.WHITE, bold=True),
                    "    Select start/end times, then review output locations.",
                    "    Use seconds, MM:SS, or HH:MM:SS. Fractions are supported.", "",
                    ui.paint("03  Analyze and export", ui.WHITE, bold=True),
                    "    Import the EDL into Premiere or enable rendered MP4 clips.", "",
                    ui.paint("KEYBOARD", ui.TEAL, bold=True), "",
                    "↑/↓ or j/k     Navigate menus and scroll pages",
                    "Enter          Select, save an edit, or return from a page",
                    "Esc / q        Return from a menu or page",
                    "/              Search a menu",
                    "Esc            Cancel an edit",
                    "Ctrl-U         Clear the current text field",
                    "Ctrl-C         Stop analysis and keep partial timestamps", "",
                    ui.paint("OUTPUT LOCATIONS", ui.TEAL, bold=True), "",
                    "Settings saves separate folders for recordings, timestamps, EDLs, and MP4 clips.",
                    "You can override destinations for each scan. MP4 rendering requires FFmpeg.",
                ], subtitle="A quick guide to your workspace.")
            elif action == 0:
                args = parser_factory(cfg).parse_args(["detect"])
                args.no_export = not config.section(cfg, 'detect').get('export', True)
                args = scan_setup(args, cfg)
                if args is None:
                    continue
                args.interactive = False
                run_job(commands["detect"], args, cfg, cfg_path)
        except (KillcutterError, OSError) as exc:
            action = screens.page("UNABLE TO CONTINUE", [
                ui.paint(str(exc), ui.AMBER), "",
                "Check the file path and your folder settings, then try again.",
                "For recordings elsewhere, use New scan → Enter video path.",
            ], subtitle="Return to the workspace to adjust your setup.", actions=[("s", "settings")])
            if action == "s":
                cfg, cfg_path = settings(cfg, cfg_path)
