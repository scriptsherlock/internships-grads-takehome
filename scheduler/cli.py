"""Command-line interface. All I/O, flag handling and exit codes live here.

Two modes:
  range mode:  --from=T1 --until=T2   -> the brief's JSON array of entries
  point mode:  --at=T                 -> who's on call at T, why, and who's next

Exit codes: 0 success, 1 invalid input (message on stderr), 2 bad flags (argparse).
"""

import argparse
import json
import sys
from typing import Any

from scheduler.core import next_handover, on_call_at, render
from scheduler.parsing import (
    InputError,
    entry_to_json,
    load_json,
    on_call_report_to_json,
    parse_overrides,
    parse_schedule,
    parse_time,
)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Exactly one mode: either --at, or both --from and --until.
    range_flags = (args.frm is not None, args.until is not None)
    if args.at is not None and any(range_flags):
        parser.error("--at cannot be combined with --from/--until")
    if args.at is None and not all(range_flags):
        parser.error("give both --from and --until, or --at")

    try:
        schedule = parse_schedule(load_json(args.schedule))
        overrides = parse_overrides(load_json(args.overrides)) if args.overrides else ()

        if args.at is not None:
            at = parse_time(args.at, "--at")
            result: Any = on_call_report_to_json(
                at, on_call_at(schedule, overrides, at), next_handover(schedule, overrides, at)
            )
        else:
            frm = parse_time(args.frm, "--from")
            until = parse_time(args.until, "--until")
            if frm >= until:
                raise InputError("--from must be before --until")
            result = [entry_to_json(e) for e in render(schedule, overrides, frm, until)]
    except InputError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except OverflowError:
        # Valid inputs can still push date arithmetic past year 9999 (Python's
        # datetime limit), e.g. a handover just after --until near the end of time.
        print("error: dates fall outside the supported range (years 1 to 9999)", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="render-schedule",
        description=(
            "Render an on-call schedule (rotation + overrides) as JSON for a time window, "
            "or answer who is on call at a single instant."
        ),
        epilog=(
            "examples:\n"
            "  render-schedule --schedule=s.json --overrides=o.json "
            "--from=2026-11-06T17:00:00Z --until=2026-11-20T17:00:00Z\n"
            "  render-schedule --schedule=s.json --overrides=o.json --at=2026-11-09T18:00:00Z"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--schedule", required=True, metavar="FILE",
                        help="JSON file with the schedule definition")
    parser.add_argument("--overrides", metavar="FILE",
                        help="JSON file with an array of overrides (optional)")
    parser.add_argument("--from", dest="frm", metavar="TIME",
                        help="start of the window (ISO 8601, e.g. 2026-11-06T17:00:00Z)")
    parser.add_argument("--until", metavar="TIME", help="end of the window (exclusive)")
    parser.add_argument("--at", metavar="TIME",
                        help="instead of a window: who is on call at TIME, and who is next")
    return parser
