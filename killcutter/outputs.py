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


def render_clips(video_path, clips, directory, *, progress=None, cancelled=None):
    """Render accurate H.264/AAC MP4 cuts, atomically replacing each output."""
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise DependencyError("Rendering video clips requires FFmpeg on PATH.")
    folder = Path(directory).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for index, clip in enumerate(clips, 1):
        if cancelled and cancelled():
            break
        target = folder / f"{Path(video_path).stem}_highlight_{index:03}.mp4"
        validate_paths([video_path], [target])
        if clip.duration <= 0:
            continue
        handle, temp = tempfile.mkstemp(suffix='.mp4', dir=folder)
        os.close(handle)
        try:
            command = [
                ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                '-ss', str(clip.start), '-i', str(Path(video_path).resolve()),
                '-t', str(clip.duration), '-map', '0:v:0', '-map', '0:a?',
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                '-c:a', 'aac', '-movflags', '+faststart', temp,
            ]
            if cancelled is None:
                result = subprocess.run(command, capture_output=True, text=True,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            else:
                result = _run_cancellable(command, cancelled)
                if result is None:
                    break
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


def _run_cancellable(command, cancelled):
    """Drain output while polling cancellation; always reap the encoder process."""
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        while True:
            if cancelled():
                process.terminate()
                try:
                    process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
                return None
            try:
                stdout, stderr = process.communicate(timeout=.15)
                return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                continue
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


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
