"""LEG WATCH IS READ-ONLY, AND ITS MESSAGES MAY NOT PREDICT.

The desk shipped tunnel_watch on a 1.75x excursion claim that did not replicate; it ran nine hours
before withdrawal. The lesson banked then was that a live instrument's founding number must be
re-derived — and the lesson here is that an alert which sounds like a forecast will be traded like
one. Every message must carry its reference class AND its own limit.
"""
import os
import re

SRC = os.path.join(os.path.dirname(__file__), "..", "scripts", "leg_watch.py")
UNIT = os.path.join(os.path.dirname(__file__), "..", "ops", "systemd", "gazbot7-leg-watch.service")


def _src():
    with open(SRC) as fh:
        return fh.read()


def test_no_order_path():
    s = _src().lower()
    for bad in ("placeorder", "place_order", "ib_async", "ib_insync", "marketorder",
                "gate_switches", "day_rider_buy", "day_rider_claim", "desk_kill"):
        assert bad not in s, f"order-path vocabulary found: {bad}"


def test_it_opens_the_tape_read_only_and_writes_only_its_own_files():
    s = _src()
    assert "mode=ro" in s, "capture.db must be opened read-only"
    writes = re.findall(r"open\(([^,)]+)\s*,\s*[\"']([aw][b+]?)[\"']", s)
    for target, _mode in writes:
        assert target.strip() in ("STATE", "LOG"), f"unexpected write target {target}"


def test_every_alert_states_it_is_not_a_forecast():
    """★ The one sentence that stops an alert being read as a signal."""
    s = _src()
    assert "REFERENCE CLASS, NOT A FORECAST" in s
    assert "50/50" in s, "the message must carry the measured forward odds"


def test_the_reference_class_is_frozen_and_tied_to_the_retrace_parameter():
    s = _src()
    assert "REFCLASS" in s and "FROZEN 2026-09-14" in s
    assert "these numbers ARE that parameter" in s, \
        "changing RETRACE_ATR invalidates the table and the source must say so"


def test_it_filters_symbol():
    """capture.db carries MNQ and MGC; folding them once read ATR 1848 against a true 15."""
    s = _src()
    assert "symbol = ?" in s or "symbol=?" in s


def test_a_stale_tape_is_named_not_judged():
    s = _src()
    assert "STALE" in s and "dead feed and a quiet tape look identical" in s


def test_the_unit_does_not_reuse_the_memory_limit_that_killed_tunnel_watch():
    u = open(UNIT).read()
    m = re.search(r"MemoryMax=(\d+)M", u)
    assert m and int(m.group(1)) > 256, "tunnel-watch was OOM-killed four times at 256M"
