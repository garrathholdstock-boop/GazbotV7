#!/usr/bin/env python3
"""REV2 Q1 — "bank one lot at a fixed points-onside, let the other run".

Part 1 §4 found this week's single biggest bucket of loss: $1,058 across 11 signals that were
up a median 39 points and still travelled the whole way to a full stop. Part 1 §11 named the
untested fix — bank Lot A at a fixed points-onside and leave Lot B on its existing exit — called
it "the first thing I would test next week", and then it never reached the plays card. This is
that test.

METHOD, and why each choice is the harsh one:
  * The rule is applied to EVERY signal, winners included (the §9.2 apply-to-all-lots honesty
    test). A rule scored only on the losers it rescues is the same mirage that killed the
    break-even stop: it "saved" $826 and actually cost $435.
  * 5-SECOND bars folded from capture.db trade ticks. The favourable extreme must be reached in
    a bar STRICTLY EARLIER than the bar Lot A actually exited in — so the bank can never be
    awarded on the same bar the trade died in, which is where a bar-replay steals money.
  * Lot A banks at exactly entry ∓ X points: X*$2.00 − $1.50 the round trip. No slippage
    modelled, so every number here is a CEILING.
  * Lot B is untouched — its real booked P&L, whatever it was.

ROBUSTNESS: leave-one-day-out on the five sessions, and a PAIRED RANDOM-TIME placebo. The
placebo keeps the count of banked lots and each banked trade's own duration-to-bank, but banks
at a RANDOM bar inside the trade's life instead of at the +X touch. If banking at a random
moment does as well, the edge is "get out earlier", not "get out at +X".

  PYTHONPATH=src ./.venv/bin/python scripts/rev2_bank_one_lot.py
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import random
import sqlite3
import statistics

import duckdb

DESK = "/home/alphabot/gazbot7/data/gazbot7.db"
CAP = "/home/alphabot/gazbot7/data/capture.db"
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/rev2_bank_one_lot.json"
VPP, FEE = 2.0, 1.50
BAR_MS = 5_000
# The proofreader asked for 8/10/12/15/20. 25/30/40 are added because the best cell of the
# asked-for grid sits on its top edge, and a best-on-the-boundary is the standing curve-fit tell:
# without the extra rungs there is no way to tell a plateau from a grid artefact.
THRESH = (8, 10, 12, 15, 20, 25, 30, 40)
DRAWS = 400
RNG = random.Random(20260815)
W = ("closed_at >= '2026-08-10' AND closed_at < '2026-08-15' AND data_quality IS NULL "
     "AND gate NOT LIKE 'day_rider%'")


def ms(s: str) -> int:
    return int(dt.datetime.fromisoformat(s).timestamp() * 1000)


def load_signals() -> list[dict]:
    con = sqlite3.connect(f"file:{DESK}?mode=ro", uri=True)
    rows = con.execute(
        f"SELECT id, side, entry_price, opened_at, closed_at, pnl_usd, exit_reason, gate "
        f"FROM trades WHERE {W} ORDER BY opened_at").fetchall()
    con.close()
    lots = [dict(id=r[0], side=r[1], entry=r[2], t0=ms(r[3]), t1=ms(r[4]), pnl=r[5],
                 why=r[6], gate=r[7], base=r[7][:-2] if r[7][-2:] in ("_A", "_B") else r[7],
                 leg=r[7][-1] if r[7][-2:] in ("_A", "_B") else "?",
                 date=r[3][:10]) for r in rows]

    # Pair A and B into signals: same base gate, same side, entries within 3 seconds. The live
    # desk stamps the two lots milliseconds apart, never identically, so an exact-timestamp join
    # silently returns 108 one-lot signals.
    sigs, used = [], set()
    for a in [x for x in lots if x["leg"] == "A"]:
        mate = None
        for b in [x for x in lots if x["leg"] == "B" and x["id"] not in used
                  and x["base"] == a["base"] and x["side"] == a["side"]
                  and abs(x["t0"] - a["t0"]) <= 3000]:
            mate = b
            break
        if mate:
            used.add(mate["id"])
        sigs.append({"A": a, "B": mate, "base": a["base"], "side": a["side"],
                     "date": a["date"], "t0": a["t0"],
                     "net": a["pnl"] + (mate["pnl"] if mate else 0.0)})
    for b in [x for x in lots if x["leg"] == "B" and x["id"] not in used]:
        sigs.append({"A": b, "B": None, "base": b["base"], "side": b["side"],
                     "date": b["date"], "t0": b["t0"], "net": b["pnl"]})
    return sorted(sigs, key=lambda s: s["t0"])


def bars() -> dict[int, tuple[float, float]]:
    """5-second bars (bar_start_ms -> (high, low)) folded from capture.db MNQ trade ticks."""
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    rows = con.execute(
        f"SELECT CAST(ts_ms/{BAR_MS} AS BIGINT)*{BAR_MS} AS b, max(price), min(price) "
        f"FROM c.ticks WHERE symbol='MNQ' GROUP BY 1 ORDER BY 1").fetchall()
    con.close()
    return {int(b): (float(h), float(lo)) for b, h, lo in rows}


def bank(sig: dict, B: dict, x_pt: float) -> tuple[float, int | None]:
    """Lot A's P&L under 'bank at +x_pt', and the bar it banked in (None = never banked)."""
    a = sig["A"]
    b0, bexit = (a["t0"] // BAR_MS) * BAR_MS, (a["t1"] // BAR_MS) * BAR_MS
    tgt = a["entry"] - x_pt if a["side"] == "SHORT" else a["entry"] + x_pt
    t = b0
    while t < bexit:                       # STRICTLY earlier than the exit bar
        hl = B.get(t)
        if hl:
            hit = hl[1] <= tgt if a["side"] == "SHORT" else hl[0] >= tgt
            if hit:
                return x_pt * VPP - FEE, t
        t += BAR_MS
    return a["pnl"], None


def placebo_bank(sig: dict, B: dict, rng: random.Random) -> float:
    """Bank Lot A at a RANDOM bar strictly inside the trade, at that bar's close-ish price."""
    a = sig["A"]
    b0, bexit = (a["t0"] // BAR_MS) * BAR_MS, (a["t1"] // BAR_MS) * BAR_MS
    cand = [t for t in range(b0, bexit, BAR_MS) if t in B]
    if not cand:
        return a["pnl"]
    hl = B[rng.choice(cand)]
    px = (hl[0] + hl[1]) / 2.0
    pts = (a["entry"] - px) if a["side"] == "SHORT" else (px - a["entry"])
    return pts * VPP - FEE


def lodo(per_day: dict[str, float]) -> float:
    tot = sum(per_day.values())
    return min(tot - v for v in per_day.values()) if per_day else 0.0


def main() -> None:
    S = load_signals()
    B = bars()
    live = sum(s["net"] for s in S)
    win = [s for s in S if s["net"] > 0]
    los = [s for s in S if s["net"] < 0]
    print(f"{len(S)} signals ({len(win)} winning, {len(los)} losing, "
          f"{len(S)-len(win)-len(los)} flat) — live net ${live:,.2f}")
    print(f"5s bars: {len(B):,}\n")

    res = {"n_signals": len(S), "n_win": len(win), "n_los": len(los),
           "live_net": round(live, 2), "cells": []}

    print(f"{'bank@':>6s} {'net$':>10s} {'delta$':>9s} {'banked':>7s} "
          f"{'onLOSERS':>9s} {'onWINNERS':>10s} {'winkept':>8s} {'LODOworst':>10s} "
          f"{'placebo p50':>12s} {'pctile':>7s}")
    for x in THRESH:
        tot, banked, day = 0.0, 0, collections.defaultdict(float)
        d_los, d_win, wk, deltas = 0.0, 0.0, 0, []
        for s in S:
            pa, at = bank(s, B, x)
            pb = s["B"]["pnl"] if s["B"] else 0.0
            new = pa + pb
            tot += new
            day[s["date"]] += new - s["net"]
            deltas.append(new - s["net"])
            if at is not None:
                banked += 1
            if s["net"] > 0:
                d_win += new - s["net"]
                if new > 0:
                    wk += 1
            elif s["net"] < 0:
                d_los += new - s["net"]
        # placebo: same population, bank Lot A at a random bar inside the trade
        draws = []
        for k in range(DRAWS):
            rng = random.Random(RNG.randrange(1 << 30))
            draws.append(sum((placebo_bank(s, B, rng) if bank(s, B, x)[1] is not None
                              else s["A"]["pnl"]) + (s["B"]["pnl"] if s["B"] else 0.0)
                             for s in S))
        draws.sort()
        pct = 100.0 * sum(1 for v in draws if v < tot) / len(draws)
        cell = {"bank_pt": x, "net": round(tot, 2), "delta": round(tot - live, 2),
                "banked": banked, "delta_losers": round(d_los, 2),
                "delta_winners": round(d_win, 2), "winners_kept": wk,
                "lodo_worst_delta": round(lodo(day), 2),
                "strip_best3_delta": round(sum(deltas) - sum(sorted(deltas, reverse=True)[:3]), 2),
                "per_day_delta": {k: round(v, 2) for k, v in sorted(day.items())},
                "placebo_median": round(statistics.median(draws), 2),
                "placebo_p95": round(draws[int(0.95 * len(draws))], 2),
                "placebo_pctile": round(pct, 1)}
        res["cells"].append(cell)
        print(f"{x:6d} {tot:10.2f} {tot-live:+9.2f} {banked:7d} {d_los:+9.2f} {d_win:+10.2f} "
              f"{wk:3d}/{len(win):<4d} {lodo(day):+10.2f} {statistics.median(draws):12.2f} "
              f"{pct:6.1f}%")

    # The 11 EXIT-fault signals §4 named: went 20pt+ our way and still stopped out.
    exitfault = []
    for s in S:
        if s["net"] >= 0:
            continue
        a = s["A"]
        b0, bexit = (a["t0"] // BAR_MS) * BAR_MS, (a["t1"] // BAR_MS) * BAR_MS
        best = 0.0
        t = b0
        while t <= bexit:
            hl = B.get(t)
            if hl:
                mv = (a["entry"] - hl[1]) if a["side"] == "SHORT" else (hl[0] - a["entry"])
                best = max(best, mv)
            t += BAR_MS
        if best >= 20:
            exitfault.append((s, best))
    print(f"\nthe EXIT-fault bucket: {len(exitfault)} losing signals reached 20pt+ onside, "
          f"live ${sum(s['net'] for s, _ in exitfault):,.2f}")
    res["exit_fault"] = {"n": len(exitfault),
                         "live_net": round(sum(s["net"] for s, _ in exitfault), 2),
                         "median_best_pt": round(statistics.median([b for _, b in exitfault]), 1)}
    for x in THRESH:
        sub = sum(bank(s, B, x)[0] + (s["B"]["pnl"] if s["B"] else 0.0) for s, _ in exitfault)
        res["exit_fault"][f"bank_{x}"] = round(sub, 2)
        print(f"   bank@{x:2d} → ${sub:,.2f}")

    json.dump(res, open(OUT, "w"), indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
