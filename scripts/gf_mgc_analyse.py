#!/usr/bin/env python3
"""MOVEMENT 3 — the MGC L2 book-break hunt, scored properly.

The gf_MGC phase died at 13.2 minutes (`gf_MGC: rc=-1 13.2m artifact=MISSING`) having written
its SIGNAL FILE but not its write-up: reports/friday_v7/sections/gf_mgc_breaks.json, 397 book
breaks on MGC across 21 sessions from 2026-07-16, each with the L2 features that were supposed
to separate the real ones (far-side obstacle, resting support, depletion ratio, book imbalance)
and the forward outcome.

This scores that file to the greenfield discipline the scope demands, and it is honest about
costs: MGC is $10.00 A POINT (never $2 — that is MNQ) and the fee is $1.50 PER ROUND TRIP.

The escalation the scope mandates is run here in full: score the FULL population, then narrow
to the top 25 by move size, then the top 15, and report every level even when it is a null.
"""
from __future__ import annotations

import collections
import json
import random
import statistics

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
FEE = 1.50          # per round trip. NEVER $5, never $2, never per-side.
MGC_PPT = 10.00     # MGC = $10.00 per point. MNQ is $2.00. Do not mix these up.

random.seed(20260814)


def load():
    rows = json.load(open(f"{SEC}/gf_mgc_breaks.json"))
    for r in rows:
        # fwd_$ is already fwd_pt * $10 (verified: 7.2pt -> $72.00). Net it of the round trip.
        r["net"] = r["fwd_$"] - FEE
    return rows


def score(rows, label):
    if not rows:
        return dict(label=label, n=0, net=0.0, per=0.0, win=0.0, strip3=0.0, lodo=0.0, days=0)
    nets = [r["net"] for r in rows]
    net = sum(nets)
    byday = collections.defaultdict(float)
    for r in rows:
        byday[r["day"]] += r["net"]
    lodo = min(net - v for v in byday.values()) if byday else net
    return dict(
        label=label, n=len(rows), net=round(net, 2),
        per=round(net / len(rows), 2),
        win=round(100.0 * sum(1 for x in nets if x > 0) / len(nets), 1),
        strip3=round(net - sum(sorted(nets, reverse=True)[:3]), 2),
        lodo=round(lodo, 2),
        days=len(byday),
        green_days=sum(1 for v in byday.values() if v > 0),
    )


def placebo(all_rows, k, real_net, draws=2000):
    """Could a RANDOM subset of the same size have done this well? Percentile of the real net."""
    if k <= 0 or k >= len(all_rows):
        return None
    nets = [r["net"] for r in all_rows]
    beat = 0
    for _ in range(draws):
        if sum(random.sample(nets, k)) < real_net:
            beat += 1
    return round(100.0 * beat / draws, 1)


