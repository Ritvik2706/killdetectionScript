# Killfeed Auto-Cutter
Detect every kill in a CoD recording and assemble the highlights into a
Premiere Pro–ready EDL — in one command.

---

## How it works

```
Your gameplay recording
        ↓
killcutter detect        ← reads the "ENEMY DOWNED" banner, logs each kill
        ↓
timestamps.txt           ← clip in/out points (start end name, in seconds)
        ↓
killcutter export        ← runs automatically; builds the highlight reel
        ↓
<video>_highlights.edl   ← File → Import in Premiere Pro
```

`detect` runs the exporter automatically when it finishes, so you normally only
run the one command.

---

## Install

```bash
pip install -e .

# plus the Tesseract binary (the one non-Python dependency):
sudo apt install tesseract-ocr            # Linux
brew install tesseract                    # macOS
winget install UB-Mannheim.TesseractOCR   # Windows
```

Then check the machine is ready:

```bash
python -m killcutter doctor
```

```
╭─ ENVIRONMENT ────────────────────────────────────────────────╮
│ ✓ Python          3.12.4 on Windows (AMD64)                  │
│ ✓ OpenCV          cv2 4.10.0                                 │
│ ✓ Tesseract OCR   tesseract 5.3.3  (C:\Program Files\...)    │
│ ✓ Clips folder    C:\Users\you\Videos  (37 videos)           │
╰──────────────────────────────────────────────────────────────╯
  [READY] Everything killcutter needs is installed.
```

It exits non-zero if something is missing and tells you the command to fix it.
On Windows, Tesseract is found even when it is not on PATH; if you installed it
somewhere unusual, set `KILLCUTTER_TESSERACT` to the full path to the binary.

Everything runs through a single CLI — `python -m killcutter <command>` (or just
`killcutter <command>` after `pip install -e .`). The `ui` package is pure
standard library.

### Running on another machine

Nothing is tied to one computer:

- **Footage folder** — found automatically (`~/Videos/Clips/Warzone`, `~/Videos`,
  `~/Movies`, `%USERPROFILE%\Videos`). Override with `KILLCUTTER_CLIPS_DIR`,
  `[detect] clips_dir`, or just pass `--video`.
- **Resolution** — the banner geometry is anchored to the top-right corner and
  scaled from the 1920x1080 reference, so 1440p, 4K and ultrawide work without
  being re-calibrated. `doctor` and `diagnose` both print the layout in use.
- **Windows / macOS / Linux** — the terminal UI, key handling and paths are all
  platform-aware.

---

## Step 1 — Detect kills

```bash
python -m killcutter detect --video "my_clip.mkv"
# or omit --video to pick from the clips folder interactively
```

Each sampled frame is gated by two cheap pixel checks — a bright pixel on the
banner icon and a saturated pixel on its left accent bar. Only frames that pass
get OCR'd, and the header then has to actually read "ENEMY DOWNED" before a kill
is counted: teammate banners share the same slot, icon and accent colour, so
pixels alone cannot tell them apart. Kills within `--merge-gap` seconds are
merged into a single clip.

The accent bar's *hue* is deliberately not checked — it was red until the
Sept 2026 HUD restyle and is yellow now, and both eras still work.

### Useful flags
| Flag           | Default | Description                                   |
|----------------|---------|-----------------------------------------------|
| `--offset`     | `5`     | Seconds before the kill for the clip start    |
| `--end-offset` | `5`     | Seconds after the kill for the clip end       |
| `--merge-gap`  | `10`    | Merge kills closer than this into one clip    |
| `--cooldown`   | `3`     | Min seconds between detections                |
| `--rate`       | `4`     | Frame samples per second (higher = tighter timing) |
| `--region`     | —       | Custom scan region: `--region X Y W H`        |
| `--preview`    | off     | Live view of the scan region + OCR (tuning)   |
| `--dry-run`    | off     | Detect without writing `timestamps.txt`       |
| `--no-export`  | off     | Stop after `timestamps.txt`                   |

