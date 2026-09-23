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
