#!/usr/bin/env python3
"""GF2 — THE SESSION CELLS. Gold's own clock, over 184 sessions instead of 16.

    PYTHONPATH=src .venv/bin/python scripts/gf2_mgc_session.py

★ WHY THIS RUN. `docs/MGC_LEADS_2026-08-14.md` calls the MGC DAY RIDER "the most promising shape
found" and shows a 15-cell sensitivity PLATEAU, all cells positive, +$1,742 against an always_short
control of +$1,502. That was **16 sessions, 8 of which fired.** A 15-cell plateau on 8 firings is
not a plateau, it is one week of gold wearing a grid. The same document's London-open FADE is n=16.
Neither can be believed or disbelieved at that size — which is exactly why the twelve-month tape
matters more here than anywhere else in this section.

Three gold-native session mechanics, all invented from the instrument's own structure, none of them
an MNQ gate in a hat:

  CELL SET 1  SESSION DRIFT RIDER  — after the COMEX open, if the session's own move is both LARGE
              (in gold ATR) and EFFICIENT (gold's own ER percentile), ride it to the clock. This is
              the MOMENTUM shape at the timescale gold's runs actually live on (census: four of the
              week's five biggest runs lasted 2-12 HOURS, median ER 0.23).
  CELL SET 2  OVERNIGHT-RANGE BREAK — gold builds a range in Asia/London while the US sleeps, then
              COMEX opens. Does the first break of that range GO or FAIL? Both directions, both
              answers, scored separately.
  CELL SET 3  THE EXPANSION QUESTION — "if direction is unpredictable but SIZE is predictable, a
              volatility-shaped entry may beat a directional one". Tested explicitly, as the brief
              demands: does compression predict expansion on gold, and can a straddle pay for
              itself?

Everything is scored against THE BEST CONSTANT on the same rows (always_long / always_short), never
against zero and never against a coinflip.
"""
from __future__ import annotations

import json, os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from gf2_mgc_histlab import BarRacer, VPP, FEE_RT, SPREAD_PT, line, load_clean, run, stat  # noqa: E402

pd.set_option("display.width", 300)
OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf2"
R: dict = {}
US_OPEN, US_FLAT = 13 * 60 + 30, 20 * 60 + 40
LDN_OPEN = 6 * 60


def mod(idx):
    return idx.hour * 60 + idx.minute


def day_frames(m):
    """Per-day view with a minute-of-day column, only days that actually cover the US session."""
    out = {}
    for d, x in m.groupby("day"):
        md = mod(x.index)
        if ((md >= US_OPEN) & (md <= US_FLAT)).sum() < 300:
            continue
        x = x.copy(); x["mod"] = md
        out[d] = x
    return out


def flat_at(x, i_in, side, fill_in, flat_mod):
    """Hold to the clock. Returns (fill_out, minutes, mfe, mae) - no stop, the pure drift number."""
    seg = x.iloc[i_in:]
    seg = seg[seg["mod"] <= flat_mod]
    if len(seg) < 2:
        return None
    ex_hi = side * (seg["high"].max() - fill_in)
    ex_lo = side * (seg["low"].min() - fill_in)
    return (float(seg["close"].iloc[-1]), len(seg),
            max(ex_hi, ex_lo, 0.0), min(ex_hi, ex_lo, 0.0))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# CELL SET 1 — the session drift rider
# ══════════════════════════════════════════════════════════════════════════════════════════════
def drift_trades(frames, *, anchor=US_OPEN, arm_after=30, window=150, er_min=0.155,
                 net_atr=2.0, flat_mod=US_FLAT, stop_atr=None, cap_mod=None):
    rows = []
    for d, x in frames.items():
        s = x[(x["mod"] >= anchor) & (x["mod"] <= anchor + window)]
        if len(s) < arm_after + 5:
            continue
        op = float(s["close"].iloc[0])
        cl = s["close"].to_numpy()
        path = np.abs(np.diff(cl, prepend=cl[0])).cumsum()
        net = cl - op
        atrv = s["atr"].to_numpy()
        fired = None
        for k in range(arm_after, len(s)):
            if not np.isfinite(atrv[k]) or atrv[k] <= 0 or path[k] <= 0:
                continue
            er = abs(net[k]) / path[k]
            if er >= er_min and abs(net[k]) >= net_atr * atrv[k]:
                fired = k
                break
        if fired is None:
            continue
        side = int(np.sign(net[fired])) or 1
        ts = s.index[fired]
        i_in = int(np.searchsorted(x.index.values, ts.to_datetime64())) + 1
        if i_in >= len(x) - 2:
            continue
        fill_in = float(x["open"].iloc[i_in]) + side * SPREAD_PT / 2
        res = flat_at(x, i_in, side, fill_in, flat_mod)
        if res is None:
            continue
        px_out, mins, mfe, mae = res
        if stop_atr is not None:
            seg = x.iloc[i_in:]; seg = seg[seg["mod"] <= flat_mod]
            stop = fill_in - side * stop_atr * atrv[fired]
            adverse = seg["low"] if side > 0 else seg["high"]
            hit = np.nonzero((adverse.to_numpy() <= stop) if side > 0 else (adverse.to_numpy() >= stop))[0]
            if len(hit):
                px_out, mins = stop, int(hit[0])
        fill_out = px_out - side * SPREAD_PT / 2
        rows.append({"day": d, "ts": ts, "side": side, "er": abs(net[fired]) / path[fired],
                     "net_atr": abs(net[fired]) / atrv[fired], "atr": atrv[fired],
                     "regime": s["regime"].iloc[fired], "session": s["session"].iloc[fired],
                     "minutes": mins, "mfe_pt": mfe, "mae_pt": mae,
                     "true_pnl": round(side * (fill_out - fill_in) * VPP - FEE_RT, 2)})
    return pd.DataFrame(rows)


