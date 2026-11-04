"""Small helpers so tests read like the brief: plain strings in, plain tuples out."""

from datetime import datetime, timedelta

from scheduler.models import Entry, Override, Schedule
from scheduler.parsing import format_time, parse_time


def T(value: str) -> datetime:
    """'2026-11-06T17:00:00Z' -> aware UTC datetime."""
    return parse_time(value, "test")


def make_schedule(users: list[str], start: str = "2026-11-06T17:00:00Z", days: int = 7) -> Schedule:
    return Schedule(tuple(users), T(start), timedelta(days=days))


def make_override(user: str, start: str, end: str) -> Override:
    return Override(user, T(start), T(end))


def rows(entries: list[Entry]) -> list[tuple[str, str, str]]:
    """Entries as (user, start, end) string tuples, for readable assertions."""
    return [(e.user, format_time(e.start), format_time(e.end)) for e in entries]


# The brief's example schedule and override.
BRIEF_SCHEDULE = make_schedule(["alice", "bob", "charlie"])
BRIEF_OVERRIDE = make_override("charlie", "2026-11-09T17:00:00Z", "2026-11-09T22:00:00Z")
