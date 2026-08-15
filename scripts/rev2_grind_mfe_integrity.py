#!/usr/bin/env python3
"""REV2 Q8 — is the live grind_long book carrying mis-attributed fills?

Part 2 §6 records a grind trade that books +$159 live while its maximum favourable excursion on
the tape was 0.81R — about $23 a lot at ATR 14.1 — and calls it "not physically reachable",
pointing at the known `_stop_seq` fill mis-attribution mechanism. That is not a shadow-tool
problem. It is a live-P&L integrity problem, and it was parked as an instrument note.

This checks every grind_long trade in the same 26-trade window against its own physical ceiling:

    ceiling$ = rMFE(R) × ATR(pt) × $2.00/pt × qty − $1.50/RT × qty

MFE here is recomputed FULL-LIFE — the highest price the tape printed between the trade's own
recorded entry and its own recorded exit, off the 5-second tape. That is deliberately the most
GENEROUS possible ceiling: it ignores the 1-ATR stop entirely, so a trade that dipped through its
stop and rallied still gets credit for the rally. A booked P&L above THAT cannot have come from
this position's own price path under any exit rule. (The watch's own rMFE column, which truncates
at the stop touch, is carried alongside for reference.)

  PYTHONPATH=src ./.venv/bin/python scripts/rev2_grind_mfe_integrity.py
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3

import numpy as np

WATCH = "/home/alphabot/gazbot7/data/two_ratchet_shadow.json"
DESK = "/home/alphabot/gazbot7/data/gazbot7.db"
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/rev2_grind_mfe_integrity.json"
TAPE = "/home/alphabot/gazbot7/scratchpad/tape5s.npz"
VPP, FEE = 2.0, 1.50

_z = np.load(TAPE)
TS, HI = _z["ts"].astype(np.int64), _z["h"]


def full_life_mfe(entry: float, t0: int, t1: int) -> float | None:
    """Highest printed price between the recorded entry and the recorded exit (a LONG)."""
    a = int(np.searchsorted(TS, t0))
    b = int(np.searchsorted(TS, t1, side="right"))
    if b <= a:
        b = min(a + 1, len(TS))
    if a >= len(TS):
        return None
    return float(HI[a:b].max()) - entry


def main() -> None:
    w = json.load(open(WATCH))
    con = sqlite3.connect(f"file:{DESK}?mode=ro", uri=True)
    tr = {r[0][:19]: r for r in con.execute(
        "SELECT opened_at, id, gate, qty, entry_price, exit_price, pnl_usd, exit_reason, "
        "data_quality, closed_at FROM trades WHERE gate LIKE 'grind_long%' AND opened_at >= ?",
        (w["since"][:10],)).fetchall()}
    alltime = con.execute(
        "SELECT count(*), round(sum(pnl_usd),2) FROM trades WHERE gate LIKE 'grind_long%' "
        "AND data_quality IS NULL").fetchone()
    con.close()

    rows, fails = [], []
    for t in w["trades"]:
        k = t["opened_at"][:19]
        m = tr.get(k)
        qty = float(m[3]) if m else 1.0
        if not m:
            continue
        t0 = int(dt.datetime.fromisoformat(m[0]).timestamp())
        t1 = int(dt.datetime.fromisoformat(m[9]).timestamp())
        mfe_pt = full_life_mfe(float(m[4]), t0, t1)
        if mfe_pt is None:
            continue
        ceil = max(mfe_pt, 0.0) * VPP * qty - FEE * qty
        row = {"opened_at": t["opened_at"], "gate": m[2], "qty": qty,
               "atr": t["atr"], "rmfe_R": t["rmfe_R"], "exit_reason": t["exit_reason"],
               "mfe_pt_full_life": round(mfe_pt, 2),
               "live_usd": t["live_usd"], "physical_ceiling_usd": round(ceil, 2),
               "excess_usd": round(t["live_usd"] - ceil, 2),
               "quarantined": bool(m[8])}
        rows.append(row)
        if row["excess_usd"] > 0.01:
            fails.append(row)

    print(f"{len(rows)} live grind_long trades in the watch window "
          f"({w['since'][:10]} → {w['until'][:10]}), live net ${w['live_net']:,.2f}")
    print(f"\n{'opened':22s}{'qty':>4s}{'ATR':>7s}{'rMFE R':>7s}{'MFEpt':>8s}{'exit':14s}"
          f"{'booked $':>10s}{'ceiling $':>11s}{'excess':>10s}")
    for r in sorted(rows, key=lambda x: -x["excess_usd"]):
        flag = "  ← IMPOSSIBLE" if r["excess_usd"] > 0.01 else ""
        print(f"{r['opened_at'][:19]:22s}{r['qty']:4.0f}{r['atr']:7.1f}{r['rmfe_R']:7.2f}"
              f"{r['mfe_pt_full_life']:8.2f}{r['exit_reason']:14s}{r['live_usd']:10.1f}"
              f"{r['physical_ceiling_usd']:11.2f}{r['excess_usd']:+10.2f}{flag}")

    res = {"window": {"since": w["since"], "until": w["until"]}, "n": len(rows),
           "live_net": w["live_net"],
           "n_impossible": len(fails),
           "impossible_usd": round(sum(f["live_usd"] for f in fails), 2),
           "excess_usd": round(sum(f["excess_usd"] for f in fails), 2),
           "share_of_live_net": (round(100.0 * sum(f["live_usd"] for f in fails) / w["live_net"], 1)
                                 if w["live_net"] else None),
           "grind_alltime_n": alltime[0], "grind_alltime_usd": alltime[1],
           "trades": rows}
    print(f"\n{len(fails)} of {len(rows)} trades book MORE than their own tape could pay — "
          f"${res['impossible_usd']:,.2f} booked against a physical ceiling that is "
          f"${res['excess_usd']:,.2f} lower.")
    print(f"grind_long all-time on the clean ledger: n={alltime[0]}, ${alltime[1]:,.2f}")

    json.dump(res, open(OUT, "w"), indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
