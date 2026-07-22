#!/usr/bin/env python3
"""Sweep live-desk trades per gate, bucketed by the efficiency ratio at entry (0.1 steps).

DuckDB-vectorized (the rule): ATTACH the live gazbot7.db (trades) + capture.db (5s bars) read-only,
build the 30-min ER off the 1-min closes, ASOF-join it onto each trade's opened_at, bucket ER into
0.1 bands, group by gate × band → N / win% / net. Shows where each gate made and LOST money by ER.

  PYTHONPATH=src python scripts/live_er_sweep.py              # today (Paris session)
  PYTHONPATH=src python scripts/live_er_sweep.py --days 7     # last 7 Paris days (the week)
"""

from __future__ import annotations

import argparse
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import pnl  # noqa: E402
from gazbot7.deciders import ER_CEIL, ER_FLOOR  # noqa: E402
import datetime as dt  # noqa: E402

DB = "/home/alphabot/gazbot7/data/gazbot7.db"
CAP = "/home/alphabot/gazbot7/data/capture.db"
CLEANUP = ("ADOPT_FLATTEN", "RECONCILED_CLOSE")
TOURNAMENT = set(ER_FLOOR) | set(ER_CEIL)   # the current 6 gates (drops retired bare-named ones)


def run(days=1, tournament_only=False):
    _t0 = pnl.paris_day_start_utc(dt.datetime.now(dt.UTC))              # today's Paris session start
    today0 = dt.datetime.fromisoformat(_t0).timestamp() if isinstance(_t0, str) else _t0.timestamp()
    t0 = today0 - (days - 1) * 86400                                    # back N-1 whole days
    con = duckdb.connect()
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")

    # 30-min ER off 1-min closes from the 5s capture (same ER as the desk uses)
    con.execute(f"""
        CREATE TABLE erm AS
        WITH m1 AS (
            SELECT (bar_ts - bar_ts % 60) AS m, arg_max(close, bar_ts) AS mc
            FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts >= {t0 - 1800} GROUP BY 1),
        st AS (SELECT m, mc, abs(mc - lag(mc) OVER (ORDER BY m)) AS step FROM m1)
        SELECT m, abs(mc - first_value(mc) OVER w) / NULLIF(SUM(step) OVER w, 0) AS er
        FROM st WINDOW w AS (ORDER BY m ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)""")

    ph = ",".join(f"'{x}'" for x in CLEANUP)
    df = con.execute(f"""
        WITH tr AS (
            SELECT gate, pnl_usd, epoch(opened_at::TIMESTAMPTZ) AS te
            FROM g.trades
            WHERE symbol='MNQ' AND epoch(opened_at::TIMESTAMPTZ) >= {t0}
              AND exit_reason NOT IN ({ph})),
        j AS (SELECT tr.*, e.er FROM tr ASOF LEFT JOIN erm e ON e.m <= tr.te)
        SELECT gate,
               CASE WHEN er IS NULL THEN NULL ELSE CAST(FLOOR(LEAST(er, 0.999)/0.1) AS INT) END AS band,
               COUNT(*) n, SUM(pnl_usd) net, SUM(CASE WHEN pnl_usd>0 THEN 1 ELSE 0 END) w
        FROM j GROUP BY gate, band ORDER BY gate, band NULLS LAST""").df()

    if tournament_only:
        df = df[df["gate"].isin(TOURNAMENT)]
    if df.empty:
        print("no live trades in that window.")
        return

    def lbl(b):
        return "n/a(notape)" if b is None or (isinstance(b, float) and b != b) else f"{b/10:.1f}-{b/10+0.1:.1f}"

    span = f"last {days} Paris day{'s' if days > 1 else ''}"
    d0 = dt.datetime.fromtimestamp(t0, dt.UTC).date()
    print(f"live trades by gate × ER-at-entry (0.1 bands) — {span} (from {d0}) — DuckDB\n")
    print(f"{'GATE':18} {'ER band':9} {'N':>3} {'win%':>5} {'NET':>9}")
    for gate in sorted(df["gate"].unique()):
        sub = df[df["gate"] == gate].sort_values("band", na_position="last")
        gn = int(sub["n"].sum())
        gnet = sub["net"].sum()
        gw = int(sub["w"].sum())
        for _, r in sub.iterrows():
            n = int(r["n"])
            b = r["band"]
            band = None if (b is None or (isinstance(b, float) and b != b)) else int(b)
            flag = "  <<< loss" if r["net"] < 0 else ""
            print(f"{gate:18} {lbl(band):10} {n:>3} {round(100*int(r['w'])/n):>4}% ${round(r['net']):>+8.0f}{flag}")
        print(f"{'  → '+gate+' TOTAL':18} {'':10} {gn:>3} {round(100*gw/gn) if gn else 0:>4}% ${round(gnet):>+8.0f}\n")

    tot = df["net"].sum()
    print(f"DESK TOTAL ({span}): ${round(tot):+.0f} over {int(df['n'].sum())} trades")
    print("(ER band = tape efficiency at entry: <0.08 chop · 0.08-0.18 mixed · >=0.18 trend)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1, help="how many Paris days back to sweep (default today only)")
    ap.add_argument("--tournament-only", action="store_true", help="drop retired bare-named gates; show only the current 6")
    a = ap.parse_args()
    run(a.days, a.tournament_only)
