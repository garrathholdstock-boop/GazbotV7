#!/usr/bin/env python3
"""FLOW-LED greenfield — STEP 8: the ADVERSARIAL RE-DERIVATION.

Everything in this section rests on one simulator I wrote this morning. If it has a bug — a
lookahead, a stop that fills at the wrong price, a target that fills without the tape trading
through it — then every number above is confidently wrong. So this re-walks a sample of trades
STRAIGHT off the raw ticks with independent code and checks four things per trade:

  1. the entry price is the first tick STRICTLY AFTER the signal minute closes (no lookahead)
  2. the tape actually TRADED THROUGH the target before the claimed exit time, if it claims TARGET
  3. the tape actually traded at/through the stop, if it claims STOP
  4. no earlier tick hit the OPPOSITE level first (the order of stop vs target inside a bar — the
     one thing a bar backtest cannot know and the reason this is tick-honest at all)

Also re-derives the headline P&L arithmetic from raw prices ($2.00/pt, $1.50 round trip) rather than
trusting the stored `net` column, and re-states the per-ISO-WEEK concentration, which is the thing
the day-level leave-one-out cannot see.

Writes reports/friday_v7/sections/fl/verify.json
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.lake import connect  # noqa: E402

DIR = "/home/alphabot/gazbot7/reports/friday_v7/sections/fl"
OUT = f"{DIR}/verify.json"
FEE, VPP, TICK = 1.50, 2.00, 0.25


def main():
    tr = pd.read_csv(f"{DIR}/trades_abl_FBREAK.csv")
    us = tr[tr["session"] == "US"].copy()
    con = connect(symbol="MNQ")

    rng = np.random.default_rng(7)
    sample = us.sample(12, random_state=11).sort_values("ts")
    checks = []
    for _, r in sample.iterrows():
        t_open = (int(r["ts"]) + 60) * 1000
        t_close = t_open + int(r["held_min"] * 60_000) + 5_000
        d = con.execute(f"""SELECT ts_ms, price FROM ticks
            WHERE ts_ms >= {t_open} AND ts_ms <= {t_close} ORDER BY ts_ms""").fetchdf()
        if d.empty:
            continue
        p = d["price"].to_numpy(float)
        first = float(p[0])
        dirn = int(r["dir"])
        exp_entry = first + dirn * TICK
        stop = exp_entry - dirn * float(r["stop_pt"]) if "stop_pt" in r else None
        targ = exp_entry + dirn * float(r["targ_pt"]) if "targ_pt" in r else None
        hit_t = None if targ is None else (np.argmax(p >= targ) if dirn > 0 else np.argmax(p <= targ))
        hit_s = None if stop is None else (np.argmax(p <= stop) if dirn > 0 else np.argmax(p >= stop))
        got_t = bool((p >= targ).any() if dirn > 0 else (p <= targ).any()) if targ else False
        got_s = bool((p <= stop).any() if dirn > 0 else (p >= stop).any()) if stop else False
        pts = dirn * (float(r["exit"]) - float(r["entry"]))
        checks.append({
            "day": r["day"], "time": pd.to_datetime(int(r["ts"]) + 60, unit="s", utc=True)
            .strftime("%m-%d %H:%M:%S"), "dir": dirn, "reason": r["reason"],
            "entry_stored": float(r["entry"]), "entry_recomputed": round(exp_entry, 2),
            "entry_ok": abs(exp_entry - float(r["entry"])) < 1e-6,
            "target_traded_through": got_t, "stop_traded_through": got_s,
            "which_came_first": ("TARGET" if got_t and (not got_s or hit_t < hit_s) else
                                 ("STOP" if got_s else "NEITHER")),
            "reason_matches_tape": r["reason"] == ("TARGET" if got_t and (not got_s or hit_t < hit_s)
                                                   else ("STOP" if got_s else "TIME")),
            "net_stored": float(r["net"]),
            "net_recomputed": round(pts * VPP - FEE, 2),
            "net_ok": abs(pts * VPP - FEE - float(r["net"])) < 0.01,
        })
    ok = {k: sum(1 for c in checks if c[k]) for k in
          ("entry_ok", "net_ok", "reason_matches_tape")}
    res = {"sampled": len(checks), "passed": ok, "checks": checks}

    # ── the concentration the day-level LOO cannot see: PER ISO WEEK ─────────────────────────
    us["wk"] = pd.to_datetime(us["day"]).dt.isocalendar().week.astype(int)
    wk = us.groupby("wk").agg(days=("day", "nunique"), n=("net", "size"), net=("net", "sum"),
                              per_trade=("net", "mean")).round(2)
    res["per_iso_week"] = {int(k): v for k, v in wk.to_dict("index").items()}
    best = wk["net"].idxmax()
    sub = us[us["wk"] != best]
    res["strip_best_week"] = {"dropped_week": int(best),
                              "dropped_net": round(float(wk.loc[best, "net"]), 2),
                              "n": int(len(sub)), "net": round(float(sub["net"].sum()), 2),
                              "per_trade": round(float(sub["net"].mean()), 2),
                              "share_of_total_pct": round(100 * float(wk.loc[best, "net"]
                                                                      / us["net"].sum()), 1)}
    res["latest_week"] = {"week": int(us["wk"].max()),
                          "n": int((us["wk"] == us["wk"].max()).sum()),
                          "net": round(float(us[us["wk"] == us["wk"].max()]["net"].sum()), 2),
                          "per_trade": round(float(us[us["wk"] == us["wk"].max()]["net"].mean()), 2)}

    json.dump(res, open(OUT, "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in res.items() if k != "checks"}, indent=1, default=str))
    for c in checks:
        print(c["time"], c["reason"], "entry_ok", c["entry_ok"], "net_ok", c["net_ok"],
              "tape_says", c["which_came_first"], "match", c["reason_matches_tape"])
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
