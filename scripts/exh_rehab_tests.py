"""EXHAUSTION_SHORT REHAB — stage 2: the four commissioned tests, each placebo-controlled.

Every filter here is judged the same way and it is the only way a cut of this kind can be
judged honestly: a filter that removes K signals is compared against 4,000 random removals of
the SAME K signals. Removing 40% of a book looks brilliant whenever the removed 40% lost, so
the question is never "did net go up" but "did net go up by more than a coin-flip cut of this
size would have". The percentile is the verdict; the headline number is decoration.

Judged on LIVE P&L (the desk's standing rule for this gate — the fixed-target shadow lies
about faders). The one place a reprice is unavoidable is the delay-veto, which moves the entry
price; that runs BOTH ways (live-P&L entry-shift AND a self-consistent 8/12 tick reprice) and
both are reported.
"""
from __future__ import annotations

import json
import random
import statistics

VPP = 2.0
IN = "reports/friday_v7/sections/exh_signals.json"
OUT = "reports/friday_v7/sections/exh_rehab_results.json"
ANCHOR = {"single": "-3", "AB": "-5"}      # era-specific, chosen by the |net|>=400 pass-rate test
PLACEBO_DRAWS = 4000
RNG = random.Random(20260815)


# ── helpers ──────────────────────────────────────────────────────────────────────────
def load():
    S = json.load(open(IN))["signals"]
    for s in S:
        s["stopped"] = "STOP" in s["reasons"]
        s["win"] = s["pnl"] > 0
        a = s["net_by_anchor"].get(ANCHOR[s["era"]])
        s["net_abs"] = abs(a["net"]) if a else None
        s["mfe"], s["mae"] = _excursion(s)
    return S


def _excursion(s):
    """Best/worst POINTS in favour of the short, from the cached tick path after entry."""
    p = [(t, px) for t, px in s["path"] if t >= 0]
    if not p:
        return None, None
    e = s["entry"]
    return round(max(e - px for _, px in p), 2), round(max(px - e for _, px in p), 2)


def summarise(keep, all_sigs, label):
    n = len(keep)
    net = round(sum(s["pnl"] for s in keep), 2)
    w = sum(1 for s in keep if s["win"])
    cut = [s for s in all_sigs if s not in keep]
    return {
        "label": label, "n": n, "net": net,
        "win_pct": round(100.0 * w / n, 1) if n else 0.0,
        "per_trade": round(net / n, 2) if n else 0.0,
        "cut_n": len(cut),
        "cut_net": round(sum(s["pnl"] for s in cut), 2),
        "cut_winners": sum(1 for s in cut if s["win"]),
        "cut_winner_usd": round(sum(s["pnl"] for s in cut if s["win"]), 2),
        "cut_losers": sum(1 for s in cut if not s["win"]),
    }


def placebo(all_sigs, k, actual_net):
    """Random removals of exactly k signals — the null the mission demands."""
    if k <= 0 or k >= len(all_sigs):
        return {"draws": 0}
    tot = sum(s["pnl"] for s in all_sigs)
    nets = []
    idx = list(range(len(all_sigs)))
    pnl = [s["pnl"] for s in all_sigs]
    for _ in range(PLACEBO_DRAWS):
        drop = RNG.sample(idx, k)
        nets.append(tot - sum(pnl[i] for i in drop))
    nets.sort()
    beat = sum(1 for x in nets if x < actual_net)
    return {
        "draws": PLACEBO_DRAWS,
        "mean": round(statistics.mean(nets), 2),
        "p05": round(nets[int(0.05 * len(nets))], 2),
        "p95": round(nets[int(0.95 * len(nets))], 2),
        "pctile": round(100.0 * beat / len(nets), 1),
        "beats_random": bool(100.0 * beat / len(nets) >= 95.0),
    }


def scored(all_sigs, keep, label):
    r = summarise(keep, all_sigs, label)
    r["placebo"] = placebo(all_sigs, len(all_sigs) - len(keep), r["net"])
    return r


# ── TEST 1 — re-entry cooldown after a stop ──────────────────────────────────────────
def test_cooldown(S, mins):
    """Suppress any signal opening within `mins` of the CLOSE of a stopped trade. Applied
    sequentially: a suppressed signal never happened, so it cannot itself start a cooldown."""
    keep, block_until = [], -1
    for s in S:
        if s["ts_ms"] < block_until:
            continue
        keep.append(s)
        if s["stopped"]:
            block_until = s["closed_ms"] + mins * 60_000
    return keep


