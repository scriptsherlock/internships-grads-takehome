"""Property-based tests: Hypothesis generates many random schedules, overrides and
windows, and checks that rules which must always hold really do hold.

Correctness is checked against a deliberately naive *oracle* that shares no code
with scheduler.core: it lists every shift by repeatedly adding the interval (no
floor-division formula), and scans the raw override list. All generated times are
whole hours, so the on-call person can only change on the hour, and checking
every hour in a window is a complete check.
"""

import random
from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from scheduler.core import next_handover, on_call_at, render
from scheduler.models import Override, Schedule

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


# --- Generators --------------------------------------------------------------------

schedules = st.builds(
    lambda users, start_h, days: Schedule(tuple(users), BASE + start_h * HOUR, timedelta(days=days)),
    users=st.lists(st.sampled_from(["alice", "bob", "charlie", "dave"]), min_size=1, max_size=4),
    start_h=st.integers(0, 100),
    days=st.integers(1, 3),
)


@st.composite
def overrides_for(draw, schedule: Schedule) -> tuple[Override, ...]:
    """Non-overlapping, hour-aligned overrides after the schedule starts (as the brief promises)."""
    cursor = schedule.handover_start
    result = []
    for _ in range(draw(st.integers(0, 6))):
        start = cursor + draw(st.integers(0, 48)) * HOUR
        end = start + draw(st.integers(1, 48)) * HOUR
        result.append(Override(draw(st.sampled_from(["alice", "bob", "zed"])), start, end))
        cursor = end
    return tuple(result)


@st.composite
def scenarios(draw):
    schedule = draw(schedules)
    overrides = draw(overrides_for(schedule))
    frm = BASE + draw(st.integers(-50, 400)) * HOUR
    until = frm + draw(st.integers(1, 300)) * HOUR
    return schedule, overrides, frm, until


# --- The naive oracle ---------------------------------------------------------------


def oracle(schedule: Schedule, overrides, t: datetime) -> str | None:
    """Who is on call at t, worked out the slow, obvious way."""
    for o in overrides:
        if o.start <= t < o.end:
            return o.user
    shift_start, i = schedule.handover_start, 0
    while shift_start + schedule.interval <= t:  # walk forward shift by shift
        shift_start += schedule.interval
        i += 1
    return schedule.users[i % len(schedule.users)] if t >= schedule.handover_start else None


def user_in_output(entries, t: datetime) -> str | None:
    for e in entries:
        if e.start <= t < e.end:
            return e.user
    return None


def hours(frm: datetime, until: datetime):
    t = frm
    while t < until:
        yield t
        t += HOUR


# --- Properties ----------------------------------------------------------------------


@settings(max_examples=300, deadline=None)
@given(scenarios())
def test_output_is_well_formed(scenario):
    schedule, overrides, frm, until = scenario
    entries = render(schedule, overrides, frm, until)
    for e in entries:
        assert frm <= e.start < e.end <= until  # inside the window, positive length
    for a, b in zip(entries, entries[1:]):
        assert a.end <= b.start  # sorted, no overlaps
        assert not (a.user == b.user and a.end == b.start)  # same-user neighbours merged


@settings(max_examples=300, deadline=None)
@given(scenarios())
def test_render_agrees_with_the_naive_oracle_every_hour(scenario):
    schedule, overrides, frm, until = scenario
    entries = render(schedule, overrides, frm, until)
    for t in hours(frm, until):
        expected = oracle(schedule, overrides, t)
        assert user_in_output(entries, t) == expected
        got = on_call_at(schedule, overrides, t)
        assert (got.user if got else None) == expected


@settings(max_examples=200, deadline=None)
@given(scenarios(), st.randoms(use_true_random=False))
def test_override_order_does_not_matter(scenario, rng: random.Random):
    schedule, overrides, frm, until = scenario
    shuffled = list(overrides)
    rng.shuffle(shuffled)
    assert render(schedule, tuple(shuffled), frm, until) == render(schedule, overrides, frm, until)


@settings(max_examples=300, deadline=None)
@given(scenarios())
def test_next_handover_is_the_first_change_of_person(scenario):
    schedule, overrides, t, _ = scenario
    current = oracle(schedule, overrides, t)
    nxt = next_handover(schedule, overrides, t)

    if nxt is None:
        # Nobody different should ever appear: check well past every override
        # and a couple of full rotation cycles.
        horizon = max([t, schedule.handover_start] + [o.end for o in overrides])
        horizon += 2 * len(schedule.users) * schedule.interval
        assert all(oracle(schedule, overrides, h) == current for h in hours(t, horizon))
    else:
        # Same person all the way up to the handover, then someone different.
        assert all(oracle(schedule, overrides, h) == current for h in hours(t, nxt.at))
        assert oracle(schedule, overrides, nxt.at) == nxt.on_call.user != current
