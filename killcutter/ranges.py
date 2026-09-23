"""User-facing timestamps and validated source-time scan ranges."""
import math

from killcutter.errors import ConfigError


def parse_timestamp(value):
    """Accept seconds, MM:SS or HH:MM:SS (including fractional seconds)."""
    try:
        parts = str(value).strip().split(":")
        if not 1 <= len(parts) <= 3:
            raise ValueError
        numbers = [float(p) for p in parts]
        if any(not math.isfinite(n) or n < 0 for n in numbers):
            raise ValueError
        if len(parts) > 1:
            if any(not p.isdigit() for p in parts[:-1]):
                raise ValueError
            if any(n >= 60 for n in numbers[1:]):
                raise ValueError
        result = 0.0
        for number in numbers:
            result = result * 60 + number
        return result
    except (ValueError, TypeError):
        raise ValueError("Use seconds, MM:SS or HH:MM:SS, for example 90 or 01:30.") from None


def resolve_range(duration, start=0.0, limit=None, end=None):
    if not math.isfinite(duration) or duration <= 0:
        raise ConfigError("Could not determine a positive video duration.")
    if not math.isfinite(start) or not 0 <= start < duration:
        raise ConfigError("Scan start must be within the video.")
    if limit is not None and end is not None:
        raise ConfigError("Use either --end or --limit, not both.")
    if limit is not None:
        if not math.isfinite(limit) or limit <= 0:
            raise ConfigError("--limit must be a positive finite duration.")
        end = min(duration, start + limit)
    end = duration if end is None else end
    if not math.isfinite(end) or not start < end <= duration:
        raise ConfigError("Scan end must be after start and within the video.")
    return start, end
