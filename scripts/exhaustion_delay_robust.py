#!/usr/bin/env python3
"""exhaustion_short delay-confirm ROBUSTNESS — per-day + LODO for a few configs (operator: backtest
thoroughly). Confirms the delay-veto edge isn't one lucky day. Same faithful 89 shadow SHORT fires,
native 8/12/120s reprice.  PYTHONPATH=src .venv/bin/python scripts/exhaustion_delay_robust.py
"""
from __future__ import annotations
import datetime as dt
import duckdb

CAP = "/home/alphabot/gazbot7/data/capture.db"; SH = "/home/alphabot/gazbot7/data/shadow.db"
VPP, FEE, STOP_PT, TARGET_PT, HOLD_S = 2.0, 1.50, 8.0, 12.0, 120
CONFIGS = [(5, 5.0), (5, 6.0), (5, 8.0), (10, 8.0)]


def reprice(entry_px, t0_ms, ticks):
    stop, tgt, end, last = entry_px + STOP_PT, entry_px - TARGET_PT, t0_ms + HOLD_S*1000, None
    for ts, px in ticks:
        if ts <= t0_ms: continue
        if ts > end: break
        last = px
        if px >= stop: return (entry_px - stop) * VPP - FEE
        if px <= tgt: return (entry_px - tgt) * VPP - FEE
    return None if last is None else (entry_px - last) * VPP - FEE


def main():
    con = duckdb.connect(); con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)"); con.execute(f"ATTACH '{SH}' AS s (TYPE sqlite, READ_ONLY)")
    rows = con.execute("""SELECT CAST(entry_ts AS BIGINT) t0, entry_price FROM s.shadow_trades
        WHERE strategy='exhaustion_rev' AND side='SHORT' AND exit_price IS NOT NULL ORDER BY entry_ts""").fetchall()
    fires = []
    for (t0, ep) in rows:
        t0ms = t0*1000
        ticks = con.execute(f"SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={t0ms} AND ts_ms<={t0ms+300000} ORDER BY ts_ms").fetchall()
        if len(ticks) >= 2:
            d = dt.datetime.fromtimestamp(t0, dt.UTC).strftime("%m-%d")
            fires.append((t0ms, ep, ticks, d))
    con.close()

    days = sorted(set(f[3] for f in fires))
    for (delay, adv) in CONFIGS:
        per_day_base = {d: 0.0 for d in days}; per_day_filt = {d: 0.0 for d in days}
        cut_total = kept_total = 0.0; cutL = cutW = 0
        for (t0ms, ep, ticks, d) in fires:
            pb = reprice(ep, t0ms, ticks)
            if pb is not None: per_day_base[d] += pb
            hi = max((px for ts, px in ticks if t0ms < ts <= t0ms+delay*1000), default=None)
            if hi is not None and hi - ep > adv:      # veto
                if pb is not None:
                    cut_total += pb; cutL += pb <= 0; cutW += pb > 0
                continue
            dw = [px for ts, px in ticks if t0ms < ts <= t0ms+delay*1000]
            pe = reprice(dw[-1] if dw else ep, t0ms+delay*1000 if dw else t0ms, ticks)
            if pe is not None: per_day_filt[d] += pe; kept_total += pe
        base_tot = sum(per_day_base.values()); filt_tot = sum(per_day_filt.values())
        bgd = sum(1 for d in days if per_day_filt[d] >= per_day_base[d])
        print(f"\n═══ delay {delay}s / adverse {adv:.0f}pt — base {base_tot:+.0f} → filtered {filt_tot:+.0f} (+{filt_tot-base_tot:.0f}), cut {cutL}L/{cutW}W")
        print(f"  filtered beats/equals base on {bgd}/{len(days)} days")
        print("  " + "  ".join(f"{d}:B{per_day_base[d]:+.0f}/F{per_day_filt[d]:+.0f}" for d in days))


if __name__ == "__main__":
    main()
