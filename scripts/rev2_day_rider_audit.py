#!/usr/bin/env python3
"""REV2 Q4 — how much of the day rider's $1,617.50 is the RIDER, and how much survives a
venue-verified accounting?

The rider produced $1,617.50 of the desk's $1,292.50 — take it out and the week is red — and the
report says plainly that four of its five trades have no venue execution record and two are
hand-reconstructed with an exit reason (CLOCK_FLAT_RECON) that no code in this repo emits. It
never asks the follow-on.

Three separate questions, answered separately because they have different answers:

  1. VENUE. For each leg: is there an execution record at all (entry_exec_id / exit_exec_id), and
     is there a fill in `fills` on that day at that price and size?
  2. TAPE. Does the recorded exit price exist on the tape at the recorded exit second? For the two
     CLOCK_FLAT_RECON rows this is the whole claim — nothing filled them, a script wrote them.
  3. THE RULE vs THE HANDS. Replay each entry under the rider's OWN deterministic exit — the
     ATR-scaled trail (arm 4xATR, trail 2xATR off peak, day_rider.trail_level) with the 20:40 UTC
     hard flat — and compare with what was booked. Two of the five exits are MANUAL_CLAIM, i.e.
     Garrath's hands, not the rider's rule. That is the difference between the rider's edge and
     its booked number.

  PYTHONPATH=src ./.venv/bin/python scripts/rev2_day_rider_audit.py
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3

import numpy as np

DESK = "/home/alphabot/gazbot7/data/gazbot7.db"
TAPE = "/home/alphabot/gazbot7/scratchpad/tape5s.npz"
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/rev2_day_rider_audit.json"
VPP, FEE_RT = 2.0, 1.50
ARM_ATR_MULT, TRAIL_ATR_MULT = 4.0, 2.0      # day_rider.py constants, read not guessed
FLAT_UTC = (20, 40)
CONTIG_S = 90

z = np.load(TAPE)
TS, H, L, C = z["ts"].astype(np.int64), z["h"], z["l"], z["c"]

_m: dict[int, list[float]] = {}
for i in range(len(TS)):
    k = int(TS[i]) // 60 * 60
    r = _m.get(k)
    if r is None:
        _m[k] = [float(H[i]), float(L[i]), float(C[i])]
    else:
        r[0] = max(r[0], float(H[i])); r[1] = min(r[1], float(L[i])); r[2] = float(C[i])
MT = np.array(sorted(_m))
MH = np.array([_m[t][0] for t in MT]); ML = np.array([_m[t][1] for t in MT])
MC = np.array([_m[t][2] for t in MT])


def atr14(ts_s: int) -> float:
    j = int(np.searchsorted(MT, ts_s, side="right"))
    trs = []
    for i in range(max(1, j - 15), j):
        hl = MH[i] - ML[i]
        trs.append(max(hl, abs(MH[i] - MC[i - 1]), abs(ML[i] - MC[i - 1]))
                   if MT[i] - MT[i - 1] <= CONTIG_S else hl)
    return float(sum(trs[-14:]) / len(trs[-14:])) if trs else 0.0


def replay(side: str, entry: float, t0: int, atr: float, qty: float):
    """The rider's own exit, on the 5-second tape: ATR trail then the 20:40 hard flat."""
    d = 1 if side == "LONG" else -1
    day = dt.datetime.fromtimestamp(t0, dt.UTC)
    flat = int(day.replace(hour=FLAT_UTC[0], minute=FLAT_UTC[1], second=0,
                           microsecond=0).timestamp())
    i0 = int(np.searchsorted(TS, t0))
    peak = entry
    for i in range(i0, len(TS)):
        t = int(TS[i])
        if t > flat:
            break
        peak = max(peak, float(H[i])) if d > 0 else min(peak, float(L[i]))
        ahead = d * (peak - entry)
        if atr > 0 and ahead >= ARM_ATR_MULT * atr:
            lvl = peak - d * TRAIL_ATR_MULT * atr
            hit = float(L[i]) <= lvl if d > 0 else float(H[i]) >= lvl
            if hit:
                return lvl, t, "TRAIL", d * (lvl - entry) * VPP * qty - FEE_RT * qty
    j = int(np.searchsorted(TS, flat, side="right")) - 1
    px = float(C[max(0, min(j, len(TS) - 1))])
    return px, flat, "CLOCK_FLAT", d * (px - entry) * VPP * qty - FEE_RT * qty


def tape_at(ts_s: int) -> float | None:
    j = int(np.searchsorted(TS, ts_s, side="right")) - 1
    if j < 0 or abs(int(TS[j]) - ts_s) > 120:
        return None
    return float(C[j])


