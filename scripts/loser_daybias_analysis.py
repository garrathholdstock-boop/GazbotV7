#!/usr/bin/env python3
"""DAY-BIAS LOSER ANALYSIS — Mon+Tue (operator: "long gates on a down day; be more brutal leaving
them off"). The router's ER-trend test misses choppy-down days (low ER → never TREND_DOWN → longs
stay on and bleed). This tests a DIRECTIONAL-BIAS measure instead: is the day NET down at entry?
Bench gates whose side FIGHTS the day's net bias.

Per trade: day-net = close@entry − Paris-day-open close (the running day move); also trailing-30min
net (local lean). bias DOWN/UP/FLAT by ±BIAS_TH pt. A trade FIGHTS the bias if LONG-in-DOWN or
SHORT-in-UP. Simulate benching the fighters. $2/pt already in pnl_usd. ⚠ 2 days only — direction
lead, calibrate threshold forward.

  PYTHONPATH=src .venv/bin/python scripts/loser_daybias_analysis.py [BIAS_TH=40]
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
BIAS_TH = float(sys.argv[1]) if len(sys.argv) > 1 else 40.0


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

    def day_rows(t0):
        now = dt.datetime.fromtimestamp(t0, dt.UTC)
        s = dr.pnl.paris_day_start_utc(now)
        ds = int(dt.datetime.fromisoformat(s).timestamp() if isinstance(s, str) else s.timestamp())
        if ds not in daycache:
            daycache[ds] = (ds, con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl
                FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
                  AND bar_ts>={ds} AND bar_ts<{ds+86400} GROUP BY 1 ORDER BY 1""").fetchall())
        return daycache[ds]

    def bias_at(t0):
        ds, rows = day_rows(t0)
        upto = [cl for (m, cl) in rows if m <= t0]
        if len(upto) < 3:
            return "FLAT", 0.0, 0.0
        dopen = rows[0][1]
        daynet = upto[-1] - dopen
        # trailing 30-min local net
        loc = [cl for (m, cl) in rows if t0 - 1800 <= m <= t0]
        locnet = (loc[-1] - loc[0]) if len(loc) >= 2 else 0.0
        b = "DOWN" if daynet < -BIAS_TH else ("UP" if daynet > BIAS_TH else "FLAT")
        return b, daynet, locnet

    def fights(side, b):
        return (side == "LONG" and b == "DOWN") or (side == "SHORT" and b == "UP")

    cat = defaultdict(lambda: {"pnl": 0.0, "n": 0, "l": 0})
    gate_fight = defaultdict(lambda: {"pnl": 0.0, "n": 0})
    side_split = defaultdict(lambda: {"pnl": 0.0, "n": 0})
    fight_pnl = 0.0; fight_n = 0; fight_l = 0
    for (t0, gate, side, pnl, d) in trades:
        b, daynet, locnet = bias_at(t0)
        key = "FIGHTS-bias" if fights(side, b) else ("with/flat" if b != "FLAT" else "flat-day")
        cat[key]["pnl"] += pnl; cat[key]["n"] += 1; cat[key]["l"] += pnl <= 0
        side_split[side]["pnl"] += pnl; side_split[side]["n"] += 1
        if fights(side, b):
            fight_pnl += pnl; fight_n += 1; fight_l += pnl <= 0
            gate_fight[gate]["pnl"] += pnl; gate_fight[gate]["n"] += 1

    total = sum(c["pnl"] for c in cat.values()); ntot = sum(c["n"] for c in cat.values())
    print(f"\nMon+Tue: {ntot} trades, {total:+.0f}   |  day-bias threshold ±{BIAS_TH:.0f}pt\n")
    print("RAW side split:  " + "  ".join(f"{s} {v['pnl']:+.0f}/{v['n']}tr" for s, v in side_split.items()))
    print(f"\n{'bucket':>14}{'n':>5}{'P&L':>9}{'losers':>8}")
    for k in ("FIGHTS-bias", "with/flat", "flat-day"):
        c = cat[k]
        if c["n"]:
            print(f"{k:>14}{c['n']:>5}{c['pnl']:>+9.0f}{c['l']:>8}")
    print(f"\n  → BENCH the bias-fighters: {total - fight_pnl:+.0f}  (cut {fight_n} tr / {fight_l} losers, worth {fight_pnl:+.0f})")
    print(f"\n  which gates fight the day-bias (the ones to bench directionally):")
    for gate, v in sorted(gate_fight.items(), key=lambda x: x[1]["pnl"]):
        print(f"    {gate:18} {v['pnl']:>+7.0f} / {v['n']}tr")


if __name__ == "__main__":
    main()
