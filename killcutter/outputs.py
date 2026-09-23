"""Consistent output naming and optional standalone video clips."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

from killcutter.errors import ConfigError, DependencyError, VideoError


def destination(video_path, directory, suffix):
    return str(Path(directory or '.').expanduser() / (Path(video_path).stem + suffix))


def prepare_file(path):
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_dir():
        raise ConfigError(f"Output is a directory, not a file: {target}")
    return str(target)


def render_clips(video_path, clips, directory, *, progress=None):
    """Render accurate H.264/AAC MP4 cuts, atomically replacing each output."""
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise DependencyError("Rendering video clips requires FFmpeg on PATH.")
    folder = Path(directory).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for index, clip in enumerate(clips, 1):
        target = folder / f"{Path(video_path).stem}_highlight_{index:03}.mp4"
        validate_paths([video_path], [target])
        if clip.duration <= 0:
            continue
        handle, temp = tempfile.mkstemp(suffix='.mp4', dir=folder)
        os.close(handle)
        try:
            result = subprocess.run([
                ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                '-ss', str(clip.start), '-i', str(Path(video_path).resolve()),
                '-t', str(clip.duration), '-map', '0:v:0', '-map', '0:a?',
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                '-c:a', 'aac', '-movflags', '+faststart', temp,
            ], capture_output=True, text=True)
            if result.returncode:
                raise VideoError(f"Could not render {target.name}: {result.stderr.strip()}")
            os.replace(temp, target)
            written.append(str(target))
            if progress:
                progress(index, len(clips), str(target))
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    return written


def validate_paths(source_paths, output_paths):
    """Prevent destinations from replacing source media or one another."""
    sources = {Path(p).expanduser().resolve() for p in source_paths}
    seen = set()
    for raw in output_paths:
        path = Path(raw).expanduser().resolve()
        if path in sources:
            raise ConfigError(f"Output would overwrite an input file: {raw}")
        if path in seen:
            raise ConfigError(f"Output files must have different paths: {raw}")
        seen.add(path)


def atomic_text(path, text):
    """Keep existing results intact if writing or replacement fails."""
    target = Path(prepare_file(path))
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         dir=target.parent, delete=False) as stream:
            temp = stream.name
            stream.write(text)
        os.replace(temp, target)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)
