#!/usr/bin/env python3
"""OPEN-NEWS greenfield — POPSAR, the candidate the NULL BATTERY asked for.

What the nulls said about POPGO, in plain English: the MOMENT is worth something and the DIRECTION
is worth nothing. Forcing every trade LONG made +$813, forcing every trade SHORT made +$1,419, and
a coin flip on the same clock made a median +$1,206 with 22% of flips beating the real signal. You
cannot get both sides paying unless the payoff is coming from the MOVE, not from the CALL.

That is a straddle. We cannot buy a straddle — the desk trades outright MNQ futures. The one-
instrument equivalent is STOP-AND-REVERSE: take the pop's own side, and if the stop pays, turn round
and take the other side for the same money. Two legs, two fees ($1.50 each, charged honestly here),
one direction-blind structure.

  POPSAR  trigger:  1-min bar >= k x ATR14 closing in the extreme close_frac of its range, >= 13:30Z
          leg 1:    the bar's own direction, stop_k x ATR14 stop
          reverse:  on the stop, flip at the stop price; same stop distance; at most `max_rev` flips
          exit:     flat 15:00Z
          costs:    $1.50 ROUND TRIP PER LEG — a 1-reverse trade pays $3.00 in total

The honest comparison is not POPSAR vs POPGO — POPSAR is direction-blind by construction, so a
coin-flip placebo is meaningless for it. The comparison that matters is POPSAR AT POP MOMENTS vs
POPSAR AT RANDOM MOMENTS in the same window. That is the test this file is built around.
"""
from __future__ import annotations

import json
import sys

import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import gf_on_engine as E  # noqa: E402
import gf_on_popgo as P  # noqa: E402
import gf_on_sweep as S  # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"


def sar(dd, sod, direction, *, stop_pt, time_stop, max_rev=1, slip_ticks=1.0):
    """Chain simulate_fast legs. Each leg is a real round trip and pays a real round-trip fee."""
    legs = []
    d = direction
    t0 = sod
    for _ in range(max_rev + 1):
        t = E.simulate_fast(dd["ticks"], t0, d, stop_pt=stop_pt, time_stop_sod=time_stop,
                            slip_ticks=slip_ticks)
        if t is None:
            break
        legs.append(t)
        if t["reason"] != "STOP" or t["exit_sod"] >= time_stop - 5:
            break
        d = -d
        t0 = t["exit_sod"]
    if not legs:
        return None
    return {"net": sum(x["net"] for x in legs), "legs": len(legs),
            "pts": sum(x["pts"] for x in legs),
            "entry_sod": legs[0]["entry_sod"], "exit_sod": legs[-1]["exit_sod"],
            "dir": legs[0]["dir"], "reason": legs[-1]["reason"],
            "leg_reasons": [x["reason"] for x in legs]}


def run(days, sigs, *, stop_k=1.0, max_rev=1, time_stop=E.WIN_HI, slip=1.0, shift=0):
    out = []
    for d, sod, direction, meta in sigs:
        dd = days[d]
        if dd["ticks"] is None:
            continue
        s = sod + shift
        if not (E.WIN_LO <= s < E.WIN_HI):
            continue
        mkey = s // 60 * 60 - 60
        atr = dd["amap"].get(mkey, np.nan)
        if np.isnan(atr) or atr <= 0:
            continue
        t = sar(dd, s, direction, stop_pt=max(stop_k * atr, 4 * E.TICK), time_stop=time_stop,
                max_rev=max_rev, slip_ticks=slip)
        if t is None:
            continue
        t.update(day=d, regime=dd["rmap"].get(mkey, "unknown"), atr=float(atr),
                 er=float(dd["emap"].get(mkey, np.nan)))
        out.append(t)
    return out