Clip times are measured from the kill itself, not from when the banner was
spotted — detection is corrected back by the banner's sweep-in plus half a
sampling interval (~0.55s at `--rate 2`). Want more lead-in than that? Raise
`--offset`; it is honest about what it gives you.

Press **Ctrl-C** at any point and the scan stops but *keeps* the kills it has
already found — a two-hour scan never throws away its work.

### When detection stops finding kills

A game update can restyle the killfeed, and `detect` will simply report zero
kills without saying why. `diagnose` samples a stretch of footage and reports
which stage broke — the pixel gate, the scan region, or the header match — along
with every banner header it saw and the colour it was drawn in:

```bash
python -m killcutter diagnose                    # 10 min of footage, 10% in
python -m killcutter diagnose --start 600 --span 300
```

```
╭─ PIPELINE ───────────────────────────────────────────╮
│ white pixel             116 frames  (19.3%)          │
│ accent pixel            143 frames  (23.8%)          │
│ both (OCR runs)         106 frames  (17.7%)          │
│ header confirmed        106 frames  (17.7%)          │
│ accent colour seen      RGB(249, 216, 1)  (yellow)   │
╰──────────────────────────────────────────────────────╯
```

It exits non-zero when it finds a problem. Then fix the constants with:

```bash
python -m killcutter detect --preview            # live banner ROI + OCR (Q to quit)
python -m killcutter calibrate                   # drag a new scan region
python -m killcutter calibrate --pixel           # click a new trigger pixel
```

---

## Interactive clip picker (vim keys)

Omit `--video` and you get a full-screen fuzzy picker (it falls back to a plain
numbered prompt when piped):

| Key                  | Action                       |
|----------------------|------------------------------|
| `j` / `k`, `↓` / `↑` | move                         |
| `gg` / `G`           | top / bottom                 |
| `Ctrl-d` / `Ctrl-u`  | half-page down / up          |
| `Ctrl-f` / `Ctrl-b`  | full page                    |
| `/`                  | fuzzy search (`Esc` clears)  |
| digits then `⏎`      | jump to a row by number      |
| `⏎`                  | select · `q` / `Esc` cancel  |

## Configuration & global flags

```bash
python -m killcutter --write-config      # ~/.config/killcutter/config.toml
```

Settings load from `--config PATH`, then `./.killcutter.toml`, then the user
config dir — first match wins, and explicit CLI flags always override. Other
global flags: `--no-color`, `--version`, `--config PATH`.

---

## Step 2 — Import into Premiere Pro

`export` writes `<video_stem>_highlights.edl` and prints the frame rate it
authored at.

1. **File → Import →** select the `.edl`
2. When asked to locate media, point it at the original video
3. The imported sequence **must** match the printed fps

The EDL is authored at the rate the media *actually* runs at — a true 60.000 fps
OBS capture stays 60.000, and genuinely NTSC footage (59.94) stays 59.94. The two
are never converted into one another: authoring 60 fps media at 59.94 makes every
timecode 0.1% short, which is invisible at the start and pulls cuts 5.4s early at
90 minutes and 7.2s early at two hours — enough to end a highlight before its kill.

Export cross-checks the authored rate against the container and prints a
`CHECK FPS` warning (with the drift it would cause) if they disagree. Force a rate
with `--fps` if you ever need to.

To run the exporter on its own:

```bash
python -m killcutter export --video "my_clip.mkv" --timestamps timestamps.txt
```

---

## Development

```bash
pip install -e ".[dev]"
pytest
```

`timecode`, `export`, `config`, the selector state machine and the detection
gates are all covered without needing a video file.

See `docs/ARCHITECTURE.md` for the module layout and data flow.

## Notes

- Only kills that surface the **"ENEMY DOWNED"** banner are detected.
- Trigger pixels and the default region assume 1920×1080 and the current HUD —
  run `diagnose` after a game update to check.
- The terminal UI auto-disables colour when piped or when `NO_COLOR` is set.
