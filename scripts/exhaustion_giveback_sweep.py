#!/usr/bin/env python3
"""exhaustion_short DOLLAR give-back sweep (operator 2026-07-29: "when something gets up over
$200 we start closing in tight — we need $ thresholds. I don't want to watch huge give-backs").

Design: ride the wide lock-chandelier normally (small trades breathe), BUT once the position peaks
>= ARM dollars, arm a TIGHT dollar give-back — bank if it retraces GB dollars from the peak. That
protects the monsters (a +$292 can't melt to +$22) while leaving small winners on the wide trail.

FAITHFUL: reprices REAL exhaustion_short entries tick-by-tick through the ACTUAL deciders exits
(exit_chandelier_lock + 1-ATR native stop) with the $-armed give-back overlay; regime@entry via the
live direction_router (only ALIGNED-trend fires get the wide exit — the fix's scope). ATR from 5s
bars, $2/pt, $1.50/RT. Shows per-MONSTER banking so you can see exactly what each threshold banks.

  PYTHONPATH=src .venv/bin/python scripts/exhaustion_giveback_sweep.py
"""
from __future__ import annotations
import datetime as dt
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr  # noqa: E402
from gazbot7.deciders import Position, exit_chandelier_lock, exit_scalp  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"
DB = "/home/alphabot/gazbot7/data/gazbot7.db"
SH = "/home/alphabot/gazbot7/data/shadow.db"
VPP, FEE, MAX_HOLD_S = 2.0, 1.50, 90 * 60
ARMS = [150.0, 200.0, 250.0]      # arm the tight $ give-back once peak >= this
GBS = [50.0, 75.0, 100.0]         # then bank if it retraces this many $ from peak


def reprice_dollar(side, ep, atr, ticks, arm_usd, gb_usd, qty):
    """Wide lock-chandelier + 1-ATR loss stop, PLUS a $-armed tight give-back: once peak_usd>=arm,
    bank on a gb_usd retrace. Returns (exit_px, peak_pt)."""
    peak = 0.0
    for _ts, px in ticks:
        fav = (ep - px) if side == "SHORT" else (px - ep)
        if fav > peak:
            peak = fav
        pos = Position(side, ep, atr, peak)
        if exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0):        # 1-ATR loss floor
            return px, peak
        peak_usd = peak * VPP * qty
        fav_usd = fav * VPP * qty
        if peak_usd >= arm_usd and fav_usd > 0 and (peak_usd - fav_usd) >= gb_usd:  # $-armed tight bank
            return px, peak
        if exit_chandelier_lock(pos, px, start_k=3.5, lock_r=6.0, lock_k=0.5):      # else ride wide
            return px, peak
    return ticks[-1][1], peak


def reprice_live(side, ep, atr, ticks):
    """LIVE: wide lock-chandelier (no $ give-back) + 1-ATR loss stop."""
    peak = 0.0
    for _ts, px in ticks:
        fav = (ep - px) if side == "SHORT" else (px - ep)
        if fav > peak:
            peak = fav
        pos = Position(side, ep, atr, peak)
        if exit_chandelier_lock(pos, px, start_k=3.5, lock_r=6.0, lock_k=0.5) \
           or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0):
            return px, peak
    return ticks[-1][1], peak


