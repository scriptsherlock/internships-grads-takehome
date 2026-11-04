"""Turning raw input (JSON values, timestamp strings) into validated models, and back.

This is the only module that touches raw JSON values. Anything invalid raises
InputError with a message that says exactly which field is wrong, so the rest of
the code can assume clean, typed, UTC data.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from scheduler.models import Entry, Handover, OnCall, Override, Schedule

OUTPUT_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class InputError(ValueError):
    """Raised for any invalid user-supplied input (file contents or flags)."""


# --- Timestamps ---------------------------------------------------------------


def parse_time(value: Any, field: str) -> datetime:
    """Parse an ISO 8601 timestamp with a timezone (e.g. '...Z' or '+01:00') into UTC."""
    if not isinstance(value, str):
        raise InputError(f"{field}: expected a timestamp string, got {value!r}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise InputError(f"{field}: {value!r} is not a valid ISO 8601 timestamp") from None
    if parsed.tzinfo is None:
        # A time without a timezone is ambiguous, so refuse to guess.
        raise InputError(f"{field}: {value!r} has no timezone, e.g. add 'Z' for UTC")
    if parsed.microsecond:
        # Output is whole seconds (the brief's format). Accepting fractions would
        # print entries that look zero-length or overlapping, so refuse them.
        raise InputError(f"{field}: {value!r} has fractional seconds; use whole seconds")
    try:
        return parsed.astimezone(timezone.utc)
    except OverflowError:  # e.g. 0001-01-01T00:00:00+01:00 is before year 1 in UTC
        raise InputError(f"{field}: {value!r} is outside the supported date range") from None


def format_time(dt: datetime) -> str:
    """Format as the brief does, e.g. 2026-11-06T17:00:00Z."""
    return dt.astimezone(timezone.utc).strftime(OUTPUT_TIME_FORMAT)


# --- Input --------------------------------------------------------------------


def load_json(path: str) -> Any:
    """Read and decode a JSON file, turning file and syntax problems into InputError."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise InputError(f"{path}: cannot read file ({e.strerror})") from None
    except json.JSONDecodeError as e:
        raise InputError(f"{path}: invalid JSON ({e})") from None
    except UnicodeDecodeError:
        raise InputError(f"{path}: not a UTF-8 text file") from None


def parse_schedule(data: Any) -> Schedule:
    """Validate the schedule JSON and build a Schedule."""
    _require_object(data, "schedule")

    users = _require_field(data, "users", "schedule")
    if not isinstance(users, list) or not users:
        raise InputError("schedule.users: expected a non-empty list of user names")
    for i, user in enumerate(users):
        if not _is_user_name(user):
            raise InputError(f"schedule.users[{i}]: expected a non-empty string, got {user!r}")

    start = parse_time(
        _require_field(data, "handover_start_at", "schedule"), "schedule.handover_start_at"
    )

    days = _require_field(data, "handover_interval_days", "schedule")
    # Whole days only: a fractional interval would drift the handover time of day.
    # bool is a subclass of int in Python, so exclude it explicitly (true would mean 1).
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        raise InputError(
            f"schedule.handover_interval_days: expected a positive whole number, got {days!r}"
        )

    try:
        interval = timedelta(days=days)
    except OverflowError:  # timedelta tops out at 999,999,999 days
        raise InputError(
            f"schedule.handover_interval_days: {days} is too large"
        ) from None
    return Schedule(tuple(users), start, interval)


def parse_overrides(data: Any) -> tuple[Override, ...]:
    """Validate the overrides JSON array. Returns overrides sorted by start time.

    Overlapping overrides are rejected: if two overrides claimed the same instant,
    the answer to "who's on call?" would depend on the order of the file.
    """
    if not isinstance(data, list):
        raise InputError("overrides: expected a JSON array")

    overrides = [_parse_override(item, f"overrides[{i}]") for i, item in enumerate(data)]
    overrides.sort(key=lambda o: o.start)

    # Once sorted by start, any overlap must show up between neighbours.
    for earlier, later in zip(overrides, overrides[1:]):
        if later.start < earlier.end:
            raise InputError(
                "overrides: overlapping overrides are not allowed "
                # Plain ASCII "to": some terminals (e.g. Windows cp1252) can't show an en dash.
                f"({earlier.user} {format_time(earlier.start)} to {format_time(earlier.end)} and "
                f"{later.user} {format_time(later.start)} to {format_time(later.end)})"
            )
    return tuple(overrides)


def _parse_override(data: Any, where: str) -> Override:
    _require_object(data, where)
    user = _require_field(data, "user", where)
    if not _is_user_name(user):
        raise InputError(f"{where}.user: expected a non-empty string, got {user!r}")
    start = parse_time(_require_field(data, "start_at", where), f"{where}.start_at")
    end = parse_time(_require_field(data, "end_at", where), f"{where}.end_at")
    if start >= end:
        raise InputError(f"{where}: start_at must be before end_at")
    return Override(user, start, end)


def _require_object(data: Any, where: str) -> None:
    if not isinstance(data, dict):
        raise InputError(f"{where}: expected a JSON object, got {type(data).__name__}")


def _require_field(data: dict, key: str, where: str) -> Any:
    if key not in data:
        raise InputError(f"{where}: missing required field {key!r}")
    return data[key]


def _is_user_name(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


# --- Output -------------------------------------------------------------------


def entry_to_json(entry: Entry) -> dict[str, str]:
    """An entry in exactly the brief's output shape."""
    return {
        "user": entry.user,
        "start_at": format_time(entry.start),
        "end_at": format_time(entry.end),
    }


def on_call_report_to_json(
    at: datetime, current: OnCall | None, upcoming: Handover | None
) -> dict[str, Any]:
    """The --at answer: who's on call now, why, and who takes over next."""
    return {
        "at": format_time(at),
        "user": current.user if current else None,
        "source": current.source if current else None,
        "next": None
        if upcoming is None
        else {
            "user": upcoming.on_call.user,
            "source": upcoming.on_call.source,
            "start_at": format_time(upcoming.at),
        },
    }
