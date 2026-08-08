#!/usr/bin/env python3
"""REAL chandelier capture by ATR (operator 2026-07-29: "$180→$59 terrible; maybe 3 chandeliers,
6R only on extremely volatile ATR 40-50 days aka US-open hour, tight/medium otherwise").

Tests it on the ACTUAL realised CHANDELIER trades: reconstruct the true peak-favorable (from ticks
over the hold) and the entry ATR (from bars) for each, → how much of the peak we actually banked,
BUCKETED BY ATR. If the wide give-back only pays off at high ATR, the operator's ATR-tiered exit is
right.  PYTHONPATH=src .venv/bin/python scripts/chandelier_real_capture.py
"""
from __future__ import annotations
import datetime as dt, sys
from collections import namedtuple, defaultdict
import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr
from gazbot7.slot_strategy import SlotStrategy
Bar = namedtuple("Bar", "close")


def main():
    con = duckdb.connect(); con.execute("ATTACH 'data/capture.db' AS c (TYPE sqlite, READ_ONLY)"); con.execute("ATTACH 'data/gazbot7.db' AS g (TYPE sqlite, READ_ONLY)")
    rows = con.execute("""SELECT epoch(opened_at::TIMESTAMPTZ) t0, epoch(closed_at::TIMESTAMPTZ) t1,
        gate, side, entry_price, pnl_usd FROM g.trades
        WHERE exit_reason='CHANDELIER' AND symbol='MNQ' AND closed_at IS NOT NULL
        AND opened_at::TIMESTAMPTZ >= TIMESTAMP '2026-07-20' ORDER BY opened_at""").fetchall()
    daybars = {}
    def dayrows(t0):
        s = dr.pnl.paris_day_start_utc(dt.datetime.fromtimestamp(t0, dt.UTC)); ds = int(dt.datetime.fromisoformat(s).timestamp() if isinstance(s, str) else s.timestamp())
        if ds not in daybars:
            daybars[ds] = con.execute(f"SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl, max(high) hi, min(low) lo FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={ds-1800} AND bar_ts<{ds+86400} GROUP BY 1 ORDER BY 1").fetchall()
        return daybars[ds]

    band = defaultdict(lambda: {"peak": 0.0, "bank": 0.0, "n": 0, "capts": []})
    print(f"{'time':>9}{'gate':16}{'ATR':>5}{'mode':>6}{'peak$':>8}{'bank$':>8}{'capt%':>7}{'gaveback':>9}")
    for t0, t1, gate, side, ep, pnl in rows:
        rws = dayrows(t0)
        tk = con.execute(f"SELECT min(price) lo, max(price) hi FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={int(t0*1000)} AND ts_ms<={int(t1*1000)}").fetchone()
        if not tk or tk[0] is None: continue
        peak_fav = (ep - tk[0]) if side == "SHORT" else (tk[1] - ep)
        peak_usd = peak_fav * 2
        ctx = [r for r in rws if t0-1800 <= r[0] <= t0]; atr = sum(r[2]-r[3] for r in ctx)/len(ctx) if len(ctx) >= 6 else 0
        bars = [Bar(cl) for m, cl, hi, lo in rws if m <= t0]; mode = SlotStrategy._regime_mode(side, bars) if len(bars) >= 6 else "?"
        b = "40+" if atr >= 40 else "30-40" if atr >= 30 else "20-30" if atr >= 20 else "<20"
        capt = 100*pnl/peak_usd if peak_usd > 0 else 0
        band[b]["peak"] += peak_usd; band[b]["bank"] += pnl; band[b]["n"] += 1
        if peak_usd >= 60: band[b]["capts"].append(capt)
        tm = dt.datetime.fromtimestamp(t0, dt.UTC).strftime("%m-%d %H:%M")
        print(f"{tm:>11}{gate:16}{atr:>5.0f}{mode:>6}{peak_usd:>+8.0f}{pnl:>+8.0f}{capt:>6.0f}%{peak_usd-pnl:>+9.0f}")
    con.close()
    print(f"\n── by ATR band (capt% = of peak, on trades peaking >=$60) ──")
    print(f"{'ATR band':>10}{'n':>4}{'peak$':>9}{'bank$':>8}{'overall capt%':>15}{'avg capt%(big)':>16}")
    for b in ["<20", "20-30", "30-40", "40+"]:
        v = band[b]
        if v["n"]:
            oc = 100*v["bank"]/v["peak"] if v["peak"] > 0 else 0
            ac = sum(v["capts"])/len(v["capts"]) if v["capts"] else 0
            print(f"{b:>10}{v['n']:>4}{v['peak']:>+9.0f}{v['bank']:>+8.0f}{oc:>14.0f}%{ac:>15.0f}%")


if __name__ == "__main__":
    main()
