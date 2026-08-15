"""EXHAUSTION_SHORT REHAB — the operator's TRIGGER-SIZE question, done three ways.

"my 500 or 600 was the amount of contracts that need to be bought instead of 400 which is
current trigger. was just an idea to test. if a different number helped."

That is FootprintCfg.net_min — the |20s net signed aggressor volume| floor, currently 400
contracts. The live gate logs no net of its own, so the number at each LIVE fire is rebuilt
from the parquet tape and calibrated against the 430 fires shadow.db.footprint_signal_net
recorded at the time (91-99% same keep/cut decision — see exh_net_validate.py).

Three framings, because the first one is confounded and saying so is the point:

  (A) ABSOLUTE thresholds, as asked. Confounded: a floor of 400 — the value ALREADY LIVE, which
      should be a no-op — "improves" the book by $641, which can only mean the rebuild's error
      is correlated with something that also loses money. It is: the 17 sub-400 signals sit on
      THINNER tape (median 1,221 ticks in the window vs 1,542), so this cell is measuring tape
      quality and execution latency, not trigger size.
  (B) QUANTILE cuts inside the live book, matched to the fractions the operator's own numbers
      imply (500 cuts ~46%, 600 cuts ~68%). Immune to any constant scale bias in the rebuild.
  (C) The direct question, no threshold at all: does a bigger trigger produce a better trade?
"""
from __future__ import annotations

import json
import math
import random
import statistics

IN = "reports/friday_v7/sections/exh_signals.json"
OUT = "reports/friday_v7/sections/exh_netmin.json"
ANCHOR = {"single": "-3", "AB": "-5"}
DRAWS = 4000
RNG = random.Random(20260815)


def load():
    S = json.load(open(IN))["signals"]
    for s in S:
        a = s["net_by_anchor"].get(ANCHOR[s["era"]])
        s["net_abs"] = abs(a["net"]) if a else None
        s["nticks"] = a["nticks"] if a else 0
        s["stopped"] = "STOP" in s["reasons"]
    return sorted(S, key=lambda s: s["ts_ms"])


def placebo(pool, k, actual):
    if k <= 0 or k >= len(pool):
        return {"pctile": None}
    tot = sum(s["pnl"] for s in pool)
    p = [s["pnl"] for s in pool]
    idx = list(range(len(pool)))
    nets = sorted(tot - sum(p[i] for i in RNG.sample(idx, k)) for _ in range(DRAWS))
    return {"mean": round(statistics.mean(nets), 2),
            "p95": round(nets[int(0.95 * len(nets))], 2),
            "pctile": round(100.0 * sum(1 for x in nets if x < actual) / len(nets), 1)}


def report(pool, keep, label):
    cut = [s for s in pool if s not in keep]
    net = round(sum(s["pnl"] for s in keep), 2)
    return {"label": label, "n": len(keep), "net": net,
            "per_trade": round(net / len(keep), 2) if keep else 0,
            "win_pct": round(100.0 * sum(1 for s in keep if s["pnl"] > 0) / len(keep), 1) if keep else 0,
            "cut_n": len(cut),
            "cut_pct": round(100.0 * len(cut) / len(pool), 1),
            "cut_winners": sum(1 for s in cut if s["pnl"] > 0),
            "forgone_winner_usd": round(sum(s["pnl"] for s in cut if s["pnl"] > 0), 2),
            "cut_losers": sum(1 for s in cut if s["pnl"] <= 0),
            "avoided_loser_usd": round(sum(s["pnl"] for s in cut if s["pnl"] <= 0), 2),
            "placebo": placebo(pool, len(cut), net)}


