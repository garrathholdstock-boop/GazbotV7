#!/usr/bin/env python3
"""exhaustion_short REHAB — DELAY/CONFIRM veto backtest (operator 2026-07-28: "put a filter/delay
veto to stop the bad entries, keep the good ones. go deep, backtest thoroughly").

The gate fires SHORT on buy-absorption. A BAD entry = the buyers weren't spent, price keeps rising,
the short stops out. A CONFIRM VETO waits DELAY seconds after the signal and only enters if the
short hasn't gone adverse by > ADVERSE_TH (i.e. the absorption held) — the mirror of abs_veto. This
is FAITHFULLY backtestable: uses the 117 real exhaustion_rev SHORT shadow fires (live tick loop, so
firing matches live) + the reliable tick path. Native exit repriced (8pt stop / 12pt target / 120s).

Cost of delaying: worse/later entry, and price may already have hit target in the window (missed fast
winner) — the backtest charges both honestly. Sweeps DELAY × ADVERSE_TH; reports vetoed-vs-kept P&L,
whether the veto cuts LOSERS (good) or WINNERS (bad), and the net vs no-filter baseline.
Fees $1.50/RT, $2/pt.   PYTHONPATH=src .venv/bin/python scripts/exhaustion_delay_rehab.py
"""
from __future__ import annotations

import sys
import duckdb

CAP = "/home/alphabot/gazbot7/data/capture.db"
SH = "/home/alphabot/gazbot7/data/shadow.db"
VPP, FEE = 2.0, 1.50
STOP_PT, TARGET_PT, HOLD_S = 8.0, 12.0, 120

DELAYS = [5, 8, 10, 12, 15]          # seconds to wait for confirm
ADVERSE = [5.0, 6.0, 8.0, 10.0, 12.0]  # skip if price rose > this (pt) during the wait (short went adverse)


def reprice(entry_px, t0_ms, ticks):
    """Fixed 8/12/120s short exit from (entry_px, t0_ms) over ticks. Returns pnl_usd or None if no ticks."""
    stop, tgt = entry_px + STOP_PT, entry_px - TARGET_PT
    end = t0_ms + HOLD_S * 1000
    last = None
    for ts, px in ticks:
        if ts <= t0_ms:
            continue
        if ts > end:
            break
        last = px
        if px >= stop:
            return (entry_px - stop) * VPP - FEE
        if px <= tgt:
            return (entry_px - tgt) * VPP - FEE
    if last is None:
        return None
    return (entry_px - last) * VPP - FEE          # timed out at last in-window price


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{SH}' AS s (TYPE sqlite, READ_ONLY)")
    rows = con.execute("""
        SELECT CAST(entry_ts AS BIGINT) t0, entry_price, ceiling_pnl
        FROM s.shadow_trades WHERE strategy='exhaustion_rev' AND side='SHORT' AND exit_price IS NOT NULL
        ORDER BY entry_ts""").fetchall()

    # preload each fire's tick path (entry .. +300s covers max delay + 120s hold)
    fires = []
    for (t0, ep, booked) in rows:
        t0ms = t0 * 1000
        ticks = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
            AND ts_ms>={t0ms} AND ts_ms<={t0ms + 300*1000} ORDER BY ts_ms""").fetchall()
        if len(ticks) >= 2:
            fires.append((t0ms, ep, booked, ticks))
    con.close()

    # baseline: no filter, reprice fixed from the signal instant
    base = []
    for (t0ms, ep, booked, ticks) in fires:
        p = reprice(ep, t0ms, ticks)
        if p is not None:
            base.append(p)
    B = sum(base)
    print(f"\nexhaustion_short DELAY/CONFIRM rehab — {len(fires)} faithful shadow SHORT fires")
    print(f"BASELINE (no filter, fixed 8/12/120s reprice): {B:+.0f}  over {len(base)} tr, "
          f"{sum(1 for p in base if p>0)}W/{sum(1 for p in base if p<=0)}L\n")

    print(f"{'delay':>6}{'adv':>5}{'kept_n':>8}{'kept$':>8}{'veto_n':>8}{'veto$':>8}{'total':>8}{'vs base':>9}  quality")
    best = None
    for delay in DELAYS:
        for adv in ADVERSE:
            kept_pnl = kept_n = 0.0, 0
            kept_pnl = 0.0; kept_n = 0
            veto_pnl_base = 0.0; veto_n = 0; veto_losers = 0
            for (t0ms, ep, booked, ticks) in fires:
                win_end = t0ms + delay * 1000
                # worst adverse (highest price) during the wait
                hi = max((px for ts, px in ticks if t0ms < ts <= win_end), default=None)
                if hi is None:
                    # no ticks in wait window → treat as enter at signal (no info)
                    p = reprice(ep, t0ms, ticks)
                    if p is not None:
                        kept_pnl += p; kept_n += 1
                    continue
                adverse = hi - ep
                if adverse > adv:                       # short went adverse → VETO
                    pbase = reprice(ep, t0ms, ticks)    # what the un-vetoed trade would have made
                    if pbase is not None:
                        veto_pnl_base += pbase; veto_n += 1; veto_losers += pbase <= 0
                else:                                    # confirmed → enter at delayed price
                    dpx = [px for ts, px in ticks if t0ms < ts <= win_end][-1]
                    p = reprice(dpx, win_end, ticks)
                    if p is not None:
                        kept_pnl += p; kept_n += 1
            total = kept_pnl
            q = f"cut {veto_n}tr ({veto_losers}L/{veto_n-veto_losers}W worth {veto_pnl_base:+.0f})"
            flag = ""
            if best is None or total > best[0]:
                best = (total, delay, adv); flag = ""
            print(f"{delay:>6}{adv:>5.0f}{kept_n:>8}{kept_pnl:>+8.0f}{veto_n:>8}{veto_pnl_base:>+8.0f}{total:>+8.0f}{total-B:>+9.0f}  {q}")
    if best:
        print(f"\nBEST: delay {best[1]}s / adverse {best[2]:.0f}pt → {best[0]:+.0f} (vs baseline {B:+.0f}, +{best[0]-B:.0f})")
    print("\nRead: a GOOD filter's veto bucket is mostly LOSERS (worth a negative $) and total > baseline.")


if __name__ == "__main__":
    main()
