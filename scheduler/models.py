"""Plain data types used throughout the scheduler.

Every time range here is half-open, [start, end): it includes its start instant
but not its end instant. At a handover the incoming person is on call, so
back-to-back ranges never overlap.

All datetimes are timezone-aware and in UTC (parsing.py guarantees this).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

Source = Literal["override", "rotation"]


@dataclass(frozen=True)
class Schedule:
    """A rotation: users take turns, each covering one `interval`, from `handover_start`."""

    users: tuple[str, ...]
    handover_start: datetime
    interval: timedelta


@dataclass(frozen=True)
class Override:
    """A temporary swap: `user` covers [start, end) whoever the rotation says."""

    user: str
    start: datetime
    end: datetime

    def covers(self, t: datetime) -> bool:
        """Whether instant t falls inside this override."""
        return self.start <= t < self.end


@dataclass(frozen=True)
class Entry:
    """One row of the rendered schedule: `user` is on call over [start, end)."""

    user: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class OnCall:
    """The answer to "who is on call at instant t?", and why."""

    user: str
    source: Source  # "override" if an override applies, otherwise "rotation"


@dataclass(frozen=True)
class Handover:
    """The next moment a different person takes over, and who that is."""

    at: datetime
    on_call: OnCall
