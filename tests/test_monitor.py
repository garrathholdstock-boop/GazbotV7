"""D9 — execution monitor: fills-based, and the V5 false-positive designed out."""

from __future__ import annotations

import json

from gazbot7.monitor import (classify_execution, execution_health, heartbeat_status,
                             page_decision, situation)
from gazbot7.store import Fill, open_store, record_fill, record_signal


def test_ok_when_fills_flowing():
    assert classify_execution(submitted=3, fills=6, rejects=0)[0] == "OK"


def test_crit_when_submitted_but_zero_fills():
    assert classify_execution(submitted=5, fills=0, rejects=0)[0] == "CRIT"


def test_crit_on_rejects_with_no_fills():
    assert classify_execution(submitted=0, fills=0, rejects=4)[0] == "CRIT"


def test_warn_below_crit_threshold():
    assert classify_execution(submitted=1, fills=0, rejects=0)[0] == "WARN"


def test_no_false_positive_on_a_normal_scalp():
    # THE V5 FIX: a 2-lot scalp is 1 submit + 2 fills (entry+exit) — reads OK,
    # never CRIT. V5 false-CRIT'd this exact case and reboot-cascaded.
    assert classify_execution(submitted=1, fills=2, rejects=0)[0] == "OK"


def test_execution_health_crit_integration(tmp_path):
    store = open_store(tmp_path / "t.db")
    for _ in range(5):
        record_signal(store, symbol="MNQ", gate="thrust", side="LONG",
                      outcome="submitted", ts="2026-07-15T13:00:00+00:00")
    v = execution_health(store, since_iso="2026-07-15T00:00:00+00:00")
    assert v.status == "CRIT" and v.submitted == 5 and v.fills == 0


def test_execution_health_ok_with_fills(tmp_path):
    store = open_store(tmp_path / "t.db")
    for _ in range(3):
        record_signal(store, symbol="MNQ", gate="thrust", side="LONG",
                      outcome="submitted", ts="2026-07-15T13:00:00+00:00")
    for i in range(4):
        record_fill(store, Fill(f"e{i}", "o", "MNQ", "BUY", 1, 29950.0, "2026-07-15T13:00:00+00:00"))
    v = execution_health(store, since_iso="2026-07-15T00:00:00+00:00")
    assert v.status == "OK" and v.fills == 4


def test_heartbeat_status(tmp_path):
    p = tmp_path / "core_health.json"
    now = "2026-07-15T18:00:00+00:00"
    assert heartbeat_status(str(p), now)[0] == "CRIT"  # missing → core down
    p.write_text(json.dumps({"ts": "2026-07-15T17:59:30+00:00"}))  # 30s old
    assert heartbeat_status(str(p), now, max_age_s=120)[0] == "OK"
    p.write_text(json.dumps({"ts": "2026-07-15T17:50:00+00:00"}))  # 10 min old
    assert heartbeat_status(str(p), now, max_age_s=120)[0] == "CRIT"  # stale → hung


# ── ★2026-09-12 the alarm's own two faults: venue-blindness, and a counter that bypassed dedupe ──

def test_no_page_while_the_venue_is_shut_for_hours():
    send, why = page_decision("CRIT", mins_to_open=2332.0)   # Saturday morning
    assert send is False and "expected while closed" in why


def test_pages_before_the_reopen_so_he_hears_it_before_the_bell():
    send, why = page_decision("CRIT", mins_to_open=20.0)     # Sunday 21:40Z
    assert send is True and "reopens" in why


def test_pages_through_the_open_session():
    assert page_decision("CRIT", mins_to_open=None)[0] is True


def test_a_non_critical_reading_never_pages():
    assert page_decision("WARN", mins_to_open=None)[0] is False
    assert page_decision("OK", mins_to_open=2332.0)[0] is False


def test_situation_strips_the_live_counter_that_defeated_dedupe():
    a = situation("0 fills / 0 submitted / 0 rejects", "core heartbeat stale 7984s (hung/dead)")
    b = situation("0 fills / 0 submitted / 0 rejects", "core heartbeat stale 8584s (hung/dead)")
    assert a == b                      # ten minutes later is the SAME situation
    c = situation("0 fills / 0 submitted / 0 rejects", "core heartbeat missing (core down?)")
    assert c != a                      # a DIFFERENT failure still gets through


def test_dedupe_suppresses_the_repeat_but_a_new_failure_gets_through(tmp_path):
    from gazbot7.notify import dedupe_ok
    p = str(tmp_path / "d.json")
    sit = situation("0 fills / 0 submitted / 0 rejects", "core heartbeat stale 7984s (hung/dead)")
    assert dedupe_ok("monitor.desk", sit, path=p) is True
    later = situation("0 fills / 0 submitted / 0 rejects", "core heartbeat stale 8584s (hung/dead)")
    assert dedupe_ok("monitor.desk", later, path=p) is False        # the flood, stopped
    other = situation("0 fills / 0 submitted / 0 rejects", "core heartbeat missing (core down?)")
    assert dedupe_ok("monitor.desk", other, path=p) is True         # not blind to a new fault