def main() -> None:
    S = load()
    T = [s for s in S if s["net_abs"] is not None]
    R = {"note_tape_gap": {
        "signals_total": len(S), "signals_with_tape": len(T),
        "missing_days": sorted({s["date"] for s in S if s["net_abs"] is None}),
        "missing_net": round(sum(s["pnl"] for s in S if s["net_abs"] is None), 2)}}
    print(f"signals {len(S)}, tape-backed {len(T)} (net ${sum(s['pnl'] for s in T):.2f})")
    print(f"no tape: {R['note_tape_gap']['missing_days']} "
          f"({len(S)-len(T)} signals, ${R['note_tape_gap']['missing_net']:.2f}) — "
          "V7 tick capture began 2026-07-24\n")

    # (A) absolute thresholds
    R["absolute"] = [report(T, [s for s in T if s["net_abs"] >= t], f"net_min {t:.0f}")
                     for t in (400, 450, 500, 550, 600, 650, 700, 800, 900)]
    print("(A) ABSOLUTE net_min on the live book — ⚠ CONFOUNDED, see below")
    hdr = (f"{'floor':12s} {'kept':>5s} {'cut':>5s} {'cut%':>6s} {'net$':>9s} {'$/sig':>7s} "
           f"{'win%':>6s} {'winners cut':>12s} {'their $':>9s} {'placebo%':>9s}")
    print(hdr)
    for c in R["absolute"]:
        print(f"{c['label']:12s} {c['n']:5d} {c['cut_n']:5d} {c['cut_pct']:5.1f}% {c['net']:9.2f} "
              f"{c['per_trade']:7.2f} {c['win_pct']:5.1f}% {c['cut_winners']:12d} "
              f"{c['forgone_winner_usd']:9.2f} {str(c['placebo']['pctile']):>9s}")

    lo = [s for s in T if s["net_abs"] < 400]
    R["confound"] = {
        "n": len(lo), "pnl": round(sum(s["pnl"] for s in lo), 2),
        "winners": sum(1 for s in lo if s["pnl"] > 0),
        "median_ticks_in_window": statistics.median([s["nticks"] for s in lo]),
        "median_ticks_rest": statistics.median([s["nticks"] for s in T if s["net_abs"] >= 400]),
        "era_single": sum(1 for s in lo if s["era"] == "single")}
    print(f"\n  ⚠ the 400 cell is NOT a no-op: it removes {len(lo)} signals worth "
          f"${R['confound']['pnl']:.2f} that the LIVE gate provably fired, so its 400-floor was met. "
          f"\n    Those signals sit on thinner tape (median {R['confound']['median_ticks_in_window']:.0f} "
          f"ticks in the 20s window vs {R['confound']['median_ticks_rest']:.0f}) and "
          f"{R['confound']['era_single']}/{len(lo)} are pre-A/B. This cell measures tape quality and\n"
          f"    signal-to-fill latency, NOT trigger size. Everything below is measured on the "
          f"{len(T)-len(lo)} signals that clear 400 on the rebuild.\n")

    # (B) quantile cuts, immune to a constant scale bias
    base = [s for s in T if s["net_abs"] >= 400]
    R["baseline_400"] = report(base, base, "live 400 floor (baseline)")
    order = sorted(base, key=lambda s: s["net_abs"])
    print(f"(B) QUANTILE cuts within the live 400-floor book (n={len(base)}, "
          f"net ${sum(s['pnl'] for s in base):.2f}) — the operator's fractions")
    print(hdr)
    R["quantile"] = []
    for frac, lab in ((0.0, "keep all (live 400)"), (0.20, "cut smallest 20%"),
                      (0.30, "cut smallest 30%"), (0.46, "cut smallest 46% (~net_min 500)"),
                      (0.58, "cut smallest 58% (~net_min 550)"),
                      (0.68, "cut smallest 68% (~net_min 600)"),
                      (0.77, "cut smallest 77% (~net_min 700)")):
        k = int(round(frac * len(order)))
        keep = order[k:]
        c = report(base, keep, lab)
        c["implied_floor"] = round(order[k]["net_abs"], 0) if k < len(order) else None
        R["quantile"].append(c)
        print(f"{lab:12.12s} {c['n']:5d} {c['cut_n']:5d} {c['cut_pct']:5.1f}% {c['net']:9.2f} "
              f"{c['per_trade']:7.2f} {c['win_pct']:5.1f}% {c['cut_winners']:12d} "
              f"{c['forgone_winner_usd']:9.2f} {str(c['placebo']['pctile']):>9s}   "
              f"(floor ~{c['implied_floor']})")

    # (C) the direct question
    xs = [s["net_abs"] for s in base]
    ys = [s["pnl"] for s in base]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den = math.sqrt(sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys))
    r = num / den if den else 0.0
    n = len(xs)
    tstat = r * math.sqrt((n - 2) / max(1e-9, 1 - r * r))
    R["correlation"] = {"r": round(r, 3), "n": n, "t": round(tstat, 2)}
    print(f"\n(C) does a BIGGER trigger make a BETTER trade? r = {r:+.3f} on n={n} (t={tstat:.2f}) "
          f"— {'nothing' if abs(tstat)<2 else 'something'}")
    q = sorted(base, key=lambda s: s["net_abs"])
    R["quintiles"] = []
    k = len(q) // 5
    print(f"{'quintile':10s} {'|net| range':>16s} {'n':>4s} {'net$':>9s} {'$/sig':>8s} {'win%':>6s} {'stop%':>6s}")
    for i in range(5):
        b = q[i * k:(i + 1) * k] if i < 4 else q[4 * k:]
        p = sum(x["pnl"] for x in b)
        row = {"q": i + 1, "lo": round(b[0]["net_abs"]), "hi": round(b[-1]["net_abs"]),
               "n": len(b), "net": round(p, 2), "per_trade": round(p / len(b), 2),
               "win_pct": round(100.0 * sum(1 for x in b if x["pnl"] > 0) / len(b), 1),
               "stop_pct": round(100.0 * sum(1 for x in b if x["stopped"]) / len(b), 1)}
        R["quintiles"].append(row)
        print(f"Q{i+1:<9d} {row['lo']:6.0f}-{row['hi']:<9.0f} {row['n']:4d} {row['net']:9.2f} "
              f"{row['per_trade']:8.2f} {row['win_pct']:5.1f}% {row['stop_pct']:5.1f}%")

    json.dump(R, open(OUT, "w"), indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
