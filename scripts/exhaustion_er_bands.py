#!/usr/bin/env python3
"""exhaustion_short REALISED P&L by ER band + by day (operator 2026-07-28: "getting chopped in
low ER — shouldn't we turn it off?"). exhaustion_short currently has NO ER/ATR filter (the old
0.05 ceiling was dropped 07-25 as bug-derived). This buckets the ACTUAL realised trades by the
30-min ER at entry (desk buckets: <0.08 chop · 0.08–0.18 mixed · ≥0.18 trend) to see WHERE the
money sits and whether a low-ER veto is warranted + robust across days (not one lucky trend day).

  PYTHONPATH=src .venv/bin/python scripts/exhaustion_er_bands.py
"""
from __future__ import annotations

import datetime as dt
import sys
from collections import defaultdict, namedtuple

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr  # noqa: E402
from gazbot7.deciders import efficiency_ratio  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"
DB = "/home/alphabot/gazbot7/data/gazbot7.db"
Bar = namedtuple("Bar", "close")


def band(er):
    return "chop(<.08)" if er < 0.08 else ("mixed(.08-.18)" if er < 0.18 else "trend(>=.18)")


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    trades = con.execute("""
        SELECT epoch(opened_at::TIMESTAMPTZ) t0, strftime(opened_at::TIMESTAMPTZ,'%Y-%m-%d') d,
               pnl_usd, exit_reason
        FROM g.trades WHERE gate='exhaustion_short' AND symbol='MNQ'
          AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE') ORDER BY opened_at""").fetchall()

    daybars: dict = {}

    def bars_upto(t0):
        now = dt.datetime.fromtimestamp(t0, dt.UTC)
        s = dr.pnl.paris_day_start_utc(now)
        ds = int(dt.datetime.fromisoformat(s).timestamp() if isinstance(s, str) else s.timestamp())
        if ds not in daybars:
            daybars[ds] = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl
                FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
                  AND bar_ts>={ds-1800} AND bar_ts<{ds+86400} GROUP BY 1 ORDER BY 1""").fetchall()
        return [Bar(cl) for (m, cl) in daybars[ds] if m <= t0]

    by_band = defaultdict(lambda: {"pnl": 0.0, "n": 0, "w": 0})
    day_band = defaultdict(lambda: defaultdict(float))
    for (t0, d, pnl, xr) in trades:
        bars = bars_upto(t0)
        er = efficiency_ratio(bars) if len(bars) >= 6 else 1.0
        b = band(er)
        by_band[b]["pnl"] += pnl; by_band[b]["n"] += 1; by_band[b]["w"] += pnl > 0
        day_band[d][b] += pnl
    con.close()

    print(f"\nexhaustion_short — {len(trades)} realised trades, REALISED P&L by 30-min ER-at-entry band\n")
    print(f"{'band':>16}{'n':>5}{'win%':>7}{'P&L$':>9}{'avg$':>8}")
    order = ["chop(<.08)", "mixed(.08-.18)", "trend(>=.18)"]
    for b in order:
        v = by_band[b]
        if v["n"]:
            print(f"{b:>16}{v['n']:>5}{100*v['w']/v['n']:>6.0f}%{v['pnl']:>+9.0f}{v['pnl']/v['n']:>+8.1f}")
    low = by_band["chop(<.08)"]["pnl"] + by_band["mixed(.08-.18)"]["pnl"]
    hi = by_band["trend(>=.18)"]["pnl"]
    print(f"\n  low-ER (<0.18) total: {low:+.0f}   ·   trend-ER (>=0.18) total: {hi:+.0f}")

    print(f"\nper-day × band (robustness — is low-ER bad EVERY day or one?):")
    print(f"{'day':>12}{'chop':>9}{'mixed':>9}{'trend':>9}")
    for d in sorted(day_band):
        r = day_band[d]
        print(f"{d:>12}{r['chop(<.08)']:>+9.0f}{r['mixed(.08-.18)']:>+9.0f}{r['trend(>=.18)']:>+9.0f}")
    # how many days is low-ER (chop+mixed) net-negative?
    lowdays = [(day_band[d]['chop(<.08)']+day_band[d]['mixed(.08-.18)']) for d in sorted(day_band)]
    print(f"\n  low-ER net-negative on {sum(1 for x in lowdays if x<0)}/{len(lowdays)} days "
          f"(worst {min(lowdays):+.0f}, best {max(lowdays):+.0f})")


if __name__ == "__main__":
    main()
