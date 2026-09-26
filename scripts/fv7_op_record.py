#!/usr/bin/env python3
"""SECTION 1 — THE RECORD. Build the entry-level table of the operator's own trading.

GROUPING RULE: the rows in `trades` are scale-out EXITS. One DECISION = one (opened_at, side,
entry_price) group. Counting rows inflates n ~2.5x.
data_quality: EXCLUDE: rows are dropped entirely; BADFILL: entries are SHOWN and set aside from
every money total (their PRICE came from a broken fill).
entry_source: 'manual' = confirmed his press. NULL = UNKNOWN and stays unknown.
"""
from __future__ import annotations
import datetime as dt, json, sqlite3
import pandas as pd

GB = "/home/alphabot/gazbot7"
PT = 2.00  # MNQ $/point

def load() -> pd.DataFrame:
    c = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
    df = pd.read_sql("select * from trades where gate like 'day_rider%' order by opened_at", c)
    df["dq"] = df.data_quality.fillna("")
    df = df[~df.dq.str.startswith("EXCLUDE:")].copy()
    df["t0"] = pd.to_datetime(df.opened_at, format="mixed", utc=True)
    df["t1"] = pd.to_datetime(df.closed_at, format="mixed", utc=True)
    return df

RUNG = {"TARGET_100", "TARGET_200", "TRAIL"}
CLOCK = {"CLOCK_FLAT", "CLOCK_FLAT_RECON", "CLOCK_FLAT_BUG"}

def entries(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (t0, side, ep), g in df.groupby(["t0", "side", "entry_price"], sort=True):
        g = g.sort_values("t1")
        last = g.iloc[-1]
        reasons = list(g.exit_reason)
        rungs = [r for r in reasons if r in RUNG]
        if last.exit_reason in CLOCK:        cat = "clock"
        elif last.exit_reason == "CROSS_DESK_FLATTEN": cat = "crossdesk"
        elif last.exit_reason == "MANUAL_CLAIM": cat = "hand"
        elif last.exit_reason in RUNG:       cat = "rung"
        else:                                cat = "other"
        badfill = bool(g.dq.str.startswith("BADFILL:").any())
        lots = float(g.qty.sum())
        pnl = float(g.pnl_usd.sum())
        rows.append(dict(
            t0=t0, date=t0.strftime("%Y-%m-%d"), hourz=t0.hour,
            side=side, lots=lots, entry=float(ep),
            t1=last.t1, hold_min=(last.t1 - t0).total_seconds() / 60.0,
            pnl=pnl, pnl_pl=pnl / lots if lots else 0.0,
            n_rows=len(g), exit_cat=cat, last_reason=last.exit_reason,
            rungs=len(rungs), reasons="+".join(reasons),
            manual=bool((g.entry_source == "manual").any()),
            badfill=badfill,
            exit_px=float((g.exit_price * g.qty).sum() / g.qty.sum()),
            pts=(float((g.exit_price * g.qty).sum() / g.qty.sum()) - float(ep))
                * (1 if side == "LONG" else -1),
            fees=float(g.fees_usd.sum()),
        ))
    e = pd.DataFrame(rows).sort_values("t0").reset_index(drop=True)
    e["clean"] = ~e.badfill
    return e

def money(e: pd.DataFrame) -> pd.DataFrame:
    return e[e.clean]

if __name__ == "__main__":
    df = load(); e = entries(df)
    e.to_csv(f"{GB}/reports/friday_v7/op/entries.csv", index=False)
    print(f"rows(after EXCLUDE)={len(df)}  entries={len(e)}  badfill_entries={int(e.badfill.sum())}")
    print(f"confirmed manual entries={int(e.manual.sum())}  unknown-source={int((~e.manual).sum())}")
    m = money(e)
    print(f"clean entries={len(m)}  net=${m.pnl.sum():,.2f}  wins={int((m.pnl>0).sum())}")
    print(e.groupby("date").agg(n=("pnl","size"), net=("pnl","sum")).to_string())
