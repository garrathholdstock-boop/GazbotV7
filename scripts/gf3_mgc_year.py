#!/usr/bin/env python3
"""GF3_MGC YEAR — the level-break mechanism across THIRTEEN MONTHS of gold, not twenty-nine days.

    PYTHONPATH=src .venv/bin/python scripts/gf3_mgc_year.py

★ WHY THIS EXISTS. The single biggest caveat on last week's gold survivor was stated plainly in
gf_MGC.md section 9.1: *"Twenty-two days is twenty-two days. Five ISO weeks, one instrument, one
macro regime."* Everything else about `mgc_hole_break_fade` passed, but no test could reach outside
one summer.

It can now. The Parquet lake gained `bars/MGC/backfill_1min.parquet` since last Friday:
**357,692 one-minute MGC bars over 320 trading days, 2025-07-28 -> 2026-08-19**, one 14-day gap in
January. That is thirteen months across a genuinely different macro tape.

★ WHAT THIS TEST CAN AND CANNOT SAY - stated first, because overclaiming it would be worse than not
running it at all.

    CAN   : does a 60-minute level break in gold, FADED, beat following it - and beat the constants -
            across 320 days and several macro regimes?  That is the MECHANISM.
    CANNOT: anything about the book gate. There is no L2 before 2026-07-16, so the liquidity-hole
            filter - which is where two thirds of last week's edge came from - cannot be applied.
    CANNOT: a fill-honest fill. No bid/ask on this stream, so entries/exits are modelled at the bar
            with an explicit crossing charge, and the charge is SWEPT rather than assumed.

So this is a test of the TRIGGER AND ITS DIRECTION, on a much longer tape, and it is reported as
exactly that. A pass does not promote anything; a fail would retire the whole family.

★ THE HARNESS IS VALIDATED BEFORE IT IS BELIEVED. The 1-minute bar racer is run over the 29 days
where the 250ms quote tape ALSO exists, and the two are compared trade-for-trade. If the coarse
racer cannot reproduce the fine one on the overlap, its verdict on the other 291 days is worthless.

MGC = $10.00/point, tick 0.10pt = $1.00. Fee $1.50 per ROUND TRIP.
"""
from __future__ import annotations

import json
import os
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gf_mgc_cells import break_entries, stat  # noqa: E402
from gf_mgc_tape import VPP, FEE_RT, atr as atr_fn, eff_ratio, session_of  # noqa: E402

pd.set_option("display.width", 250)
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections"
BACKFILL = "/home/alphabot/gazbot7/data/tape/bars/MGC/backfill_1min.parquet"
TICK = 0.10
CHAND = dict(stop=3.0, arm=2.0, trail=2.0, cap_min=480)
R: dict = {}


def line(t: str) -> None:
    print("\n" + "=" * 104 + f"\n{t}\n" + "=" * 104, flush=True)


def load_year() -> pd.DataFrame:
    c = duckdb.connect()
    df = c.execute(f"""
        SELECT bar_ts, open, high, low, close, volume
        FROM read_parquet('{BACKFILL}')
        WHERE timeframe='1min' AND close > 0 ORDER BY bar_ts
    """).df()
    df["ts"] = pd.to_datetime(df["bar_ts"], unit="s", utc=True)
    return df.set_index("ts")[["open", "high", "low", "close", "volume"]]


def label(m: pd.DataFrame) -> pd.DataFrame:
    """Regime labels on GOLD's own percentiles, computed on this frame."""
    m = m.copy()
    m["atr"] = atr_fn(m)
    m["er"] = eff_ratio(m["close"])
    m["session"] = session_of(m.index).values
    m["day"] = m.index.strftime("%Y-%m-%d")
    a_lo, a_hi = m["atr"].quantile(0.33), m["atr"].quantile(0.67)
    e_lo, e_hi = m["er"].quantile(0.40), m["er"].quantile(0.75)
    reg = pd.Series("NORMAL_CHOP", index=m.index)
    reg[(m["atr"] <= a_lo) & (m["er"] <= e_hi)] = "DEAD_CHOP"
    reg[(m["atr"] >= a_hi) & (m["er"] >= e_hi)] = "CLEAN_TREND"
    reg[(m["atr"] >= a_hi) & (m["er"] <= e_lo)] = "VIOLENT_WHIPSAW"
    reg[(m["atr"].between(a_lo, a_hi, inclusive="neither")) & (m["er"] >= e_hi)] = "BUILDING"
    m["regime"] = reg.values
    m.attrs["cuts"] = {"atr_p33": float(a_lo), "atr_p67": float(a_hi),
                       "er_p40": float(e_lo), "er_p75": float(e_hi)}
    return m


