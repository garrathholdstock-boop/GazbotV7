"""An armed shadow slate that records NOTHING through a live session is a finding.

★★★2026-08-18. `gazbot7-shadow-mgc` recorded ZERO sims for three days — service active, CPU burning,
feed delivering, gate replaying 459 fires on the same tape — because the sim step was gated on the
bar COUNT growing and the ring is a pre-warmed fixed-size deque. `check_shadow` said OK throughout:
it counts sims in the MNQ store, and gold has its own store nothing looked at.

⚠ THE TEST THAT MATTERS IS `test_a_shut_market_is_skipped_not_alarmed`. This shares a channel with
naked-position alarms; firing every weekend would make it worthless.
"""
import os
import sqlite3
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import sweep  # noqa: E402
from gazbot7.config import RunConfig  # noqa: E402

NOW = datetime(2026, 8, 18, 15, 0, tzinfo=UTC)
DAY0 = int(datetime(2026, 8, 16, 22, 0, tzinfo=UTC).timestamp())   # the session under judgement


def _mk(tmp_path, mnq_sims, mgc_sims, mgc_bars, mnq_bars=16000):
    for name, n in (("shadow.db", mnq_sims), ("shadow_mgc.db", mgc_sims)):
        c = sqlite3.connect(f"{tmp_path}/{name}")
        c.execute("CREATE TABLE shadow_trades (id INTEGER PRIMARY KEY, entry_ts INTEGER)")
        c.executemany("INSERT INTO shadow_trades (entry_ts) VALUES (?)",
                      [(DAY0 + 60 * i,) for i in range(n)])
        c.commit()
        c.close()
    cap = sqlite3.connect(f"{tmp_path}/capture.db")
    cap.execute("CREATE TABLE bars (symbol TEXT, bar_ts INTEGER)")
    for sym, n in (("MNQ", mnq_bars), ("MGC", mgc_bars)):
        cap.executemany("INSERT INTO bars VALUES (?,?)", [(sym, DAY0 + i) for i in range(n)])
    cap.commit()
    cap.close()
    return RunConfig(shadow_store_path=f"{tmp_path}/shadow.db", capture_path=f"{tmp_path}/capture.db")


def _point_mgc_at(monkeypatch, tmp_path):
    real = os.path.join
    monkeypatch.setattr(sweep.os.path, "join",
                        lambda *a: f"{tmp_path}/shadow_mgc.db" if a[-1] == "shadow_mgc.db"
                        else real(*a))


def test_a_silent_armed_slate_on_a_live_session_is_a_finding(monkeypatch, tmp_path):
    """★ THE 3-DAY OUTAGE. Gold armed, gold silent, tape plainly running."""
    cfg = _mk(tmp_path, mnq_sims=390, mgc_sims=0, mgc_bars=16000)
    _point_mgc_at(monkeypatch, tmp_path)
    r = sweep.check_shadow_arms(cfg, NOW)
    assert r["status"] == sweep.WARN, r
    assert "MGC" in r["detail"] and "not firing at all" in r["detail"]


def test_a_shut_market_is_skipped_not_alarmed(monkeypatch, tmp_path):
    """★ THE ONE THAT MATTERS. A weekend produces zero sims legitimately. Alarming then would make
    the channel worthless — and this one carries naked-position alarms."""
    cfg = _mk(tmp_path, mnq_sims=0, mgc_sims=0, mgc_bars=0, mnq_bars=0)  # nothing traded
    _point_mgc_at(monkeypatch, tmp_path)
    r = sweep.check_shadow_arms(cfg, NOW)
    assert r["status"] == sweep.OK, r
    assert "SKIPPED" in r["detail"] and "not the same as clean" in r["detail"]


def test_a_firing_slate_is_quiet(monkeypatch, tmp_path):
    cfg = _mk(tmp_path, mnq_sims=390, mgc_sims=4, mgc_bars=16000)
    _point_mgc_at(monkeypatch, tmp_path)
    r = sweep.check_shadow_arms(cfg, NOW)
    assert r["status"] == sweep.OK, r
    assert "4 sims" in r["detail"]


def test_it_judges_the_slate_not_the_individual_arm(monkeypatch, tmp_path):
    """A level_break arm can legitimately go days without firing. One sim from the slate is enough
    to prove the MECHANISM is alive, which is all this check claims to measure."""
    cfg = _mk(tmp_path, mnq_sims=390, mgc_sims=1, mgc_bars=16000)
    _point_mgc_at(monkeypatch, tmp_path)
    assert sweep.check_shadow_arms(cfg, NOW)["status"] == sweep.OK
