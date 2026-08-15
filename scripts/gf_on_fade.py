#!/usr/bin/env python3
"""OPEN-NEWS greenfield — decomposing POPSAR, and the POPFADE candidate hiding inside it.

POPSAR's leg table says the whole story is two different trades wearing one name:
    12 trades never stopped and rode the clock          +$4,220
    42 trades stopped, reversed, and the REVERSAL paid  +$1,486   (POPGO booked -$2,117 on these)

So the reversal is worth +$3,603 on its own. If that leg stands up alone it is a CHEAPER gate — one
round trip instead of two — and it deserves its own name and its own battery:

  POPFADE  trigger: a 1-min bar >= k x ATR14 closing on its extreme, at or after 13:30Z …
                    … then price RETRACES stop_k x ATR14 back through the bar's close
           entry:   at the retrace level, AGAINST the pop
           stop:    stop_k x ATR14 (i.e. back at the pop bar's own close)
           exit:    flat 15:00Z
           costs:   $1.50 round trip

Also settles the direction question POPSAR's "wrong side" run raised: a 200-draw coin-flip null on
the SAR's STARTING side, so we know whether the pop's own direction is information or decoration.
"""
from __future__ import annotations

import json
import sys

import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import gf_on_engine as E  # noqa: E402
import gf_on_popgo as P  # noqa: E402
import gf_on_popsar as SAR  # noqa: E402
import gf_on_sweep as S  # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"


def run_fade(days, sigs, *, stop_k=1.0, time_stop=E.WIN_HI, slip=1.0, retrace_k=None):
    """Leg 1 is a TRIGGER, not a trade: we wait for the pop-direction move to fail by retrace_k x ATR
    and only then take the other side. No fee is paid for waiting."""
    out = []
    rk = retrace_k if retrace_k is not None else stop_k
    for d, sod, direction, meta in sigs:
        dd = days[d]
        if dd["ticks"] is None:
            continue
        mkey = sod // 60 * 60 - 60
        atr = dd["amap"].get(mkey, np.nan)
        if np.isnan(atr) or atr <= 0:
            continue
        # find the retrace WITHOUT paying for it — a zero-cost probe with the same tick walk
        probe = E.simulate_fast(dd["ticks"], sod, direction, stop_pt=max(rk * atr, 4 * E.TICK),
                                time_stop_sod=time_stop, slip_ticks=0.0)
        if probe is None or probe["reason"] != "STOP" or probe["exit_sod"] >= time_stop - 5:
            continue
        t = E.simulate_fast(dd["ticks"], probe["exit_sod"], -direction,
                            stop_pt=max(stop_k * atr, 4 * E.TICK), time_stop_sod=time_stop,
                            slip_ticks=slip)
        if t is None:
            continue
        t.update(day=d, regime=dd["rmap"].get(mkey, "unknown"), atr=float(atr),
                 er=float(dd["emap"].get(mkey, np.nan)), pop_sod=sod)
        out.append(t)
    return out


