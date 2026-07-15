"""D9 — execution monitor: fills-based, and the V5 false-positive designed out."""

from __future__ import annotations

import json

from gazbot7.monitor import classify_execution, execution_health, heartbeat_status
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
