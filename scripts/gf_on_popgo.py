#!/usr/bin/env python3
"""OPEN-NEWS greenfield — POPGO, the refined survivor, put through everything.

POPGO is VPOP with one change forced by the evidence, not by the P&L: the pre-open half hour
(13:00-13:30Z) is dropped. VPOP's own time-of-day split was +$7.31/trade before the cash open and
+$77.68/trade after it, and the -30min placebo "beat" the real signal only because shifting the
series 30 minutes earlier happens to DISCARD the pre-open half. Once you see that, the pre-open leg
is not a signal, it is padding.

  POPGO  trigger:  a 1-min bar, at or after 13:30Z, whose TRUE RANGE >= k x ATR14(1-min)
                   and whose CLOSE sits in the extreme `close_frac` of its own range
         direction: the direction of that bar
         entry:    the first trade tick after the bar closes (+1 tick adverse slippage)
         stop:     stop_k x ATR14 from entry
         exit:     no target — flat on the clock
         costs:    $1.50 round trip, $2.00/point

Everything here is measured tick-honest on the parquet lake, then re-measured on 19 days of tape the
tick study never touched (bar-executed, stop-wins-ties) as a true out-of-sample leg.
"""
from __future__ import annotations

import json
import sys

import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import gf_on_cands as C  # noqa: E402
import gf_on_engine as E  # noqa: E402
import gf_on_sweep as S  # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"


def sig_popgo(dd, *, k=2.0, close_frac=0.70, max_trades=3, lo=13 * 3600 + 1800, hi=E.WIN_HI):
    return C.sig_vpop(dd, k=k, close_frac=close_frac, max_trades=max_trades, lo=lo, hi=hi)


def go(days, sigs, *, stop_k=1.0, time_stop=E.WIN_HI, slip=1.0, **kw):
    return S.exec_signals(days, sigs, stop_mode="atr", stop_k=stop_k, time_stop=time_stop,
                          slip_ticks=slip, **kw)


# ────────────────────────────────────────────────────────────────────────────────────────────
# bar-executed simulator — for the 19 days that have BARS but no TICKS (the true OOS leg)
# ────────────────────────────────────────────────────────────────────────────────────────────
def simulate_bars(dd, sig_sod, direction, *, stop_pt, time_stop_sod):
    """5s bars, and when a bar's range contains the stop we assume the STOP filled — the pessimistic
    ordering. On a no-target rule that is the only ambiguity there is, and it always resolves against
    us, so the OOS number is a floor, not a hope."""
    b = dd["bars5"]
    sod = b["sod"].values
    i = int(np.searchsorted(sod, sig_sod, side="right"))
    if i >= len(sod):
        return None
    ent = float(b["open"].values[i]) + direction * E.TICK
    ent_sod = int(sod[i])
    stop = ent - direction * stop_pt
    hi, lo, cl = b["high"].values, b["low"].values, b["close"].values
    j = i
    best = ent
    while j < len(sod) and sod[j] <= time_stop_sod:
        if direction > 0:
            best = max(best, float(hi[j]))
            if lo[j] <= stop:
                return E._close(ent, ent_sod, stop, int(sod[j]), direction, E.TICK, best, "STOP")
        else:
            best = min(best, float(lo[j]))
            if hi[j] >= stop:
                return E._close(ent, ent_sod, stop, int(sod[j]), direction, E.TICK, best, "STOP")
        j += 1
    k = max(i, min(j - 1, len(sod) - 1))
    return E._close(ent, ent_sod, float(cl[k]), int(sod[k]), direction, E.TICK, best, "TIME")


def run_bars(days, dayset, *, k, close_frac, max_trades, stop_k, time_stop=E.WIN_HI):
    out = []
    for d in sorted(dayset):
        dd = days[d]
        for sod, direction, meta in sig_popgo(dd, k=k, close_frac=close_frac, max_trades=max_trades):
            mkey = sod // 60 * 60 - 60
            atr = dd["amap"].get(mkey, np.nan)
            if np.isnan(atr) or atr <= 0:
                continue
            t = simulate_bars(dd, sod, direction, stop_pt=max(stop_k * atr, 4 * E.TICK),
                              time_stop_sod=time_stop)
            if t is None:
                continue
            t.update(day=d, regime=dd["rmap"].get(mkey, "unknown"), atr=float(atr))
            out.append(t)
    return out