# ── TEST 2 — streak breaker ──────────────────────────────────────────────────────────
def test_streak(S, n_stops, bench_min):
    """Bench the gate after `n_stops` consecutive stopped signals, for `bench_min` minutes
    (bench_min=None → rest of the session/day). The streak resets on any non-stop outcome."""
    keep, run, block_until, blocked_day = [], 0, -1, None
    for s in S:
        if blocked_day == s["date"] or s["ts_ms"] < block_until:
            continue
        keep.append(s)
        run = run + 1 if s["stopped"] else 0
        if run >= n_stops:
            if bench_min is None:
                blocked_day = s["date"]
            else:
                block_until = s["closed_ms"] + bench_min * 60_000
            run = 0
    return keep


# ── TEST 3 — the operator's veto: delay-and-RE-TEST on the side already chosen ───────
def test_veto(S, delay_s, adverse_pt):
    """Wait `delay_s` PAST the live entry and take the short only if price has not run UP by
    more than `adverse_pt` in that window (buyers still pushing = the absorption failed).
    This is the live 5s/5pt confirm-veto extended — never a direction selector."""
    keep = []
    for s in S:
        p = [(t, px) for t, px in s["path"] if 0 <= t <= delay_s * 1000]
        if len(p) < 3:
            keep.append((s, None))                    # no tape to re-test on → take it (live behaviour)
            continue
        worst_up = max(px for _, px in p) - s["entry"]
        if worst_up > adverse_pt:
            continue
        keep.append((s, p[-1][1]))                    # entry re-priced at the end of the wait
    return keep


def veto_pnl_liveshift(kept):
    """Live P&L credited with the better/worse entry the wait produced (a SHORT entered higher
    is worth (new-old)*$2 per lot). Exit price held at what the desk actually got."""
    tot = 0.0
    for s, px in kept:
        tot += s["pnl"] + ((px - s["entry"]) * VPP * s["n_legs"] if px is not None else 0.0)
    return round(tot, 2)


# ── the gate's DESIGN exit, repriced on ticks (8pt stop / 12pt target / 120s) ────────
def reprice_design(s, entry_px=None, t0=0, stop_pt=8.0, tgt_pt=12.0, hold_s=120, fee=1.50):
    """What the FootprintShadow design exit — the one the 07-25 rehab revived this gate on —
    would have made on this signal's own tape. SHORT only. Returns $ for ONE lot."""
    e = entry_px if entry_px is not None else s["entry"]
    p = [(t, px) for t, px in s["path"] if t >= t0]
    if not p:
        return None, None
    stop, tgt = e + stop_pt, e - tgt_pt
    for t, px in p:
        if px >= stop:
            return round((e - stop) * VPP - fee, 2), "STOP"
        if px <= tgt:
            return round((e - tgt) * VPP - fee, 2), "TARGET"
        if (t - t0) >= hold_s * 1000:
            return round((e - px) * VPP - fee, 2), "TIME"
    return round((e - p[-1][1]) * VPP - fee, 2), "EOD"


# ── TEST 4 — the operator's trigger size: net_min ────────────────────────────────────
def test_netmin(S, thr):
    """Cut signals whose 20s |net signed aggressor volume| at the fire was below `thr`.
    Signals with NO tape (2026-07-21..23, before V7 tick capture) are KEPT — we cannot know,
    and silently dropping them would fake the cut."""
    return [s for s in S if s["net_abs"] is None or s["net_abs"] >= thr]


# ── robustness ───────────────────────────────────────────────────────────────────────
def lodo(S, fn):
    """Leave-one-day-out: the filter's $ delta re-measured with each day removed in turn."""
    days = sorted({s["date"] for s in S})
    out = []
    for d in days:
        sub = [s for s in S if s["date"] != d]
        base = sum(s["pnl"] for s in sub)
        out.append({"drop": d, "delta": round(sum(s["pnl"] for s in fn(sub)) - base, 2)})
    return out


def strip_best(S, fn, k=3):
    """Strip the k best signals and re-measure — kills a filter that lives on one lucky trade."""
    order = sorted(S, key=lambda s: -s["pnl"])[:k]
    sub = [s for s in S if s not in order]
    return round(sum(s["pnl"] for s in fn(sub)) - sum(s["pnl"] for s in sub), 2)


