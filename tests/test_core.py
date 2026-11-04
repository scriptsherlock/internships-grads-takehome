"""Unit and edge-case tests for scheduler.core, built up from the point lookup."""

import pytest

from scheduler.core import (
    change_points,
    handovers_between,
    next_handover,
    on_call_at,
    override_at,
    render,
    rotation_user_at,
)
from scheduler.models import OnCall
from tests.support import BRIEF_OVERRIDE, BRIEF_SCHEDULE, T, make_override, make_schedule, rows

S = BRIEF_SCHEDULE
O = (BRIEF_OVERRIDE,)


# --- rotation_user_at ----------------------------------------------------------


@pytest.mark.parametrize(
    "t, expected",
    [
        ("2026-11-06T16:59:59Z", None),  # 1s before the schedule starts
        ("2026-11-06T17:00:00Z", "alice"),  # first instant of the first shift
        ("2026-11-13T16:59:59Z", "alice"),  # last second of alice's shift
        ("2026-11-13T17:00:00Z", "bob"),  # handover instant belongs to the incoming user
        ("2026-11-20T17:00:00Z", "charlie"),
        ("2026-11-27T17:00:00Z", "alice"),  # wraps back round
        ("2032-08-06T17:00:00Z", "alice"),  # 300 shifts (2100 days) later: 300 % 3 == 0
        ("2032-08-13T17:00:00Z", "bob"),  # 301 shifts later
    ],
)
def test_rotation_user_at(t, expected):
    assert rotation_user_at(S, T(t)) == expected


# --- override_at / on_call_at ------------------------------------------------


def test_override_at_is_half_open():
    assert override_at(O, T("2026-11-09T16:59:59Z")) is None
    assert override_at(O, T("2026-11-09T17:00:00Z")) == BRIEF_OVERRIDE  # start included
    assert override_at(O, T("2026-11-09T21:59:59Z")) == BRIEF_OVERRIDE
    assert override_at(O, T("2026-11-09T22:00:00Z")) is None  # end excluded


@pytest.mark.parametrize(
    "t, expected",
    [
        ("2026-11-01T00:00:00Z", None),
        ("2026-11-07T00:00:00Z", OnCall("alice", "rotation")),
        ("2026-11-09T18:00:00Z", OnCall("charlie", "override")),
        ("2026-11-09T22:00:00Z", OnCall("alice", "rotation")),
        ("2026-11-14T00:00:00Z", OnCall("bob", "rotation")),
    ],
)
def test_on_call_at(t, expected):
    assert on_call_at(S, O, T(t)) == expected


# --- handovers_between / change_points ------------------------------------------


def test_handovers_between_includes_the_first_shift_start():
    got = list(handovers_between(S, T("2026-11-01T00:00:00Z"), T("2026-11-21T00:00:00Z")))
    assert got == [T("2026-11-06T17:00:00Z"), T("2026-11-13T17:00:00Z"), T("2026-11-20T17:00:00Z")]


def test_handovers_between_excludes_both_ends():
    assert list(handovers_between(S, T("2026-11-13T17:00:00Z"), T("2026-11-20T17:00:00Z"))) == []


def test_change_points_only_inside_the_window():
    far_override = make_override("dave", "2026-12-01T00:00:00Z", "2026-12-02T00:00:00Z")
    got = change_points(S, O + (far_override,), T("2026-11-08T00:00:00Z"), T("2026-11-14T00:00:00Z"))
    assert got == [
        T("2026-11-08T00:00:00Z"),
        T("2026-11-09T17:00:00Z"),
        T("2026-11-09T22:00:00Z"),
        T("2026-11-13T17:00:00Z"),
        T("2026-11-14T00:00:00Z"),
    ]


# --- render -----------------------------------------------------------------------


