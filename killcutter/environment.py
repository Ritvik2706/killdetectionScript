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
import sys
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
    "Linux": "install tesseract with your package manager",
}

# How to install a package, per platform family. Linux families are recognised
# from /etc/os-release so the hint names the command that machine actually has:
# telling an Arch user to run apt is worse than saying nothing.
_INSTALLERS = {
    "arch": "sudo pacman -S --needed {}",
    "debian": "sudo apt install {}",
    "fedora": "sudo dnf install {}",
    "suse": "sudo zypper install {}",
    "alpine": "sudo apk add {}",
    "darwin": "brew install {}",
    "windows": "winget install {}",
}
_OS_RELEASE_IDS = {
    "arch": "arch", "archarm": "arch", "manjaro": "arch", "endeavouros": "arch",
    "cachyos": "arch", "garuda": "arch",
    "debian": "debian", "ubuntu": "debian", "linuxmint": "debian",
    "pop": "debian", "raspbian": "debian", "elementary": "debian",
    "fedora": "fedora", "rhel": "fedora", "centos": "fedora",
    "rocky": "fedora", "almalinux": "fedora", "nobara": "fedora",
    "opensuse": "suse", "opensuse-tumbleweed": "suse", "opensuse-leap": "suse",
    "sles": "suse", "suse": "suse",
    "alpine": "alpine",
}

# component -> (PyPI name or None, {family: native package name})
_COMPONENTS = {
    "opencv": ("opencv-python", {
        "arch": "python-opencv", "debian": "python3-opencv",
        "fedora": "python3-opencv", "suse": "python3-opencv",
        "alpine": "py3-opencv"}),
    "numpy": ("numpy", {
        "arch": "python-numpy", "debian": "python3-numpy",
        "fedora": "python3-numpy", "suse": "python3-numpy",
        "alpine": "py3-numpy"}),
    "pytesseract": ("pytesseract", {
        "arch": "python-pytesseract", "debian": "python3-pytesseract",
        "fedora": "python3-pytesseract"}),
    "tesseract": (None, {
        "arch": "tesseract tesseract-data-eng", "debian": "tesseract-ocr",
        "fedora": "tesseract", "suse": "tesseract-ocr", "alpine": "tesseract-ocr",
        "darwin": "tesseract", "windows": "UB-Mannheim.TesseractOCR"}),
    "ffmpeg": (None, {
        "arch": "ffmpeg", "debian": "ffmpeg", "fedora": "ffmpeg",
        "suse": "ffmpeg", "alpine": "ffmpeg", "darwin": "ffmpeg",
        "windows": "Gyan.FFmpeg"}),
}


def platform_family() -> str:
    """This machine's packaging family: ``arch``, ``debian``, ``darwin``, …

    Returns ``"linux"`` for a distribution we have no package names for, which
    callers treat as "we cannot name the command for you".
    """
    system = platform.system()
    if system == "Windows":
        return "windows"
    if system == "Darwin":
        return "darwin"
    try:
        with open("/etc/os-release", encoding="utf-8") as handle:
            fields = dict(
                line.rstrip("\n").split("=", 1) for line in handle if "=" in line)
    except OSError:
        return "linux"
    ids = [fields.get("ID", "")] + fields.get("ID_LIKE", "").split()
    for name in ids:
        family = _OS_RELEASE_IDS.get(name.strip().strip('"').lower())
        if family:
            return family
    return "linux"


def _in_virtualenv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def pip_is_blocked() -> bool:
    """True if this interpreter refuses ``pip install`` (PEP 668).

    Arch, Debian and Fedora all ship an externally-managed system Python, so
    the obvious ``pip install pytesseract`` fails with a wall of text. When that
    is the case we lead with the distro package instead.
    """
    if _in_virtualenv():
        return False
    try:
        import sysconfig
        stdlib = sysconfig.get_path("stdlib")
    except Exception:
        return False
    return bool(stdlib) and os.path.isfile(os.path.join(stdlib, "EXTERNALLY-MANAGED"))


def install_command(component: str) -> str:
    """The best single command to install *component* on this machine."""
    pypi, packages = _COMPONENTS[component]
    family = platform_family()
    native = packages.get(family)
    if native and (pypi is None or pip_is_blocked()):
        return _INSTALLERS[family].format(native)
    if pypi:
        return f"{os.path.basename(sys.executable)} -m pip install {pypi}"
    if native:
        return _INSTALLERS[family].format(native)
    return INSTALL_HINT.get(platform.system(), INSTALL_HINT["Linux"])


def install_hint() -> str:
    """Legacy single-line hint for the Tesseract binary."""
    return install_command("tesseract")


def setup_steps(results) -> list:
    """Copy-pasteable commands that would fix *results*, in the order to run.

    Empty when nothing is missing, so callers can use it as "is there anything
    to tell the user".
    """
    wanted = {
        "OpenCV": "opencv", "NumPy": "numpy", "pytesseract": "pytesseract",
        "Tesseract OCR": "tesseract", "FFmpeg": "ffmpeg",
    }
    steps = []
    for check in results:
        component = wanted.get(check.name)
        if component and not check.ok:
            label = check.name + ("" if check.required else "  (optional)")
            steps.append((label, install_command(component)))
    return steps


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
                             install_command("opencv")))

    try:
        import numpy
        results.append(Check("NumPy", True, numpy.__version__))
    except Exception as exc:
        results.append(Check("NumPy", False, str(exc),
                             install_command("numpy")))

    try:
        import pytesseract          # noqa: F401
        results.append(Check("pytesseract", True, "installed"))
    except Exception as exc:
        results.append(Check("pytesseract", False, str(exc),
                             install_command("pytesseract")))

    binary = find_tesseract()
    if binary:
        results.append(Check("Tesseract OCR", True,
                             f"{_version_of(binary)}  ({binary})"))
    else:
        results.append(Check(
            "Tesseract OCR", False, "not found on PATH or in the usual places",
            install_command("tesseract")))

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
