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
sudo apt install tesseract-ocr
pip install -e .          # or: pip install opencv-python numpy pytesseract
```

Everything runs through a single CLI — `python -m killcutter <command>` (or just
`killcutter <command>` after `pip install -e .`). The `ui` package is pure
standard library.

---

## Step 1 — Detect kills

```bash
python -m killcutter detect --video "my_clip.mkv"
# or omit --video to pick from the clips folder interactively
```

Each sampled frame is gated by two cheap pixel checks (a white and a red pixel
on the banner); only matching frames get OCR'd to read the player name. Kills
within `--merge-gap` seconds are merged into a single clip.

### Useful flags
| Flag           | Default | Description                                   |
|----------------|---------|-----------------------------------------------|
| `--offset`     | `5`     | Seconds before the kill for the clip start    |
| `--end-offset` | `5`     | Seconds after the kill for the clip end       |
| `--merge-gap`  | `10`    | Merge kills closer than this into one clip    |
| `--cooldown`   | `3`     | Min seconds between detections                |
| `--rate`       | `2`     | Frame samples per second                      |
| `--region`     | —       | Custom scan region: `--region X Y W H`        |
| `--preview`    | off     | Live view of the scan region + OCR (tuning)   |
| `--dry-run`    | off     | Detect without writing `timestamps.txt`       |
| `--no-export`  | off     | Stop after `timestamps.txt`                   |

### Tuning a new clip / HUD change
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
3. The imported sequence **must** match the printed fps (it NTSC-corrects 60 →
   59.94 so cuts don't drift over long recordings)

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

See `docs/ARCHITECTURE.md` for the module layout and data flow.

## Notes

- Only kills that surface the **"ENEMY DOWNED"** banner are detected.
- Trigger pixels and the default region assume 1920×1080 and the current HUD.
- The terminal UI auto-disables colour when piped or when `NO_COLOR` is set.
