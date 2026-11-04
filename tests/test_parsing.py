"""Tests for input validation and output formatting (scheduler.parsing)."""

from datetime import timedelta

import pytest

from scheduler.parsing import (
    InputError,
    format_time,
    parse_overrides,
    parse_schedule,
    parse_time,
)
from tests.support import T

# --- Timestamps -------------------------------------------------------------------


def test_parse_time_z_and_offsets_mean_the_same_instant():
    assert parse_time("2026-11-06T17:00:00Z", "f") == parse_time("2026-11-06T18:00:00+01:00", "f")


def test_format_time_always_outputs_utc_z():
    assert format_time(parse_time("2026-11-06T18:00:00+01:00", "f")) == "2026-11-06T17:00:00Z"


@pytest.mark.parametrize(
    "value, message",
    [
        ("2026-11-06T17:00:00", "has no timezone"),
        ("next tuesday", "not a valid ISO 8601"),
        ("2026-13-01T00:00:00Z", "not a valid ISO 8601"),
        (12345, "expected a timestamp string"),
    ],
)
def test_parse_time_rejects_bad_values(value, message):
    with pytest.raises(InputError, match=message):
        parse_time(value, "f")


# --- Schedule -------------------------------------------------------------------

VALID_SCHEDULE = {
    "users": ["alice", "bob", "charlie"],
    "handover_start_at": "2026-11-06T17:00:00Z",
    "handover_interval_days": 7,
}


def test_parse_schedule():
    s = parse_schedule(VALID_SCHEDULE)
    assert s.users == ("alice", "bob", "charlie")
    assert s.handover_start == T("2026-11-06T17:00:00Z")
    assert s.interval == timedelta(days=7)


@pytest.mark.parametrize(
    "change, message",
    [
        ({"users": []}, "non-empty list"),
        ({"users": "alice"}, "non-empty list"),
        ({"users": ["alice", ""]}, r"users\[1\]"),
        ({"users": ["alice", 7]}, r"users\[1\]"),
        ({"handover_start_at": "soon"}, "handover_start_at"),
        ({"handover_interval_days": 0}, "positive whole number"),
        ({"handover_interval_days": -7}, "positive whole number"),
        ({"handover_interval_days": 1.5}, "positive whole number"),
        ({"handover_interval_days": "7"}, "positive whole number"),
        ({"handover_interval_days": True}, "positive whole number"),
    ],
)
def test_parse_schedule_rejects_bad_fields(change, message):
    with pytest.raises(InputError, match=message):
        parse_schedule({**VALID_SCHEDULE, **change})


@pytest.mark.parametrize("field", ["users", "handover_start_at", "handover_interval_days"])
def test_parse_schedule_requires_every_field(field):
    data = {k: v for k, v in VALID_SCHEDULE.items() if k != field}
    with pytest.raises(InputError, match=f"missing required field '{field}'"):
        parse_schedule(data)


def test_parse_schedule_requires_an_object():
    with pytest.raises(InputError, match="expected a JSON object"):
        parse_schedule([VALID_SCHEDULE])


# --- Overrides --------------------------------------------------------------------


def _ov(user, start, end):
    return {"user": user, "start_at": start, "end_at": end}


def test_parse_overrides_sorts_by_start():
    got = parse_overrides([
        _ov("bob", "2026-11-10T00:00:00Z", "2026-11-10T01:00:00Z"),
        _ov("alice", "2026-11-09T00:00:00Z", "2026-11-09T01:00:00Z"),
    ])
    assert [o.user for o in got] == ["alice", "bob"]


def test_back_to_back_overrides_are_allowed():
    got = parse_overrides([
        _ov("alice", "2026-11-09T00:00:00Z", "2026-11-09T01:00:00Z"),
        _ov("bob", "2026-11-09T01:00:00Z", "2026-11-09T02:00:00Z"),
    ])
    assert len(got) == 2


def test_overlapping_overrides_are_rejected():
    with pytest.raises(InputError, match="overlapping"):
        parse_overrides([
            _ov("alice", "2026-11-09T00:00:00Z", "2026-11-09T02:00:00Z"),
            _ov("bob", "2026-11-09T01:00:00Z", "2026-11-09T03:00:00Z"),
        ])


def test_overlap_is_found_regardless_of_file_order():
    with pytest.raises(InputError, match="overlapping"):
        parse_overrides([
            _ov("bob", "2026-11-09T01:00:00Z", "2026-11-09T03:00:00Z"),
            _ov("carol", "2026-11-10T00:00:00Z", "2026-11-10T01:00:00Z"),
            _ov("alice", "2026-11-09T00:00:00Z", "2026-11-09T02:00:00Z"),
        ])


@pytest.mark.parametrize(
    "data, message",
    [
        ({"not": "a list"}, "expected a JSON array"),
        (["oops"], r"overrides\[0\]: expected a JSON object"),
        ([{"user": "alice", "start_at": "2026-11-09T00:00:00Z"}], "missing required field 'end_at'"),
        ([_ov("", "2026-11-09T00:00:00Z", "2026-11-09T01:00:00Z")], r"overrides\[0\].user"),
        ([_ov("alice", "2026-11-09T01:00:00Z", "2026-11-09T01:00:00Z")], "start_at must be before end_at"),
        ([_ov("alice", "2026-11-09T02:00:00Z", "2026-11-09T01:00:00Z")], "start_at must be before end_at"),
    ],
)
def test_parse_overrides_rejects_bad_input(data, message):
    with pytest.raises(InputError, match=message):
        parse_overrides(data)


# --- Precision and range limits --------------------------------------------------------


def test_fractional_seconds_are_rejected():
    # Output is whole seconds, so accepting fractions would print entries that
    # look zero-length or overlapping.
    with pytest.raises(InputError, match="fractional seconds"):
        parse_time("2026-11-09T17:00:00.250Z", "f")


def test_explicit_zero_fraction_is_fine():
    assert parse_time("2026-11-09T17:00:00.000Z", "f") == parse_time("2026-11-09T17:00:00Z", "f")


def test_timestamp_that_overflows_when_converted_to_utc():
    with pytest.raises(InputError, match="outside the supported date range"):
        parse_time("0001-01-01T00:00:00+01:00", "f")


def test_huge_interval_is_a_clear_error():
    with pytest.raises(InputError, match="too large"):
        parse_schedule({**VALID_SCHEDULE, "handover_interval_days": 1_000_000_000})


def test_non_utf8_file_is_a_clear_error(tmp_path):
    from scheduler.parsing import load_json

    bad = tmp_path / "bad.json"
    bad.write_bytes(b"\xff\xfe{}")
    with pytest.raises(InputError, match="not a UTF-8 text file"):
        load_json(str(bad))
