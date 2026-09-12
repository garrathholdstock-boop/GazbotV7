#!/usr/bin/env python3
"""REV2 — price the Friday 2026-08-28 tournament week on each lot's OWN configured exit.

WHY THIS EXISTS. Two FRESH sections of the 08-28 report printed different values for the same
quantity — Part 1 §3 said the 14:45Z router arm was worth +$180.65 on its own exits, Part 2.6
§2/§2.1 said +$266.10 and called `grind_long_B` "unpriceable" — and the proofread asked which one
wins. Neither, exactly: both used a MODELLED entry ATR (23.5 and ~25.5 respectively) and the venue
tells us the real one for free. This script settles it from evidence and is saved so the number can
be re-derived rather than re-argued.

THE ENTRY ATR IS NOT A GUESS. The tournament places a NATIVE 1xATR stop with every fill, and the
placement is in the systemd journal as an `auxPrice`. Distance from the fill IS the entry ATR:

    stp-000001 29,612.00   capitulation_long_A  entry 29,638.75  ->  ATR 26.75
    stp-000002 29,611.50   capitulation_long_B  entry 29,638.25  ->  ATR 26.75
    stp-000003 29,714.00   grind_long_A         entry 29,738.25  ->  ATR 24.25
    stp-000004 29,714.00   grind_long_B         entry 29,738.25  ->  ATR 24.25
    stp-000005 29,703.00   abs_veto_long_A      entry 29,727.25  ->  ATR 24.25
    stp-000006 29,705.75   abs_veto_long_B      entry 29,730.00  ->  ATR 24.25

  journalctl -u gazbot7-tournament --since "2026-08-28 13:59" --until "2026-08-28 14:50" \
    | grep -oE "auxPrice=[0-9.]+.*orderRef='stp-[0-9]+'"

THE RULE FOR WHICH LEGS GET REPLAYED. A leg whose `exit_reason` is a MACHINE exit (TARGET,
CHANDELIER, STOP) already tells us what its own exit did, slippage and all — its own-exit value is
the booked value, full stop. Only a `MANUAL_CLAIM` truncates the exit stack, and only those legs are
replayed forward on the tick tape. Pricing a machine-exited leg at its theoretical trigger instead
of its real fill silently credits the gate with the slippage it actually paid (abs_veto_long_A:
1.0R trigger 29,751.50, real fill 29,750.50 — a dollar of it, on one lot).

METHOD. MNQ trade ticks from data/capture.db (08-28 is inside the 5-day rolling window), replayed
from the fill forward. Exit stack per data/exit_overrides.json and slot_strategy._lot_b:
  grind_long        A = scalp 2.5R                B = "wide"  = chandelier_lock 3.5 / 6.0R / 0.5
  abs_veto_long     A = scalp 1.0R                B = scalp 1.5R
  capitulation_long A = scalp 1.5R                B = "tight" = chandelier k1.5, min 0.5, tighten .75
Quiet-tape clip (atr_split 22) is OFF on every leg here — both entry ATRs are above 22.
Native 1xATR stop is the loss floor on every leg. $2.00/point, $1.50 per round trip.

HONEST LIMIT: a replay fills at the TRIGGERING TICK, with no slippage. The real machine exits paid
about a point on the one leg we can measure, so a replayed leg is worth ~$2 less than it prints.
That is smaller than any difference this script is being used to settle, and it runs one way.

  python3 scripts/rev2_arm_own_exits.py
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3

CAP = "/home/alphabot/gazbot7/data/capture.db"
DESK = "/home/alphabot/gazbot7/data/gazbot7.db"
VPP, FEE = 2.0, 1.50          # MNQ $2.00/point; $1.50 PER ROUND TRIP (not per side)

# gate -> (entry_atr from the native stop actually placed, stop_price actually placed)
ATR = {
    "capitulation_long_A": (26.75, 29612.00), "capitulation_long_B": (26.75, 29611.50),
    "grind_long_A":        (24.25, 29714.00), "grind_long_B":        (24.25, 29714.00),
    "abs_veto_long_A":     (24.25, 29703.00), "abs_veto_long_B":     (24.25, 29705.75),
}
# gate -> exit spec
EXITS = {
    "capitulation_long_A": ("scalp", 1.5),
    "capitulation_long_B": ("chandelier", dict(start_k=1.5, min_k=0.5, tighten=0.75)),
    "grind_long_A":        ("scalp", 2.5),
    "grind_long_B":        ("chandelier_lock", dict(start_k=3.5, lock_r=6.0, lock_k=0.5)),
    "abs_veto_long_A":     ("scalp", 1.0),
    "abs_veto_long_B":     ("scalp", 1.5),
}
HORIZON_H = 6.0               # replay ceiling; every leg below resolves well inside it


def ticks(t0_ms: int, t1_ms: int):
    c = sqlite3.connect(f"file:{CAP}?mode=ro", uri=True)
    try:
        return list(c.execute(
            "SELECT ts_ms, price FROM ticks WHERE symbol='MNQ' AND ts_ms BETWEEN ? AND ? "
            "ORDER BY ts_ms", (t0_ms, t1_ms)))
    finally:
        c.close()


def replay(gate: str, entry: float, opened_ms: int):
    """Forward-replay one LONG lot on its own exit stack. Returns (reason, px, ts_ms)."""
    atr, stop = ATR[gate]
    kind, cfg = EXITS[gate]
    tk = ticks(opened_ms, opened_ms + int(HORIZON_H * 3600 * 1000))
    peak = 0.0
    for ts, px in tk:
        if px <= stop:                                  # native 1xATR stop owns the downside
            return "STOP", stop, ts
        fav = px - entry
        peak = max(peak, fav)
        if kind == "scalp":
            if fav >= cfg * atr:
                return "TARGET", entry + cfg * atr, ts
        elif kind == "chandelier_lock":
            if peak > 0:
                k = cfg["start_k"] if peak / atr < cfg["lock_r"] else cfg["lock_k"]
                if fav > 0 and fav <= peak - k * atr:
                    return "CHANDELIER", px, ts
        elif kind == "chandelier":
            if peak > 0:
                k = max(cfg["min_k"], cfg["start_k"] - cfg["tighten"] * (peak / atr))
                if fav > 0 and fav <= peak - k * atr:
                    return "CHANDELIER", px, ts
    return "OPEN", tk[-1][1] if tk else entry, tk[-1][0] if tk else opened_ms


def main() -> int:
    c = sqlite3.connect(f"file:{DESK}?mode=ro", uri=True)
    rows = list(c.execute(
        "SELECT gate, entry_price, exit_price, opened_at, closed_at, pnl_usd, exit_reason "
        "FROM trades WHERE data_quality IS NULL AND date(closed_at)='2026-08-28' "
        "AND gate NOT LIKE 'day_rider%' ORDER BY opened_at"))
    c.close()

    out, booked_t, own_t = [], 0.0, 0.0
    for gate, ep, xp, oa, ca, pnl, reason in rows:
        opened = dt.datetime.fromisoformat(oa)
        atr, stop = ATR[gate]
        if reason == "MANUAL_CLAIM":
            r, px, ts = replay(gate, ep, int(opened.timestamp() * 1000))
            own = round((px - ep) * VPP - FEE, 2)
            when = dt.datetime.fromtimestamp(ts / 1000, dt.UTC).strftime("%H:%M:%S")
            note = f"{r} @ {px:,.2f} at {when}Z ({(ts/1000 - opened.timestamp())/60:.1f} min held)"
        else:
            own, note = pnl, f"machine exit ({reason}) @ {xp:,.2f} — booked IS its own exit"
        out.append(dict(gate=gate, entry=ep, atr=atr, stop=stop, booked=pnl, own=own,
                        delta=round(own - pnl, 2), reason=reason, note=note))
        booked_t += pnl
        own_t += own

    arm = [o for o in out if o["gate"].startswith(("grind_long", "abs_veto_long"))]
    claims = [o for o in out if o["reason"] == "MANUAL_CLAIM"]
    res = dict(
        legs=out,
        week=dict(booked=round(booked_t, 2), own=round(own_t, 2),
                  delta=round(own_t - booked_t, 2)),
        arm_1445=dict(booked=round(sum(o["booked"] for o in arm), 2),
                      own=round(sum(o["own"] for o in arm), 2),
                      delta=round(sum(o["delta"] for o in arm), 2)),
        claims=dict(n=len(claims), booked=round(sum(o["booked"] for o in claims), 2),
                    own=round(sum(o["own"] for o in claims), 2),
                    delta=round(sum(o["delta"] for o in claims), 2)),
    )
    print(json.dumps(res, indent=2))
    with open("/home/alphabot/gazbot7/reports/friday_v7/sections/rev2_arm_own_exits.json", "w") as fh:
        json.dump(res, fh, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
