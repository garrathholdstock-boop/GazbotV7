#!/usr/bin/env python3
"""ER-FLOOR validation on the BIGGER faithful sample (operator 2026-07-28: "backtest the ER theory
further back"). Offline gate-replay 2 weeks back is UNRELIABLE — the exhaustion signal is episodic
(net>=400 in a 20s window is ~0.01% of windows), so a coarse-cadence walk misses ~all fires. The
faithful source is the exhaustion_rev SHADOW (224 trades, Jul 18-26): it runs the SAME live tick
footprint loop, so firing matches live. It uses the NATIVE 8/12 snap-back exit — so this tests
whether chop ENTRIES are bad on their own merits, independent of the adaptive exit.

Buckets the 224 shadow trades by 30-min ER at entry (chop<.08 / mixed.08-.18 / trend>=.18) + by day.
ER needs capture bars (from Jul 20 22:00) → pre-capture trades reported separately. P&L from stored
shadow prices ($2/pt, $1.50/RT). ⚠ shadow P&L is a FLOOR (live losses run 1.1-3.1x modeled) → a
chop bleed here is if anything WORSE live.

  PYTHONPATH=src .venv/bin/python scripts/shadow_er_validate.py
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
SH = "/home/alphabot/gazbot7/data/shadow.db"
VPP, FEE = 2.0, 1.50
Bar = namedtuple("Bar", "close")


def band(er):
    return "chop(<.08)" if er < 0.08 else ("mixed(.08-.18)" if er < 0.18 else "trend(>=.18)")


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{SH}' AS s (TYPE sqlite, READ_ONLY)")
    rows = con.execute("""
        SELECT CAST(entry_ts AS DOUBLE) t0, side, qty, entry_price, exit_price, exit_reason
        FROM s.shadow_trades WHERE strategy='exhaustion_rev' AND exit_price IS NOT NULL
        ORDER BY entry_ts""").fetchall()

    # capture bar coverage
    lo = con.execute("SELECT min(bar_ts) FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'").fetchone()[0]
    daybars: dict = {}

    def bars_upto(t0):
        now = dt.datetime.fromtimestamp(t0, dt.UTC)
        sday = dr.pnl.paris_day_start_utc(now)
        ds = int(dt.datetime.fromisoformat(sday).timestamp() if isinstance(sday, str) else sday.timestamp())
        if ds not in daybars:
            daybars[ds] = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl
                FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
                  AND bar_ts>={ds-1800} AND bar_ts<{ds+86400} GROUP BY 1 ORDER BY 1""").fetchall()
        return [Bar(cl) for (m, cl) in daybars[ds] if m <= t0]

    by_band = defaultdict(lambda: {"pnl": 0.0, "n": 0, "w": 0})
    day_band = defaultdict(lambda: defaultdict(float))
    no_bars = 0
    for (t0, side, qty, ep, xp, xr) in rows:
        q = qty or 1
        pl = ((ep - xp) if side == "SHORT" else (xp - ep)) * VPP * q - FEE * q
        if t0 < lo:
            no_bars += 1
            continue
        bars = bars_upto(t0)
        if len(bars) < 6:
            no_bars += 1
            continue
        b = band(efficiency_ratio(bars))
        by_band[b]["pnl"] += pl; by_band[b]["n"] += 1; by_band[b]["w"] += pl > 0
        d = dt.datetime.fromtimestamp(t0, dt.UTC).strftime("%Y-%m-%d")
        day_band[d][b] += pl
    con.close()

    tot = len(rows)
    used = sum(v["n"] for v in by_band.values())
    print(f"\nexhaustion_rev SHADOW — {tot} trades, {used} with ER (capture-covered), {no_bars} pre-capture\n")
    print(f"{'band':>16}{'n':>5}{'win%':>7}{'P&L$':>9}{'avg$':>8}")
    order = ["chop(<.08)", "mixed(.08-.18)", "trend(>=.18)"]
    for b in order:
        v = by_band[b]
        if v["n"]:
            print(f"{b:>16}{v['n']:>5}{100*v['w']/v['n']:>6.0f}%{v['pnl']:>+9.0f}{v['pnl']/v['n']:>+8.1f}")
    low = by_band["chop(<.08)"]["pnl"] + by_band["mixed(.08-.18)"]["pnl"]
    hi = by_band["trend(>=.18)"]["pnl"]
    print(f"\n  low-ER (<0.18): {low:+.0f}   ·   trend-ER (>=0.18): {hi:+.0f}   ·   chop(<.08) alone: {by_band['chop(<.08)']['pnl']:+.0f}")

    print(f"\nper-day x band (robustness):")
    print(f"{'day':>12}{'chop':>9}{'mixed':>9}{'trend':>9}")
    for d in sorted(day_band):
        r = day_band[d]
        print(f"{d:>12}{r['chop(<.08)']:>+9.0f}{r['mixed(.08-.18)']:>+9.0f}{r['trend(>=.18)']:>+9.0f}")
    chopdays = [day_band[d]['chop(<.08)'] for d in sorted(day_band) if day_band[d]['chop(<.08)'] != 0]
    print(f"\n  chop(<.08) net-negative on {sum(1 for x in chopdays if x<0)}/{len(chopdays)} days "
          f"(worst {min(chopdays):+.0f}, best {max(chopdays):+.0f})")


if __name__ == "__main__":
    main()
