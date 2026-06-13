from killcutter import config


def test_write_default_and_load(tmp_path):
    path = tmp_path / "config.toml"
    config.write_default(str(path))
    assert path.is_file()

    cfg, src = config.load(str(path))
    assert src == str(path)
    detect = config.section(cfg, "detect")
    assert detect["offset"] == 5
    assert detect["export"] is True
    assert config.section(cfg, "export")["name"] == "Kill Highlights"
    assert config.section(cfg, "ui")["color"] is True


def test_write_default_does_not_clobber(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[detect]\noffset = 99\n")
    config.write_default(str(path))
    cfg, _ = config.load(str(path))
    assert config.section(cfg, "detect")["offset"] == 99   # untouched


def test_section_missing_returns_empty(tmp_path):
    cfg, _ = config.load(str(tmp_path / "nope.toml"))
    assert cfg == {}
    assert config.section(cfg, "detect") == {}
