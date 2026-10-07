#!/usr/bin/env python3
"""FROZEN Q1-Q5 + Law-0 DIAGNOSTICS FOR THE S LINE (A2, pre-registered before the S1 number exists).

Pooled over every closed trade of every CLEAN, page-stamped day of one tag. Definitions are fixed here
so the baseline cannot drift with whoever recomputes it:
  Q1 exits in profit    = share of closed trades with points > 0           (denominator: all closed trades)
  Q1m                   = the same share over MODEL-CHOSEN exits only (why == CLAUDE_EXIT); this is the one that
                          tests the "take it" wording. Q1w = window-close (13:30Z) flattens, reported separately
                          because the simulator, not the model, made that exit.
  Q2 never green        = share of closed trades with peak_1m < 5pt        (all closed trades)
  Q3 give-backs         = of trades with peak_1m >= 30pt, share with points <= 0
  Q4 worst trade        = min pnl_usd over closed trades
  Q5 with/against       = entry direction vs the day's net move 02:00Z -> 13:30Z (1-min closes), P&L per group
READ-ONLY. `page_hash()` is the assembled-page identity written to the launch stamp.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import statistics as st
import sys

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")
import sim_week_recursive as SW  # noqa: E402

POISON = 0.10
PEAK_GREEN, PEAK_BIG = 5.0, 30.0


def page_hash(day: str = "2026-02-05", hhmm: str = "12:50") -> str:
    """sha of BRIEF_V2 + context(leg_list=False, band=False) at a fixed day/time, as run_day assembles it."""
    bars, _ = SW.load_day(day)
    h, m = map(int, hhmm.split(":"))
    d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
    now = d0 + (h * 60 + m) * 60
    upto = [b for b in bars if b[0] <= now]
    page = SW.BRIEF_V2 + "\n\n=== THE TAPE ===\n" + SW.context(upto, now, None, "", [], True, band=False, leg_list=False)
    return hashlib.sha256(page.encode()).hexdigest()[:16]


def _day_move(day: str) -> float:
    bars, _ = SW.load_day(day)
    d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
    w = [b for b in bars if d0 + SW.WIN_START_MIN * 60 <= b[0] <= d0 + SW.WIN_END_MIN * 60]
    return w[-1][3] - w[0][3] if len(w) > 1 else 0.0


def load(tag: str) -> tuple[list[dict], list[str]]:
    ok, skipped = [], []
    for p in sorted(glob.glob(f"{SW.OUT}/{tag}_????-??-??.json")):
        r = json.load(open(p))
        c = r.get("calls") or []
        err = sum(1 for x in c if x.get("error")) / len(c) if c else 1.0
        if r.get("line") != "v2" or r.get("peak_def") != "1m" or err > POISON:
            skipped.append(f"{r.get('day')} (line={r.get('line')} peak_def={r.get('peak_def')} err={err:.0%})")
            continue
        ok.append(r)
    return ok, skipped


def diagnose(days: list[dict]) -> dict:
    trades = [dict(t, _day=r["day"]) for r in days for t in r["trades"]]
    n = len(trades)
    big = [t for t in trades if t.get("peak_1m", t["peak_pt"]) >= PEAK_BIG]
    nets = [r["net_usd"] for r in days]
    out = {
        "days": len(days), "trades": n,
        "usd_per_day": round(st.mean(nets), 2) if nets else 0.0,
        "daily_sd": round(st.pstdev(nets), 2) if len(nets) > 1 else 0.0,
        "days_positive": sum(1 for x in nets if x > 0), "worst_day": min(nets) if nets else 0.0,
        "Q1_exits_in_profit": (sum(1 for t in trades if t["points"] > 0), n),
        "Q1m_model_exits_in_profit": (sum(1 for t in trades if t["why"] == "CLAUDE_EXIT" and t["points"] > 0),
                                      sum(1 for t in trades if t["why"] == "CLAUDE_EXIT")),
        "Q1w_window_close_in_profit": (sum(1 for t in trades if t["why"] != "CLAUDE_EXIT" and t["points"] > 0),
                                       sum(1 for t in trades if t["why"] != "CLAUDE_EXIT")),
        "Q2_never_green": (sum(1 for t in trades if t.get("peak_1m", t["peak_pt"]) < PEAK_GREEN), n),
        "Q3_giveback": (sum(1 for t in big if t["points"] <= 0), len(big)),
        "Q4_worst_trade": min((t["pnl_usd"] for t in trades), default=0.0),
    }
    mv = {r["day"]: _day_move(r["day"]) for r in days}
    w, a = [], []
    for t in trades:
        d = 1 if t["side"] == "LONG" else -1
        (w if d * mv[t["_day"]] > 0 else a).append(t["pnl_usd"])
    out["Q5_with"] = (len(w), round(sum(w), 2))
    out["Q5_against"] = (len(a), round(sum(a), 2))
    out["per_day"] = [(r["day"], len(r["trades"]), r["net_usd"]) for r in days]
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="sline_s1b")
    ap.add_argument("--page-hash", action="store_true")
    ap.add_argument("--write", action="store_true", help="stamp the result to reports/recursive_loop/S1_BASELINE.json")
    a = ap.parse_args()
    if a.page_hash:
        print(page_hash())
        sys.exit(0)
    days, skipped = load(a.tag)
    res = diagnose(days)
    print(json.dumps(res, indent=1, default=str))
    if a.write:
        res["tag"], res["excluded"] = a.tag, skipped
        res["stamped"] = dt.datetime.now(dt.UTC).isoformat()
        json.dump(res, open(f"{GB}/reports/recursive_loop/S1_BASELINE.json", "w"), indent=1, default=str)
    if skipped:
        print("EXCLUDED:", *skipped, sep="\n  ")
