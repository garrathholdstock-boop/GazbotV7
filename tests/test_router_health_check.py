"""router_health_check tail parsing.

Fixtures are REAL lines from data/router_headless.log around the 2026-08-13 outage, because the
whole point of this monitor is to catch that exact shape and a synthetic approximation would not
prove it.
"""
import sys
import time

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

from router_health_check import parse_tail  # noqa: E402

ABORT = ("2026-08-13T{}Z ABORT: no JSON in output -> no change | "
         "raw='Failed to authenticate: OAuth session expired and could not be refreshed'")
OK = "2026-08-13T{}Z no change | 13:40Z US-PRE, halted=false healthy flat, day book +0.0"
APPLIED = "2026-08-13T{}Z APPLIED {{'abs_veto_long': 'on'}} | 13:35Z US-PRE, the 29922 ceiling broke"


def test_counts_only_the_current_abort_streak():
    lines = [OK.format("12:30:00"), ABORT.format("12:35:00"), ABORT.format("12:40:00"),
             ABORT.format("12:45:00")]
    streak, ts, last = parse_tail(lines)
    assert streak == 3
    assert "ABORT" in last
    assert ts is not None


def test_a_recovered_streak_is_history_not_an_alarm():
    # This is the real 13:00 -> 13:05 recovery. The router is fine NOW; the streak must read 0,
    # otherwise the alarm would keep firing for as long as the old ABORTs sit in the tail.
    lines = [ABORT.format("12:55:00"), ABORT.format("13:00:00"), APPLIED.format("13:05:28")]
    streak, _, last = parse_tail(lines)
    assert streak == 0
    assert "APPLIED" in last


def test_healthy_tail_is_zero():
    lines = [OK.format("15:15:17"), OK.format("15:20:21"), OK.format("15:25:21")]
    streak, _, _ = parse_tail(lines)
    assert streak == 0


def test_timestamp_is_parsed_as_utc_not_local():
    # The log stamps UTC with a trailing Z. Parsing it as local time would shift the computed age
    # by the box's offset and could mask or fake a SILENT fault.
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    _, ts, _ = parse_tail([f"{now}Z no change | fresh"])
    assert ts is not None
    assert abs(time.time() - ts) < 120, "a just-written line must read as seconds old, not hours"


def test_blank_lines_do_not_break_the_scan():
    lines = ["\n", ABORT.format("12:40:00"), "", ABORT.format("12:45:00"), "\n"]
    streak, _, _ = parse_tail(lines)
    assert streak == 2


def test_empty_log_is_not_a_crash():
    streak, ts, last = parse_tail([])
    assert (streak, ts, last) == (0, None, "")