def test_render_matches_the_brief_example():
    got = render(S, O, T("2026-11-06T17:00:00Z"), T("2026-11-20T17:00:00Z"))
    assert rows(got) == [
        ("alice", "2026-11-06T17:00:00Z", "2026-11-09T17:00:00Z"),
        ("charlie", "2026-11-09T17:00:00Z", "2026-11-09T22:00:00Z"),
        ("alice", "2026-11-09T22:00:00Z", "2026-11-13T17:00:00Z"),
        ("bob", "2026-11-13T17:00:00Z", "2026-11-20T17:00:00Z"),
    ]


def test_render_without_overrides():
    got = render(S, (), T("2026-11-06T17:00:00Z"), T("2026-11-27T17:00:00Z"))
    assert [user for user, _, _ in rows(got)] == ["alice", "bob", "charlie"]


def test_window_starting_mid_shift_is_truncated():
    got = render(S, O, T("2026-11-08T14:00:00Z"), T("2026-11-10T00:00:00Z"))
    assert rows(got) == [
        ("alice", "2026-11-08T14:00:00Z", "2026-11-09T17:00:00Z"),
        ("charlie", "2026-11-09T17:00:00Z", "2026-11-09T22:00:00Z"),
        ("alice", "2026-11-09T22:00:00Z", "2026-11-10T00:00:00Z"),
    ]


def test_window_starting_before_the_schedule_skips_the_empty_part():
    got = render(S, O, T("2026-11-05T00:00:00Z"), T("2026-11-07T00:00:00Z"))
    assert rows(got) == [("alice", "2026-11-06T17:00:00Z", "2026-11-07T00:00:00Z")]


def test_window_entirely_before_the_schedule_is_empty():
    assert render(S, O, T("2026-11-01T00:00:00Z"), T("2026-11-02T00:00:00Z")) == []


def test_override_crossing_a_handover():
    dave = make_override("dave", "2026-11-12T12:00:00Z", "2026-11-14T12:00:00Z")
    got = render(S, (dave,), T("2026-11-06T17:00:00Z"), T("2026-11-20T17:00:00Z"))
    assert rows(got) == [
        ("alice", "2026-11-06T17:00:00Z", "2026-11-12T12:00:00Z"),
        ("dave", "2026-11-12T12:00:00Z", "2026-11-14T12:00:00Z"),
        ("bob", "2026-11-14T12:00:00Z", "2026-11-20T17:00:00Z"),
    ]


def test_override_partly_outside_the_window_is_truncated():
    got = render(S, O, T("2026-11-09T19:00:00Z"), T("2026-11-09T21:00:00Z"))
    assert rows(got) == [("charlie", "2026-11-09T19:00:00Z", "2026-11-09T21:00:00Z")]


def test_override_entirely_outside_the_window_is_ignored():
    got = render(S, O, T("2026-11-13T17:00:00Z"), T("2026-11-14T17:00:00Z"))
    assert rows(got) == [("bob", "2026-11-13T17:00:00Z", "2026-11-14T17:00:00Z")]


def test_override_exactly_covering_a_whole_shift():
    dave = make_override("dave", "2026-11-13T17:00:00Z", "2026-11-20T17:00:00Z")
    got = render(S, (dave,), T("2026-11-06T17:00:00Z"), T("2026-11-27T17:00:00Z"))
    assert [user for user, _, _ in rows(got)] == ["alice", "dave", "charlie"]


def test_self_override_merges_into_one_entry():
    alice = make_override("alice", "2026-11-08T00:00:00Z", "2026-11-09T00:00:00Z")
    got = render(S, (alice,), T("2026-11-06T17:00:00Z"), T("2026-11-13T17:00:00Z"))
    assert rows(got) == [("alice", "2026-11-06T17:00:00Z", "2026-11-13T17:00:00Z")]


def test_back_to_back_overrides_for_different_users_stay_separate():
    dave = make_override("dave", "2026-11-09T22:00:00Z", "2026-11-10T02:00:00Z")
    got = render(S, (BRIEF_OVERRIDE, dave), T("2026-11-09T12:00:00Z"), T("2026-11-10T12:00:00Z"))
    assert [user for user, _, _ in rows(got)] == ["alice", "charlie", "dave", "alice"]


