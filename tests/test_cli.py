"""End-to-end tests: run the real ./render-schedule executable as a subprocess."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "render-schedule"
EXAMPLES = ROOT / "examples"

# The brief's expected output, verbatim.
BRIEF_OUTPUT = """\
[
  {
    "user": "alice",
    "start_at": "2026-11-06T17:00:00Z",
    "end_at": "2026-11-09T17:00:00Z"
  },
  {
    "user": "charlie",
    "start_at": "2026-11-09T17:00:00Z",
    "end_at": "2026-11-09T22:00:00Z"
  },
  {
    "user": "alice",
    "start_at": "2026-11-09T22:00:00Z",
    "end_at": "2026-11-13T17:00:00Z"
  },
  {
    "user": "bob",
    "start_at": "2026-11-13T17:00:00Z",
    "end_at": "2026-11-20T17:00:00Z"
  }
]
"""


def run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=cwd
    )


def example_args(*extra: str) -> list[str]:
    return [
        f"--schedule={EXAMPLES / 'schedule.json'}",
        f"--overrides={EXAMPLES / 'overrides.json'}",
        *extra,
    ]


def write_json(tmp_path: Path, name: str, data) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_brief_example_output_is_byte_for_byte_identical():
    result = run(*example_args("--from=2026-11-06T17:00:00Z", "--until=2026-11-20T17:00:00Z"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.replace("\r\n", "\n") == BRIEF_OUTPUT


def test_works_from_another_directory(tmp_path):
    result = run(*example_args("--from=2026-11-06T17:00:00Z", "--until=2026-11-20T17:00:00Z"), cwd=tmp_path)
    assert result.returncode == 0, result.stderr


def test_at_mode():
    result = run(*example_args("--at=2026-11-09T18:00:00Z"))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "at": "2026-11-09T18:00:00Z",
        "user": "charlie",
        "source": "override",
        "next": {"user": "alice", "source": "rotation", "start_at": "2026-11-09T22:00:00Z"},
    }


def test_at_mode_before_the_schedule_starts():
    result = run(*example_args("--at=2026-11-01T00:00:00Z"))
    report = json.loads(result.stdout)
    assert (report["user"], report["source"]) == (None, None)
    assert report["next"]["user"] == "alice"


def test_overrides_flag_is_optional():
    result = run(f"--schedule={EXAMPLES / 'schedule.json'}",
                 "--from=2026-11-06T17:00:00Z", "--until=2026-11-13T17:00:00Z")
    assert result.returncode == 0, result.stderr
    assert [e["user"] for e in json.loads(result.stdout)] == ["alice"]


def test_help():
    result = run("--help")
    assert result.returncode == 0
    assert "--at" in result.stdout


# --- Errors: invalid input -> exit 1 with a message on stderr -------------------


def test_missing_file(tmp_path):
    result = run(f"--schedule={tmp_path / 'nope.json'}", "--at=2026-11-09T00:00:00Z")
    assert result.returncode == 1
    assert "cannot read file" in result.stderr
    assert result.stdout == ""


def test_invalid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    result = run(f"--schedule={bad}", "--at=2026-11-09T00:00:00Z")
    assert result.returncode == 1
    assert "invalid JSON" in result.stderr


def test_from_must_be_before_until():
    result = run(*example_args("--from=2026-11-20T17:00:00Z", "--until=2026-11-06T17:00:00Z"))
    assert result.returncode == 1
    assert "--from must be before --until" in result.stderr


def test_overlapping_overrides(tmp_path):
    overrides = write_json(tmp_path, "o.json", [
        {"user": "a", "start_at": "2026-11-09T00:00:00Z", "end_at": "2026-11-09T02:00:00Z"},
        {"user": "b", "start_at": "2026-11-09T01:00:00Z", "end_at": "2026-11-09T03:00:00Z"},
    ])
    result = run(f"--schedule={EXAMPLES / 'schedule.json'}", f"--overrides={overrides}",
                 "--at=2026-11-09T00:00:00Z")
    assert result.returncode == 1
    assert "overlapping" in result.stderr


def test_bad_timestamp_flag():
    result = run(*example_args("--at=yesterday"))
    assert result.returncode == 1
    assert "--at" in result.stderr


# --- Errors: wrong flags -> exit 2 with usage --------------------------------


@pytest.mark.parametrize(
    "flags",
    [
        ["--at=2026-11-09T00:00:00Z", "--from=2026-11-06T17:00:00Z"],
        ["--from=2026-11-06T17:00:00Z"],
        [],
    ],
)
def test_mode_flags_must_be_consistent(flags):
    result = run(*example_args(*flags))
    assert result.returncode == 2
    assert "usage:" in result.stderr


# --- Hands-on scenarios: custom inputs written to temp files, run end to end ---------
# pytest's tmp_path gives each test a fresh folder and cleans it up afterwards,
# so these never touch examples/.

BRIEF_SCHEDULE_JSON = {
    "users": ["alice", "bob", "charlie"],
    "handover_start_at": "2026-11-06T17:00:00Z",
    "handover_interval_days": 7,
}


def run_custom(tmp_path: Path, schedule: dict, overrides: list, *flags: str):
    """Write the given inputs to temp files, run the real script, return (code, stdout, stderr)."""
    result = run(
        f"--schedule={write_json(tmp_path, 'schedule.json', schedule)}",
        f"--overrides={write_json(tmp_path, 'overrides.json', overrides)}",
        *flags,
    )
    return result.returncode, result.stdout, result.stderr


def as_rows(stdout: str) -> list[tuple[str, str, str]]:
    return [(e["user"], e["start_at"], e["end_at"]) for e in json.loads(stdout)]


def test_scenario_two_users_daily_handovers(tmp_path):
    schedule = {**BRIEF_SCHEDULE_JSON, "users": ["alice", "bob"], "handover_interval_days": 1}
    code, out, err = run_custom(tmp_path, schedule, [],
                                "--from=2026-11-06T17:00:00Z", "--until=2026-11-09T17:00:00Z")
    assert code == 0, err
    assert as_rows(out) == [
        ("alice", "2026-11-06T17:00:00Z", "2026-11-07T17:00:00Z"),
        ("bob", "2026-11-07T17:00:00Z", "2026-11-08T17:00:00Z"),
        ("alice", "2026-11-08T17:00:00Z", "2026-11-09T17:00:00Z"),
    ]


def test_scenario_override_crossing_a_handover(tmp_path):
    overrides = [{"user": "dave", "start_at": "2026-11-12T12:00:00Z", "end_at": "2026-11-14T12:00:00Z"}]
    code, out, err = run_custom(tmp_path, BRIEF_SCHEDULE_JSON, overrides,
                                "--from=2026-11-06T17:00:00Z", "--until=2026-11-20T17:00:00Z")
    assert code == 0, err
    assert as_rows(out) == [
        ("alice", "2026-11-06T17:00:00Z", "2026-11-12T12:00:00Z"),  # end of alice's shift
        ("dave", "2026-11-12T12:00:00Z", "2026-11-14T12:00:00Z"),   # spans the 13th 17:00 handover
        ("bob", "2026-11-14T12:00:00Z", "2026-11-20T17:00:00Z"),    # rest of bob's shift
    ]


def test_scenario_fractional_interval_is_a_clear_error(tmp_path):
    schedule = {**BRIEF_SCHEDULE_JSON, "handover_interval_days": 1.5}
    code, out, err = run_custom(tmp_path, schedule, [], "--at=2026-11-09T00:00:00Z")
    assert code == 1
    assert out == ""
    assert "handover_interval_days" in err and "positive whole number" in err
    assert "Traceback" not in err  # a message, not a crash


def test_scenario_overlapping_overrides_is_a_clear_error(tmp_path):
    overrides = [
        {"user": "dave", "start_at": "2026-11-09T17:00:00Z", "end_at": "2026-11-09T22:00:00Z"},
        {"user": "erin", "start_at": "2026-11-09T20:00:00Z", "end_at": "2026-11-10T02:00:00Z"},
    ]
    code, out, err = run_custom(tmp_path, BRIEF_SCHEDULE_JSON, overrides, "--at=2026-11-09T00:00:00Z")
    assert code == 1
    assert out == ""
    assert "overlapping" in err and "dave" in err and "erin" in err
    assert "2026-11-09T17:00:00Z to 2026-11-09T22:00:00Z" in err
    assert err.isascii()  # renders correctly in any terminal encoding
    assert "Traceback" not in err


@pytest.mark.parametrize(
    "at, user, source, next_user, next_at",
    [
        ("2026-11-07T00:00:00Z", "alice", "rotation", "charlie", "2026-11-09T17:00:00Z"),
        ("2026-11-09T18:00:00Z", "charlie", "override", "alice", "2026-11-09T22:00:00Z"),
        ("2026-11-10T00:00:00Z", "alice", "rotation", "bob", "2026-11-13T17:00:00Z"),
        ("2026-11-13T17:00:00Z", "bob", "rotation", "charlie", "2026-11-20T17:00:00Z"),
    ],
)
def test_scenario_at_mode_next_changes_over_time(at, user, source, next_user, next_at):
    result = run(*example_args(f"--at={at}"))
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert (report["user"], report["source"]) == (user, source)
    assert (report["next"]["user"], report["next"]["start_at"]) == (next_user, next_at)


# --- Precision and range limits: clear errors, never a traceback ------------------------


def test_fractional_seconds_in_overrides(tmp_path):
    overrides = [{"user": "dave", "start_at": "2026-11-09T17:00:00.250Z",
                  "end_at": "2026-11-09T17:00:00.750Z"}]
    code, out, err = run_custom(tmp_path, BRIEF_SCHEDULE_JSON, overrides,
                                "--from=2026-11-09T16:59:59Z", "--until=2026-11-09T17:00:02Z")
    assert code == 1 and out == ""
    assert "fractional seconds" in err and "Traceback" not in err


def test_non_utf8_schedule_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"\xff\xfe{}")
    result = run(f"--schedule={bad}", "--at=2026-11-09T00:00:00Z")
    assert result.returncode == 1
    assert "not a UTF-8 text file" in result.stderr and "Traceback" not in result.stderr


def test_window_at_the_end_of_time():
    result = run(*example_args("--from=9999-12-20T00:00:00Z", "--until=9999-12-31T23:59:59Z"))
    assert result.returncode == 1
    assert "outside the supported range" in result.stderr and "Traceback" not in result.stderr


def test_huge_interval(tmp_path):
    schedule = {**BRIEF_SCHEDULE_JSON, "handover_interval_days": 1_000_000_000}
    code, out, err = run_custom(tmp_path, schedule, [], "--at=2026-11-09T00:00:00Z")
    assert code == 1
    assert "too large" in err and "Traceback" not in err
