"""Settings validation — catching bad input before a two-hour scan, not during."""

import pytest

from killcutter.detection import DetectionSettings, validate
from killcutter.errors import ConfigError

GOOD = dict(region=(1598, 186, 189, 45))


def test_sane_settings_pass():
    validate(DetectionSettings(**GOOD))


@pytest.mark.parametrize("field,value", [
    ("rate", 0),
    ("rate", -1),
    ("rate", 1000),
    ("offset", -1),
    ("end_offset", -0.5),
    ("merge_gap", -10),
    ("cooldown", -3),
])
def test_impossible_values_are_rejected(field, value):
    with pytest.raises(ConfigError):
        validate(DetectionSettings(**{**GOOD, field: value}))


@pytest.mark.parametrize("region", [
    (1, 2, 3),              # too few
    (1, 2, 3, 4, 5),        # too many
    (-1, 0, 10, 10),        # negative origin
    (0, 0, 0, 10),          # zero width
    (0, 0, 10, 0),          # zero height
])
def test_impossible_regions_are_rejected(region):
    with pytest.raises(ConfigError):
        validate(DetectionSettings(region=region))


def test_the_error_names_the_flag_so_the_message_is_actionable():
    with pytest.raises(ConfigError, match="--rate"):
        validate(DetectionSettings(**{**GOOD, "rate": 0}))
    with pytest.raises(ConfigError, match="--offset"):
        validate(DetectionSettings(**{**GOOD, "offset": -1}))