def main():
    days = E.load_days()
    E.attach_regimes(days)
    K, CF, MT = 2.0, 0.70, 3
    sigs = S.gen_signals(days, P.sig_popgo, dict(k=K, close_frac=CF, max_trades=MT))
    res = {}

    # ── 1. does the pop's own DIRECTION matter to the SAR? 200-draw coin flip on the start side ──
    rng = np.random.default_rng(97)
    nets = []
    for _ in range(200):
        ss = [(a, b, int(rng.choice([-1, 1])), m) for a, b, _, m in sigs]
        nets.append(E.score(SAR.run(days, ss, stop_k=1.0, max_rev=1))["net"])
    real = E.score(SAR.run(days, sigs, stop_k=1.0, max_rev=1))
    wrong = E.score(SAR.run(days, [(a, b, -c, m) for a, b, c, m in sigs], stop_k=1.0, max_rev=1))
    res["sar_direction_null"] = {
        "real_net": real["net"], "wrong_side_net": wrong["net"],
        "coinflip_median": round(float(np.median(nets)), 2),
        "coinflip_mean": round(float(np.mean(nets)), 2),
        "coinflip_p90": round(float(np.percentile(nets, 90)), 2),
        "pct_beating_real": round(100 * float(np.mean([x >= real["net"] for x in nets])), 1)}
    r = res["sar_direction_null"]
    print("── does the POP'S OWN DIRECTION matter to POPSAR? ──")
    print(f"   pop's side   ${real['net']:+.0f}")
    print(f"   wrong side   ${wrong['net']:+.0f}")
    print(f"   coin flip    median ${r['coinflip_median']:+.0f}  mean ${r['coinflip_mean']:+.0f}  "
          f"p90 ${r['coinflip_p90']:+.0f}  — {r['pct_beating_real']}% of 200 flips beat the pop's side")

    # ── 2. POPFADE on its own ─────────────────────────────────────────────────────────────
    grid = {}
    for sk in (0.5, 0.75, 1.0, 1.5, 2.0):
        for rk in (0.5, 0.75, 1.0, 1.5):
            tr = run_fade(days, sigs, stop_k=sk, retrace_k=rk)
            grid[f"stop{sk}|ret{rk}"] = E.score(tr)
    res["fade_grid"] = grid
    print("\n── POPFADE grid (stop x retrace, both in ATR) ──")
    print(f"{'cfg':<20}{'n':>4}{'net':>9}{'win':>7}{'$/tr':>9}")
    for lbl, sc in sorted(grid.items(), key=lambda x: -(x[1]['net'] or 0)):
        print(f"{lbl:<20}{sc['n']:>4}{sc['net']:>+9.0f}{str(sc['win']):>7}{str(sc['per']):>9}")
    neg = sum(1 for sc in grid.values() if (sc["net"] or 0) < 0)
    print(f"   cells negative: {neg}/{len(grid)}")
    res["fade_grid_negative_cells"] = neg

    SK, RK = 1.0, 1.0
    base = run_fade(days, sigs, stop_k=SK, retrace_k=RK)
    res["fade"] = {"cfg": f"stop{SK}|ret{RK}", "headline": E.score(base),
                   "by_regime": E.by(base, lambda t: t["regime"]),
                   "by_dir": E.by(base, lambda t: "LONG" if t["dir"] > 0 else "SHORT"),
                   "by_reason": E.by(base, lambda t: t["reason"]),
                   "by_day": E.by(base, lambda t: t["day"])}
    h = res["fade"]["headline"]
    print(f"\n═══ POPFADE stop {SK}xATR retrace {RK}xATR — n={h['n']} net=${h['net']:+.0f} "
          f"win={h['win']}% $/tr={h['per']:+.2f}")
    print(E.table(res["fade"]["by_regime"], "regime"))
    print(E.table(res["fade"]["by_reason"], "exit"))

    srt = sorted(base, key=lambda t: -t["net"])
    for kk in (1, 3, 5):
        res["fade"][f"strip_{kk}"] = E.score(srt[kk:])
    loo = {d: E.score([t for t in base if t["day"] != d]) for d in sorted({t["day"] for t in base})}
    res["fade"]["loo"] = {"days": len(loo), "min_net": min(v["net"] for v in loo.values()),
                          "n_negative": sum(1 for v in loo.values() if v["net"] < 0)}
    ds = sorted({t["day"] for t in base})
    cut = len(ds) // 2
    res["fade"]["half_split"] = {"first": E.score([t for t in base if t["day"] in set(ds[:cut])]),
                                 "second": E.score([t for t in base if t["day"] in set(ds[cut:])])}
    res["fade"]["cost_2x"] = E.score(run_fade(days, sigs, stop_k=SK, retrace_k=RK, slip=2.0))
    print(f"    strip-1 ${res['fade']['strip_1']['net']:+.0f}  strip-3 ${res['fade']['strip_3']['net']:+.0f}  "
          f"strip-5 ${res['fade']['strip_5']['net']:+.0f}")
    print(f"    LOO worst ${res['fade']['loo']['min_net']:+.0f} "
          f"({res['fade']['loo']['n_negative']}/{res['fade']['loo']['days']} negative)")
    print(f"    halves ${res['fade']['half_split']['first']['net']:+.0f} / "
          f"${res['fade']['half_split']['second']['net']:+.0f}   "
          f"cost2x ${res['fade']['cost_2x']['net']:+.0f}")

    # random-clock placebo for the fade: a fade of a RANDOM moment, same rules
    per = {}
    for d, *_ in sigs:
        per[d] = per.get(d, 0) + 1
    fn = []
    for _ in range(200):
        rs = [(d, int(rng.integers(13 * 3600 + 1800, E.WIN_HI)), int(rng.choice([-1, 1])), {})
              for d in per for _ in range(per[d])]
        fn.append(E.score(run_fade(days, rs, stop_k=SK, retrace_k=RK))["net"])
    res["fade"]["random_clock"] = {"median": round(float(np.median(fn)), 2),
                                   "p90": round(float(np.percentile(fn, 90)), 2),
                                   "pct_beating_real": round(100 * float(np.mean([x >= h["net"] for x in fn])), 1)}
    fr = res["fade"]["random_clock"]
    print(f"    RANDOM-CLOCK placebo median ${fr['median']:+.0f}  p90 ${fr['p90']:+.0f}  "
          f"— {fr['pct_beating_real']}% beat it")

    res["fade"]["trades"] = base
    json.dump(res, open(f"{SEC}/gf_on_fade.json", "w"), indent=1, default=float)
    print(f"\n→ {SEC}/gf_on_fade.json")


if __name__ == "__main__":
    main()