def main() -> None:
    S = load()
    S.sort(key=lambda s: s["ts_ms"])
    base_net = round(sum(s["pnl"] for s in S), 2)
    R = {"baseline": summarise(S, S, "LIVE as traded")}
    R["baseline"]["stopped_signals"] = sum(1 for s in S if s["stopped"])
    print(f"BASELINE  n={len(S)} net={base_net} win={R['baseline']['win_pct']}%")

    R["cooldown"] = [scored(S, test_cooldown(S, m), f"cooldown {m}min") for m in
                     (1, 2, 3, 5, 8, 10, 15, 20, 30, 45, 60, 90, 120)]
    R["streak"] = [scored(S, test_streak(S, n, w), f"bench after {n} stops for {w or 'session'}")
                   for n in (2, 3, 4) for w in (15, 30, 60, 120, None)]
    R["netmin"] = [scored(S, test_netmin(S, t), f"net_min {t}") for t in
                   (400, 450, 500, 550, 600, 650, 700, 800, 900)]

    # veto — live-shift AND design-exit reprice, on the tape-backed signals only
    T = [s for s in S if s["path_n"] > 0]
    tot_T = round(sum(s["pnl"] for s in T), 2)
    base_design = [reprice_design(s) for s in T]
    bd = round(sum(x[0] * s["n_legs"] for x, s in zip(base_design, T) if x[0] is not None), 2)
    R["veto"] = {"tape_n": len(T), "tape_live_net": tot_T, "tape_design_net": bd, "cells": []}
    for d in (5, 10, 15, 20, 30, 45, 60, 90):
        for a in (2.0, 3.0, 5.0, 8.0):
            kept = test_veto(T, d, a)
            ks = [s for s, _ in kept]
            live = veto_pnl_liveshift(kept)
            des = 0.0
            for s, px in kept:
                v, _ = reprice_design(s, entry_px=px, t0=d * 1000)
                if v is not None:
                    des += v * s["n_legs"]
            R["veto"]["cells"].append({
                "delay_s": d, "adverse_pt": a, "n": len(ks),
                "cut": len(T) - len(ks),
                "cut_winners": sum(1 for s in T if s not in ks and s["win"]),
                "live_shift_net": live, "design_net": round(des, 2),
                "placebo": placebo(T, len(T) - len(ks), sum(s["pnl"] for s in ks)),
                "raw_keep_live": round(sum(s["pnl"] for s in ks), 2),
            })

    # robustness for the headline cells (filled in after reading the sweeps)
    R["robust"] = {
        "cooldown": {str(m): {"lodo": lodo(S, lambda x, m=m: test_cooldown(x, m)),
                              "strip3": strip_best(S, lambda x, m=m: test_cooldown(x, m))}
                     for m in (5, 10, 15, 30, 60)},
        "netmin": {str(t): {"lodo": lodo(S, lambda x, t=t: test_netmin(x, t)),
                            "strip3": strip_best(S, lambda x, t=t: test_netmin(x, t))}
                   for t in (450, 500, 600, 700)},
        "streak": {"2x60": {"lodo": lodo(S, lambda x: test_streak(x, 2, 60)),
                            "strip3": strip_best(S, lambda x: test_streak(x, 2, 60))},
                   "2xsession": {"lodo": lodo(S, lambda x: test_streak(x, 2, None)),
                                 "strip3": strip_best(S, lambda x: test_streak(x, 2, None))}},
    }

    json.dump(R, open(OUT, "w"), indent=1)
    for k in ("cooldown", "streak", "netmin"):
        print(f"\n=== {k} ===")
        for c in R[k]:
            p = c["placebo"]
            print(f"  {c['label']:34s} n={c['n']:3d} net={c['net']:9.2f} /tr={c['per_trade']:7.2f} "
                  f"cut={c['cut_n']:3d} (win {c['cut_winners']}, ${c['cut_winner_usd']:.0f}) "
                  f"placebo mean={p.get('mean',0):8.2f} pct={p.get('pctile','-')}")
    print(f"\n=== veto (tape n={len(T)}, live {tot_T}, design {bd}) ===")
    for c in R["veto"]["cells"]:
        print(f"  d={c['delay_s']:3d}s adv={c['adverse_pt']:.0f}pt n={c['n']:3d} cut={c['cut']:3d} "
              f"(win {c['cut_winners']}) live_shift={c['live_shift_net']:9.2f} "
              f"design={c['design_net']:9.2f} pct={c['placebo'].get('pctile','-')}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
