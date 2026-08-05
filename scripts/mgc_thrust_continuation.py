#!/usr/bin/env python3
"""MGC THRUST-CONTINUATION — jump ON a run that has ALREADY started, and autopsy the losses first.

Operator, 2026-08-05: "for those big 300 runs. did you create a gate that would catch them? a momentum
or thrust continuation gate? if we can create something that will jump on them once theyve started...
each gate only needs to contribute a few hundred bucks a week when its turned on and then can stay off
the rest of the time. firstly try and isolate the losses. anything in common?"

★ THIS IS A REAL GAP AND THE OPERATOR IS RIGHT. What was tested before:
    census        — PREDICT a run at bar i, before anything has happened        (~2pp over constant)
    delay-confirm — wait 20-90 SECONDS, follow whichever way price ticked        (negative, all cells)
  Neither is a thrust gate. 30 seconds of movement is noise; a run that is already 2 ATR and 10
  minutes underway is STRUCTURE. Entering an established move has never been tested on gold.

★ AND THE SCORING FRAME CHANGES. Earlier studies judged total P&L across all tape, which punishes a
selective gate for being flat. A gate that fires 4x a week, makes $300, and sits benched otherwise is
a WIN. So the headline column here is $/WEEK WHILE ARMED, alongside days-green — not gross total.

★ WHAT WOULD MAKE THIS SUCCEED WHERE SIX ATTACKS FAILED. It needs no direction predictor (the thrust
picks the side) and no reversion (it rides continuation). The honest prior is still poor — Hurst on
this tape is 0.489, a random walk, which says a move underway carries no more information about the
next move than a coin — but that is a statement about AVERAGE tape, and a selective gate only claims
the tail. That is exactly what a sweep can settle.

★ COSTS ARE THE KNOWN KILLER ON GOLD. R is small: ATR ~1.6-2.9pt x $10 = $16-29, against MNQ's $30-50,
so a fixed $1.50/RT is ~2x as regressive here. Fee sensitivity is printed for every headline cell.

  PYTHONPATH=src .venv/bin/python scripts/mgc_thrust_continuation.py
  PYTHONPATH=src .venv/bin/python scripts/mgc_thrust_continuation.py --sweep
"""
from __future__ import annotations

import argparse
import datetime as dt
import random
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.lake import connect  # noqa: E402

VPP = 10.0
LOOK = 40          # max hold, minutes


def frame(con):
    return con.execute("""
        WITH s AS (SELECT ts_ms, (bid1p+ask1p)/2.0 AS mid FROM depth
                   WHERE bid1p IS NOT NULL AND ask1p IS NOT NULL AND ask1p > bid1p)
        SELECT CAST(ts_ms/60000 AS BIGINT)*60 AS m, max(mid) hi, min(mid) lo,
               arg_max(mid, ts_ms) cl, count(*) n
        FROM s GROUP BY 1 HAVING count(*) >= 20 ORDER BY 1""").fetchall()


class Tape:
    def __init__(self, rows):
        self.m = [r[0] for r in rows]
        self.hi = [float(r[1]) for r in rows]
        self.lo = [float(r[2]) for r in rows]
        self.cl = [float(r[3]) for r in rows]
        n = len(rows)
        self.atr = [0.0] * n
        for i in range(1, n):
            w0 = max(1, i - 60)
            trs = [max(self.hi[j] - self.lo[j], abs(self.hi[j] - self.cl[j - 1]),
                       abs(self.lo[j] - self.cl[j - 1])) for j in range(w0, i + 1)]
            self.atr[i] = sum(trs) / len(trs) if trs else 0.0

    def contiguous(self, i, k):
        return i + k < len(self.m) and self.m[i + k] - self.m[i] <= k * 60 * 1.5

    def er(self, i, w):
        """Efficiency ratio over the last w bars: net move / summed absolute move. High = clean run."""
        if i - w < 0:
            return 0.0
        net = abs(self.cl[i] - self.cl[i - w])
        path = sum(abs(self.cl[j] - self.cl[j - 1]) for j in range(i - w + 1, i + 1))
        return net / path if path > 0 else 0.0