def main() -> None:
    con = sqlite3.connect(f"file:{DESK}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT id, side, qty, entry_price, exit_price, opened_at, closed_at, pnl_usd, "
        "exit_reason, entry_exec_id, exit_exec_id FROM trades WHERE gate LIKE 'day_rider%' "
        "AND closed_at >= '2026-08-10' AND closed_at < '2026-08-15' AND data_quality IS NULL "
        "ORDER BY opened_at").fetchall()
    fills = con.execute(
        "SELECT date(exec_time), exec_time, side, qty, price FROM fills "
        "WHERE exec_time >= '2026-08-10' AND exec_time < '2026-08-15'").fetchall()
    con.close()

    out = {"legs": [], "totals": {}}
    booked = sum(r[7] for r in rows)
    print(f"{len(rows)} clean day-rider trades, booked ${booked:,.2f}\n")
    print(f"{'day':11s}{'side':6s}{'booked exit':14s}{'booked $':>10s}{'exec id?':>9s}"
          f"{'fill @px?':>10s}{'tape@exit':>10s}{'RULE exit':12s}{'RULE $':>9s}{'delta':>10s}")

    tot_rule = 0.0
    for tid, side, qty, ep, xp, t0s, t1s, pnl, why, eeid, xeid in rows:
        t0 = int(dt.datetime.fromisoformat(t0s).timestamp())
        t1 = int(dt.datetime.fromisoformat(t1s).timestamp())
        atr = atr14(t0)
        rpx, rts, rwhy, rpnl = replay(side, ep, t0, atr, qty)
        tot_rule += rpnl
        day = t0s[:10]
        near = [f for f in fills if f[0] == day and abs(f[4] - xp) < 0.26 and f[3] >= 2]
        tp = tape_at(t1)
        leg = {"id": tid, "day": day, "side": side, "qty": qty, "entry": ep, "exit": xp,
               "booked_reason": why, "booked_pnl": pnl,
               "has_exec_ids": bool(eeid or xeid),
               "matching_venue_fill": len(near),
               "tape_price_at_booked_exit": tp,
               "tape_vs_booked_exit_pt": None if tp is None else round(xp - tp, 2),
               "entry_atr": round(atr, 2),
               "rule_exit_px": round(rpx, 2), "rule_exit_reason": rwhy,
               "rule_exit_ts": dt.datetime.fromtimestamp(rts, dt.UTC).isoformat(),
               "rule_pnl": round(rpnl, 2), "delta_booked_minus_rule": round(pnl - rpnl, 2)}
        out["legs"].append(leg)
        print(f"{day:11s}{side:6s}{why:14s}{pnl:10.2f}{'no' if not (eeid or xeid) else 'yes':>9s}"
              f"{len(near):10d}{(f'{tp:.2f}' if tp else '—'):>10s}{rwhy:12s}{rpnl:9.2f}"
              f"{pnl-rpnl:+10.2f}")

    manual = [l for l in out["legs"] if l["booked_reason"] == "MANUAL_CLAIM"]
    recon = [l for l in out["legs"] if l["booked_reason"].endswith("_RECON")]
    coded = [l for l in out["legs"] if l not in manual and l not in recon]
    out["totals"] = {
        "booked": round(booked, 2),
        "rule_replay": round(tot_rule, 2),
        "booked_minus_rule": round(booked - tot_rule, 2),
        "manual_claim_n": len(manual), "manual_claim_usd": round(sum(l["booked_pnl"] for l in manual), 2),
        "reconstructed_n": len(recon), "reconstructed_usd": round(sum(l["booked_pnl"] for l in recon), 2),
        "code_emitted_n": len(coded), "code_emitted_usd": round(sum(l["booked_pnl"] for l in coded), 2),
        "legs_with_exec_id": sum(1 for l in out["legs"] if l["has_exec_ids"]),
        "legs_with_matching_fill": sum(1 for l in out["legs"] if l["matching_venue_fill"]),
    }
    t = out["totals"]
    print(f"\nBOOKED ${t['booked']:,.2f}   RULE-ONLY REPLAY ${t['rule_replay']:,.2f}   "
          f"the hands and the backfill are worth ${t['booked_minus_rule']:+,.2f}")
    print(f"  MANUAL_CLAIM      {t['manual_claim_n']} legs  ${t['manual_claim_usd']:,.2f}  "
          f"({100*t['manual_claim_usd']/booked:.0f}% of the booked total) — Garrath's hands, not the rule")
    print(f"  *_RECON backfill  {t['reconstructed_n']} legs  ${t['reconstructed_usd']:,.2f}  "
          f"({100*t['reconstructed_usd']/booked:.0f}%) — written by a script, no code path emits it")
    print(f"  code-emitted exit {t['code_emitted_n']} leg   ${t['code_emitted_usd']:,.2f}  "
          f"({100*t['code_emitted_usd']/booked:.0f}%)")
    print(f"  legs with an execution id: {t['legs_with_exec_id']}/5   "
          f"legs with a size-2 venue fill at the booked exit price: {t['legs_with_matching_fill']}/5")

    json.dump(out, open(OUT, "w"), indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
