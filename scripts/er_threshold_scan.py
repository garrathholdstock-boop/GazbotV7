#!/usr/bin/env python3
"""Per-gate ER threshold SCAN — derive each gate's cut from the P&L curve, don't pick a round number.

For each Features gate we sweep candidate ER cuts and report the net P&L kept:
  momentum  → FLOOR scan  (keep trades with er >= cut; it bleeds in chop)
  reversion → CEILING scan (keep trades with er <= cut; it bleeds in trend)
Two samples side by side: the 30-day V5 backtest (big, robust, but bar-close optimistic) and the
LIVE desk trades (real fills, thin). The peak of each curve is the data-chosen threshold — shown
with the trade count so you can see how much sample is behind it. DuckDB for the live join (the rule).

  PYTHONPATH=src python scripts/er_threshold_scan.py [--days 7]
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import pnl  # noqa: E402
from gazbot7.deciders import ER_CEIL, ER_FLOOR  # noqa: E402

import gate_backtest as gb  # noqa: E402  (scripts/ is on sys.path via cwd)

GRID = [0.05, 0.10, 0.15, 0.18, 0.20, 0.25, 0.30, 0.35, 0.40]
STYLE = {"grind_long": "momentum", "thrust_short": "momentum",
         "rgv_long": "reversion", "rgv_short": "reversion"}
DB = "/home/alphabot/gazbot7/data/gazbot7.db"
CAP = "/home/alphabot/gazbot7/data/capture.db"


def live_trades(days):
    """[(gate, pnl, er)] for live tournament trades over the window, ER ASOF-joined (DuckDB)."""
    _t0 = pnl.paris_day_start_utc(dt.datetime.now(dt.UTC))
    today0 = dt.datetime.fromisoformat(_t0).timestamp() if isinstance(_t0, str) else _t0.timestamp()
    t0 = today0 - (days - 1) * 86400
    con = duckdb.connect()
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"""
        CREATE TABLE erm AS
        WITH m1 AS (SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) mc FROM c.bars
                    WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={t0-1800} GROUP BY 1),
             st AS (SELECT m, mc, abs(mc-lag(mc) OVER (ORDER BY m)) step FROM m1)
        SELECT m, abs(mc-first_value(mc) OVER w)/NULLIF(SUM(step) OVER w,0) er
        FROM st WINDOW w AS (ORDER BY m ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)""")
    rows = con.execute(f"""
        WITH tr AS (SELECT gate, pnl_usd, epoch(opened_at::TIMESTAMPTZ) te FROM g.trades
                    WHERE symbol='MNQ' AND epoch(opened_at::TIMESTAMPTZ)>={t0}
                      AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE'))
        SELECT tr.gate, tr.pnl_usd, e.er FROM tr ASOF LEFT JOIN erm e ON e.m<=tr.te
        WHERE e.er IS NOT NULL""").fetchall()
    con.close()
    out = {}
    for gate, p, er in rows:
        out.setdefault(gate, []).append((p, er))
    return out


def scan(trades, style):
    """Return (natural_net, [(cut, n_kept, net)...], best_cut, best_net) for one gate's (pnl,er) list."""
    nat = sum(p for p, _ in trades)
    curve = []
    for c in GRID:
        kept = [p for p, er in trades if (er >= c if style == "momentum" else er <= c)]
        curve.append((c, len(kept), round(sum(kept))))
    best = max(curve, key=lambda x: x[2])
    return round(nat), curve, best


def show(title, by_gate):
    print(f"\n=== {title} ===")
    for gate, style in STYLE.items():
        ts = by_gate.get(gate, [])
        if not ts:
            print(f"{gate:14} {style:9} — no trades")
            continue
        nat, curve, best = scan(ts, style)
        kind = "floor≥" if style == "momentum" else "ceil≤"
        cells = "  ".join(f"{kind}{c:.2f}:${net:>+5}({n})" for c, n, net in curve)
        star = f"  ★ best {kind}{best[0]:.2f} → ${best[2]:+} ({best[1]}tr)"
        print(f"{gate:14} {style:9} nat=${nat:+5} | {cells}{star}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    a = ap.parse_args()

    days = gb.load_days("/home/alphabot/alphabot2/data/alphabot.db", "1m")
    bt = gb.backtest(days)          # {gate: [(pnl, er)]}
    print(f"30-day V5 backtest: {len(days)} days {min(days)}→{max(days)} (bar-close, OPTIMISTIC)")
    show("30-DAY BACKTEST (robust sample)", bt)
    show(f"LIVE desk (last {a.days} days — real fills, THIN)", live_trades(a.days))
    print(f"\ncurrently-wired thresholds: FLOOR {ER_FLOOR} · CEIL {ER_CEIL}")
    print("★ = P&L-maximising cut on that sample. Trust the 30-day peak where live is thin; where "
          "both agree, high confidence. Momentum floor / reversion ceiling.")


if __name__ == "__main__":
    main()