def constant(frames, side, *, anchor=US_OPEN, arm_after=30, flat_mod=US_FLAT):
    """The control that must be beaten: take the SAME clock slot every single day, one direction."""
    rows = []
    for d, x in frames.items():
        s = x[(x["mod"] >= anchor + arm_after)]
        if len(s) < 5:
            continue
        ts = s.index[0]
        i_in = int(np.searchsorted(x.index.values, ts.to_datetime64()))
        fill_in = float(x["open"].iloc[i_in]) + side * SPREAD_PT / 2
        res = flat_at(x, i_in, side, fill_in, flat_mod)
        if res is None:
            continue
        px_out, mins, mfe, mae = res
        fill_out = px_out - side * SPREAD_PT / 2
        rows.append({"day": d, "ts": ts, "side": side, "minutes": mins, "mfe_pt": mfe,
                     "mae_pt": mae, "atr": float(x["atr"].iloc[i_in]),
                     "regime": x["regime"].iloc[i_in], "session": x["session"].iloc[i_in],
                     "true_pnl": round(side * (fill_out - fill_in) * VPP - FEE_RT, 2)})
    return pd.DataFrame(rows)


def batt(d):
    if d is None or len(d) < 8:
        return {}
    v = d["true_pnl"].sort_values()
    byday = d.groupby("day")["true_pnl"].sum()
    mo = d.groupby(d["day"].str[:7])["true_pnl"].sum()
    days = sorted(d["day"].unique()); mid = days[len(days) // 2]
    return {"strip_best3": round(float(v.iloc[:-3].sum()), 0),
            "loo_best_day": round(float(byday.sum() - byday.max()), 0),
            "days_green%": round(100 * float((byday > 0).mean()), 1),
            "months_green": f"{int((mo>0).sum())}/{len(mo)}",
            "h1": round(float(d[d['day'] < mid]['true_pnl'].sum()), 0),
            "h2": round(float(d[d['day'] >= mid]['true_pnl'].sum()), 0)}


def main():
    m = load_clean()
    frames = day_frames(m)
    print("=" * 140)
    print(f"SESSION LAB — {len(frames)} gold sessions with a full US block, "
          f"{min(frames)} .. {max(frames)}")
    print("=" * 140)

    # ── the constants first: what does simply being in gold pay? ─────────────────────────────
    print("\nTHE CONSTANTS — hold from 14:00 UTC to the 20:40 flat, every single day, no signal:")
    cons = {}
    for lbl, sd in (("always LONG", 1), ("always SHORT", -1)):
        c = constant(frames, sd)
        cons[lbl] = c
        print(line(lbl, stat(c), f"batt {batt(c)}"))
    R["constants"] = {k: stat(v) for k, v in cons.items()}
    best_const = max(cons.items(), key=lambda kv: stat(kv[1])["net"])
    print(f"  -> the bar to clear is {best_const[0]} at ${stat(best_const[1])['net']:,.0f} "
          f"({stat(best_const[1])['per']:+.2f}/session)")

    # ── CELL SET 1: the drift rider, and the plateau re-run at 11x the sample ────────────────
    print("\n" + "=" * 140)
    print("CELL SET 1 — SESSION DRIFT RIDER.  The 08-14 plateau, re-run on 184 sessions")
    print("=" * 140)
    grid = []
    for er in (0.09, 0.124, 0.155, 0.20, 0.30):
        for na in (1.0, 1.5, 2.0, 3.0):
            t = drift_trades(frames, er_min=er, net_atr=na)
            s = stat(t)
            grid.append({"ER>=": er, "net>=xATR": na, **s,
                         "LONG": stat(t[t.side > 0])["net"] if len(t) else 0,
                         "SHORT": stat(t[t.side < 0])["net"] if len(t) else 0,
                         "dir_held%": round(100 * float((t["true_pnl"] > 0).mean()), 1) if len(t) else 0})
    g = pd.DataFrame(grid)
    print(g.to_string(index=False))
    R["drift_grid"] = grid
    pos = (g["net"] > 0).sum()
    print(f"\n  ★ {pos} of {len(g)} cells positive.  (the 08-14 read on 16 sessions was 15 of 15)")
    beat = (g["net"] > stat(best_const[1])["net"]).sum()
    print(f"  ★ {beat} of {len(g)} cells beat the best CONSTANT (${stat(best_const[1])['net']:,.0f}).")

    base = drift_trades(frames, er_min=0.155, net_atr=2.0)
    print("\n  the DERIVED cell (ER 0.155 / net 2.0xATR — gold's own p65 selectivity):")
    print(line("    pooled", stat(base)))
    print(line("    LONG", stat(base[base.side > 0])))
    print(line("    SHORT", stat(base[base.side < 0])))
    print(f"    battery {batt(base)}")
    for k in ("regime", "session"):
        rows = [{k: kk, "side": s, **stat(gg)} for (kk, s), gg in
                base.groupby([k, base["side"].map({1: "LONG", -1: "SHORT"})])]
        print(f"\n    by {k}:"); print(pd.DataFrame(rows).sort_values("per", ascending=False).to_string(index=False))
        R.setdefault("drift_home", {})[k] = rows
    R["drift_base"] = {"pooled": stat(base), "LONG": stat(base[base.side > 0]),
                       "SHORT": stat(base[base.side < 0]), "battery": batt(base)}

    # a stop, since "hold naked to the clock" is not a shippable exit
    print("\n  with a stop (the drift rider held naked is not shippable):")
    for sa in (2.0, 3.0, 5.0, 8.0):
        t = drift_trades(frames, er_min=0.155, net_atr=2.0, stop_atr=sa)
        print(line(f"    stop {sa}xATR", stat(t)))
        R.setdefault("drift_stops", {})[str(sa)] = stat(t)

    # the LONDON anchor, because gold is a London instrument too
    print("\n  the same rider anchored at the LONDON open (06:00Z) instead of COMEX:")
    for lbl, kw in (("LDN anchor, flat 20:40", dict(anchor=LDN_OPEN, flat_mod=US_FLAT)),
                    ("LDN anchor, flat 13:30", dict(anchor=LDN_OPEN, flat_mod=US_OPEN))):
        t = drift_trades(frames, er_min=0.155, net_atr=2.0, **kw)
        print(line(f"    {lbl}", stat(t)))
        R.setdefault("drift_london", {})[lbl] = stat(t)

    # ── CELL SET 2: the overnight-range break ────────────────────────────────────────────────
    print("\n" + "=" * 140)
    print("CELL SET 2 — THE OVERNIGHT-RANGE BREAK at the COMEX open.  go, or fail?")
    print("=" * 140)
    racer = BarRacer(m)
    for rng_end, lbl in ((US_OPEN, "overnight 00:00-13:30Z range"), (LDN_OPEN, "Asia 00:00-06:00Z range")):
        ents = []
        for d, x in frames.items():
            pre = x[x["mod"] < rng_end]
            post = x[(x["mod"] >= rng_end) & (x["mod"] <= US_FLAT)]
            if len(pre) < 120 or len(post) < 60:
                continue
            hi, lo = float(pre["high"].max()), float(pre["low"].min())
            hit_u = post.index[post["high"].to_numpy() > hi]
            hit_d = post.index[post["low"].to_numpy() < lo]
            first = None
            if len(hit_u) and (not len(hit_d) or hit_u[0] <= hit_d[0]):
                first = (hit_u[0], 1, hi)
            elif len(hit_d):
                first = (hit_d[0], -1, lo)
            if first is None:
                continue
            ts, brk, lvl = first
            i = int(np.searchsorted(m.index.values, ts.to_datetime64()))
            if i <= 0 or i >= len(m) - 2 or not np.isfinite(m["atr"].iloc[i]):
                continue
            ents.append({"i": i, "ts": ts, "brk": brk, "level": lvl, "atr": float(m["atr"].iloc[i]),
                         "regime": m["regime"].iloc[i], "session": m["session"].iloc[i], "day": d,
                         "rng_atr": (hi - lo) / max(float(m["atr"].iloc[i]), 1e-9)})
        e = pd.DataFrame(ents)
        print(f"\n  {lbl}: {len(e)} sessions broke their range ({100*len(e)/len(frames):.0f}% of days)")
        for nm, sgn in (("GO with the break", 1), ("FADE the break", -1)):
            ee = e.copy(); ee["side"] = ee["brk"] * sgn
            for exlbl, kw in (("chand sl3/arm2/tr2", dict(stop=3.0, arm=2.0, trail=2.0, cap_min=480)),
                              ("chand sl5/arm3/tr3", dict(stop=5.0, arm=3.0, trail=3.0, cap_min=480)),
                              ("scalp tp1.5R/sl1R", dict(stop=1.0, target=1.5, cap_min=480))):
                r = run(racer, ee, **kw)
                print(line(f"    {nm} · {exlbl}", stat(r),
                           f"L {stat(r[r.side>0])['per']:+.2f} S {stat(r[r.side<0])['per']:+.2f}"))
                R.setdefault("range_break", {}).setdefault(lbl, {})[f"{nm}|{exlbl}"] = stat(r)

    # ── CELL SET 3: does compression predict expansion? ──────────────────────────────────────
    print("\n" + "=" * 140)
    print("CELL SET 3 — THE EXPANSION QUESTION. is SIZE predictable where direction is not?")
    print("=" * 140)
    h = m.copy()
    h["r60"] = h["high"].rolling(60).max() - h["low"].rolling(60).min()
    h["r60n"] = h["r60"] / h["close"] * 10000
    fut_hi = h["high"].shift(-60).rolling(60).max()
    fut_lo = h["low"].shift(-60).rolling(60).min()
    h["fwd"] = (fut_hi - fut_lo) / h["close"] * 10000
    h["fwd_net"] = (h["close"].shift(-60) - h["close"]).abs() / h["close"] * 10000
    z = h.dropna(subset=["r60n", "fwd"])
    z = z[z.index.minute % 15 == 0]                     # 15-min sampling: overlapping windows are not n
    z["quint"] = pd.qcut(z["r60n"], 5, labels=["Q1 tightest", "Q2", "Q3", "Q4", "Q5 widest"])
    g = z.groupby("quint", observed=True).agg(n=("fwd", "size"), prior_range_bp=("r60n", "median"),
                                              next_range_bp=("fwd", "median"),
                                              next_net_bp=("fwd_net", "median"))
    g["expansion_x"] = (g["next_range_bp"] / g["prior_range_bp"]).round(2)
    print("\n  prior 60-min range quintile -> the NEXT 60 minutes (medians, in basis points of price):")
    print(g.round(2).to_string())
    print("\n  ★ if compression predicted expansion, expansion_x would FALL from Q1 to Q5.")
    R["expansion"] = g.round(3).reset_index().astype(str).to_dict("records")

    # the straddle itself
    print("\n  THE STRADDLE, priced: at the top of each hour, place a stop-buy and a stop-sell")
    print("  0.5xATR either side; whichever fills, ride the chandelier. Both legs pay the spread.")
    rows = []
    for band in (0.25, 0.5, 1.0):
        ents = []
        for i in range(60, len(m) - 500):
            if m.index[i].minute != 0:
                continue
            a = m["atr"].iloc[i]
            if not np.isfinite(a) or a <= 0:
                continue
            px = m["close"].iloc[i]
            up, dn = px + band * a, px - band * a
            seg = m.iloc[i + 1:i + 61]
            hu = np.nonzero(seg["high"].to_numpy() >= up)[0]
            hd = np.nonzero(seg["low"].to_numpy() <= dn)[0]
            if not len(hu) and not len(hd):
                continue
            if len(hu) and (not len(hd) or hu[0] <= hd[0]):
                j, side = int(hu[0]), 1
            else:
                j, side = int(hd[0]), -1
            ents.append({"i": i + j, "side": side, "atr": float(a), "day": m["day"].iloc[i],
                         "ts": m.index[i + j], "regime": m["regime"].iloc[i],
                         "session": m["session"].iloc[i]})
        e = pd.DataFrame(ents)
        for exlbl, kw in (("chand sl3/arm2/tr2", dict(stop=3.0, arm=2.0, trail=2.0, cap_min=480)),
                          ("chand sl5/arm3/tr3", dict(stop=5.0, arm=3.0, trail=3.0, cap_min=480))):
            r = run(racer, e, **kw)
            rows.append({"band": band, "exit": exlbl, **stat(r)})
            print(line(f"    band {band}xATR · {exlbl}", stat(r)))
    R["straddle"] = rows

    json.dump(R, open(f"{OUT}/session.json", "w"), indent=1, default=str)
    print(f"\nJSON -> {OUT}/session.json")


if __name__ == "__main__":
    main()
