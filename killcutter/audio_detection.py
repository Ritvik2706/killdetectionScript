"""Bounded-memory audio level sampling, decoded by the existing FFmpeg dependency."""
from queue import Empty, Full, Queue
from threading import Event, Thread
import math
import os
import shutil
import subprocess
import tempfile

import numpy as np
from .errors import DependencyError, VideoError


def samples(path, start, end, rate, cancelled=None):
    executable = shutil.which('ffmpeg')
    if not executable:
        raise DependencyError('Audio detection requires FFmpeg on PATH.')
    sample_rate = 8000
    count = max(1, round(sample_rate/rate))
    buffers = Queue(maxsize=4)
    stop = Event()
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen([
            executable, '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-ss', str(start), '-i', os.path.abspath(path), '-t', str(end-start),
            '-map', '0:a:0', '-vn', '-ac', '1', '-ar', str(sample_rate),
            '-f', 's16le', 'pipe:1',
        ], stdout=subprocess.PIPE, stderr=errors,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        def send(value):
            while not stop.is_set():
                try:
                    buffers.put(value, timeout=.1)
                    return
                except Full:
                    pass
        def read():
            try:
                while not stop.is_set():
                    block = process.stdout.read(count*2)
                    if not block:
                        break
                    send(block)
            finally:
                send(None)
        reader = Thread(target=read, daemon=True)
        reader.start()
        offset = 0
        try:
            while True:
                if cancelled and cancelled():
                    raise KeyboardInterrupt
                try:
                    block = buffers.get(timeout=.1)
                except Empty:
                    continue
                if block is None:
                    break
                values = np.frombuffer(block, dtype='<i2').astype(np.float64)/32768
                rms = float(np.sqrt(np.mean(values*values)))
                yield start + offset/sample_rate, 20*math.log10(max(rms, 1e-10))
                offset += len(values)
            process.wait(timeout=5)
            if process.returncode:
                errors.seek(0)
                raise VideoError('Could not decode audio: ' + errors.read(4096).decode(errors='replace').strip())
        finally:
            stop.set()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            reader.join(timeout=2)
            process.stdout.close()