def main():
    days = E.load_days()
    E.attach_regimes(days)
    K, CF, MT = 2.0, 0.70, 3
    sigs = S.gen_signals(days, P.sig_popgo, dict(k=K, close_frac=CF, max_trades=MT))
    res = {"spec": {"k": K, "close_frac": CF, "max_trades": MT, "window": "13:30-15:00Z",
                    "exit": "flat 15:00Z", "fee_note": "$1.50 round trip PER LEG"}}

    # ── grid over stop distance x how many reversals we allow ─────────────────────────────
    grid = {}
    for sk in (0.5, 0.75, 1.0, 1.5, 2.0):
        for mr in (0, 1, 2, 3):
            tr = run(days, sigs, stop_k=sk, max_rev=mr)
            grid[f"stop{sk}|rev{mr}"] = E.score(tr) | {"legs": sum(t["legs"] for t in tr)}
    res["grid"] = grid
    print("── POPSAR grid (n = trades; legs = fee-paying round trips) ──")
    print(f"{'cfg':<18}{'n':>4}{'legs':>6}{'net':>9}{'win':>7}{'$/tr':>9}")
    for lbl, sc in grid.items():
        print(f"{lbl:<18}{sc['n']:>4}{sc['legs']:>6}{sc['net']:>+9.0f}{str(sc['win']):>7}{str(sc['per']):>9}")

    SK, MR = 1.0, 1
    base = run(days, sigs, stop_k=SK, max_rev=MR)
    res["chosen"] = f"stop{SK}|rev{MR}"
    res["headline"] = E.score(base)
    res["by_regime"] = E.by(base, lambda t: t["regime"])
    res["by_legs"] = E.by(base, lambda t: f"{t['legs']} leg(s)")
    res["by_day"] = E.by(base, lambda t: t["day"])
    h = res["headline"]
    print(f"\n═══ POPSAR stop {SK}xATR, {MR} reversal, flat 15:00Z")
    print(f"    n={h['n']}  net=${h['net']:+.0f}  win={h['win']}%  $/tr={h['per']:+.2f}")
    print(E.table(res["by_regime"], "regime"))
    print(E.table(res["by_legs"], "legs"))

    # ── THE test: pop moments vs RANDOM moments, same structure ───────────────────────────
    rng = np.random.default_rng(53)
    per = {}
    for d, *_ in sigs:
        per[d] = per.get(d, 0) + 1
    rnets = []
    for _ in range(200):
        rs = [(d, int(rng.integers(13 * 3600 + 1800, E.WIN_HI)), int(rng.choice([-1, 1])), {})
              for d in per for _ in range(per[d])]
        rnets.append(E.score(run(days, rs, stop_k=SK, max_rev=MR))["net"])
    res["random_clock"] = {"draws": 200, "median": round(float(np.median(rnets)), 2),
                           "mean": round(float(np.mean(rnets)), 2),
                           "p90": round(float(np.percentile(rnets, 90)), 2),
                           "p95": round(float(np.percentile(rnets, 95)), 2),
                           "real": h["net"],
                           "pct_beating_real": round(100 * float(np.mean([x >= h["net"] for x in rnets])), 1)}
    r = res["random_clock"]
    print(f"\n    RANDOM-CLOCK placebo (same structure, random times in 13:30-15:00Z, 200 draws)")
    print(f"      median ${r['median']:+.0f}   p90 ${r['p90']:+.0f}   p95 ${r['p95']:+.0f}")
    print(f"      real ${h['net']:+.0f}  — {r['pct_beating_real']}% of random-clock draws beat it")

    # ── direction placebo: it should NOT matter. If it does, the structure is not what we think ──
    res["dir_flip"] = E.score(run(days, [(a, b, -c, m) for a, b, c, m in sigs], stop_k=SK, max_rev=MR))
    print(f"    start the SAR on the WRONG side: ${res['dir_flip']['net']:+.0f} "
          f"(direction-blind by design — a big gap here would mean it is not)")

    # ── shift placebo ─────────────────────────────────────────────────────────────────────
    sh = {f"{s:+d}min": E.score(run(days, sigs, stop_k=SK, max_rev=MR, shift=s * 60))
          for s in (-20, -10, -5, 5, 10, 20, 30)}
    res["shift_placebo"] = sh
    print("    shift placebo ($/tr, n): " + "  ".join(f"{k}={v['per']}({v['n']})" for k, v in sh.items()))

    # ── strip / LOO / halves / cost ───────────────────────────────────────────────────────
    srt = sorted(base, key=lambda t: -t["net"])
    for kk in (1, 3, 5, 8):
        res[f"strip_{kk}"] = E.score(srt[kk:])
    loo = {d: E.score([t for t in base if t["day"] != d]) for d in sorted({t["day"] for t in base})}
    res["loo"] = {"days": len(loo), "min_net": min(v["net"] for v in loo.values()),
                  "n_negative": sum(1 for v in loo.values() if v["net"] < 0), "detail": loo}
    ds = sorted({t["day"] for t in base})
    cut = len(ds) // 2
    res["half_split"] = {"first": E.score([t for t in base if t["day"] in set(ds[:cut])]),
                         "second": E.score([t for t in base if t["day"] in set(ds[cut:])])}
    res["cost_2x"] = E.score(run(days, sigs, stop_k=SK, max_rev=MR, slip=2.0))
    res["cost_4x"] = E.score(run(days, sigs, stop_k=SK, max_rev=MR, slip=4.0))
    print(f"\n    strip-1 ${res['strip_1']['net']:+.0f}  strip-3 ${res['strip_3']['net']:+.0f}  "
          f"strip-5 ${res['strip_5']['net']:+.0f}  strip-8 ${res['strip_8']['net']:+.0f}")
    print(f"    LOO worst ${res['loo']['min_net']:+.0f} ({res['loo']['n_negative']}/{res['loo']['days']} negative)")
    print(f"    halves ${res['half_split']['first']['net']:+.0f} / ${res['half_split']['second']['net']:+.0f}")
    print(f"    cost 2x ${res['cost_2x']['net']:+.0f}   4x ${res['cost_4x']['net']:+.0f}")

    res["bmc"] = S.big_moves_caught(
        [{"day": t["day"], "dir": t["dir"], "entry_sod": t["entry_sod"], "net": t["net"]} for t in base])
    print(f"    big-moves-caught {res['bmc']['caught']}/{res['bmc']['of']}")
    res["trades"] = base
    json.dump(res, open(f"{SEC}/gf_on_popsar.json", "w"), indent=1, default=float)
    print(f"\n→ {SEC}/gf_on_popsar.json")


if __name__ == "__main__":
    main()