def trades(T, *, thr_atr, win, er_min, atr_min=0.0, hours=None, k_stop=1.0, a_r=1.0,
           k_ch=3.0, fee=1.5, fade=False):
    """Enter in the direction of a thrust that has ALREADY happened over `win` minutes."""
    out, busy = [], 0
    n = len(T.m)
    for i in range(70, n - 2):
        if T.m[i] < busy or T.atr[i] <= 0 or T.atr[i] < atr_min:
            continue
        if not T.contiguous(i - win, win):
            continue
        move = T.cl[i] - T.cl[i - win]
        if abs(move) < thr_atr * T.atr[i]:
            continue
        if T.er(i, win) < er_min:
            continue
        if hours and dt.datetime.fromtimestamp(T.m[i], dt.UTC).hour not in hours:
            continue
        sgn = (1 if move > 0 else -1) * (-1 if fade else 1)
        entry = T.cl[i]
        r = k_stop * T.atr[i]
        stop = entry - sgn * r
        tgt = entry + sgn * a_r * r
        best = entry
        ea = eb = None
        end = min(i + 1 + LOOK, n)
        for j in range(i + 1, end):
            if not T.contiguous(i, j - i):
                break
            h_, l_ = T.hi[j], T.lo[j]
            if sgn > 0:
                best = max(best, h_)
            else:
                best = min(best, l_)
            trail = best - sgn * k_ch * T.atr[i]
            hit_stop = (l_ <= stop) if sgn > 0 else (h_ >= stop)
            if ea is None:
                if hit_stop:
                    ea = stop
                elif (h_ >= tgt) if sgn > 0 else (l_ <= tgt):
                    ea = tgt
            if eb is None:
                if hit_stop:
                    eb = stop
                elif sgn * (best - entry) > k_ch * T.atr[i] and \
                        ((l_ <= trail) if sgn > 0 else (h_ >= trail)):
                    eb = trail
            if ea is not None and eb is not None:
                break
        last = T.cl[min(i + LOOK, n - 1)]
        ea = last if ea is None else ea
        eb = last if eb is None else eb
        pa = sgn * (ea - entry) * VPP - fee
        pb = sgn * (eb - entry) * VPP - fee
        out.append({"ts": T.m[i], "i": i, "side": "L" if sgn > 0 else "S", "a": pa, "b": pb,
                    "pnl": pa + pb, "atr": T.atr[i], "er": T.er(i, win),
                    "thrust": abs(move) / T.atr[i],
                    "hour": dt.datetime.fromtimestamp(T.m[i], dt.UTC).hour,
                    "day": dt.datetime.fromtimestamp(T.m[i], dt.UTC).date().isoformat()})
        busy = T.m[i] + LOOK * 60
    return out


def summarise(tr, ndays):
    if not tr:
        return None
    tot = sum(t["pnl"] for t in tr)
    bd = defaultdict(float)
    for t in tr:
        bd[t["day"]] += t["pnl"]
    return {"n": len(tr), "tot": tot, "wk": tot / (ndays / 5.0),
            "win": 100 * sum(1 for t in tr if t["pnl"] > 0) / len(tr),
            "green": sum(1 for v in bd.values() if v > 0), "days": len(bd),
            "strip1": tot - max(t["pnl"] for t in tr),
            "stripday": tot - max(bd.values())}


def row(lab, s):
    if not s:
        print(f"{lab:<30}{'—':>6}")
        return
    print(f"{lab:<30}{s['n']:>5}{s['tot']:>9.0f}{s['wk']:>9.0f}{s['win']:>6.0f}%"
          f"{s['green']:>4}/{s['days']:<3}{s['strip1']:>9.0f}{s['stripday']:>10.0f}")


