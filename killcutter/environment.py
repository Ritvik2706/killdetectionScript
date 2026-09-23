"""Finding Tesseract, and checking the machine is ready to run.

The one dependency that is not a Python package is the Tesseract binary, and a
missing or unfindable one is the single most likely reason this fails on a new
computer. On Windows it is routinely installed somewhere sensible that is still
not on PATH, so look there before giving up.

:func:`check` powers ``killcutter doctor``: it answers "will this work here?"
without needing footage to try it on.
"""

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass

# Installed-but-not-on-PATH locations, in the order worth trying.
_WINDOWS_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Tesseract-OCR\tesseract.exe",
)
_UNIX_CANDIDATES = (
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
    "/opt/homebrew/bin/tesseract",      # Apple Silicon Homebrew
    "/usr/local/opt/tesseract/bin/tesseract",
)

INSTALL_HINT = {
    "Windows": "winget install UB-Mannheim.TesseractOCR  "
               "(or https://github.com/UB-Mannheim/tesseract/wiki)",
    "Darwin": "brew install tesseract",
    "Linux": "sudo apt install tesseract-ocr",
}


def find_tesseract():
    """Return a path to the Tesseract binary, or ``None``.

    ``KILLCUTTER_TESSERACT`` wins, then PATH, then the usual install locations.
    """
    override = os.environ.get("KILLCUTTER_TESSERACT")
    if override and os.path.isfile(override):
        return override
    found = shutil.which("tesseract")
    if found:
        return found
    candidates = _WINDOWS_CANDIDATES if os.name == "nt" else _UNIX_CANDIDATES
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def install_hint() -> str:
    return INSTALL_HINT.get(platform.system(), INSTALL_HINT["Linux"])


def configure_tesseract() -> bool:
    """Point pytesseract at the binary. True if OCR should work.

    Called once at startup so a Windows install that is not on PATH still works
    instead of failing deep inside the scan.
    """
    path = find_tesseract()
    if not path:
        return False
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = path
    except Exception:
        return False
    return True


def _version_of(path) -> str:
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True,
                             timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        first = (out.stdout or out.stderr).strip().splitlines()
        return first[0] if first else "unknown version"
    except Exception:
        return "unknown version"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fix: str = ""
    required: bool = True


def check(clips_dir=None, config_path=None) -> list:
    """Run every readiness check and return the results, in report order."""
    results = []

    results.append(Check(
        "Python", True,
        f"{platform.python_version()} on {platform.system()} "
        f"({platform.machine()})"))

    try:
        import cv2
        results.append(Check("OpenCV", True, f"cv2 {cv2.__version__}"))
    except Exception as exc:
        results.append(Check("OpenCV", False, str(exc),
                             "pip install opencv-python"))

    try:
        import numpy
        results.append(Check("NumPy", True, numpy.__version__))
    except Exception as exc:
        results.append(Check("NumPy", False, str(exc), "pip install numpy"))

    try:
        import pytesseract          # noqa: F401
        results.append(Check("pytesseract", True, "installed"))
    except Exception as exc:
        results.append(Check("pytesseract", False, str(exc),
                             "pip install pytesseract"))

    binary = find_tesseract()
    if binary:
        results.append(Check("Tesseract OCR", True,
                             f"{_version_of(binary)}  ({binary})"))
    else:
        results.append(Check(
            "Tesseract OCR", False, "not found on PATH or in the usual places",
            install_hint()))

    if config_path:
        results.append(Check("Config", True, config_path, required=False))
    else:
        results.append(Check("Config", True, "using built-in defaults",
                             "killcutter --write-config  to create one",
                             required=False))

    if clips_dir:
        if os.path.isdir(clips_dir):
            try:
                from killcutter.constants import VIDEO_EXTENSIONS
                n = sum(1 for f in os.listdir(clips_dir)
                        if os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS)
            except OSError as exc:
                results.append(Check("Clips folder", False,
                                     f"{clips_dir} ({exc.strerror})",
                                     "point [detect] clips_dir at a readable folder"))
            else:
                results.append(Check(
                    "Clips folder", True,
                    f"{clips_dir}  ({n} video{'s' if n != 1 else ''})",
                    "" if n else "folder is empty — put recordings here",
                    required=False))
        else:
            results.append(Check(
                "Clips folder", False, f"not found: {clips_dir}",
                "set [detect] clips_dir in your config, or pass --video",
                required=False))

    return results


def blocking_failures(results) -> list:
    return [c for c in results if c.required and not c.ok]
