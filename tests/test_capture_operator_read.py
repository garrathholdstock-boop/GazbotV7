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


# ── CAPTURE THE GAUGE HE IS ACTUALLY READING (2026-09-25) ────────────────────────────────────────
# ★★★ Operator: "if it slides powerfully to the right or left i buy or sell and it works."
# ⚠⚠ THAT IS A CLAIM ABOUT THE SLOPE, AND NOTHING ON THIS DESK HAS EVER MEASURED THE SLOPE. The
# 80-cell grid and the gap rule both test the LEVEL — where the marker SITS. He is describing how
# fast it MOVES, which is the quantity I told him to read ("read the slope, the level is just where
# you have been") and then never tested.
# ⚠⚠⚠ AND HIS PRESSES WERE BEING RECORDED WITHOUT IT. The operator-model dataset could not see the
# method he was using, so no amount of collecting would ever have answered this.

def _src():
    return open("/home/alphabot/gazbot7/scripts/capture_operator_read.py", encoding="utf-8").read()


def test_the_press_records_the_cvd_slide_at_three_speeds():
    """★ Which window his eye actually reads is UNKNOWN, so record all three and decide later —
    but record them from the START, because ticks prune at 5 DAYS and a window not captured today
    can never be reconstructed."""
    s = _src()
    assert 'rec["gauge"] = g' in s
    for m in (1, 5, 15):
        assert f'g[f"slope_{{_m}}m"]' in s or f"slope_{m}m" in s
    assert "for _m in (1, 5, 15)" in s


def test_the_capture_window_matches_the_gauge_he_looks_at():
    """⚠ Rolling 3h, not the session — the gauge stopped using a session anchor this morning. A
    session-anchored capture would faithfully record a number he is not looking at."""
    s = _src()
    assert '"window_min": 180' in s and "_t - 180 * 60" in s


def test_a_gauge_failure_is_recorded_loudly():
    """⚠ Same rule as the context snapshot: a dataset that drops its failures quietly becomes
    "the presses where nothing went wrong"."""
    assert 'rec["gauge_error"]' in _src()


def test_the_capture_still_cannot_consume_or_place_anything():
    """⚠⚠⚠ UNCHANGED AND NON-NEGOTIABLE. It reads; the rider consumes. A second reader that
    disposed of a request would silently EAT HIS PRESS."""
    s = _src()
    assert "mode=ro" in s, "the new query must open capture.db READ-ONLY"
    for forbidden in ("placeOrder", "os.remove", "os.unlink"):
        assert forbidden not in s
