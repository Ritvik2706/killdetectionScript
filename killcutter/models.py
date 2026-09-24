"""Shared domain objects passed between detection, export and the CLI."""

from dataclasses import dataclass, field


@dataclass
class Clip:
    """A single highlight: a start/end window (seconds) and who got the kill."""

    start: float
    end: float
    name: str = "???"
    # Tri-state facts about the kill, keyed by trait name (see
    # killcutter.traits). A missing key, or a None value, means "not known" --
    # which is a real answer, not a no.
    traits: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.end - self.start
