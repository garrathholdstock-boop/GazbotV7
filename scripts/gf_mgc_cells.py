#!/usr/bin/env python3
"""GF_MGC CELLS — the gold 2x2 hunt, scored to the Friday-report discipline.

    PYTHONPATH=src .venv/bin/python scripts/gf_mgc_cells.py [--quick]

★ WHAT THIS IS. Four cells — {MOMENTUM, REVERSION} x {LONG, SHORT} — each with a mechanical trigger
invented from GOLD's own tape, each raced spread-honestly on the 250ms quote book, each scored on
its HOME regime with the blanket number alongside as context, each put through the same robustness
battery, and each swept across the full exit matrix (tight scalp / wide chandelier / dual slot /
time cap).

★ RULE 1 COMPLIANCE. Nothing here is a re-tuned MNQ gate. The two triggers are:

    BREAK FADE      price closes beyond its own 60-minute extreme -> trade AGAINST the break.
                    Motivated by a MEASUREMENT, not a hunch: on 397 gold level breaks the
                    continuation is -$291 blanket and -$2,059 when the far side of the book is
                    EMPTY (4.8th percentile of its own placebo). Gold's breaks are traps and the
                    book says which ones.
    SESSION DRIFT   after the US open, if the session's own net move is both LARGE (in gold ATR)
                    and EFFICIENT (gold's own ER percentile), ride that direction to the close.
                    Gold's runs are GRINDS - median ER 0.23, four of five lasting 2-12 HOURS - so
                    the momentum cell is built at the session timescale, not the minute one.

★ COSTS, BOTH WAYS, ALWAYS. `true_pnl` crosses the spread on entry AND exit (MGC's spread is a flat
~0.30pt = $3.00, and gold's R is only ~$16-36, so the spread is a QUARTER of an R and it decides
cases). `desk_pnl` is the mid-to-mid $1.50-only convention every previous gold study used. Both are
reported everywhere; `true_pnl` is the number that decides.

★ MGC = $10.00/point (NOT MNQ's $2.00). Fee $1.50 per ROUND TRIP (not per side, never $5).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gf_mgc_tape import FEE_RT, VPP, build_tape, load_quotes  # noqa: E402

pd.set_option("display.width", 260)
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections"
RESULTS: dict = {}


# ════════════════════════════════════════════════════════════════════════════════════════════════
# THE RACER — 5s bid/ask bars, conservative tie-breaking, every exit family in one function
# ════════════════════════════════════════════════════════════════════════════════════════════════
def five_second(q: pd.DataFrame) -> pd.DataFrame:
    g = q.resample("5s")
    return pd.DataFrame({
        "bid_hi": g["bid1p"].max(), "bid_lo": g["bid1p"].min(), "bid_cl": g["bid1p"].last(),
        "ask_hi": g["ask1p"].max(), "ask_lo": g["ask1p"].min(), "ask_cl": g["ask1p"].last(),
    }).dropna()


class Racer:
    """Race an exit forward on 5-second bid/ask bars.

    ORDER INSIDE A BAR, and it is deliberately the pessimistic one: STOP, then TRAIL, then TARGET,
    then extend the peak. A 5s bar does not record whether its high or its low came first, so every
    ambiguity is resolved against the trade. That biases every number here DOWNWARD, which is the
    only direction a bias may point.

    A LONG is filled on the ASK and marked out on the BID; a SHORT the reverse. Both legs cross,
    because the live desk's entries are marketable-limit IOC and its exits are MKT.
    """

    def __init__(self, f: pd.DataFrame):
        self.idx = f.index.tz_convert("UTC").tz_localize(None).astype("datetime64[ns]").astype("int64").to_numpy()
        self.bh, self.bl, self.bc = (f[c].to_numpy() for c in ("bid_hi", "bid_lo", "bid_cl"))
        self.ah, self.al, self.ac = (f[c].to_numpy() for c in ("ask_hi", "ask_lo", "ask_cl"))
        self.n = len(f)

    def locate(self, ts) -> int:
        return int(np.searchsorted(self.idx, np.int64(pd.Timestamp(ts).value), side="left"))

    def race(self, ts, side: int, *, stop_pts: float, target_pts: float | None = None,
             arm_pts: float | None = None, trail_pts: float | None = None,
             cap_min: float = 120.0, be_at_pts: float | None = None) -> dict | None:
        i = self.locate(ts)
        if i >= self.n - 2:
            return None
        fill_in = self.ac[i] if side > 0 else self.bc[i]
        mid_in = (self.ac[i] + self.bc[i]) / 2.0
        if not np.isfinite(fill_in) or fill_in <= 0:
            return None
        span = int(cap_min * 12)
        j = min(i + 1 + span, self.n)

        stop = fill_in - side * stop_pts
        target = fill_in + side * target_pts if target_pts is not None else None
        peak = 0.0            # best favourable excursion, in points, marked on the EXIT side
        mae = 0.0
        armed = False
        trail_lvl = None

        for k in range(i + 1, j):
            if side > 0:
                adverse, favour = self.bl[k], self.bh[k]
            else:
                adverse, favour = self.ah[k], self.al[k]
            if not (np.isfinite(adverse) and np.isfinite(favour)):
                continue
            adv_exc = side * (adverse - fill_in)
            mae = min(mae, adv_exc)
            # 1. STOP
            if (adverse <= stop) if side > 0 else (adverse >= stop):
                return self._out(i, k, side, fill_in, mid_in, stop, "STOP", peak, mae)
            # 2. TRAIL (uses the same adverse extreme; checked before the peak is extended)
            if armed and trail_lvl is not None:
                if (adverse <= trail_lvl) if side > 0 else (adverse >= trail_lvl):
                    return self._out(i, k, side, fill_in, mid_in, trail_lvl, "TRAIL", peak, mae)
            # 3. TARGET
            if target is not None and ((favour >= target) if side > 0 else (favour <= target)):
                return self._out(i, k, side, fill_in, mid_in, target, "TARGET", peak, mae)
            # 4. extend the peak, re-arm, re-hang the trail
            peak = max(peak, side * (favour - fill_in))
            if be_at_pts is not None and peak >= be_at_pts:
                stop = max(stop, fill_in) if side > 0 else min(stop, fill_in)
            if arm_pts is not None and peak >= arm_pts:
                armed = True
            if armed and trail_pts is not None:
                trail_lvl = fill_in + side * (peak - trail_pts)
        k = min(j - 1, self.n - 1)
        out = self.bc[k] if side > 0 else self.ac[k]
        return self._out(i, k, side, fill_in, mid_in, out, "TIME_CAP", peak, mae)

    def _out(self, i, k, side, fill_in, mid_in, fill_out, reason, peak, mae) -> dict:
        mid_out = (self.ac[k] + self.bc[k]) / 2.0
        return {
            "fill_in": round(float(fill_in), 2), "fill_out": round(float(fill_out), 2),
            "reason": reason, "minutes": round((k - i) * 5.0 / 60.0, 1),
            "true_pnl": round(side * (fill_out - fill_in) * VPP - FEE_RT, 2),
            "desk_pnl": round(side * (mid_out - mid_in) * VPP - FEE_RT, 2),
            "mfe_pt": round(float(peak), 2), "mae_pt": round(float(mae), 2),
        }


def run_entries(racer: Racer, e: pd.DataFrame, **kw) -> pd.DataFrame:
    """Race every entry. Stop/target/trail are given in ATR MULTIPLES and scaled per entry."""
    atr_keys = {"stop": "stop_pts", "target": "target_pts", "arm": "arm_pts",
                "trail": "trail_pts", "be_at": "be_at_pts"}
    rows = []
    for r in e.itertuples():
        a = float(r.atr)
        if not np.isfinite(a) or a <= 0:
            continue
        args = {}
        for k, v in atr_keys.items():
            if kw.get(k) is not None:
                args[v] = kw[k] * a
        res = racer.race(r.ts, int(r.side), cap_min=kw.get("cap_min", 120.0), **args)
        if res is None:
            continue
        rows.append({**{c: getattr(r, c) for c in e.columns}, **res})
    return pd.DataFrame(rows)


# ════════════════════════════════════════════════════════════════════════════════════════════════
# SCORING + THE ROBUSTNESS BATTERY
# ════════════════════════════════════════════════════════════════════════════════════════════════
def stat(d: pd.DataFrame, col: str = "true_pnl") -> dict:
    if d is None or d.empty:
        return {"n": 0, "net": 0.0, "win": 0.0, "per": 0.0, "med": 0.0, "days": 0}
    v = d[col]
    return {"n": int(len(v)), "net": round(float(v.sum()), 0),
            "win": round(100.0 * float((v > 0).mean()), 1),
            "per": round(float(v.mean()), 2), "med": round(float(v.median()), 2),
            "days": int(d["day"].nunique()) if "day" in d else 0}


def battery(d: pd.DataFrame, col: str = "true_pnl") -> dict:
    """strip-best-3 · leave-one-day-out (drop the BEST day) · both calendar halves · the JUL leg."""
    if d is None or len(d) < 4:
        return {}
    v = d[col].sort_values()
    byday = d.groupby("day")[col].sum()
    days = sorted(d["day"].unique())
    mid = days[len(days) // 2]
    h1, h2 = d[d["day"] < mid], d[d["day"] >= mid]
    jul, aug = d[d["day"] < "2026-08-01"], d[d["day"] >= "2026-08-01"]
    return {
        "strip_best3": round(float(v.iloc[:-3].sum()), 0),
        "strip_worst3": round(float(v.iloc[3:].sum()), 0),
        "loo_worst": round(float(byday.sum() - byday.max()), 0),
        "days_green": round(100.0 * float((byday > 0).mean()), 1),
        "best_day": f"{byday.idxmax()} {byday.max():+.0f}",
        "worst_day": f"{byday.idxmin()} {byday.min():+.0f}",
        "h1": [int(len(h1)), round(float(h1[col].sum()), 0)],
        "h2": [int(len(h2)), round(float(h2[col].sum()), 0)],
        "JUL_oos": [int(len(jul)), round(float(jul[col].sum()), 0)],
        "AUG_is": [int(len(aug)), round(float(aug[col].sum()), 0)],
    }


def placebo(racer: Racer, real: pd.DataFrame, m: pd.DataFrame, *, n_runs: int = 30,
            seed: int = 20260815, col: str = "true_pnl", **exit_kw) -> dict:
    """The control that has killed more gold candidates than any other test.

    Draw the SAME NUMBER of entries, on the SAME DAYS, in the SAME HOUR-OF-DAY mix, with the SAME
    side mix, at random minutes — and race them through the IDENTICAL exit. If the real trigger
    cannot beat that, the trigger is doing nothing and the P&L belongs to the exit or to the drift.
    """
    if real is None or real.empty:
        return {"runs": 0}
    target = float(real[col].sum())
    rng = np.random.default_rng(seed)
    pool = m.dropna(subset=["atr"])
    pool = pool[pool["atr"] > 0]
    pool_hour = pool.index.hour.to_numpy()
    pool_day = pool["day"].to_numpy()
    want = real.groupby([real["ts"].dt.hour, real["day"], real["side"]]).size()
    nets = []
    for _ in range(n_runs):
        picks = []
        for (hr, day, side), cnt in want.items():
            cand = np.nonzero((pool_hour == hr) & (pool_day == day))[0]
            if len(cand) == 0:
                continue
            for ix in rng.choice(cand, size=min(cnt, len(cand)), replace=False):
                picks.append({"ts": pool.index[ix] + pd.Timedelta(seconds=60), "side": int(side),
                              "atr": float(pool["atr"].iloc[ix]), "day": day,
                              "regime": pool["regime"].iloc[ix], "session": pool["session"].iloc[ix]})
        if not picks:
            continue
        r = run_entries(racer, pd.DataFrame(picks), **exit_kw)
        nets.append(float(r[col].sum()) if not r.empty else 0.0)
    if not nets:
        return {"runs": 0}
    beaten = sum(1 for x in nets if x >= target)
    return {"runs": len(nets), "beaten": beaten, "real": round(target, 0),
            "mean": round(float(np.mean(nets)), 0), "p90": round(float(np.percentile(nets, 90)), 0),
            "pctile": round(100.0 * float(np.mean([x < target for x in nets])), 1)}


def cooldown(e: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """One position at a time PER SIDE. Without it a single gold move manufactures 30 correlated
    'trades' and every n in the report is a lie."""
    if e.empty:
        return e
    keep, last = [], {}
    for r in e.itertuples():
        if r.side in last and (r.ts - last[r.side]).total_seconds() < minutes * 60:
            continue
        last[r.side] = r.ts
        keep.append(r.Index)
    return e.loc[keep].reset_index(drop=True)


# ════════════════════════════════════════════════════════════════════════════════════════════════
# TRIGGER 1 — THE BREAK FADE  (the two REVERSION cells)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def break_entries(m: pd.DataFrame, *, look: int = 60, margin_atr: float = 0.10,
                  cool: int = 45, fade: bool = True) -> pd.DataFrame:
    """Price CLOSES beyond its own `look`-minute extreme by `margin_atr` ATR.

    ⚠ TWO LOOK-AHEADS KILLED HERE. (1) The extreme is taken over bars STRICTLY BEFORE the signal bar
    (`shift(1)`) — including the signal bar's own high in its own break level is circular. (2) The
    bar labelled 10:00 does not close until 10:01, so entry is stamped at ts+60s. Getting (2) wrong
    cost the coil gate +$906 -> +$470 on 2026-08-14.

    `fade=True` trades AGAINST the break (reversion); `fade=False` with it (the momentum control).
    """
    d = m.copy()
    hi = d["high"].rolling(look).max().shift(1)
    lo = d["low"].rolling(look).min().shift(1)
    d = d.assign(hi=hi, lo=lo).dropna(subset=["hi", "lo", "atr"])
    up = d["close"] >= d["hi"] + margin_atr * d["atr"]
    dn = d["close"] <= d["lo"] - margin_atr * d["atr"]
    rows = []
    for ts, u, v in zip(d.index, up.to_numpy(), dn.to_numpy()):
        if not (u or v):
            continue
        brk = 1 if u else -1
        rows.append({"ts": ts + pd.Timedelta(seconds=60), "sig_ts": ts,
                     "side": (-brk if fade else brk), "brk": brk,
                     "level": float(d.at[ts, "hi"] if u else d.at[ts, "lo"]),
                     "atr": float(d.at[ts, "atr"]), "regime": d.at[ts, "regime"],
                     "session": d.at[ts, "session"], "day": d.at[ts, "day"],
                     "er": float(d.at[ts, "er"]) if np.isfinite(d.at[ts, "er"]) else np.nan})
    e = pd.DataFrame(rows)
    return cooldown(e, cool) if not e.empty else e


# ════════════════════════════════════════════════════════════════════════════════════════════════
# TRIGGER 2 — THE SESSION DRIFT RIDER  (the two MOMENTUM cells)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def drift_entries(m: pd.DataFrame, *, anchor_min: int = 13 * 60 + 30, arm_after: int = 30,
                  window: int = 150, er_min: float = 0.155, net_atr_min: float = 2.0,
                  one_per_day: bool = True) -> pd.DataFrame:
    """Ride the SESSION's own drift once gold has declared it.

    From `anchor_min` (13:30 UTC = the COMEX open), at every minute from anchor+`arm_after` to
    anchor+`window`, measure the session so far:

        net  = close - session open                (points)
        path = sum of |minute changes| so far      (points)
        ER   = |net| / path                        (dimensionless)

    Enter in the direction of `net` the first time BOTH `ER >= er_min` AND `|net| >= net_atr_min *
    ATR`. Both floors are dimensionless-or-ATR-scaled, so neither is an MNQ number in disguise; the
    ER floor is gold's own p65 selectivity (0.155, derived 2026-08-14 by percentile-matching, not by
    sweeping P&L) and the size floor is in gold ATR.

    This is a SESSION-timescale momentum trigger, which is the timescale gold's runs actually live
    on (median run 206 minutes, median ER 0.23). It is not a minute-impulse continuation gate — that
    shape is already refuted.
    """
    rows = []
    for day, dm in m.groupby("day"):
        idx = dm.index
        mod = idx.hour * 60 + idx.minute
        sess = dm[(mod >= anchor_min) & (mod < anchor_min + window + 1)]
        if len(sess) < arm_after + 5:
            continue
        op = float(sess["close"].iloc[0])
        c = sess["close"]
        path = c.diff().abs().cumsum()
        net = c - op
        er = (net.abs() / path).replace([np.inf, -np.inf], np.nan)
        for k in range(arm_after, len(sess)):
            ts = sess.index[k]
            a = float(sess["atr"].iloc[k])
            if not np.isfinite(a) or a <= 0:
                continue
            e_v, n_v = float(er.iloc[k]), float(net.iloc[k])
            if not np.isfinite(e_v):
                continue
            if e_v >= er_min and abs(n_v) >= net_atr_min * a:
                rows.append({"ts": ts + pd.Timedelta(seconds=60), "side": 1 if n_v > 0 else -1,
                             "atr": a, "regime": sess["regime"].iloc[k],
                             "session": sess["session"].iloc[k], "day": day,
                             "er": e_v, "net_atr": round(n_v / a, 2),
                             "mins_in": k})
                if one_per_day:
                    break
    return pd.DataFrame(rows)


def always_constant(m: pd.DataFrame, racer: Racer, side: int, *, anchor_min: int = 13 * 60 + 30,
                    arm_after: int = 30, **exit_kw) -> pd.DataFrame:
    """THE CONTROL EVERY MOMENTUM CELL MUST BEAT. `always_short` beat every directed gold gate in
    the 08-05 study, so a directional cell that cannot clear the best CONSTANT has found nothing."""
    rows = []
    for day, dm in m.groupby("day"):
        mod = dm.index.hour * 60 + dm.index.minute
        sess = dm[(mod >= anchor_min + arm_after)]
        if sess.empty:
            continue
        a = float(sess["atr"].iloc[0])
        if not np.isfinite(a) or a <= 0:
            continue
        rows.append({"ts": sess.index[0] + pd.Timedelta(seconds=60), "side": side, "atr": a,
                     "regime": sess["regime"].iloc[0], "session": sess["session"].iloc[0], "day": day})
    return run_entries(racer, pd.DataFrame(rows), **exit_kw)


# ════════════════════════════════════════════════════════════════════════════════════════════════
# REPORT HELPERS
# ════════════════════════════════════════════════════════════════════════════════════════════════
def line(lbl: str, s: dict, extra: str = "") -> str:
    return (f"  {lbl:<44} n={s['n']:>4}  net${s['net']:>8.0f}  win {s['win']:>5.1f}%  "
            f"${s['per']:>7.2f}/tr  med ${s['med']:>7.2f}  {extra}")


def side_split(d: pd.DataFrame, col: str = "true_pnl") -> dict:
    return {"LONG": stat(d[d["side"] > 0], col), "SHORT": stat(d[d["side"] < 0], col)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()

    m, q = build_tape()
    print(f"tape: {len(m):,} minutes  {m['day'].nunique()} days  {m.index.min()} .. {m.index.max()}")
    print("building 5s bid/ask frame ...", flush=True)
    f = five_second(q)
    racer = Racer(f)
    print(f"  {len(f):,} five-second bars\n")
    spread = float((q["ask1p"] - q["bid1p"]).median())
    print(f"MGC median spread {spread:.2f}pt = ${spread * VPP:.2f}; a crossing round trip therefore "
          f"costs ${spread * VPP * 2 + FEE_RT:.2f}, not ${FEE_RT:.2f}.\n")
    RESULTS["tape"] = {"minutes": len(m), "days": int(m["day"].nunique()),
                       "span": [str(m.index.min()), str(m.index.max())],
                       "spread_pt": round(spread, 3),
                       "true_rt_cost": round(spread * VPP * 2 + FEE_RT, 2)}

    # ── 1. THE BREAK: does it run or does it fail? ───────────────────────────────────────────────
    print("=" * 126)
    print("[1] THE TRIGGER'S BASE RATE — a 60-minute level break, traded BOTH ways on identical rows")
    print("    exit held fixed at tp 1.0 / sl 1.0 ATR, 120min cap, so only the DIRECTION varies")
    print("=" * 126)
    ef = break_entries(m, fade=True)
    ec = break_entries(m, fade=False)
    print(f"  n={len(ef)} breaks  ({int((ef['brk'] > 0).sum())} up, {int((ef['brk'] < 0).sum())} down), "
          f"22 days, 45min cooldown")
    rf = run_entries(racer, ef, stop=1.0, target=1.0, cap_min=120)
    rc = run_entries(racer, ec, stop=1.0, target=1.0, cap_min=120)
    print(line("FADE the break (reversion)", stat(rf)))
    print(line("FOLLOW the break (momentum control)", stat(rc)))
    print(line("  ... on the old mid-fill $1.50 convention", stat(rf, "desk_pnl")))
    RESULTS["break_base"] = {"fade": stat(rf), "follow": stat(rc),
                             "fade_desk": stat(rf, "desk_pnl"), "n_up": int((ef["brk"] > 0).sum()),
                             "n_dn": int((ef["brk"] < 0).sum())}

    # ── 2. THE HOME REGIME ──────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 126)
    print("[2] ★ THE ROUTER QUESTION — where does the fade live? (same exit everywhere; only the")
    print("    REGIME varies. A blanket number is context, never the verdict.)")
    print("=" * 126)
    rows = []
    for reg, g in rf.groupby("regime"):
        rows.append({"regime": reg, **stat(g)})
    reg_t = pd.DataFrame(rows).sort_values("per", ascending=False)
    print(reg_t.to_string(index=False))
    RESULTS["fade_by_regime"] = reg_t.to_dict("records")

    print("\n  by SESSION:")
    rows = [{"session": s, **stat(g)} for s, g in rf.groupby("session")]
    print(pd.DataFrame(rows).sort_values("per", ascending=False).to_string(index=False))
    RESULTS["fade_by_session"] = rows

    print("\n  by ER at the break (gold's own terciles) — does the fade need a TRENDING tape?")
    rows = []
    qs = rf["er"].quantile([0.33, 0.67]).to_list()
    band = pd.cut(rf["er"], [-1] + qs + [9], labels=["ER low", "ER mid", "ER high"])
    for b, g in rf.groupby(band, observed=True):
        rows.append({"band": str(b), "cut": round(float(g["er"].max()), 3), **stat(g)})
    print(pd.DataFrame(rows).to_string(index=False))
    RESULTS["fade_by_er"] = rows

    print("\n  by ATR at the break:")
    rows = []
    qa = rf["atr"].quantile([0.33, 0.67]).to_list()
    bandA = pd.cut(rf["atr"], [-1] + qa + [99], labels=["ATR low", "ATR mid", "ATR high"])
    for b, g in rf.groupby(bandA, observed=True):
        rows.append({"band": str(b), "cut": round(float(g["atr"].max()), 2), **stat(g)})
    print(pd.DataFrame(rows).to_string(index=False))
    RESULTS["fade_by_atr"] = rows

    # ── 3. THE 2x2 SPLIT BY SIDE ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 126)
    print("[3] ★★ THE TWO REVERSION CELLS, SEPARATELY — a strong long may NOT stand in for a")
    print("    missing short. Blanket first, then the home regime.")
    print("=" * 126)
    for lbl, sub in (("BLANKET (all 22 days, all regimes)", rf),
                     ("HOME: CLEAN_TREND only", rf[rf["regime"] == "CLEAN_TREND"]),
                     ("HOME: ER-high tercile only", rf[band == "ER high"]),
                     ("HOME: CLEAN_TREND or ER-high", rf[(rf["regime"] == "CLEAN_TREND") | (band == "ER high")])):
        ss = side_split(sub)
        print(f"\n  {lbl}")
        print(line("    REVERSION-SHORT (fade an UP break)", ss["SHORT"]))
        print(line("    REVERSION-LONG  (fade a DOWN break)", ss["LONG"]))
        RESULTS.setdefault("fade_cells", {})[lbl] = ss

    json.dump(RESULTS, open(f"{OUT}/gf_mgc_cells.json", "w"), indent=1, default=str)
    print(f"\n[partial JSON -> {OUT}/gf_mgc_cells.json]")

    # ── 4. THE EXIT MATRIX ──────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 126)
    print("[4] ★★★ THE FULL EXIT MATRIX ON THE BREAK FADE — the entry and the exit are separate")
    print("    questions and this desk has been burned assuming one implies the other.")
    print("=" * 126)
    home = rf.index  # recompute per exit below on the SAME entry rows
    ef_home = ef.loc[ef.index.isin(rf.index)] if False else ef
    grids = {}

    print("\n  (a) TIGHT-R SCALP — target swept against a matched stop, 120min cap")
    rows = []
    for tp, sl in ((0.5, 0.5), (0.5, 1.0), (0.75, 0.75), (0.75, 1.5), (1.0, 1.0),
                   (1.0, 1.5), (1.5, 1.5), (1.5, 2.0), (2.0, 2.0)):
        r = run_entries(racer, ef, stop=sl, target=tp, cap_min=120)
        ss = side_split(r)
        rows.append({"tp_atr": tp, "sl_atr": sl, **stat(r),
                     "LONG$/tr": ss["LONG"]["per"], "SHORT$/tr": ss["SHORT"]["per"],
                     "desk_net": stat(r, "desk_pnl")["net"]})
    grids["scalp"] = rows
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n  (b) WIDE CHANDELIER — arm at N ATR then trail M ATR, wide stop, 480min cap")
    rows = []
    for stop_a, arm, trail in ((2.0, 1.0, 1.0), (2.0, 1.5, 1.5), (3.0, 1.5, 1.5),
                               (3.0, 2.0, 2.0), (5.0, 2.0, 2.0), (5.0, 3.0, 3.0)):
        r = run_entries(racer, ef, stop=stop_a, arm=arm, trail=trail, cap_min=480)
        ss = side_split(r)
        rows.append({"stop_atr": stop_a, "arm": arm, "trail": trail, **stat(r),
                     "LONG$/tr": ss["LONG"]["per"], "SHORT$/tr": ss["SHORT"]["per"]})
    grids["chandelier"] = rows
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n  (c) DUAL SLOT — Lot A scalps 1.0 ATR, Lot B rides a 3.0-ATR-stop chandelier (this is")
    print("      the shape the live MNQ desk actually runs; the two lots are summed per signal)")
    ra = run_entries(racer, ef, stop=1.0, target=1.0, cap_min=120)
    rb = run_entries(racer, ef, stop=3.0, arm=2.0, trail=2.0, cap_min=480)
    dual = pd.DataFrame({"A": stat(ra), "B": stat(rb)}).T
    print(dual.to_string())
    both = round(float(ra["true_pnl"].sum() + rb["true_pnl"].sum()), 0)
    print(f"      Lot A + Lot B combined net ${both:,.0f} over {len(ra)} signals "
          f"(${both / max(len(ra), 1):.2f} per SIGNAL, 2 lots)")
    grids["dual"] = {"A": stat(ra), "B": stat(rb), "combined_net": both,
                     "per_signal": round(both / max(len(ra), 1), 2)}

    print("\n  (d) TIME CAP — no target at all, a 1.5 ATR stop, flat at the clock")
    rows = []
    for cap in (15, 30, 60, 120, 240, 480):
        r = run_entries(racer, ef, stop=1.5, cap_min=cap)
        ss = side_split(r)
        rows.append({"cap_min": cap, **stat(r), "LONG$/tr": ss["LONG"]["per"],
                     "SHORT$/tr": ss["SHORT"]["per"]})
    grids["timecap"] = rows
    print(pd.DataFrame(rows).to_string(index=False))
    RESULTS["exit_matrix_fade"] = grids

    # ── 5. TRIGGER PLATEAU ──────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 126)
    print("[5] PARAMETER PLATEAU ON THE TRIGGER — an edge that exists only at one lookback is a fit")
    print("=" * 126)
    rows = []
    for look in (30, 45, 60, 90, 120):
        for marg in (0.0, 0.10, 0.25):
            e2 = break_entries(m, look=look, margin_atr=marg)
            if e2.empty:
                continue
            r2 = run_entries(racer, e2, stop=1.0, target=1.0, cap_min=120)
            ss = side_split(r2)
            rows.append({"look_min": look, "margin_atr": marg, **stat(r2),
                         "LONG$/tr": ss["LONG"]["per"], "SHORT$/tr": ss["SHORT"]["per"]})
    plate = pd.DataFrame(rows)
    print(plate.to_string(index=False))
    print(f"  cells positive: {int((plate['per'] > 0).sum())}/{len(plate)}   "
          f"LONG positive: {int((plate['LONG$/tr'] > 0).sum())}/{len(plate)}   "
          f"SHORT positive: {int((plate['SHORT$/tr'] > 0).sum())}/{len(plate)}")
    RESULTS["fade_plateau"] = rows

    # ── 6. ROBUSTNESS ───────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 126)
    print("[6] ★ THE ROBUSTNESS BATTERY on the break fade (tp 1.0 / sl 1.0 ATR, 120min)")
    print("=" * 126)
    for lbl, sub in (("ALL", rf), ("SHORT only", rf[rf["side"] < 0]), ("LONG only", rf[rf["side"] > 0])):
        b = battery(sub)
        print(f"\n  {lbl}: {stat(sub)}")
        for k, v in b.items():
            print(f"      {k:<14} {v}")
        RESULTS.setdefault("fade_battery", {})[lbl] = {"stat": stat(sub), **b}

    print("\n  PLACEBO — same count, same days, same hours, same side mix, random minutes:")
    for lbl, sub in (("ALL", rf), ("SHORT", rf[rf["side"] < 0]), ("LONG", rf[rf["side"] > 0])):
        p = placebo(racer, sub, m, n_runs=10 if a.quick else 30,
                    stop=1.0, target=1.0, cap_min=120)
        print(f"    {lbl:<7} {p}")
        RESULTS.setdefault("fade_placebo", {})[lbl] = p

    json.dump(RESULTS, open(f"{OUT}/gf_mgc_cells.json", "w"), indent=1, default=str)

    # ── 7. THE MOMENTUM CELLS ───────────────────────────────────────────────────────────────────
    print("\n" + "=" * 126)
    print("[7] ★★ THE MOMENTUM CELLS — the SESSION DRIFT RIDER, and the CONSTANT it must beat")
    print("=" * 126)
    ed = drift_entries(m)
    print(f"  fired on {len(ed)} of {m['day'].nunique()} days "
          f"({int((ed['side'] > 0).sum())} long, {int((ed['side'] < 0).sum())} short), "
          f"median {ed['mins_in'].median():.0f} min after the 13:30 open")
    rows = []
    for lbl, kw in (("scalp 1.0/1.0 ATR, 120m", dict(stop=1.0, target=1.0, cap_min=120)),
                    ("scalp 2.0/1.0 ATR, 240m", dict(stop=1.0, target=2.0, cap_min=240)),
                    ("wide 3xATR stop, ride to 20:40 (430m)", dict(stop=3.0, cap_min=430)),
                    ("wide 5xATR stop, 480m", dict(stop=5.0, cap_min=480)),
                    ("chandelier arm2/trail2, stop 3", dict(stop=3.0, arm=2.0, trail=2.0, cap_min=430))):
        r = run_entries(racer, ed, **kw)
        ss = side_split(r)
        cl = always_constant(m, racer, 1, **kw)
        cs = always_constant(m, racer, -1, **kw)
        rows.append({"exit": lbl, **stat(r), "LONG$/tr": ss["LONG"]["per"], "SHORT$/tr": ss["SHORT"]["per"],
                     "always_LONG": stat(cl)["net"], "always_SHORT": stat(cs)["net"]})
    rid = pd.DataFrame(rows)
    print(rid.to_string(index=False))
    RESULTS["rider_exits"] = rows

    print("\n  the rider's two cells, on its best exit, with the battery:")
    best = run_entries(racer, ed, stop=3.0, cap_min=430)
    for lbl, sub in (("MOMENTUM-LONG", best[best["side"] > 0]), ("MOMENTUM-SHORT", best[best["side"] < 0])):
        print(f"\n  {lbl}: {stat(sub)}")
        for k, v in battery(sub).items():
            print(f"      {k:<14} {v}")
        RESULTS.setdefault("rider_battery", {})[lbl] = {"stat": stat(sub), **battery(sub)}

    print("\n  rider threshold plateau (ER floor x size floor), exit = 3xATR stop to the clock:")
    rows = []
    for er_min in (0.09, 0.124, 0.155, 0.20):
        for na in (1.0, 1.5, 2.0, 3.0):
            e3 = drift_entries(m, er_min=er_min, net_atr_min=na)
            if e3.empty:
                continue
            r3 = run_entries(racer, e3, stop=3.0, cap_min=430)
            ss = side_split(r3)
            rows.append({"er_min": er_min, "net_atr": na, **stat(r3),
                         "LONG$/tr": ss["LONG"]["per"], "SHORT$/tr": ss["SHORT"]["per"]})
    pl = pd.DataFrame(rows)
    print(pl.to_string(index=False))
    print(f"  cells with positive expectancy: {int((pl['per'] > 0).sum())}/{len(pl)}")
    RESULTS["rider_plateau"] = rows

    print("\n  PLACEBO on the rider (same days, same hours, same sides, random minutes):")
    p = placebo(racer, best, m, n_runs=10 if a.quick else 30, stop=3.0, cap_min=430)
    print(f"    {p}")
    RESULTS["rider_placebo"] = p

    json.dump(RESULTS, open(f"{OUT}/gf_mgc_cells.json", "w"), indent=1, default=str)
    print(f"\nJSON -> {OUT}/gf_mgc_cells.json")


if __name__ == "__main__":
    main()
