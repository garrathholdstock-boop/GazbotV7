#!/usr/bin/env python3
"""GF_MGC VERIFY — the adversarial round on the gold 2x2.

    PYTHONPATH=src .venv/bin/python scripts/gf_mgc_verify.py

★ WHY THIS FILE EXISTS. `gf_mgc_cells.py` found that the break-fade entry is -$4.15/trade on a tight
scalp and +$4.35/trade on a wide chandelier — the SAME 449 entries, only the exit changed. That is
either a real finding about the SHAPE gold's snap-backs have, or it is the oldest trap in the book:
a wide-stop long-hold exit on a tape that closed UP on 13 of 22 days makes money from the drift no
matter what the entry says. This file settles it, and the design is deliberately hostile:

  1. THE MIRROR. Run the identical chandelier on the OPPOSITE side of the identical rows. If
     FOLLOW is green too, the entry is worth nothing and the exit is harvesting drift and vol.
  2. THE PLACEBO. Same count, same days, same hours, same side mix, random minutes, same exit.
  3. THE CONSTANT. always-long and always-short, entered at the same timestamps, same exit.
  4. THE DRIFT-NEUTRAL READ. Score each side separately AND net the sample's own drift out, so a
     long book cannot be credited for gold simply going up.

Everything is spread-honest: MGC = $10.00/pt, spread ~0.30pt crossed on BOTH legs, fee $1.50/RT.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gf_mgc_cells import (  # noqa: E402
    Racer, battery, break_entries, cooldown, five_second, line, placebo, run_entries,
    side_split, stat,
)
from gf_mgc_tape import FEE_RT, VPP, build_tape  # noqa: E402

pd.set_option("display.width", 260)
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections"
R: dict = {}

# The exit that turned the fade green in gf_mgc_cells.py [4b]. Fixed here so every test below is
# run against the SAME exit and only one thing varies at a time.
CHAND = dict(stop=3.0, arm=2.0, trail=2.0, cap_min=480)


# ════════════════════════════════════════════════════════════════════════════════════════════════
def coil_entries(m: pd.DataFrame, *, coil_min: int = 20, norm_min: int = 120,
                 compress: float = 0.60, edge_pct: float = 0.85, cool: int = 30) -> pd.DataFrame:
    """THE COIL BOUNCER, re-derived on the 22-day quote tape and split by side.

    A 20-minute range that has collapsed to <= 60% of its own 2-hour median, with price at the
    outer 15% of that range -> trade back toward the middle. Reversion by COMPRESSION, which is a
    different claim from reversion by EXTENSION (that one is refuted: Hurst 0.489 on our tape).

    Entry at ts+60s — the coil's range is only known at the bar's close, and racing from `ts`
    replays the decision minute (it cost this gate +$906 -> +$470 on 2026-08-14).
    """
    d = m.copy()
    hi = d["high"].rolling(coil_min).max()
    lo = d["low"].rolling(coil_min).min()
    rng = hi - lo
    norm = rng.rolling(norm_min).median()
    pos = (d["close"] - lo) / rng.replace(0, np.nan)
    ok = (rng <= compress * norm) & rng.notna() & norm.notna() & d["atr"].notna()
    up_edge = ok & (pos >= edge_pct)
    dn_edge = ok & (pos <= 1 - edge_pct)
    rows = []
    for ts, u, v in zip(d.index, up_edge.to_numpy(), dn_edge.to_numpy()):
        if not (u or v):
            continue
        rows.append({"ts": ts + pd.Timedelta(seconds=60), "side": -1 if u else 1,
                     "atr": float(d.at[ts, "atr"]), "regime": d.at[ts, "regime"],
                     "session": d.at[ts, "session"], "day": d.at[ts, "day"],
                     "er": float(d.at[ts, "er"]) if np.isfinite(d.at[ts, "er"]) else np.nan})
    e = pd.DataFrame(rows)
    return cooldown(e, cool) if not e.empty else e


def constant_at(e: pd.DataFrame, side: int) -> pd.DataFrame:
    """The same timestamps, but always the same direction. Isolates the DRIFT in the sample."""
    c = e.copy()
    c["side"] = side
    return c


def drift_neutral(d: pd.DataFrame, col: str = "true_pnl") -> float:
    """(long book + short book) / 2 — the part of the P&L that is NOT the sample's direction.

    If a candidate's whole result is that gold went up, this collapses toward zero; if the two
    sides both earn, it survives. It is the cheapest guard against the confound the map named as
    the single biggest one in every gold study.
    """
    lo = d[d["side"] > 0][col]
    sh = d[d["side"] < 0][col]
    if len(lo) == 0 or len(sh) == 0:
        return float("nan")
    return round((float(lo.mean()) + float(sh.mean())) / 2.0, 2)


def cost_stress(d: pd.DataFrame) -> dict:
    """Three cost worlds. The middle one is the truth; the others bracket it.

    desk_pnl  mid-to-mid, $1.50 fee   — the convention every previous gold study used
    true_pnl  crosses both legs        — what the live desk's marketable-limit/MKT pair actually pays
    stress    true_pnl minus one more tick (0.10pt = $1.00) each way — a bad-fill world
    """
    if d.empty:
        return {}
    n = len(d)
    return {
        "desk_$1.50_mid": round(float(d["desk_pnl"].sum()), 0),
        "true_spread_crossed": round(float(d["true_pnl"].sum()), 0),
        "plus_1tick_each_way": round(float(d["true_pnl"].sum()) - 2.0 * n, 0),
        "per_tr_true": round(float(d["true_pnl"].mean()), 2),
        "per_tr_stress": round(float(d["true_pnl"].mean()) - 2.0, 2),
    }


def main() -> None:
    m, q = build_tape()
    f = five_second(q)
    racer = Racer(f)
    print(f"tape {len(m):,} min · {m['day'].nunique()} days · {len(f):,} 5s bid/ask bars\n")

    ef = break_entries(m, fade=True)
    ec = break_entries(m, fade=False)

    # ── 1. THE MIRROR ───────────────────────────────────────────────────────────────────────────
    print("=" * 126)
    print("[1] ★★★ THE MIRROR TEST — the same 449 break rows, the same wide chandelier")
    print("    (stop 3 ATR · arm 2 ATR · trail 2 ATR · 480min cap), traded BOTH WAYS.")
    print("    If FOLLOW is green as well, the exit is harvesting drift and the entry is worthless.")
    print("=" * 126)
    rf = run_entries(racer, ef, **CHAND)
    rc = run_entries(racer, ec, **CHAND)
    cl = run_entries(racer, constant_at(ef, 1), **CHAND)
    cs = run_entries(racer, constant_at(ef, -1), **CHAND)
    for lbl, d in (("FADE the break   (reversion)", rf), ("FOLLOW the break (momentum)", rc),
                   ("always LONG at the same stamps", cl), ("always SHORT at the same stamps", cs)):
        s = side_split(d)
        print(line(lbl, stat(d),
                   f"LONG ${s['LONG']['per']:>6.2f}  SHORT ${s['SHORT']['per']:>6.2f}  "
                   f"drift-neutral ${drift_neutral(d)}"))
    R["mirror"] = {"fade": stat(rf), "follow": stat(rc), "always_long": stat(cl),
                   "always_short": stat(cs), "fade_sides": side_split(rf),
                   "follow_sides": side_split(rc),
                   "fade_drift_neutral": drift_neutral(rf), "follow_drift_neutral": drift_neutral(rc)}

    # ── 2. THE PLACEBO ON THE WINNING EXIT ──────────────────────────────────────────────────────
    print("\n" + "=" * 126)
    print("[2] ★★★ THE PLACEBO ON THE WINNING EXIT — 30 draws of the same count, same days, same")
    print("    hours, same side mix, at RANDOM minutes, through the identical chandelier.")
    print("=" * 126)
    for lbl, sub in (("ALL", rf), ("REVERSION-SHORT", rf[rf["side"] < 0]), ("REVERSION-LONG", rf[rf["side"] > 0])):
        p = placebo(racer, sub, m, n_runs=30, **CHAND)
        print(f"    {lbl:<17} {p}")
        R.setdefault("placebo_chand", {})[lbl] = p

    # ── 3. THE BATTERY ON THE WINNING EXIT ──────────────────────────────────────────────────────
    print("\n" + "=" * 126)
    print("[3] THE ROBUSTNESS BATTERY on the fade + chandelier, per cell")
    print("=" * 126)
    for lbl, sub in (("ALL", rf), ("REVERSION-SHORT", rf[rf["side"] < 0]), ("REVERSION-LONG", rf[rf["side"] > 0])):
        print(f"\n  {lbl}: {stat(sub)}")
        for k, v in battery(sub).items():
            print(f"      {k:<14} {v}")
        print(f"      {'cost_stress':<14} {cost_stress(sub)}")
        R.setdefault("battery_chand", {})[lbl] = {"stat": stat(sub), **battery(sub),
                                                  "cost": cost_stress(sub)}

    # ── 4. THE HOME REGIME ON THE WINNING EXIT ──────────────────────────────────────────────────
    print("\n" + "=" * 126)
    print("[4] ★ HOME REGIME on the winning exit — the router rule has to be readable off this")
    print("=" * 126)
    for key in ("regime", "session"):
        rows = []
        for (k, sd), g in rf.groupby([key, rf["side"].map({1: "LONG", -1: "SHORT"})]):
            rows.append({key: k, "side": sd, **stat(g)})
        t = pd.DataFrame(rows).sort_values(["side", "per"], ascending=[True, False])
        print(f"\n  by {key}:")
        print(t.to_string(index=False))
        R.setdefault("home_chand", {})[key] = rows

    # ── 5. THE EXIT PLATEAU ─────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 126)
    print("[5] EXIT PLATEAU around the winner — a single green cell in a red field is a fit")
    print("=" * 126)
    rows = []
    for stop_a in (2.0, 2.5, 3.0, 4.0, 5.0):
        for arm in (1.5, 2.0, 2.5):
            for trail in (1.5, 2.0, 2.5):
                r = run_entries(racer, ef, stop=stop_a, arm=arm, trail=trail, cap_min=480)
                s = side_split(r)
                rows.append({"stop": stop_a, "arm": arm, "trail": trail, "n": len(r),
                             "net": stat(r)["net"], "per": stat(r)["per"], "win": stat(r)["win"],
                             "LONG$/tr": s["LONG"]["per"], "SHORT$/tr": s["SHORT"]["per"]})
    pl = pd.DataFrame(rows)
    print(pl.to_string(index=False))
    print(f"\n  positive cells: {int((pl['per'] > 0).sum())}/{len(pl)}   "
          f"LONG positive {int((pl['LONG$/tr'] > 0).sum())}/{len(pl)}   "
          f"SHORT positive {int((pl['SHORT$/tr'] > 0).sum())}/{len(pl)}")
    R["exit_plateau"] = rows

    # ── 6. THE CAP SWEEP — how long does the snap-back need? ────────────────────────────────────
    print("\n" + "=" * 126)
    print("[6] HOLD-TIME — the 08-14 session found an 8h-to-12h boundary on a different entry.")
    print("    Here it is measured on this one, chandelier held constant.")
    print("=" * 126)
    rows = []
    for cap in (60, 120, 240, 360, 480, 720):
        r = run_entries(racer, ef, stop=3.0, arm=2.0, trail=2.0, cap_min=cap)
        s = side_split(r)
        rows.append({"cap_min": cap, **stat(r), "LONG$/tr": s["LONG"]["per"],
                     "SHORT$/tr": s["SHORT"]["per"],
                     "median_mins_held": round(float(r["minutes"].median()), 1)})
    print(pd.DataFrame(rows).to_string(index=False))
    R["holdtime"] = rows

    # ── 7. THE COIL BOUNCER, SPLIT BY SIDE ──────────────────────────────────────────────────────
    print("\n" + "=" * 126)
    print("[7] THE OTHER REVERSION SHAPE — the COIL BOUNCER, re-derived on the 22-day quote tape")
    print("    and split by side (2026-08-14 reported it pooled, which hides a one-sided gate).")
    print("=" * 126)
    ecoil = coil_entries(m)
    print(f"  n={len(ecoil)} coil-edge events "
          f"({int((ecoil['side'] > 0).sum())} long, {int((ecoil['side'] < 0).sum())} short)")
    for lbl, kw in (("scalp to the coil mid (tp 0.75 / sl 1.0 ATR, 60m)",
                     dict(stop=1.0, target=0.75, cap_min=60)),
                    ("tight scalp (tp 0.5 / sl 0.5 ATR, 60m)", dict(stop=0.5, target=0.5, cap_min=60)),
                    ("the fade's chandelier (3/2/2, 480m)", CHAND)):
        r = run_entries(racer, ecoil, **kw)
        s = side_split(r)
        print(line(f"  {lbl}", stat(r),
                   f"LONG ${s['LONG']['per']:>6.2f}  SHORT ${s['SHORT']['per']:>6.2f}  "
                   f"desk${stat(r, 'desk_pnl')['net']:>7.0f}"))
        R.setdefault("coil", {})[lbl] = {"all": stat(r), "sides": s,
                                         "desk": stat(r, "desk_pnl")}
    rbest = run_entries(racer, ecoil, stop=1.0, target=0.75, cap_min=60)
    print("\n  coil battery (scalp form):")
    for k, v in battery(rbest).items():
        print(f"      {k:<14} {v}")
    print(f"      {'cost_stress':<14} {cost_stress(rbest)}")
    p = placebo(racer, rbest, m, n_runs=20, stop=1.0, target=0.75, cap_min=60)
    print(f"      {'placebo':<14} {p}")
    R["coil_battery"] = {**battery(rbest), "cost": cost_stress(rbest), "placebo": p}

    json.dump(R, open(f"{OUT}/gf_mgc_verify.json", "w"), indent=1, default=str)
    print(f"\nJSON -> {OUT}/gf_mgc_verify.json")


if __name__ == "__main__":
    main()
