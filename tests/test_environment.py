"""Environment discovery — the thing most likely to break on a new machine."""

import os

from killcutter import environment


def test_env_override_wins_when_it_points_at_a_real_file(tmp_path, monkeypatch):
    fake = tmp_path / "tesseract"
    fake.write_text("")
    monkeypatch.setenv("KILLCUTTER_TESSERACT", str(fake))
    assert environment.find_tesseract() == str(fake)


def test_env_override_is_ignored_when_the_path_is_wrong(tmp_path, monkeypatch):
    monkeypatch.setenv("KILLCUTTER_TESSERACT", str(tmp_path / "nope"))
    # falls through to PATH / known locations rather than returning a bad path
    found = environment.find_tesseract()
    assert found is None or os.path.isfile(found)


def test_install_hint_is_platform_specific():
    assert environment.install_hint()
    assert environment.INSTALL_HINT["Windows"] != environment.INSTALL_HINT["Darwin"]


def test_check_reports_every_dependency():
    names = {c.name for c in environment.check()}
    assert {"Python", "OpenCV", "NumPy", "pytesseract", "Tesseract OCR"} <= names


def test_missing_clips_folder_is_reported_but_not_blocking(tmp_path):
    missing = str(tmp_path / "does-not-exist")
    results = environment.check(clips_dir=missing)
    folder = next(c for c in results if c.name == "Clips folder")
    assert not folder.ok and not folder.required
    # a missing footage folder must not stop you using --video
    assert all(c.name != "Clips folder" for c in environment.blocking_failures(results))


def test_blocking_failures_only_counts_required_checks():
    ok = environment.Check("x", True, "")
    soft = environment.Check("y", False, "", required=False)
    hard = environment.Check("z", False, "")
    assert environment.blocking_failures([ok, soft, hard]) == [hard]


def _os_release(tmp_path, monkeypatch, text):
    path = tmp_path / "os-release"
    path.write_text(text)
    real = open

    def fake_open(name, *args, **kwargs):
        if name == "/etc/os-release":
            return real(path, *args, **kwargs)
        return real(name, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    monkeypatch.setattr(environment.platform, "system", lambda: "Linux")


def test_platform_family_reads_os_release(tmp_path, monkeypatch):
    _os_release(tmp_path, monkeypatch, 'ID=arch\nNAME="Arch Linux"\n')
    assert environment.platform_family() == "arch"


def test_platform_family_falls_back_to_id_like(tmp_path, monkeypatch):
    _os_release(tmp_path, monkeypatch, 'ID=pika\nID_LIKE="ubuntu debian"\n')
    assert environment.platform_family() == "debian"


def test_platform_family_unknown_distro_is_generic(tmp_path, monkeypatch):
    _os_release(tmp_path, monkeypatch, "ID=plan9\n")
    assert environment.platform_family() == "linux"


def test_install_command_prefers_distro_when_pip_is_blocked(monkeypatch):
    monkeypatch.setattr(environment, "platform_family", lambda: "arch")
    monkeypatch.setattr(environment, "pip_is_blocked", lambda: True)
    assert environment.install_command("pytesseract") == (
        "sudo pacman -S --needed python-pytesseract")
    monkeypatch.setattr(environment, "pip_is_blocked", lambda: False)
    assert "pip install pytesseract" in environment.install_command("pytesseract")


def test_install_command_for_binaries_never_uses_pip(monkeypatch):
    monkeypatch.setattr(environment, "platform_family", lambda: "debian")
    monkeypatch.setattr(environment, "pip_is_blocked", lambda: False)
    assert environment.install_command("tesseract") == "sudo apt install tesseract-ocr"
    assert environment.install_command("ffmpeg") == "sudo apt install ffmpeg"


def test_install_command_unknown_linux_still_says_something(monkeypatch):
    monkeypatch.setattr(environment, "platform_family", lambda: "linux")
    monkeypatch.setattr(environment.platform, "system", lambda: "Linux")
    assert environment.install_command("tesseract") == environment.INSTALL_HINT["Linux"]


def test_setup_steps_only_covers_failures(monkeypatch):
    monkeypatch.setattr(environment, "platform_family", lambda: "arch")
    monkeypatch.setattr(environment, "pip_is_blocked", lambda: True)
    results = [
        environment.Check("Python", True, "3.13"),
        environment.Check("NumPy", True, "2.0"),
        environment.Check("Tesseract OCR", False, "not found"),
        environment.Check("FFmpeg", False, "not installed", required=False),
    ]
    steps = environment.setup_steps(results)
    assert [label for label, _ in steps] == ["Tesseract OCR", "FFmpeg  (optional)"]
    assert steps[0][1] == "sudo pacman -S --needed tesseract tesseract-data-eng"


def test_setup_steps_empty_when_ready():
    assert environment.setup_steps([environment.Check("Tesseract OCR", True, "5.5")]) == []