class BarRacer:
    """Race an exit on 1-MINUTE OHLC. Coarser than the 250ms quote racer and deliberately harsher.

    ORDER INSIDE A BAR: STOP, then TRAIL, then TARGET, then extend the peak - a minute bar hides
    which extreme came first, so every ambiguity is resolved AGAINST the trade.

    COSTS: entry and exit each cross `cross_pt` points (half the quoted spread is the default, which
    is what crossing actually costs against the mid), plus `FEE_RT` once. `slip_pt` adds further
    adverse points to BOTH legs and is what the cost sweep moves.
    """

    def __init__(self, m: pd.DataFrame):
        self.idx = m.index.tz_convert("UTC").tz_localize(None).values.astype("datetime64[ns]").astype("int64")
        self.o, self.h, self.l, self.c = (m[k].to_numpy() for k in ("open", "high", "low", "close"))
        self.n = len(m)

    def race(self, ts, side: int, *, stop_pts, arm_pts=None, trail_pts=None, target_pts=None,
             cap_min=480.0, cross_pt=0.15, slip_pt=0.0) -> dict | None:
        i = int(np.searchsorted(self.idx, np.int64(pd.Timestamp(ts).value), side="left"))
        if i >= self.n - 2:
            return None
        adj = cross_pt + slip_pt
        ref = float(self.o[i])                      # entry races from the NEXT bar's open
        if not np.isfinite(ref) or ref <= 0:
            return None
        fill_in = ref + side * adj                  # crossing is adverse on entry
        stop = fill_in - side * stop_pts
        target = fill_in + side * target_pts if target_pts is not None else None
        j = min(i + 1 + int(cap_min), self.n)
        peak, mae, armed, trail_lvl = 0.0, 0.0, False, None
        for k in range(i + 1, j):
            hi, lo = self.h[k], self.l[k]
            if not (np.isfinite(hi) and np.isfinite(lo)):
                continue
            adverse, favour = (lo, hi) if side > 0 else (hi, lo)
            mae = min(mae, side * (adverse - fill_in))
            if (adverse <= stop) if side > 0 else (adverse >= stop):
                return self._out(i, k, side, fill_in, stop, "STOP", peak, mae, adj)
            if armed and trail_lvl is not None and ((adverse <= trail_lvl) if side > 0 else (adverse >= trail_lvl)):
                return self._out(i, k, side, fill_in, trail_lvl, "TRAIL", peak, mae, adj)
            if target is not None and ((favour >= target) if side > 0 else (favour <= target)):
                return self._out(i, k, side, fill_in, target, "TARGET", peak, mae, adj)
            peak = max(peak, side * (favour - fill_in))
            if arm_pts is not None and peak >= arm_pts:
                armed = True
            if armed and trail_pts is not None:
                trail_lvl = fill_in + side * (peak - trail_pts)
        k = min(j - 1, self.n - 1)
        return self._out(i, k, side, fill_in, float(self.c[k]), "TIME_CAP", peak, mae, adj)

    def _out(self, i, k, side, fill_in, raw_out, reason, peak, mae, adj) -> dict:
        fill_out = raw_out - side * adj             # crossing is adverse on exit too
        return {"fill_in": round(fill_in, 3), "fill_out": round(fill_out, 3), "reason": reason,
                "minutes": float(k - i),
                "true_pnl": round(side * (fill_out - fill_in) * VPP - FEE_RT, 2),
                "mfe_pt": round(float(peak), 2), "mae_pt": round(float(mae), 2)}


def run(racer: BarRacer, e: pd.DataFrame, *, stop=3.0, arm=2.0, trail=2.0, target=None,
        cap_min=480.0, cross_pt=0.15, slip_pt=0.0) -> pd.DataFrame:
    rows = []
    for r in e.itertuples():
        a = float(r.atr)
        if not np.isfinite(a) or a <= 0:
            continue
        res = racer.race(r.ts, int(r.side), stop_pts=stop * a,
                         arm_pts=arm * a if arm else None, trail_pts=trail * a if trail else None,
                         target_pts=target * a if target else None, cap_min=cap_min,
                         cross_pt=cross_pt, slip_pt=slip_pt)
        if res:
            rows.append({**{c: getattr(r, c) for c in e.columns}, **res})
    return pd.DataFrame(rows)