def main():
    days = E.load_days()
    E.attach_regimes(days)
    tick_days = {d for d in days if days[d]["ticks"] is not None}
    bar_only = {d for d in days if days[d]["ticks"] is None and len(days[d]["bars5"]) > 5000}
    res = {"tick_days": len(tick_days), "bar_only_days": len(bar_only),
           "bar_only_list": sorted(bar_only)}
    print(f"tick days {len(tick_days)}   bar-only (OOS) days {len(bar_only)}")

    # ── 1. ENTRY parameter sweep — is there a PLATEAU or a spike? ──────────────────────────
    grid = {}
    for k in (1.5, 1.75, 2.0, 2.5, 3.0):
        for cf in (0.60, 0.70, 0.80):
            for mt in (2, 3, 5):
                sg = S.gen_signals(days, sig_popgo, dict(k=k, close_frac=cf, max_trades=mt))
                sc = E.score(go(days, sg, stop_k=1.0))
                grid[f"k{k}|cf{cf}|mt{mt}"] = sc
    res["entry_grid"] = grid
    top = sorted(grid.items(), key=lambda x: -(x[1]["net"] or 0))
    print("\n── ENTRY GRID (stop 1.0xATR, flat at 15:00) — top 10 of "
          f"{len(grid)} cells ──")
    for lbl, sc in top[:10]:
        print(f"   {lbl:<22} n={sc['n']:>3}  net=${sc['net']:>+7.0f}  win={sc['win']:>5}%  $/tr={sc['per']:>+7.2f}")
    neg = sum(1 for _, sc in grid.items() if (sc["net"] or 0) < 0)
    print(f"   cells negative: {neg}/{len(grid)}   median $/tr across the grid: "
          f"{np.median([sc['per'] for sc in grid.values() if sc['per'] is not None]):+.2f}")
    res["entry_grid_summary"] = {
        "cells": len(grid), "negative_cells": neg,
        "median_per_trade": round(float(np.median([sc["per"] for sc in grid.values()
                                                   if sc["per"] is not None])), 2),
        "median_net": round(float(np.median([sc["net"] for sc in grid.values()])), 2)}

    # ── 2. the chosen spec: the grid's MEDIAN-ish cell, not its best ───────────────────────
    K, CF, MT, SK = 2.0, 0.70, 3, 1.0
    sigs = S.gen_signals(days, sig_popgo, dict(k=K, close_frac=CF, max_trades=MT))
    base = go(days, sigs, stop_k=SK)
    res["spec"] = {"k": K, "close_frac": CF, "max_trades": MT, "stop_k": SK,
                   "window": "13:30-15:00Z", "exit": "flat 15:00Z, no target"}
    res["headline"] = E.score(base)
    res["by_regime"] = E.by(base, lambda t: t["regime"])
    res["by_dir"] = E.by(base, lambda t: "LONG" if t["dir"] > 0 else "SHORT")
    res["by_day"] = E.by(base, lambda t: t["day"])
    res["by_reason"] = E.by(base, lambda t: t["reason"])
    h = res["headline"]
    print(f"\n═══ POPGO  k={K} cf={CF} mt={MT} stop={SK}xATR  flat 15:00Z")
    print(f"    n={h['n']}  net=${h['net']:+.0f}  win={h['win']}%  $/tr={h['per']:+.2f}")
    print(E.table(res["by_regime"], "regime"))
    print(E.table(res["by_dir"], "side"))
    print(E.table(res["by_reason"], "exit"))

    # ── 3. NULLS ──────────────────────────────────────────────────────────────────────────
    import gf_on_null as N
    rng = np.random.default_rng(31)
    cf_nets = [E.score(go(days, N.rand_dir(sigs, rng), stop_k=SK))["net"] for _ in range(200)]
    res["coinflip"] = {"draws": 200, "median": round(float(np.median(cf_nets)), 2),
                       "p90": round(float(np.percentile(cf_nets, 90)), 2),
                       "p99": round(float(np.percentile(cf_nets, 99)), 2),
                       "real": h["net"],
                       "pct_beating_real": round(100 * float(np.mean([x >= h["net"] for x in cf_nets])), 1)}
    res["drift_long"] = E.score(go(days, N.force_dir(sigs, +1), stop_k=SK))
    res["drift_short"] = E.score(go(days, N.force_dir(sigs, -1), stop_k=SK))
    rc = [E.score(go(days, N.rand_clock(days, sigs, rng), stop_k=SK))["net"] for _ in range(200)]
    res["random_clock"] = {"median": round(float(np.median(rc)), 2),
                           "p90": round(float(np.percentile(rc, 90)), 2),
                           "pct_beating_real": round(100 * float(np.mean([x >= h["net"] for x in rc])), 1)}
    print(f"\n    COINFLIP median ${res['coinflip']['median']:+.0f}  p90 ${res['coinflip']['p90']:+.0f}"
          f"  — {res['coinflip']['pct_beating_real']}% of 200 flips beat it")
    print(f"    drift LONG ${res['drift_long']['net']:+.0f}   drift SHORT ${res['drift_short']['net']:+.0f}")
    print(f"    RANDOM CLOCK median ${res['random_clock']['median']:+.0f}"
          f"  — {res['random_clock']['pct_beating_real']}% beat it")

    # ── 4. shift placebo, count-preserving ────────────────────────────────────────────────
    sh = {}
    for s in (-20, -15, -10, -5, 5, 10, 15, 20, 30, 45):
        sc = E.score(go(days, sigs, stop_k=SK, shift=s * 60))
        sh[f"{s:+d}min"] = sc
    res["shift_placebo"] = sh
    print("\n    shift placebo ($/trade, n): " + "  ".join(
        f"{k}={v['per']:+.1f}({v['n']})" for k, v in sh.items()))

    # ── 5. strip-the-best / LOO / OOS-half / cost ─────────────────────────────────────────
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
    res["cost_2x"] = E.score(go(days, sigs, stop_k=SK, slip=2.0))
    res["cost_4x"] = E.score(go(days, sigs, stop_k=SK, slip=4.0))
    print(f"\n    strip-1 ${res['strip_1']['net']:+.0f}  strip-3 ${res['strip_3']['net']:+.0f}  "
          f"strip-5 ${res['strip_5']['net']:+.0f}  strip-8 ${res['strip_8']['net']:+.0f}")
    print(f"    LOO worst ${res['loo']['min_net']:+.0f} ({res['loo']['n_negative']}/{res['loo']['days']} days negative)")
    print(f"    halves: ${res['half_split']['first']['net']:+.0f} / ${res['half_split']['second']['net']:+.0f}")
    print(f"    cost 2x-slip ${res['cost_2x']['net']:+.0f}   4x-slip ${res['cost_4x']['net']:+.0f}")

    # ── 6. TRUE OOS — 19 days of tape the tick study never saw, bar-executed ──────────────
    oos = run_bars(days, bar_only, k=K, close_frac=CF, max_trades=MT, stop_k=SK)
    ins = run_bars(days, tick_days, k=K, close_frac=CF, max_trades=MT, stop_k=SK)
    res["oos_bars"] = {"score": E.score(oos), "by_day": E.by(oos, lambda t: t["day"]),
                       "by_reason": E.by(oos, lambda t: t["reason"])}
    res["insample_bars_control"] = E.score(ins)
    print(f"\n    OOS ({len(bar_only)} untouched days, BAR-executed, stop wins ties): "
          f"n={res['oos_bars']['score']['n']} net=${res['oos_bars']['score']['net']:+.0f} "
          f"$/tr={res['oos_bars']['score']['per']}")
    print(f"    same engine on the tick days (control): n={res['insample_bars_control']['n']} "
          f"net=${res['insample_bars_control']['net']:+.0f} $/tr={res['insample_bars_control']['per']}")

    # ── 7. big-moves-caught vs the census ─────────────────────────────────────────────────
    res["bmc"] = S.big_moves_caught(base)
    print(f"\n    big-moves-caught {res['bmc']['caught']}/{res['bmc']['of']}  "
          f"(${res['bmc']['net_on_them']:+.0f} on them)")

    res["trades"] = base
    json.dump(res, open(f"{SEC}/gf_on_popgo.json", "w"), indent=1, default=float)
    print(f"\n→ {SEC}/gf_on_popgo.json")


if __name__ == "__main__":
    main()
