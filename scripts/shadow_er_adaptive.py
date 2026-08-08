#!/usr/bin/env python3
"""DEFINITIVE ER-band P&L under the LIVE adaptive exit, on the 225-trade exhaustion shadow sample
(operator 2026-07-28). shadow_er_validate showed the ER-band ranking under the shadow's NATIVE 8/12
exit; this reprices the SAME 225 entries under the ACTUAL live exit (regime-3 selector: aligned→wide
lock-chand / counter→k2.0 / chop→k1.5, loss=native 1-ATR STP) — shadow stores entry_atr so the ride
reprice is FAITHFUL (no ATR reconstruction). Settles the floor level: is mixed (0.08-0.18) rescued
by the adaptive exit (keep floor 0.08) or a bleeder (raise to 0.18)?

NATIVE reprice is included as a sanity check — it should ~match the shadow's own booked P&L.
Fees $1.50/RT, $2/pt, 120min max hold.  PYTHONPATH=src .venv/bin/python scripts/shadow_er_adaptive.py
"""
from __future__ import annotations

import datetime as dt
import sys
from collections import defaultdict, namedtuple

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr  # noqa: E402
from gazbot7.deciders import (  # noqa: E402
    Position, exit_chandelier, exit_chandelier_lock, exit_fixed, exit_scalp,
)
from gazbot7.slot_strategy import SlotStrategy  # noqa: E402
from gazbot7.deciders import efficiency_ratio  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"
SH = "/home/alphabot/gazbot7/data/shadow.db"
VPP, FEE, MAX_HOLD_S = 2.0, 1.50, 120 * 60
Bar = namedtuple("Bar", "close")


def band(er):
    return "chop(<.08)" if er < 0.08 else ("mixed(.08-.18)" if er < 0.18 else "trend(>=.18)")


def replay(book, side, ep, atr, mode, ticks):
    peak = 0.0
    for ts, px in ticks:
        fav = (px - ep) if side == "LONG" else (ep - px)
        if fav > peak:
            peak = fav
        pos = Position(side, ep, atr, peak)
        if book == "NATIVE":
            r = exit_fixed(pos, px, stop_pt=8.0, target_pt=12.0)
        else:  # ADAPTIVE: profit exit by mode + native 1-ATR stop
            if mode == "wide":
                r = exit_chandelier_lock(pos, px, start_k=3.5, lock_r=6.0, lock_k=0.5)
            else:
                k = 2.0 if mode == "mid" else 1.5
                r = "CHANDELIER" if exit_chandelier(pos, px, start_k=k, min_k=0.5, tighten=0.75) else None
            r = r or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0)
        if r:
            return px
    return ticks[-1][1]


def pnl(side, ep, xp, q):
    return ((xp - ep) if side == "LONG" else (ep - xp)) * VPP * q - FEE * q


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{SH}' AS s (TYPE sqlite, READ_ONLY)")
    rows = con.execute("""
        SELECT CAST(entry_ts AS DOUBLE) t0, side, qty, entry_price, entry_atr
        FROM s.shadow_trades WHERE strategy='exhaustion_rev' AND exit_price IS NOT NULL
          AND entry_atr > 0 ORDER BY entry_ts""").fetchall()
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

    bb = defaultdict(lambda: {"nat": 0.0, "adp": 0.0, "n": 0, "wadp": 0})
    modes = defaultdict(lambda: defaultdict(int))
    by_mode = defaultdict(lambda: {"adp": 0.0, "nat": 0.0, "n": 0, "w": 0})  # alignment: wide/mid/tight
    skip = 0
    for (t0, side, qty, ep, atr) in rows:
        if t0 < lo:
            skip += 1
            continue
        bars = bars_upto(t0)
        if len(bars) < 6:
            skip += 1
            continue
        er = efficiency_ratio(bars)
        mode = SlotStrategy._regime_mode(side, bars)
        ticks = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
            AND ts_ms>{int(t0*1000)} AND ts_ms<={int((t0+MAX_HOLD_S)*1000)} ORDER BY ts_ms""").fetchall()
        if len(ticks) < 2:
            skip += 1
            continue
        q = qty or 1
        b = band(er)
        pn = pnl(side, ep, replay("NATIVE", side, ep, atr, mode, ticks), q)
        pa = pnl(side, ep, replay("ADAPTIVE", side, ep, atr, mode, ticks), q)
        bb[b]["nat"] += pn; bb[b]["adp"] += pa; bb[b]["n"] += 1; bb[b]["wadp"] += pa > 0
        modes[b][mode] += 1
        m = by_mode[mode]
        m["adp"] += pa; m["nat"] += pn; m["n"] += 1; m["w"] += pa > 0
    con.close()

    print(f"\nexhaustion_rev SHADOW repriced under LIVE adaptive exit — {sum(v['n'] for v in bb.values())} trades ({skip} skipped)\n")
    print(f"{'band':>16}{'n':>5}{'NATIVE$':>10}{'ADAPTIVE$':>11}{'adp win%':>10}   modes")
    order = ["chop(<.08)", "mixed(.08-.18)", "trend(>=.18)"]
    for b in order:
        v = bb[b]
        if v["n"]:
            m = " ".join(f"{k}:{n}" for k, n in sorted(modes[b].items()))
            print(f"{b:>16}{v['n']:>5}{v['nat']:>+10.0f}{v['adp']:>+11.0f}{100*v['wadp']/v['n']:>9.0f}%   {m}")
    print(f"\n  ADAPTIVE totals — chop:{bb['chop(<.08)']['adp']:+.0f}  mixed:{bb['mixed(.08-.18)']['adp']:+.0f}  trend:{bb['trend(>=.18)']['adp']:+.0f}")
    print(f"  FLOOR verdict: cut <0.08 → keep {bb['mixed(.08-.18)']['adp']+bb['trend(>=.18)']['adp']:+.0f} | cut <0.18 → keep {bb['trend(>=.18)']['adp']:+.0f} (trend only)")

    print(f"\n── by ALIGNMENT (the real lever?): wide=short-in-downtrend(aligned) · mid=short-in-uptrend(counter) · tight=chop ──")
    print(f"{'mode':>8}{'n':>5}{'ADAPTIVE$':>11}{'win%':>7}{'avg$':>8}")
    for mode in ("wide", "mid", "tight"):
        v = by_mode[mode]
        if v["n"]:
            print(f"{mode:>8}{v['n']:>5}{v['adp']:>+11.0f}{100*v['w']/v['n']:>6.0f}%{v['adp']/v['n']:>+8.1f}")
    print(f"\n  DIRECTIONAL verdict: cut counter(mid) → keep {by_mode['wide']['adp']+by_mode['tight']['adp']:+.0f} "
          f"(wide {by_mode['wide']['adp']:+.0f} + tight {by_mode['tight']['adp']:+.0f})")
    print(f"  sanity: NATIVE reprice total {sum(v['nat'] for v in bb.values()):+.0f} should ~match shadow's booked P&L (fixed 8/12)")


if __name__ == "__main__":
    main()