def main():
    rows = load()
    out = {}

    base = score(rows, "every book break, as detected")
    out["baseline"] = base
    print(f"BASELINE  n={base['n']} net=${base['net']} per=${base['per']} win={base['win']}% "
          f"days={base['days']} strip3=${base['strip3']} lodo_worst=${base['lodo']}")

    # ── the candidate filters, each a single mechanical rule ──────────────────────────
    cands = [
        ("far side is EMPTY (obstacle = 0)", lambda r: r["obstacle"] == 0),
        ("far side thin (obstacle < 5 lots)", lambda r: r["obstacle"] < 5),
        ("far side depleted vs pre (obst < 50% of obst_pre)",
         lambda r: r["obst_pre"] > 0 and r["obstacle"] < 0.5 * r["obst_pre"]),
        ("depletion ratio = 1.0 (fully cleared)", lambda r: r.get("depletion") == 1.0),
        ("book imbalance with us (imb > 0.10)", lambda r: r["imb"] > 0.10),
        ("book imbalance strongly with us (imb > 0.25)", lambda r: r["imb"] > 0.25),
        ("support behind us (support > obstacle)", lambda r: r["support"] > r["obstacle"]),
        ("efficiency >= 0.35 at the break", lambda r: r["er"] >= 0.35),
        ("efficiency >= 0.50 at the break", lambda r: r["er"] >= 0.50),
        ("ATR >= 2.0pt (the move has room)", lambda r: r["atr"] >= 2.0),
        ("ATR >= 3.0pt", lambda r: r["atr"] >= 3.0),
        ("CLEAN_TREND only", lambda r: r["regime"] == "CLEAN_TREND"),
        ("not DEAD_CHOP", lambda r: r["regime"] != "DEAD_CHOP"),
        ("US session only", lambda r: r["session"] == "US"),
        ("LONDON session only", lambda r: r["session"] == "LONDON"),
        ("ASIA session only", lambda r: r["session"] == "ASIA"),
        ("LONDON or US (skip Asia)", lambda r: r["session"] in ("LONDON", "US")),
        ("empty far side AND trend", lambda r: r["obstacle"] == 0 and r["regime"] == "CLEAN_TREND"),
        ("empty far side AND ER>=0.35", lambda r: r["obstacle"] == 0 and r["er"] >= 0.35),
        ("empty far side AND not Asia",
         lambda r: r["obstacle"] == 0 and r["session"] != "ASIA"),
    ]
    out["candidates"] = []
    for label, fn in cands:
        sel = [r for r in rows if fn(r)]
        s = score(sel, label)
        s["placebo"] = placebo(rows, s["n"], s["net"])
        s["delta"] = round(s["net"] - base["net"], 2)
        out["candidates"].append(s)
        print(f"  {label:<48} n={s['n']:<4} net=${s['net']:>9} per=${s['per']:>7} "
              f"win={s['win']:>5}% strip3=${s['strip3']:>9} lodo=${s['lodo']:>9} "
              f"placebo={s['placebo']}")

    # ── the escalation: full -> top 25 -> top 15 by absolute move ─────────────────────
    out["escalation"] = []
    by_size = sorted(rows, key=lambda r: -abs(r["fwd_pt"]))
    for name, pop in (("FULL population", rows),
                      ("TOP 25 by move size", by_size[:25]),
                      ("TOP 15 by move size", by_size[:15])):
        lvl = {"level": name, "base": score(pop, f"{name} — no filter"), "best": []}
        for label, fn in cands:
            sel = [r for r in pop if fn(r)]
            if len(sel) < 8:
                continue
            s = score(sel, label)
            s["placebo"] = placebo(pop, s["n"], s["net"])
            lvl["best"].append(s)
        lvl["best"].sort(key=lambda s: -s["net"])
        lvl["best"] = lvl["best"][:5]
        out["escalation"].append(lvl)
        print(f"\n{name}: base net=${lvl['base']['net']} n={lvl['base']['n']}")
        for s in lvl["best"]:
            print(f"   best: {s['label']:<44} n={s['n']:<3} net=${s['net']:>8} "
                  f"strip3=${s['strip3']:>8} placebo={s['placebo']}")

    # ── the excursion / killer statistic ──────────────────────────────────────────────
    mfe = [r["mfe_atr"] for r in rows]
    mae = [r["mae_atr"] for r in rows]
    out["excursion"] = {
        "median_mfe_atr": round(statistics.median(mfe), 2),
        "median_mae_atr": round(statistics.median(mae), 2),
        "mfe_ge_2atr_pct": round(100.0 * sum(1 for x in mfe if x >= 2) / len(mfe), 1),
        "mae_ge_1atr_pct": round(100.0 * sum(1 for x in mae if x <= -1) / len(mae), 1),
        "ran_pct": round(100.0 * sum(r["ran"] for r in rows) / len(rows), 1),
    }
    print("\nEXCURSION:", json.dumps(out["excursion"]))

    # ── the book-imbalance separation table the scope asks for ────────────────────────
    out["book_sep"] = []
    for lo, hi, name in ((-1.0, -0.10, "book AGAINST us (imb < −0.10)"),
                         (-0.10, 0.10, "book neutral (−0.10 to +0.10)"),
                         (0.10, 0.25, "book with us (+0.10 to +0.25)"),
                         (0.25, 2.0, "book strongly with us (> +0.25)")):
        sel = [r for r in rows if lo <= r["imb"] < hi]
        out["book_sep"].append(score(sel, name))
    for s in out["book_sep"]:
        print(f"  {s['label']:<38} n={s['n']:<4} net=${s['net']:>9} per=${s['per']:>7} win={s['win']}%")

    # ── day-by-day ────────────────────────────────────────────────────────────────────
    byday = collections.defaultdict(list)
    for r in rows:
        byday[r["day"]].append(r["net"])
    out["by_day"] = [{"day": d, "n": len(v), "net": round(sum(v), 2)}
                     for d, v in sorted(byday.items())]

    # ── regime / session cross-tab ────────────────────────────────────────────────────
    out["regime"] = [score([r for r in rows if r["regime"] == g], g)
                     for g in sorted({r["regime"] for r in rows})]
    out["session"] = [score([r for r in rows if r["session"] == g], g)
                      for g in sorted({r["session"] for r in rows})]

    json.dump(out, open(f"{SEC}/gf_mgc_scored.json", "w"), indent=1)
    print(f"\nJSON -> {SEC}/gf_mgc_scored.json")


if __name__ == "__main__":
    main()