def pnl(side, ep, xp, qty):
    pts = (ep - xp) if side == "SHORT" else (xp - ep)
    return pts * VPP * (qty or 1) - FEE


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{SH}' AS s (TYPE sqlite, READ_ONLY)")
    daycache: dict = {}

    def load_day(t0):
        ss = dr.pnl.paris_day_start_utc(dt.datetime.fromtimestamp(t0, dt.UTC))
        ds = dt.datetime.fromisoformat(ss).timestamp() if isinstance(ss, str) else ss.timestamp()
        if ds not in daycache:
            rows = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl, max(high) hi, min(low) lo
                FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={ds-1800} AND bar_ts<{ds+86400}
                GROUP BY 1 ORDER BY 1""").fetchall()
            marks = dr.replay_marks([r[0] for r in rows], [r[1] for r in rows],
                                    int(ds), int(ds+86400)) if len(rows) > dr.WINDOW else []
            daycache[ds] = (rows, marks)
        return daycache[ds]

    def build(fires):
        out = []
        for (side, ep, qty, t0, d) in fires:
            rows, marks = load_day(t0)
            ctx = [r for r in rows if t0 - 1800 <= r[0] <= t0]
            atr = sum(r[2]-r[3] for r in ctx) / len(ctx) if len(ctx) >= 6 else 0.0
            if atr <= 0:
                continue
            ticks = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
                AND ts_ms>={int(t0*1000)} AND ts_ms<={int((t0+MAX_HOLD_S)*1000)} ORDER BY ts_ms""").fetchall()
            if len(ticks) < 2:
                continue
            st = "CHOP"
            for mt, sm, _e, _n in marks:
                if mt <= t0:
                    st = sm
                else:
                    break
            aligned = (side == "SHORT" and st == "TREND_DOWN")
            if aligned:
                out.append((d, atr, ep, side, qty or 1, ticks[1:]))
        return out

    real = con.execute("""SELECT side, entry_price, qty, epoch(opened_at::TIMESTAMPTZ) t0,
           strftime(opened_at::TIMESTAMPTZ,'%m-%d') d FROM g.trades
        WHERE symbol='MNQ' AND gate='exhaustion_short' AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE')
        ORDER BY opened_at""").fetchall()
    shad = con.execute("""SELECT 'SHORT', entry_price, 1, CAST(entry_ts AS BIGINT), strftime(to_timestamp(CAST(entry_ts AS BIGINT)),'%m-%d')
        FROM s.shadow_trades WHERE strategy='exhaustion_rev' AND side='SHORT' AND exit_price IS NOT NULL ORDER BY entry_ts""").fetchall()

    for label, fires in [("REAL exhaustion_short", real), ("SHADOW exhaustion_rev (bigger sample)", shad)]:
        aligned = build(fires)
        print(f"\n{'='*94}\n{label}: {len(aligned)} ALIGNED-trend (wide-exit) fires")
        if not aligned:
            print("  none"); continue

        # LIVE baseline + per-config totals
        live_tot = sum(pnl(sd, ep, reprice_live(sd, ep, atr, tk)[0], q) for (d, atr, ep, sd, q, tk) in aligned)
        # peaks (in $) to identify monsters
        peaks = [(d, atr, ep, sd, q, tk, reprice_live(sd, ep, atr, tk)) for (d, atr, ep, sd, q, tk) in aligned]
        monsters = sorted([p for p in peaks if p[6][1]*VPP*p[4] >= 200], key=lambda x: -x[6][1]*VPP*x[4])

        print(f"\n  LIVE (wide chandelier, no $ give-back): banked ${live_tot:+.0f} over {len(aligned)} fires")
        print(f"  {len(monsters)} MONSTERS peaked >=$200. $-armed give-back sweep (arm / give-back):\n")
        print(f"  {'arm$':>5}/{'gb$':>4} | {'total$':>8} | {'vs LIVE':>8} | {'monster banked$':>15} | avg %peak kept")
        print("  " + "-"*74)
        best = None
        for arm in ARMS:
            for gb in GBS:
                tot = 0.0; kept = []; mons = 0.0
                for (d, atr, ep, sd, q, tk) in aligned:
                    xp, peak = reprice_dollar(sd, ep, atr, tk, arm, gb, q)
                    p = pnl(sd, ep, xp, q); tot += p
                    peak_usd = peak*VPP*q
                    if peak > 0:
                        banked_pt = max(0.0, (ep-xp) if sd == "SHORT" else (xp-ep))
                        kept.append(banked_pt/peak)
                        if peak_usd >= 200:
                            mons += p
                if best is None or tot > best[1]:
                    best = ((arm, gb), tot, mons)
                ak = 100*sum(kept)/len(kept) if kept else 0
                print(f"  {arm:>5.0f}/{gb:>4.0f} | {tot:>+8.0f} | {tot-live_tot:>+8.0f} | {mons:>+14.0f} | {ak:.0f}%")
        print("  " + "-"*74)
        (ba, bg), bt, bm = best
        print(f"  BEST total: arm ${ba:.0f}/gb ${bg:.0f} = ${bt:+.0f} (vs LIVE ${live_tot:+.0f}, {bt-live_tot:+.0f})")

        # PER-MONSTER detail — what each monster banks LIVE vs the operator's "$200 arm / $75 gb"
        print(f"\n  PER-MONSTER: what it banks LIVE (wide) vs arm$200/gb$75 (the 'close in tight over $200'):")
        print(f"  {'day':>5} {'peak$':>7} | {'LIVE banked$':>12} | {'arm200/gb75 banked$':>20}")
        for (d, atr, ep, sd, q, tk, (lxp, lpeak)) in monsters:
            peak_usd = lpeak*VPP*q
            live_b = pnl(sd, ep, lxp, q)
            gx, _ = reprice_dollar(sd, ep, atr, tk, 200.0, 75.0, q)
            new_b = pnl(sd, ep, gx, q)
            print(f"  {d:>5} {peak_usd:>+7.0f} | {live_b:>+12.0f} | {new_b:>+20.0f}")
    con.close()


if __name__ == "__main__":
    main()
