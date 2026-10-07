import json, sys
sys.path.insert(0, "scripts")
import s_line_diagnostics as D


def _rec(day, line, peak_def, err, trades):
    calls = [{"error": "x" if i < err else None} for i in range(10)]
    return {"day": day, "line": line, "peak_def": peak_def, "calls": calls, "trades": trades,
            "net_usd": sum(t["pnl_usd"] for t in trades)}


def _t(side, pts, peak, usd, why="CLAUDE_EXIT"):
    return {"side": side, "points": pts, "peak_pt": peak, "peak_1m": peak, "pnl_usd": usd, "why": why}


def test_pooled_counts_and_exclusions(tmp_path, monkeypatch):
    monkeypatch.setattr(D.SW, "OUT", str(tmp_path))
    good = _rec("2026-02-05", "v2", "1m", 0,
                [_t("LONG", 10, 12, 80), _t("LONG", -5, 2, -40), _t("SHORT", -8, 40, -64), _t("LONG", 3, 30, 24, "WINDOW_CLOSE_1330Z")])
    json.dump(good, open(tmp_path / "x_2026-02-05.json", "w"))
    json.dump(_rec("2026-02-19", "v2", None, 0, []), open(tmp_path / "x_2026-02-19.json", "w"))      # old page
    json.dump(_rec("2026-03-05", "v2", "1m", 5, []), open(tmp_path / "x_2026-03-05.json", "w"))      # poisoned
    json.dump(_rec("2026-03-19", "v1", "5m_sampled", 0, []), open(tmp_path / "x_2026-03-19.json", "w"))
    days, skipped = D.load("x")
    assert [d["day"] for d in days] == ["2026-02-05"] and len(skipped) == 3
    monkeypatch.setattr(D, "_day_move", lambda d: 50.0)
    q = D.diagnose(days)
    assert q["Q1_exits_in_profit"] == (2, 4)
    assert q["Q1m_model_exits_in_profit"] == (1, 3) and q["Q1w_window_close_in_profit"] == (1, 1)
    assert q["Q2_never_green"] == (1, 4)
    assert q["Q3_giveback"] == (1, 2)          # peaks 40 and 30; only the -8pt one gave back
    assert q["Q4_worst_trade"] == -64
    assert q["Q5_with"] == (3, 64.0) and q["Q5_against"] == (1, -64.0)
