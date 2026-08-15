"""EXHAUSTION_SHORT REHAB — EVERY candidate filter, one battery, nothing hidden.

The operator's standing rule: report every attempt including the nulls, each by name with its
stats and a one-line cause of death. So every idea that was tried on this gate — the four he
commissioned, plus the two the regime split threw up — goes through the identical battery:

  net / $-per-signal / win%          what it made
  winners cut + their $              the keep-the-winners test; a filter that "wins" by
                                     dropping the target winners is a FAKE win
  placebo percentile                 vs 4,000 random removals of the SAME number of signals.
                                     Below ~95 means a coin-flip cut of that size does as well.
  LODO worst fold                    the filter's $ delta with its best day removed
  strip-best-3                       the filter's $ delta with the 3 biggest winners removed

A candidate has to clear the placebo FIRST. Nothing that fails it is worth reading the rest of
the row for, and none of the rest of the row can rescue it.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import random
import statistics

IN = "reports/friday_v7/sections/exh_signals.json"
OUT = "reports/friday_v7/sections/exh_candidates.json"
ANCHOR = {"single": "-3", "AB": "-5"}
DRAWS = 4000
RNG = random.Random(20260815)


def load():
    S = json.load(open(IN))["signals"]
    for s in S:
        a = s["net_by_anchor"].get(ANCHOR[s["era"]])
        s["net_abs"] = abs(a["net"]) if a else None
        s["stopped"] = "STOP" in s["reasons"]
        s["hour"] = dt.datetime.fromtimestamp(s["ts_ms"] / 1000, dt.UTC).hour
    return sorted(S, key=lambda x: x["ts_ms"])


# ── the candidate filters, each a pure function pool -> kept ─────────────────────────
def f_cooldown(m):
    def g(P):
        keep, until = [], -1
        for s in P:
            if s["ts_ms"] < until:
                continue
            keep.append(s)
            if s["stopped"]:
                until = s["closed_ms"] + m * 60_000
        return keep
    return g


def f_streak(n, w):
    def g(P):
        keep, run, until, dead = [], 0, -1, None
        for s in P:
            if dead == s["date"] or s["ts_ms"] < until:
                continue
            keep.append(s)
            run = run + 1 if s["stopped"] else 0
            if run >= n:
                if w is None:
                    dead = s["date"]
                else:
                    until = s["closed_ms"] + w * 60_000
                run = 0
        return keep
    return g


def f_netmin(t):
    return lambda P: [s for s in P if s["net_abs"] is None or s["net_abs"] >= t]


def f_atr_ceil(t):
    return lambda P: [s for s in P if not s["atr"] or s["atr"] < t]


def f_atr_floor(t):
    return lambda P: [s for s in P if not s["atr"] or s["atr"] >= t]


def f_us_only(P):
    return [s for s in P if s["hour"] >= 13]


def f_none(P):
    return list(P)


# ── the battery ──────────────────────────────────────────────────────────────────────
def placebo(P, k, actual):
    if k <= 0 or k >= len(P):
        return None
    tot = sum(s["pnl"] for s in P)
    p = [s["pnl"] for s in P]
    idx = list(range(len(P)))
    nets = sorted(tot - sum(p[i] for i in RNG.sample(idx, k)) for _ in range(DRAWS))
    return {"mean": round(statistics.mean(nets), 2),
            "p95": round(nets[int(0.95 * len(nets))], 2),
            "pctile": round(100.0 * sum(1 for x in nets if x < actual) / len(nets), 1)}


def lodo_worst(P, fn):
    out = []
    for d in sorted({s["date"] for s in P}):
        sub = [s for s in P if s["date"] != d]
        out.append(sum(s["pnl"] for s in fn(sub)) - sum(s["pnl"] for s in sub))
    return round(min(out), 2) if out else 0.0


def strip3(P, fn):
    best = set(id(s) for s in sorted(P, key=lambda s: -s["pnl"])[:3])
    sub = [s for s in P if id(s) not in best]
    return round(sum(s["pnl"] for s in fn(sub)) - sum(s["pnl"] for s in sub), 2)


def battery(P, fn, label, why):
    keep = fn(P)
    kid = set(id(s) for s in keep)
    cut = [s for s in P if id(s) not in kid]
    net = round(sum(s["pnl"] for s in keep), 2)
    base = round(sum(s["pnl"] for s in P), 2)
    return {"label": label, "mechanism": why, "n": len(keep), "net": net,
            "delta": round(net - base, 2),
            "per_trade": round(net / len(keep), 2) if keep else 0.0,
            "win_pct": round(100.0 * sum(1 for s in keep if s["pnl"] > 0) / len(keep), 1) if keep else 0.0,
            "cut_n": len(cut),
            "cut_winners": sum(1 for s in cut if s["pnl"] > 0),
            "forgone_winner_usd": round(sum(s["pnl"] for s in cut if s["pnl"] > 0), 2),
            "placebo": placebo(P, len(cut), net),
            "lodo_worst_delta": lodo_worst(P, fn),
            "strip3_delta": strip3(P, fn)}


def main() -> None:
    S = load()
    base = round(sum(s["pnl"] for s in S), 2)
    cands = [
        (f_none, "NO FILTER (live as traded)", "baseline"),
        (f_cooldown(5), "cooldown 5min after a stop", "operator test 1"),
        (f_cooldown(15), "cooldown 15min after a stop", "operator test 1"),
        (f_cooldown(30), "cooldown 30min after a stop", "operator test 1"),
        (f_cooldown(60), "cooldown 60min after a stop", "operator test 1"),
        (f_streak(2, 60), "bench 60min after 2 stops", "operator test 2"),
        (f_streak(2, None), "bench rest-of-session after 2 stops", "operator test 2"),
        (f_streak(3, None), "bench rest-of-session after 3 stops", "operator test 2"),
        (f_netmin(500), "net_min 500 (from 400)", "operator test 4"),
        (f_netmin(600), "net_min 600 (from 400)", "operator test 4"),
        (f_netmin(700), "net_min 700 (from 400)", "operator test 4"),
        (f_atr_ceil(37), "skip when entry ATR >= 37pt", "from the regime split"),
        (f_atr_ceil(27), "skip when entry ATR >= 27pt", "from the regime split"),
        (f_atr_floor(14), "skip when entry ATR < 14pt", "from the regime split"),
        (f_us_only, "US session only (>=13:00Z)", "from the time-of-day split"),
    ]
    R = [battery(S, fn, lab, why) for fn, lab, why in cands]
    json.dump({"baseline": base, "n": len(S), "candidates": R}, open(OUT, "w"), indent=1)

    print(f"exhaustion_short — {len(S)} signals, live net ${base:.2f}\n")
    print(f"{'candidate':38s} {'n':>4s} {'net$':>9s} {'delta':>8s} {'$/sig':>7s} {'win%':>6s} "
          f"{'cut':>4s} {'Wcut':>5s} {'their$':>9s} {'plac%':>6s} {'LODOw':>8s} {'strip3':>8s}")
    for c in R:
        p = c["placebo"]["pctile"] if c["placebo"] else None
        print(f"{c['label']:38s} {c['n']:4d} {c['net']:9.2f} {c['delta']:8.2f} {c['per_trade']:7.2f} "
              f"{c['win_pct']:5.1f}% {c['cut_n']:4d} {c['cut_winners']:5d} {c['forgone_winner_usd']:9.2f} "
              f"{(f'{p:.1f}' if p is not None else '-'):>6s} {c['lodo_worst_delta']:8.2f} {c['strip3_delta']:8.2f}")
    print("\nplac% = percentile vs 4,000 random removals of the SAME number of signals. "
          "Needs >=95 to be doing anything a coin flip wouldn't.")
    surv = [c for c in R if c["placebo"] and c["placebo"]["pctile"] >= 95.0]
    print(f"\nCandidates clearing the placebo: {len(surv)} — "
          f"{', '.join(c['label'] for c in surv) if surv else 'NONE'}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