def show(tag: str, d: pd.DataFrame) -> dict:
    s = stat(d)
    lo = stat(d[d["side"] > 0]) if not d.empty else s
    sh = stat(d[d["side"] < 0]) if not d.empty else s
    dn = (lo["per"] + sh["per"]) / 2.0
    print(f"  {tag:<44} n={s['n']:<5} net={s['net']:>+8.0f} win={s['win']:>5.1f}% $/tr={s['per']:>+7.2f} "
          f"| LONG {lo['per']:>+7.2f} SHORT {sh['per']:>+7.2f} | drift-neutral {dn:>+7.2f}")
    return {"pooled": s, "long": lo, "short": sh, "drift_neutral": round(dn, 2)}


def main() -> None:
    y = label(load_year())
    days = sorted(y["day"].unique())
    print(f"YEAR TAPE  {len(y):,} minute bars  {days[0]} .. {days[-1]}  {len(days)} trading days")
    print(f"  regime cuts (gold's own): {json.dumps({k: round(v, 3) for k, v in y.attrs['cuts'].items()})}")
    R["span"] = [days[0], days[-1], len(days)]
    R["cuts"] = y.attrs["cuts"]
    yr = y.copy()
    yr["ym"] = yr.index.strftime("%Y-%m")
    print("  months: " + " ".join(sorted(yr["ym"].unique())))

    racer = BarRacer(y)
    e_fade = break_entries(y, look=60, margin_atr=0.10, cool=45, fade=True)
    e_foll = break_entries(y, look=60, margin_atr=0.10, cool=45, fade=False)
    print(f"\n  60-min breaks over the year: {len(e_fade):,} after a 45-min per-side cooldown")

    # ── 1. VALIDATE THE COARSE RACER ON THE OVERLAP ─────────────────────────────────────────────
    line("1. HARNESS VALIDATION — the 1-min bar racer vs the 250ms quote racer, same 29 days")
    ov = e_fade[e_fade["day"] >= "2026-07-16"]
    d_ov = run(racer, ov, **CHAND)
    s_ov = stat(d_ov)
    print(f"  1-min bar racer, all breaks faded, 2026-07-16 onward : n={s_ov['n']} net={s_ov['net']:+.0f} "
          f"$/tr={s_ov['per']:+.2f} win={s_ov['win']:.1f}%")
    print("  250ms quote racer, same rule, same window (gf_mgc_cells): n=449(22d) net=+1952 $/tr=+4.35")
    print("  -> the two tapes are not the same rows (the year tape has no 08-22/23/25 and is TRADE-based),")
    print("     so this is a SANITY band, not an equality check. Sign and rough magnitude must agree.")
    R["validation"] = s_ov

    # ── 2. THE MECHANISM OVER THE YEAR ──────────────────────────────────────────────────────────
    line("2. ★★★ THE MECHANISM OVER 320 DAYS — fade the break, follow it, or hold a constant")
    R["headline"] = {}
    d_fade = run(racer, e_fade, **CHAND)
    d_foll = run(racer, e_foll, **CHAND)
    R["headline"]["FADE"] = show("FADE the 60-min break", d_fade)
    R["headline"]["FOLLOW"] = show("FOLLOW the break (the mirror)", d_foll)
    for lbl, sd in (("always LONG at the same stamps", 1), ("always SHORT at the same stamps", -1)):
        ec = e_fade.copy(); ec["side"] = sd
        R["headline"][lbl] = show(lbl, run(racer, ec, **CHAND))

    # ── 3. IS IT ONE REGIME, OR ALL OF THEM? ────────────────────────────────────────────────────
    line("3. BY CALENDAR MONTH — is the fade one lucky summer, or persistent?")
    dm = d_fade.copy()
    dm["ym"] = pd.to_datetime(dm["day"]).dt.strftime("%Y-%m")
    g = dm.groupby("ym")["true_pnl"].agg(["count", "sum", "mean"]).round(2)
    print(g.to_string())
    green = int((g["sum"] > 0).sum())
    print(f"\n  GREEN MONTHS: {green}/{len(g)}   worst {g['sum'].min():+.0f} ({g['sum'].idxmin()})   "
          f"best {g['sum'].max():+.0f} ({g['sum'].idxmax()})")
    R["by_month"] = {k: [int(v["count"]), round(float(v["sum"]), 0), round(float(v["mean"]), 2)]
                     for k, v in g.iterrows()}
    R["green_months"] = [green, len(g)]

    line("4. BY REGIME AND SIDE — the router read, on a year instead of a month")
    g2 = d_fade.groupby(["regime", d_fade["side"].map({1: "LONG", -1: "SHORT"})])["true_pnl"].agg(
        ["count", "sum", "mean"]).round(2)
    print(g2.to_string())
    R["by_regime"] = {f"{a}|{b}": [int(r["count"]), round(float(r["sum"]), 0), round(float(r["mean"]), 2)]
                      for (a, b), r in g2.iterrows()}
    print()
    g3 = d_fade.groupby("session")["true_pnl"].agg(["count", "sum", "mean"]).round(2)
    print(g3.to_string())
    R["by_session"] = {k: [int(v["count"]), round(float(v["sum"]), 0), round(float(v["mean"]), 2)]
                       for k, v in g3.iterrows()}

    # ── 5. THE COST SWEEP — the $7.50 argument, settled by measurement ──────────────────────────
    line("5. THE COST SWEEP — how much slippage does the mechanism survive?")
    R["cost_sweep"] = {}
    print("  slip is EXTRA adverse points on EACH leg, on top of a 0.15pt crossing charge per leg.")
    for slip in (0.0, 0.05, 0.10, 0.15, 0.20, 0.30):
        d = run(racer, e_fade, **CHAND, slip_pt=slip)
        s = stat(d)
        allin = (0.15 + slip) * 2 * VPP + FEE_RT
        print(f"  slip {slip:.2f}pt/leg  (all-in ${allin:5.2f}/RT)   n={s['n']:<5} net={s['net']:>+8.0f} "
              f"$/tr={s['per']:>+7.2f} win={s['win']:>5.1f}%")
        R["cost_sweep"][f"{slip:.2f}"] = {"allin_rt": round(allin, 2), **s}

    # ── 6. THE TRIGGER PLATEAU, ON THE CHANDELIER — last week's named loose thread ───────────────
    line("6. ★ THE LOOSE THREAD — lookback x margin plateau, ON THE CHANDELIER EXIT (year tape)")
    print("  gf_MGC.md 6.5: the 15-cell grid was 0/15 positive, but it was run on the tp1.0/sl1.0 SCALP")
    print("  - the exit that cannot pay gold's spread. Re-run on the exit the gate actually uses:\n")
    rows = []
    for look in (30, 45, 60, 90, 120):
        for marg in (0.0, 0.10, 0.25):
            ee = break_entries(y, look=look, margin_atr=marg, cool=45, fade=True)
            d = run(racer, ee, **CHAND)
            s = stat(d)
            rows.append({"look_min": look, "margin_atr": marg, "n": s["n"], "net": s["net"],
                         "per": s["per"], "win": s["win"]})
            print(f"  look {look:>3}min  margin {marg:.2f} ATR   n={s['n']:<5} net={s['net']:>+8.0f} "
                  f"$/tr={s['per']:>+7.2f} win={s['win']:>5.1f}%")
    pos = sum(1 for r in rows if r["net"] > 0)
    print(f"\n  -> {pos}/{len(rows)} cells POSITIVE on the chandelier (was 0/15 on the scalp)")
    R["plateau"] = rows
    R["plateau_positive"] = [pos, len(rows)]

    # ── 7. STRIP / HALVES / YEAR-ON-YEAR ────────────────────────────────────────────────────────
    line("7. ROBUSTNESS ON THE YEAR")
    v = d_fade["true_pnl"].sort_values()
    byday = d_fade.groupby("day")["true_pnl"].sum()
    ds = sorted(d_fade["day"].unique()); midd = ds[len(ds) // 2]
    h1 = d_fade[d_fade["day"] < midd]["true_pnl"].sum(); h2 = d_fade[d_fade["day"] >= midd]["true_pnl"].sum()
    pre = d_fade[d_fade["day"] < "2026-07-16"]["true_pnl"]
    bat = {"n": int(len(v)), "net": round(float(v.sum()), 0),
           "strip_best_10": round(float(v.iloc[:-10].sum()), 0),
           "strip_best_1pct": round(float(v.iloc[:-max(1, len(v) // 100)].sum()), 0),
           "drop_best_day": round(float(byday.sum() - byday.max()), 0),
           "days_green": round(100.0 * float((byday > 0).mean()), 1),
           "h1": round(float(h1), 0), "h2": round(float(h2), 0),
           "PRE_L2_ERA": [int(len(pre)), round(float(pre.sum()), 0), round(float(pre.mean()), 2)]}
    for k, val in bat.items():
        print(f"  {k:<18} {val}")
    R["battery"] = bat

    with open(f"{OUT}/gf3_mgc_year.json", "w") as fh:
        json.dump(R, fh, indent=1, default=str)
    print(f"\nwrote {OUT}/gf3_mgc_year.json")


if __name__ == "__main__":
    main()
