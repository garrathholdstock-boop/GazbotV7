#!/usr/bin/env python3
"""Sweep EVERY shadow gate for its best ER gate — floor AND ceiling scanned, the curve picks.

The live tournament gates got per-gate ER thresholds; this does the same for the ~28 shadow
variants so the Saturday promotion feeder knows each candidate's favourable-condition gate too.
Shadow styles vary (and some are unlabelled), so we DON'T assume floor-vs-ceiling — we scan both
across the grid and report the better. Honest P&L = shadow_real.real_pnl (tick-repriced, filled).
DuckDB-vectorized (the rule): ATTACH shadow.db + capture.db, 30-min ER off the 1-min closes,
ASOF-join onto each trade's entry_ts.

  PYTHONPATH=src python scripts/shadow_er_sweep.py [--days 2]
"""

from __future__ import annotations

import argparse
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")

SHADOW = "/home/alphabot/gazbot7/data/shadow.db"
CAP = "/home/alphabot/gazbot7/data/capture.db"
GRID = [0.05, 0.10, 0.15, 0.18, 0.20, 0.25, 0.30, 0.35, 0.40]
MIN_KEEP = 20   # a cut is only trustworthy if it retains this many trades — else it's overfit noise
# name heuristic for a sanity style-guess (data still decides the actual gate)
REV = ("rg_", "capit", "exhaustion")


def style_guess(name):
    return "reversion" if name.startswith(REV) or "exhaust" in name else "momentum"


def best(trades, direction):
    """(cut, n_kept, net) maximising net for floor(er>=cut) or ceiling(er<=cut),
    among cuts that RETAIN >= MIN_KEEP trades (overfit guard). None if no cut qualifies."""
    cur = []
    for c in GRID:
        kept = [p for p, er in trades if (er >= c if direction == "floor" else er <= c)]
        if len(kept) >= MIN_KEEP:
            cur.append((c, len(kept), round(sum(kept))))
    return max(cur, key=lambda x: x[2]) if cur else None


def run(days=2):
    con = duckdb.connect()
    con.execute(f"ATTACH '{SHADOW}' AS s (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    t0 = con.execute("SELECT max(entry_ts) - ?*86400 FROM s.shadow_trades", [days]).fetchone()[0]
    con.execute(f"""
        CREATE TABLE erm AS
        WITH m1 AS (SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) mc FROM c.bars
                    WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={t0-1800} GROUP BY 1),
             st AS (SELECT m, mc, abs(mc-lag(mc) OVER (ORDER BY m)) step FROM m1)
        SELECT m, abs(mc-first_value(mc) OVER w)/NULLIF(SUM(step) OVER w,0) er
        FROM st WINDOW w AS (ORDER BY m ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)""")
    rows = con.execute(f"""
        WITH tr AS (
            SELECT st.strategy, sr.real_pnl, st.entry_ts te
            FROM s.shadow_trades st JOIN s.shadow_real sr ON sr.trade_id = st.id
            WHERE st.symbol='MNQ' AND sr.fill_status='filled' AND st.entry_ts >= {t0})
        SELECT tr.strategy, tr.real_pnl, e.er
        FROM tr ASOF LEFT JOIN erm e ON e.m <= tr.te
        WHERE e.er IS NOT NULL""").fetchall()
    con.close()

    by = {}
    for strat, p, er in rows:
        by.setdefault(strat, []).append((p, er))

    print(f"shadow gates — best ER gate over last {days} days (real_pnl, tick-honest) — DuckDB")
    print(f"(only cuts retaining >= {MIN_KEEP} trades qualify — overfit guard)\n")
    print(f"{'STRATEGY':24} {'style?':9} {'N':>3} {'NAT':>7}   {'best FLOOR≥':>15}   {'best CEIL≤':>15}   RECOMMENDATION")
    order = sorted(by.items(), key=lambda kv: -len(kv[1]))
    for strat, ts in order:
        n = len(ts)
        nat = round(sum(p for p, _ in ts))
        bf, bc = best(ts, "floor"), best(ts, "ceil")
        fcell = f"≥{bf[0]:.2f} ${bf[2]:+}({bf[1]})" if bf else "—"
        ccell = f"≤{bc[0]:.2f} ${bc[2]:+}({bc[1]})" if bc else "—"
        cands = [(k, b) for k, b in (("FLOOR", bf), ("CEIL", bc)) if b]
        win = max(cands, key=lambda kb: kb[1][2]) if cands else None
        if n < MIN_KEEP:
            rec = "⚠ too thin"
        elif win and win[1][2] > nat + 100:      # needs a real margin, not noise
            kind, b = win
            rec = f"{kind}{'≥' if kind == 'FLOOR' else '≤'}{b[0]:.2f} → ${b[2]:+} ({b[1]}tr, +${b[2]-nat})"
        else:
            rec = "no robust gate (natural ~best)"
        print(f"{strat:24} {style_guess(strat):9} {n:>3} ${nat:>+6} | {fcell:>15} | {ccell:>15} | {rec}")
    print(f"\n⚠ real_pnl = tick-repriced shadow fills (honest floor). Only cuts keeping >= {MIN_KEEP} trades "
          "shown as candidates; a gate flips to a recommendation only if it beats natural by >$100. A LEAD "
          "for the Saturday promotion feeder — ~5 days is still short of the 30-day live basis.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=2)
    run(ap.parse_args().days)
