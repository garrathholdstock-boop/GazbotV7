#!/usr/bin/env python3
"""LOSER / COUNTER-TREND ANALYSIS — Mon+Tue (operator 2026-07-28: "stop the little bad entries that
bleed us out; long gates on a down day; use the router to turn them off, be more brutal").

Tags every Mon(07-27)+Tue(07-28) Paris trade with the ROUTER's day-path regime at entry (what the
live router benches on), classifies aligned/counter/chop vs the gate's side, and simulates benching
policies. Question: how many losers does a 'bench counter-trend' router policy cut, and does it flip
the book green? Uses the module's OWN replay (no drift). $2/pt already in pnl_usd.

  PYTHONPATH=src .venv/bin/python scripts/loser_router_analysis.py
"""
from __future__ import annotations

import datetime as dt
import sys
from collections import defaultdict

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"
DB = "/home/alphabot/gazbot7/data/gazbot7.db"


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    trades = con.execute("""
        SELECT epoch(opened_at::TIMESTAMPTZ) t0, gate, side, pnl_usd,
               strftime(opened_at::TIMESTAMPTZ,'%m-%d') d
        FROM g.trades WHERE symbol='MNQ'
          AND opened_at::TIMESTAMPTZ >= TIMESTAMP '2026-07-26 22:00'
          AND opened_at::TIMESTAMPTZ <  TIMESTAMP '2026-07-28 22:00'
          AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE')
        ORDER BY opened_at""").fetchall()

    daycache: dict = {}

    def marks_for(t0):
        now = dt.datetime.fromtimestamp(t0, dt.UTC)
        s = dr.pnl.paris_day_start_utc(now)
        ds = int(dt.datetime.fromisoformat(s).timestamp() if isinstance(s, str) else s.timestamp())
        if ds not in daycache:
            rows = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl
                FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
                  AND bar_ts>={ds-1800} AND bar_ts<{ds+86400} GROUP BY 1 ORDER BY 1""").fetchall()
            mins = [r[0] for r in rows]
            daycache[ds] = dr.replay_marks(mins, [r[1] for r in rows], ds, ds+86400) if len(mins) > dr.WINDOW else []
        return daycache[ds]

    def regime_at(marks, t):
        st = "CHOP"
        for mt, s, _e, _n in marks:
            if mt <= t:
                st = s
            else:
                break
        return st

    def align(side, reg):
        if reg == "CHOP":
            return "chop"
        if (side == "LONG" and reg == "TREND_UP") or (side == "SHORT" and reg == "TREND_DOWN"):
            return "aligned"
        return "counter"

    cat = defaultdict(lambda: {"pnl": 0.0, "n": 0, "w": 0, "l": 0})     # alignment bucket
    gatecat = defaultdict(lambda: defaultdict(lambda: {"pnl": 0.0, "n": 0}))  # gate -> alignment
    rows_tagged = []
    for (t0, gate, side, pnl, d) in trades:
        reg = regime_at(marks_for(t0), t0)
        a = align(side, reg)
        cat[a]["pnl"] += pnl; cat[a]["n"] += 1; cat[a]["w"] += pnl > 0; cat[a]["l"] += pnl <= 0
        gatecat[gate][a]["pnl"] += pnl; gatecat[gate][a]["n"] += 1
        rows_tagged.append((gate, side, pnl, reg, a))

    total = sum(c["pnl"] for c in cat.values())
    ntot = sum(c["n"] for c in cat.values())
    print(f"\nMon+Tue: {ntot} trades, {total:+.0f} total  (router day-path regime @ entry)\n")
    print(f"{'alignment':>10}{'n':>5}{'P&L':>9}{'win%':>7}{'avg':>7}")
    for a in ("aligned", "chop", "counter"):
        c = cat[a]
        if c["n"]:
            print(f"{a:>10}{c['n']:>5}{c['pnl']:>+9.0f}{100*c['w']//max(c['n'],1):>6}%{c['pnl']/c['n']:>+7.1f}")

    print(f"\n── SIMULATED ROUTER POLICIES (P&L if we'd benched a bucket) ──")
    print(f"  current (all on)          : {total:+.0f}")
    print(f"  bench COUNTER-trend       : {total - cat['counter']['pnl']:+.0f}   (cut {cat['counter']['n']} tr, {cat['counter']['l']} losers, gave up {cat['counter']['w']} winners = {cat['counter']['pnl']:+.0f})")
    print(f"  bench counter + chop      : {cat['aligned']['pnl']:+.0f}   (aligned-only)")

    print(f"\n── WORST COUNTER-TREND OFFENDERS (gate × counter bucket) ──")
    off = []
    for gate, ac in gatecat.items():
        if ac["counter"]["n"]:
            off.append((gate, ac["counter"]["pnl"], ac["counter"]["n"], ac["aligned"]["pnl"], ac["aligned"]["n"]))
    for gate, cp, cn, ap, an in sorted(off, key=lambda x: x[1]):
        print(f"  {gate:18} counter {cp:>+7.0f}/{cn}tr   |  aligned {ap:>+7.0f}/{an}tr")

    print(f"\n── the operator's lever: LONG gates in a DOWN regime + SHORT gates in an UP regime ──")
    longs_down = sum(p for (gt, sd, p, rg, a) in rows_tagged if sd == "LONG" and rg == "TREND_DOWN")
    n_ld = sum(1 for (gt, sd, p, rg, a) in rows_tagged if sd == "LONG" and rg == "TREND_DOWN")
    shorts_up = sum(p for (gt, sd, p, rg, a) in rows_tagged if sd == "SHORT" and rg == "TREND_UP")
    n_su = sum(1 for (gt, sd, p, rg, a) in rows_tagged if sd == "SHORT" and rg == "TREND_UP")
    print(f"  LONG in TREND_DOWN : {longs_down:+.0f} over {n_ld} tr")
    print(f"  SHORT in TREND_UP  : {shorts_up:+.0f} over {n_su} tr")
    print(f"  → benching both = {total - longs_down - shorts_up:+.0f}  (vs {total:+.0f})")


if __name__ == "__main__":
    main()