HDR = (f"{'config':<30}{'n':>5}{'total':>9}{'$/wk':>9}{'win':>7}{'green':>8}"
       f"{'strip-1':>9}{'strip-day':>10}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fee", type=float, default=1.50)
    ap.add_argument("--sweep", action="store_true")
    z = ap.parse_args()
    con = connect(symbol="MGC")
    T = Tape(frame(con))
    days = sorted({dt.datetime.fromtimestamp(x, dt.UTC).date() for x in T.m})
    ND = len(days)
    print(f"MGC {len(T.m):,} minutes, {ND} days ({days[0]}..{days[-1]}), price = book mid")
    print(f"fee ${z.fee:.2f}/RT/lot (ASSUMED — MGC fills record 0.00)\n")

    base = dict(thr_atr=1.5, win=10, er_min=0.5, fee=z.fee)

    # ── PART 1: the losses, first, as asked ──────────────────────────────────
    tr = trades(T, **base)
    print("PART 1 — LOSS AUTOPSY  (baseline: thrust>=1.5 ATR in 10 min, ER>=0.5)")
    W = [t for t in tr if t["pnl"] > 0]
    L = [t for t in tr if t["pnl"] <= 0]
    print(f"{'':<10}{'n':>5}{'avg P&L':>10}{'ATR':>8}{'ER':>8}{'thrust':>9}{'hour(med)':>11}")
    for nm, g in (("WINNERS", W), ("LOSERS", L)):
        if g:
            print(f"{nm:<10}{len(g):>5}{statistics.mean(t['pnl'] for t in g):>10.0f}"
                  f"{statistics.mean(t['atr'] for t in g):>8.2f}"
                  f"{statistics.mean(t['er'] for t in g):>8.2f}"
                  f"{statistics.mean(t['thrust'] for t in g):>9.2f}"
                  f"{statistics.median([t['hour'] for t in g]):>11.0f}")
    if W and L:
        print("\n  separation (losers vs winners, in SDs of the loser pool):")
        for k in ("atr", "er", "thrust"):
            a = statistics.mean(t[k] for t in W)
            b = statistics.mean(t[k] for t in L)
            s = statistics.pstdev([t[k] for t in L]) or 1e-9
            d = (a - b) / s
            flag = "  <-- SEPARATES" if abs(d) >= 0.30 else ""
            print(f"    {k:<8} winners {a:.2f}  losers {b:.2f}   d={d:+.2f}{flag}")
    bs = defaultdict(lambda: [0, 0.0])
    for t in tr:
        bs[t["side"]][0] += 1
        bs[t["side"]][1] += t["pnl"]
    print("\n  by side: " + "  ".join(f"{k}: n={v[0]} ${v[1]:.0f}" for k, v in sorted(bs.items())))
    bh = defaultdict(lambda: [0, 0.0])
    for t in tr:
        bh[t["hour"]][0] += 1
        bh[t["hour"]][1] += t["pnl"]
    worst = sorted(bh.items(), key=lambda kv: kv[1][1])[:4]
    print("  worst hours: " + "  ".join(f"{h:02d}:00 n={v[0]} ${v[1]:.0f}" for h, v in worst))
    print("  ★ If losers and winners share every feature, there is nothing to filter ON and")
    print("    selectivity cannot be built — that is the question this part answers.\n")

    if z.sweep:
        print("PART 2 — SWEEP  (B lot = chandelier; $/wk assumes armed only on firing days)")
        print(HDR)
        cells = []
        for thr in (1.0, 1.5, 2.0, 2.5):
            for win in (5, 10, 20):
                for er in (0.3, 0.5, 0.7):
                    t = trades(T, thr_atr=thr, win=win, er_min=er, fee=z.fee)
                    s = summarise(t, ND)
                    lab = f"thr{thr} win{win}m ER{er}"
                    row(lab, s)
                    if s:
                        cells.append((s["tot"], lab, s, dict(thr_atr=thr, win=win, er_min=er)))
        pos = [c for c in cells if c[0] > 0]
        print(f"\n★ {len(pos)} of {len(cells)} cells positive")
        if cells:
            cells.sort(reverse=True)
            tot, lab, s, kw = cells[0]
            print(f"★ best: {lab}  ${tot:.0f}  ${s['wk']:.0f}/wk  green {s['green']}/{s['days']}  "
                  f"strip-day ${s['stripday']:.0f}")
            print("  ★ 36 cells were tried — the best is a SELECTION. Robustness below.")
            bt = trades(T, fee=z.fee, **kw)
            full = trades(T, thr_atr=1.0, win=10, er_min=0.3, fee=z.fee)
            if len(bt) >= 8 and len(full) > len(bt):
                rnd = random.Random(20260805)
                d = [sum(x["pnl"] for x in rnd.sample(full, len(bt))) for _ in range(3000)]
                mu, sd = statistics.mean(d), statistics.pstdev(d)
                pct = 100.0 * sum(1 for x in d if x >= tot) / len(d)
                print(f"  placebo: random {len(bt)}-of-{len(full)} -> ${mu:.0f} (sd ${sd:.0f}); "
                      f"real ${tot:.0f} = {(tot-mu)/sd if sd else 0:+.2f} sd, beaten by {pct:.0f}%")
            for fee in (3.0, 5.0):
                row(f"  same cell @ ${fee:.2f} fee", summarise(trades(T, fee=fee, **kw), ND))
        return 0

    print("PART 2 — HEADLINE CONFIGS")
    print(HDR)
    for thr in (1.0, 1.5, 2.0):
        row(f"thrust>={thr} ATR / 10m ER0.5",
            summarise(trades(T, thr_atr=thr, win=10, er_min=0.5, fee=z.fee), ND))
    print("\nCONTROLS")
    row("FADE the thrust instead", summarise(trades(T, fade=True, **base), ND))
    row("no ER filter", summarise(trades(T, thr_atr=1.5, win=10, er_min=0.0, fee=z.fee), ND))
    print("\nrun with --sweep for the full grid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