def test_one_person_rotation_is_one_continuous_entry():
    solo = make_schedule(["alice"])
    got = render(solo, (), T("2026-11-06T17:00:00Z"), T("2026-12-04T17:00:00Z"))
    assert rows(got) == [("alice", "2026-11-06T17:00:00Z", "2026-12-04T17:00:00Z")]


def test_override_order_does_not_matter():
    dave = make_override("dave", "2026-11-15T00:00:00Z", "2026-11-16T00:00:00Z")
    frm, until = T("2026-11-06T17:00:00Z"), T("2026-11-20T17:00:00Z")
    assert render(S, (BRIEF_OVERRIDE, dave), frm, until) == render(S, (dave, BRIEF_OVERRIDE), frm, until)


# --- next_handover ---------------------------------------------------------------


def _next(schedule, overrides, t):
    h = next_handover(schedule, overrides, T(t))
    return None if h is None else (h.on_call.user, h.on_call.source, h.at)


def test_next_after_an_override_is_back_to_the_rotation():
    assert _next(S, O, "2026-11-09T18:00:00Z") == ("alice", "rotation", T("2026-11-09T22:00:00Z"))


def test_next_can_be_an_override():
    assert _next(S, O, "2026-11-06T17:00:00Z") == ("charlie", "override", T("2026-11-09T17:00:00Z"))


def test_next_is_a_normal_rotation_handover():
    assert _next(S, O, "2026-11-10T00:00:00Z") == ("bob", "rotation", T("2026-11-13T17:00:00Z"))


def test_next_before_the_schedule_starts_is_the_first_person():
    assert _next(S, O, "2026-11-01T00:00:00Z") == ("alice", "rotation", T("2026-11-06T17:00:00Z"))


def test_next_skips_boundaries_where_the_person_does_not_change():
    alice = make_override("alice", "2026-11-08T00:00:00Z", "2026-11-09T00:00:00Z")
    assert _next(S, (alice,), "2026-11-07T00:00:00Z") == ("bob", "rotation", T("2026-11-13T17:00:00Z"))


def test_next_skips_repeated_users_in_the_rotation():
    s = make_schedule(["alice", "alice", "bob"])
    assert _next(s, (), "2026-11-06T17:00:00Z") == ("bob", "rotation", T("2026-11-20T17:00:00Z"))


def test_next_is_none_for_a_one_person_rotation():
    assert _next(make_schedule(["alice"]), (), "2026-11-10T00:00:00Z") is None


def test_one_person_rotation_with_an_override():
    solo = make_schedule(["alice"])
    dave = (make_override("dave", "2026-12-01T00:00:00Z", "2026-12-02T00:00:00Z"),)
    assert _next(solo, dave, "2026-11-10T00:00:00Z") == ("dave", "override", T("2026-12-01T00:00:00Z"))
    assert _next(solo, dave, "2026-12-01T12:00:00Z") == ("alice", "rotation", T("2026-12-02T00:00:00Z"))
    assert _next(solo, dave, "2026-12-03T00:00:00Z") is None


def test_next_handover_stops_at_the_first_change(monkeypatch):
    """The search is lazy: a far-future override must not make it generate every
    handover up to that override (about 2.6 million daily handovers here)."""
    import scheduler.core as core

    daily = make_schedule(["alice", "bob"], days=1)
    far = (make_override("zed", "9000-01-01T00:00:00Z", "9000-01-02T00:00:00Z"),)

    generated = 0
    real_handovers_between = core.handovers_between

    def counting_handovers_between(*args):
        nonlocal generated
        for handover in real_handovers_between(*args):
            generated += 1
            yield handover

    monkeypatch.setattr(core, "handovers_between", counting_handovers_between)
    h = core.next_handover(daily, far, T("2026-11-07T00:00:00Z"))

    assert (h.on_call.user, h.at) == ("bob", T("2026-11-07T17:00:00Z"))
    assert generated <= 2  # heapq.merge may read one item ahead; eager would read millions
