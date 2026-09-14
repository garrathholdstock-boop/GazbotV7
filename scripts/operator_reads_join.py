#!/usr/bin/env python3
"""LABEL THE OPERATOR'S READS — join each captured press to what the trade actually did.

This is the other half of capture_operator_read.py. The capture records the INPUT (what the tape
looked like when he pressed); this attaches the OUTCOME (what the resulting trade made). Together
they are the dataset eleven months of studies never had: 119 calibrations tried to reverse-engineer
his judgement from its results alone, and all of them lost.

⚠ COLLECT FIRST, MODEL LATER, AND THE THRESHOLD IS WRITTEN DOWN NOW SO IT CANNOT DRIFT: do not fit
anything until there are at least 30 labelled presses with outcomes. At n<30 any "what separates his
winners" answer is a story about noise, and telling it would be the 120th calibration.

⚠ SINGLE LOT ONLY for P&L, always. His manual entries are +$78.27/trade at one lot and -$222.59 at
multi-lot, and the difference is the paper engine's fabricated fill, not his judgement.
"""
from __future__ import annotations
import datetime as dt
import json
import sqlite3

import pandas as pd

GB = "/home/alphabot/gazbot7"
WINDOW_S = 180          # a press and its trade should open within this; wider would mis-attribute


def main() -> int:
    try:
        reads = [json.loads(l) for l in open(f"{GB}/data/operator_reads.jsonl") if l.strip()]
    except FileNotFoundError:
        print("no reads captured yet"); return 0
    reads = [r for r in reads if (r.get("request") or {}).get("raw")]
    if not reads:
        print("no reads with a recorded request yet — the capture is armed and waiting for a press")
        return 0
    c = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
    tr = pd.read_sql("select id,side,qty,entry_price,exit_price,opened_at,closed_at,pnl_usd,"
                     "exit_reason,gate from trades where closed_at is not null", c)
    tr["t0"] = pd.to_datetime(tr.opened_at, format="mixed", utc=True)

    rows = []
    for r in reads:
        t = dt.datetime.fromisoformat(r["ts"])
        near = tr[(tr.t0 >= t - dt.timedelta(seconds=30)) &
                  (tr.t0 <= t + dt.timedelta(seconds=WINDOW_S))]
        f = r.get("facts") or {}
        rows.append({
            "ts": r["ts"], "kind": r["kind"],
            "pressed": (r.get("request") or {}).get("raw", "")[:60],
            "price": f.get("price"), "atr": f.get("atr"),
            "pos_in_range": f.get("pos_in_range"),
            "vwap_stretch": (None if not f.get("atr") else
                             round((f.get("price", 0) - f.get("vwap", 0)) / f["atr"], 2)),
            "drift": (f.get("drift") or {}).get("direction"),
            "drift_ok": (f.get("drift") or {}).get("confirmed"),
            "n_trades": len(near),
            "lots": float(near.qty.sum()) if len(near) else 0.0,
            "pnl_all": round(float(near.pnl_usd.sum()), 2) if len(near) else None,
            "pnl_1lot": (round(float(near[near.qty == 1].pnl_usd.sum()), 2)
                         if len(near[near.qty == 1]) else None),
        })
    d = pd.DataFrame(rows)
    matched = d[d.n_trades > 0]
    print(f"{len(d)} captured presses · {len(matched)} matched to a trade within {WINDOW_S}s\n")
    if len(d):
        cols = ["ts", "kind", "pressed", "price", "atr", "pos_in_range", "vwap_stretch",
                "drift", "n_trades", "lots", "pnl_1lot", "pnl_all"]
        print(d[cols].to_string(index=False, max_colwidth=34))
    n = int((matched.pnl_1lot.notna()).sum()) if len(matched) else 0
    print(f"\n  labelled single-lot presses: {n}")
    if n < 30:
        print(f"  ⚠ {30-n} more needed before ANY analysis. Fitting below 30 is the 120th "
              f"calibration, and the previous 119 all lost.")
    else:
        print("  n>=30 — the question is now answerable: what separates his winners from his losers?")
    d.to_csv(f"{GB}/data/operator_reads_labelled.csv", index=False)
    print(f"  -> data/operator_reads_labelled.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
