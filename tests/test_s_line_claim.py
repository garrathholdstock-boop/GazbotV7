import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import s_line_claim as C


def _t(side, opened, closed, entry, pnl):
    return {"side": side, "opened": opened, "closed": closed, "entry": entry, "exit": entry, "pnl_usd": pnl,
            "held_min": 5, "peak_pt": 0}


def test_claim_rebuys_counts_only_same_side_after_claim():
    a = _t("LONG", "2026-02-05T10:00:00+00:00", "2026-02-05T10:10:00+00:00", 100, 200)
    b = _t("LONG", "2026-02-05T10:15:00+00:00", "2026-02-05T10:30:00+00:00", 100, -50)
    c = _t("SHORT", "2026-02-05T10:32:00+00:00", "2026-02-05T10:40:00+00:00", 100, 10)
    claims = [{"action": "EXIT", "closed": a["closed"]}]
    assert C.claim_rebuys([a, b, c], claims, 15) == [-50]
    assert C.claim_rebuys([a, b, c], [{"action": "HOLD", "closed": a["closed"]}], 15) == []
    assert C.claim_rebuys([a, b, c], claims, 3) == []


def test_target_look_requires_k_times_atr(monkeypatch):
    monkeypatch.setattr(C.SW, "atr14", lambda b: 10.0)
    bars = [(i * 60, 0, 0, 0) for i in range(40)]
    t = _t("LONG", "1970-01-01T00:05:00+00:00", "1970-01-01T00:35:00+00:00", 100, 0)
    calls = [{"ts": "1970-01-01T00:20:00+00:00", "px": 115, "action": "HOLD", "holding": True},
             {"ts": "1970-01-01T00:25:00+00:00", "px": 121, "action": "EXIT", "holding": True},
             {"ts": "1970-01-01T00:30:00+00:00", "px": 130, "action": "HOLD", "holding": True}]
    x = C.target_looks(bars, calls, [t], 2.0)
    assert len(x) == 1 and x[0]["action"] == "EXIT" and x[0]["ahead"] == 21
