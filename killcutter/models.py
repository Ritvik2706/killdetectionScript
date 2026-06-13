"""Shared domain objects passed between detection, export and the CLI."""

from dataclasses import dataclass


@dataclass
class Clip:
    """A single highlight: a start/end window (seconds) and who got the kill."""

    start: float
    end: float
    name: str = "???"

    @property
    def duration(self) -> float:
        return self.end - self.start
