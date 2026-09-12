#!/usr/bin/env python3
"""THE BENCH REPLAY — one instrument, one population, one number.

★ WHY THIS EXISTS (2026-08-30, Rev 3). The week's most-quoted policy number — "the bench
saved +$810.44 over 127 signals" — had NO section behind it. It was computed inside the
Part 1 phase, printed on the scorecard and on HOLD #1, and the per-impulse working was
never written to disk. Two published impulse counts disagreed (380 in Part 1 §6, 187/127
in the front matter) because they came from two DIFFERENT instruments that nobody named:

  * signal_journal (shadow.db)  — every fire the deciders logged, FIVE gates, durable on
    disk from 2026-08-04. This is what Part 1 §6 counted.
  * SUPPRESSED-OPEN log lines (systemd journal, tournament.py:306) — SIX gates including
    exhaustion_short, which never writes to signal_journal at all. This is what the $810
    came from. ⚠ IT IS A RING BUFFER. As of 2026-08-30 the oldest tournament entry systemd
    still holds is 2026-08-24 19:46Z, so Monday's lines are GONE and the 127-signal
    population can no longer be rebuilt. That is why this harness is keyed to the durable
    store and why the $810 is retired rather than reproduced.

WHAT IT DOES
  1. Pulls signal_journal for the report week (2026-08-24 00:00Z .. 2026-08-28 22:00Z).
  2. Collapses to distinct impulses on a 120s per-(gate,side) gap — the same DEDUP_GAP_S
     router_nightly.py uses, so the two are comparable.
  3. Splits ABOVE / BELOW each gate's own ATR floor (deciders.ATR_FLOOR). A benched impulse
     under the gate's floor was never going to trade, so blocking it cost nothing.
  4. Reprices every ABOVE-FLOOR impulse tick-by-tick on capture.db against the gate's OWN
     live Lot-A exit from data/exit_overrides.json, at stop widths 0.5x-1.5x.
     ★ THE SWEEP MOVES THE STOP ONLY. R is pinned to the CONFIGURED stop (stop_k x ATR at
     fire) and the target stays where the live desk puts it. Widening the target with the
     stop would test a different strategy at every cell, which is not a robustness test.
  5. Robustness: leave-one-day-out, strip-best-3, a 10,000-draw bootstrap, and a regime
     split read off the columns the gate itself recorded (er30 / net_30m_pt).

MONEY: MNQ $2.00/point, $1.50 per round trip, ONE lot (Lot A is base_size=1, flat sizing).
SIGN: pnl is what the blocked trade WOULD have made. BENCH SAVING = -pnl.

  PYTHONPATH=src .venv/bin/python scripts/rev3_bench_replay.py
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import random
import sqlite3
import sys
from collections import defaultdict

import duckdb

SHADOW = "/home/alphabot/gazbot7/data/shadow.db"
CAP = "/home/alphabot/gazbot7/data/capture.db"
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/rev3_bench_replay.json"

VPP, FEE = 2.0, 1.50
DEDUP_GAP_MS = 120_000
MAX_HOLD_S = 120 * 60          # cfg.max_hold_minutes
KS = (0.5, 0.75, 1.0, 1.25, 1.5)
SEED = 20260830

T0 = dt.datetime(2026, 8, 24, tzinfo=dt.UTC)
T1 = dt.datetime(2026, 8, 28, 22, 0, tzinfo=dt.UTC)

# deciders.ATR_FLOOR — only two gates carry one.
FLOOR = {"grind_long": 22.0, "capitulation_long": 10.0}

# Lot A, straight off data/exit_overrides.json + slot_strategy.scaleout_slots().
# (a_r, stop_k). Every gate here is exit="scalp" on Lot A.
LOT_A = {
    "grind_long":        (2.5, 1.0),
    "capitulation_long": (1.5, 1.0),
    "abs_veto_long":     (1.0, 1.0),
    "abs_veto_short":    (1.5, 1.0),
    "rgv_short":         (1.5, 1.0),
}


def impulses(con_sj):
    rows = con_sj.execute(
        "SELECT ts_ms,gate,side,price,atr_pt,er30,er15,net_30m_pt,range_30m_pt,suppressed_by "
        "FROM signal_journal WHERE ts_ms>=? AND ts_ms<? ORDER BY ts_ms",
        (int(T0.timestamp() * 1000), int(T1.timestamp() * 1000))).fetchall()
    last, out = {}, []
    for ts, g, s, px, atr, er30, er15, n30, r30, sb in rows:
        k = (g, s)
        if k in last and ts - last[k] <= DEDUP_GAP_MS:
            last[k] = ts
            continue
        last[k] = ts
        out.append(dict(ts=ts, gate=g, side=s, px=px, atr=atr or 0.0, er30=er30, er15=er15,
                        net30=n30, rng30=r30, suppressed_by=sb))
    return out


def regime(im):
    """The router's own language, read off what the gate recorded at fire time.

    direction_router declares a trend at ER30 >= 0.35 and holds it to 0.30 (the hysteresis
    band Part 2.5 §2.4 describes). Below 0.30 is CHOP. In a declared trend the question is
    whether the gate was pointing WITH the 30-minute move or against it."""
    er, n30 = im["er30"], im["net30"]
    if er is None or n30 is None:
        return "UNKNOWN"
    if er < 0.30:
        return "CHOP"
    aligned = (n30 > 0) if im["side"] == "LONG" else (n30 < 0)
    return "ALIGNED" if aligned else "COUNTER"


def reprice_all(TS, PX, im):
    """Tick-honest Lot-A P&L for one blocked impulse at EVERY stop width, in one tape pass.

    Returns {k: (pnl_usd, reason)}. The stop is checked BEFORE the target inside a tick, so a
    tick that breaches both is never awarded the target."""
    a_r, stop_k = LOT_A[im["gate"]]
    atr = im["atr"]
    if atr <= 0:
        return {k: (None, "no ATR at fire") for k in KS}
    r_cfg = stop_k * atr                 # R the live desk prices the TARGET in
    targ_pt = a_r * r_cfg                # fixed as k moves
    i0 = bisect.bisect_left(TS, im["ts"])
    i1 = bisect.bisect_right(TS, im["ts"] + MAX_HOLD_S * 1000)
    if i1 - i0 < 2:
        return {k: (None, "no tape") for k in KS}
    entry = PX[i0]
    lng = im["side"] == "LONG"
    sgn = 1.0 if lng else -1.0
    out, live = {}, {k: k * stop_k * atr for k in KS}
    for j in range(i0 + 1, i1):
        d = sgn * (PX[j] - entry)        # + favourable, - adverse
        for k, stop_pt in list(live.items()):
            if -d >= stop_pt:
                out[k] = (-stop_pt * VPP - FEE, "STOP")
                del live[k]
            elif d >= targ_pt:
                out[k] = (targ_pt * VPP - FEE, "TARGET")
                del live[k]
        if not live:
            return out
    mtm = sgn * (PX[i1 - 1] - entry)
    for k in live:
        out[k] = (mtm * VPP - FEE, "TIMEOUT")
    return out


def boot(vals, n=10_000):
    rnd = random.Random(SEED)
    tot = []
    for _ in range(n):
        tot.append(sum(rnd.choice(vals) for _ in vals))
    tot.sort()
    return tot[int(0.025 * n)], tot[int(0.975 * n)], sum(1 for t in tot if t >= 0) / n


def main():
    sj = sqlite3.connect(f"file:{SHADOW}?mode=ro", uri=True)
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")

    imps = impulses(sj)
    for im in imps:
        im["above"] = not (im["gate"] in FLOOR and im["atr"] < FLOOR[im["gate"]])
        im["regime"] = regime(im)
        im["day"] = dt.datetime.fromtimestamp(im["ts"] / 1000, dt.UTC).strftime("%a %d")
    above = [i for i in imps if i["above"]]

    print("loading the week's MNQ tape ...", file=sys.stderr)
    tape = con.execute("SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ' ORDER BY ts_ms").fetchall()
    TS = [t[0] for t in tape]
    PX = [t[1] for t in tape]
    print(f"  {len(TS):,} ticks", file=sys.stderr)

    for im in above:
        r = reprice_all(TS, PX, im)
        im["pnl"] = {k: r[k][0] for k in KS}
        im["reason"] = {k: r[k][1] for k in KS}

    priced = [i for i in above if i["pnl"][1.0] is not None]
    unpriced = [i for i in above if i["pnl"][1.0] is None]

    res = {
        "window": f"{T0.isoformat()} .. {T1.isoformat()}",
        "source": "shadow.db signal_journal (5 gates); capture.db ticks; exit_overrides.json Lot A",
        "seed": SEED,
        "n_fires": sum(1 for _ in imps),
        "n_impulses": len(imps),
        "n_above": len(above),
        "n_priced": len(priced),
        "unpriced": [{"gate": i["gate"], "ts": i["ts"], "why": i["reason"][1.0]} for i in unpriced],
    }

    # per-gate x k
    pg = defaultdict(lambda: defaultdict(float))
    pgn = defaultdict(int)
    for i in priced:
        pgn[i["gate"]] += 1
        for k in KS:
            pg[i["gate"]][k] += i["pnl"][k]
    res["per_gate"] = {g: {"n": pgn[g], "saving": {str(k): round(-pg[g][k], 2) for k in KS}} for g in pgn}
    res["desk"] = {str(k): round(-sum(i["pnl"][k] for i in priced), 2) for k in KS}

    # per-day and LODO at the live width
    pd_ = defaultdict(float)
    pdn = defaultdict(int)
    for i in priced:
        pd_[i["day"]] += i["pnl"][1.0]
        pdn[i["day"]] += 1
    tot = sum(i["pnl"][1.0] for i in priced)
    res["per_day"] = {d: {"n": pdn[d], "saving": round(-pd_[d], 2)} for d in sorted(pd_, key=lambda x: int(x.split()[1]))}
    res["lodo"] = {d: round(-(tot - pd_[d]), 2) for d in res["per_day"]}

    # strip-best-3 = drop the three impulses that contributed the most SAVING
    by_save = sorted(priced, key=lambda i: -(-i["pnl"][1.0]))
    res["strip_best_3"] = round(-(tot - sum(i["pnl"][1.0] for i in by_save[:3])), 2)
    res["top3"] = [{"gate": i["gate"], "day": i["day"], "saving": round(-i["pnl"][1.0], 2)} for i in by_save[:3]]

    lo, hi, pge = boot([-i["pnl"][1.0] for i in priced])
    res["bootstrap"] = {"lo": round(lo, 2), "hi": round(hi, 2), "p_ge_0": pge, "draws": 10000}

    # regime split
    rg = defaultdict(lambda: {"n": 0, "s": 0.0})
    for i in priced:
        rg[i["regime"]]["n"] += 1
        rg[i["regime"]]["s"] += -i["pnl"][1.0]
    res["regime"] = {r: {"n": v["n"], "saving": round(v["s"], 2),
                         "per_signal": round(v["s"] / v["n"], 2)} for r, v in rg.items()}

    # ★ LABEL-SHUFFLE PLACEBO on the CHOP-vs-ALIGNED per-signal gap. The published claim was
    # that benching is FREE in aligned trend and expensive in chop; if that is real, shuffling
    # the regime labels across the same 117 savings should rarely reproduce the gap.
    lab = [i["regime"] for i in priced]
    sav = [-i["pnl"][1.0] for i in priced]
    def gap(labels):
        c = [s for l, s in zip(labels, sav) if l == "CHOP"]
        a = [s for l, s in zip(labels, sav) if l == "ALIGNED"]
        if not c or not a:
            return 0.0
        return sum(c) / len(c) - sum(a) / len(a)
    obs = gap(lab)
    rnd = random.Random(SEED + 1)
    hits = 0
    for _ in range(10_000):
        sh = lab[:]
        rnd.shuffle(sh)
        if abs(gap(sh)) >= abs(obs):
            hits += 1
    res["regime_placebo"] = {"observed_gap_per_signal": round(obs, 2),
                             "p_two_sided": hits / 10_000, "draws": 10000}

    # concentration: how few days carry the saving
    day_s = sorted(((d, -v) for d, v in pd_.items()), key=lambda x: -x[1])
    pos = sum(v for _, v in day_s if v > 0)
    res["concentration"] = {"green_days": [(d, round(v, 2)) for d, v in day_s if v > 0],
                            "red_days": [(d, round(v, 2)) for d, v in day_s if v <= 0],
                            "pct_of_gross_positive_in_top2": round(
                                100 * sum(v for _, v in day_s[:2] if v > 0) / pos, 1) if pos else None}

    # exit-reason mix at the live width
    rm = defaultdict(int)
    for i in priced:
        rm[i["reason"][1.0]] += 1
    res["reason_mix"] = dict(rm)

    # below-floor population, for the record
    bel = defaultdict(int)
    for i in imps:
        if not i["above"]:
            bel[i["gate"]] += 1
    res["below_floor"] = dict(bel)

    res["per_impulse"] = [
        {"ts": i["ts"],
         "utc": dt.datetime.fromtimestamp(i["ts"] / 1000, dt.UTC).strftime("%Y-%m-%d %H:%M:%S"),
         "gate": i["gate"], "side": i["side"], "atr": round(i["atr"], 2),
         "er30": i["er30"], "regime": i["regime"],
         "saving": {str(k): (None if i["pnl"][k] is None else round(-i["pnl"][k], 2)) for k in KS},
         "reason": {str(k): i["reason"][k] for k in KS}}
        for i in above]

    with open(OUT, "w") as f:
        json.dump(res, f, indent=1)

    print(f"impulses {res['n_impulses']}  above-floor {res['n_above']}  priced {res['n_priced']}")
    print("desk bench saving by stop width:", res["desk"])
    for g, v in sorted(res["per_gate"].items()):
        print(f"  {g:20} n={v['n']:3}  " + "  ".join(f"{k}x {v['saving'][k]:>9.2f}" for k in map(str, KS)))
    print("per-day:", res["per_day"])
    print("LODO:", res["lodo"])
    print("strip-best-3:", res["strip_best_3"], res["top3"])
    print("bootstrap:", res["bootstrap"])
    print("regime:", res["regime"])
    print("reasons:", res["reason_mix"])
    print("->", OUT)


if __name__ == "__main__":
    sys.exit(main())
