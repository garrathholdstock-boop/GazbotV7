"""THE PRESS SNAPSHOT MUST NEVER CONSUME THE PRESS.

`day_rider` reads day_rider_buy.txt / day_rider_claim.txt and CLEARS them. This capture script runs
on the same inotify event. If it ever wrote to, cleared, renamed or deleted one of those files, the
operator's press would vanish between the button and the broker — and it would look like the button
was broken, which this desk has already spent four hours debugging once.
"""
import os
import re

SRC = os.path.join(os.path.dirname(__file__), "..", "scripts", "capture_operator_read.py")


def _src():
    with open(SRC) as fh:
        return fh.read()


def test_it_never_writes_to_a_request_file():
    s = _src()
    # the only permitted write target is its own log
    writes = re.findall(r"open\(([^,)]+)\s*,\s*[\"']([aw][b+]?)[\"']", s)
    assert writes, "expected at least the log append"
    for target, mode in writes:
        assert target.strip() == "LOG", f"writes to {target} in mode {mode!r}; only LOG is allowed"


def test_it_cannot_clear_move_or_delete_anything():
    s = _src().lower()
    for forbidden in ("unlink", "remove(", "rename", "replace(", "truncate", "clear_buy",
                      "clear_claim", "shutil"):
        assert forbidden not in s, f"destructive call found: {forbidden}"


def test_it_has_no_order_path():
    s = _src().lower()
    for forbidden in ("placeorder", "place_order", "ib_async", "ib_insync", "marketorder",
                      "gate_switches", "desk_kill"):
        assert forbidden not in s, f"order-path vocabulary found: {forbidden}"


def test_a_failed_snapshot_still_leaves_a_row():
    """★ Otherwise the dataset silently becomes 'the presses where nothing went wrong', which is the
    worst possible bias in a record of a human's judgement."""
    s = _src()
    assert "context_error" in s and "LOUD, never silent" in s


def test_the_path_units_are_modified_not_exists():
    """An orphaned request flag lives up to 15 minutes; PathExists would re-snapshot in a loop."""
    here = os.path.dirname(__file__)
    for k in ("buy", "claim"):
        p = os.path.join(here, "..", "ops", "systemd", f"gazbot7-capture-read-{k}.path")
        txt = open(p).read()
        assert "PathModified=" in txt and "PathExists=" not in txt
