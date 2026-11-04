"""The scheduling logic: pure functions, no I/O.

Everything is built on one question: "who is on call at instant t?" (on_call_at).

- render() answers it for a whole window. The answer can only change at a
  handover or at an override's start/end, so we collect those "change points",
  ask on_call_at() once per gap between them, and merge same-user neighbours.
- next_handover() answers "who takes over next, and when?" for paging.
"""

import heapq
from collections.abc import Iterator, Sequence
from datetime import datetime

from scheduler.models import Entry, Handover, OnCall, Override, Schedule

# --- The point lookup -----------------------------------------------------------


def rotation_user_at(schedule: Schedule, t: datetime) -> str | None:
    """Whose turn the rotation says it is at t, or None before the schedule starts."""
    if t < schedule.handover_start:
        return None
    # timedelta // timedelta is exact integer division: the number of whole
    # shifts completed before t, i.e. the index of the shift containing t.
    shift_index = (t - schedule.handover_start) // schedule.interval
    return schedule.users[shift_index % len(schedule.users)]


def override_at(overrides: Sequence[Override], t: datetime) -> Override | None:
    """The override covering t, if any. Overrides never overlap, so there is at most one."""
    for override in overrides:
        if override.covers(t):
            return override
    return None


def on_call_at(schedule: Schedule, overrides: Sequence[Override], t: datetime) -> OnCall | None:
    """Who is on call at instant t. An override wins; otherwise the rotation applies."""
    override = override_at(overrides, t)
    if override is not None:
        return OnCall(override.user, "override")
    user = rotation_user_at(schedule, t)
    return OnCall(user, "rotation") if user is not None else None


# --- Rendering a window ------------------------------------------------------


def handovers_between(schedule: Schedule, after: datetime, before: datetime) -> Iterator[datetime]:
    """Rotation handover instants h with after < h < before, in order.

    The very first shift's start (handover_start) counts as a handover.
    """
    start, interval = schedule.handover_start, schedule.interval
    # Index of the first handover strictly after `after`. Floor division of a
    # negative timedelta rounds down, so max(0, ...) covers `after` < start.
    k = max(0, (after - start) // interval + 1)
    while (handover := start + k * interval) < before:
        yield handover
        k += 1


def change_points(
    schedule: Schedule, overrides: Sequence[Override], frm: datetime, until: datetime
) -> list[datetime]:
    """Every instant in [frm, until] where the on-call person could change, sorted.

    Between two consecutive points nothing starts or ends, so on_call_at() is
    constant there. Only points inside the window are produced, which is what
    truncates the output to [frm, until).
    """
    points = {frm, until}
    points.update(handovers_between(schedule, frm, until))
    for override in overrides:
        for edge in (override.start, override.end):
            if frm < edge < until:
                points.add(edge)
    return sorted(points)


def render(
    schedule: Schedule, overrides: Sequence[Override], frm: datetime, until: datetime
) -> list[Entry]:
    """The final schedule for [frm, until): rotation + overrides, truncated and merged."""
    entries: list[Entry] = []
    points = change_points(schedule, overrides, frm, until)

    for start, end in zip(points, points[1:]):
        # Constant over [start, end), so asking at `start` answers for the whole gap.
        who = on_call_at(schedule, overrides, start)
        if who is None:
            continue  # before the schedule starts: nobody is on call

        previous = entries[-1] if entries else None
        if previous and previous.user == who.user and previous.end == start:
            # Same person, no break: extend their entry rather than start a new one.
            entries[-1] = Entry(who.user, previous.start, end)
        else:
            entries.append(Entry(who.user, start, end))
    return entries


# --- Paging: who's next? -----------------------------------------------------


def next_handover(
    schedule: Schedule, overrides: Sequence[Override], t: datetime
) -> Handover | None:
    """The first instant after t when a *different* person goes on call, or None if never.

    Why the search ends: once every override is over and the rotation has
    started, the rotation repeats every len(users) * interval. One full cycle
    past that point visits every user's turn, so if nobody different has
    appeared by then, nobody ever will (e.g. a one-person rotation).
    """
    current = on_call_at(schedule, overrides, t)
    current_user = current.user if current else None

    settled = max([t, schedule.handover_start] + [o.end for o in overrides])
    horizon = settled + len(schedule.users) * schedule.interval

    # Candidates are produced lazily, in time order: heapq.merge interleaves the
    # handover generator with the (small, sorted) override edges one item at a
    # time. We usually stop at the first candidate, so nothing beyond it is built.
    # `horizon + interval` because handovers_between excludes its upper bound,
    # and the handover exactly at `horizon` must still be checked.
    handovers = handovers_between(schedule, t, horizon + schedule.interval)
    override_edges = sorted(edge for o in overrides for edge in (o.start, o.end) if edge > t)

    for point in heapq.merge(handovers, override_edges):
        who = on_call_at(schedule, overrides, point)
        if who is not None and who.user != current_user:
            return Handover(point, who)
    return None
