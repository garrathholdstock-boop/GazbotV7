#!/usr/bin/env python3
"""GF RIDER — the shared engine: signal generation, tick-honest exit racing, scoring, robustness.

Everything the rider study prices goes through here, so a cost or a tie-break can only be wrong in
ONE place.

★ COSTS, stated once. MNQ = **$2.00 per point**. Fee = **$1.50 per ROUND TRIP** (not per side).
  Slippage = one MNQ tick (0.25pt) crossed on entry AND on exit, so 0.5pt = $1.00 of the round trip.
  Effective all-in cost of a trade = $2.50. Nothing here uses $5, $2 or $1.50-per-side.

★ TIE-BREAKS GO AGAINST THE TRADE. If a 5-second bar's high reaches the target and its low reaches
  the stop, the STOP is taken. If the trail and the target are both touched, the trail is taken.

★ ENTRY CANNOT SEE ITS OWN BAR. A rule evaluates on the CLOSE of minute t and fills at the OPEN of
  minute t+1. That is deliberately a minute LATER than a first-crossing backtest would enter, and it
  is the honest side of the sampling bias the desk measured this week.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VPP = 2.00      # MNQ $/point
FEE = 1.50      # $/round trip
SLIP = 0.25     # points crossed per side


# ══════════════════════════════════════════════════════════════════════════════════════════════
# EXIT RACING
# ══════════════════════════════════════════════════════════════════════════════════════════════
class Racer:
    """Races exits on 5-second bars. Built once over the whole tape; every sweep re-uses it."""

    def __init__(self, s5: pd.DataFrame):
        s5 = s5.sort_values("ts").reset_index(drop=True)
        self.ts = s5["ts"].to_numpy(np.int64)
        self.h = s5["h"].to_numpy(np.float64)
        self.l = s5["l"].to_numpy(np.float64)
        self.c = s5["c"].to_numpy(np.float64)
        self.o = s5["o"].to_numpy(np.float64)

    def idx(self, ts: int) -> int:
        return int(np.searchsorted(self.ts, ts, side="left"))

    def race(self, ts: int, side: int, entry: float, stop_pt: float, targ_pt: float,
             cap_min: int, arm_pt: float | None = None, trail_pt: float | None = None,
             be_pt: float | None = None) -> tuple[float, str, int, float, float]:
        """Return (exit_price, reason, held_seconds, mfe_pt, mae_pt) for ONE trade.

        side +1 long / -1 short. stop_pt / targ_pt / trail_pt are POINTS (already ATR-scaled).
        targ_pt = np.inf means "no target — hold to the trail or the time cap".
        arm_pt/trail_pt add a chandelier; be_pt moves the stop to break-even once that much is made.
        """
        i0 = self.idx(ts)
        n = len(self.ts)
        if i0 >= n:
            return entry, "NO_TAPE", 0, 0.0, 0.0
        i1 = min(n, i0 + cap_min * 12)
        # a session boundary inside the window ends the trade — never hold across an overnight hole
        seg = self.ts[i0:i1]
        brk = np.nonzero(np.diff(seg) > 1800)[0]
        if len(brk):
            i1 = i0 + int(brk[0]) + 1
            seg = self.ts[i0:i1]
        if i1 <= i0:
            return entry, "NO_TAPE", 0, 0.0, 0.0

        h, l, c, o = self.h[i0:i1], self.l[i0:i1], self.c[i0:i1], self.o[i0:i1]
        # favourable / adverse excursion in points, both non-negative-ish and side-corrected
        if side > 0:
            fav, adv, worst_open = h - entry, entry - l, o - entry
        else:
            fav, adv, worst_open = entry - l, h - entry, entry - o
        rmax = np.maximum.accumulate(fav)

        stop_lvl = np.full(len(h), -stop_pt, dtype=np.float64)      # in profit-points terms
        if be_pt is not None:
            armed_be = np.concatenate([[False], rmax[:-1] >= be_pt])
            stop_lvl = np.where(armed_be, 0.0, stop_lvl)
        if arm_pt is not None and trail_pt is not None:
            # the trail only reads bars STRICTLY BEFORE the current one — a trail computed from the
            # same bar it fires in is lookahead, and it is the single most common way a chandelier
            # backtest lies.
            prev = np.concatenate([[0.0], rmax[:-1]])
            trailed = np.where(prev >= arm_pt, prev - trail_pt, -np.inf)
            stop_lvl = np.maximum(stop_lvl, trailed)

        hit_stop = (-adv) <= stop_lvl                       # adverse move reached the stop level
        hit_targ = fav >= targ_pt if np.isfinite(targ_pt) else np.zeros(len(h), bool)

        si = int(np.argmax(hit_stop)) if hit_stop.any() else 10**9
        ti = int(np.argmax(hit_targ)) if hit_targ.any() else 10**9
        k = min(si, ti)
        if k == 10**9:
            k = len(h) - 1
            px, why = c[k], "TIME_CAP"
        elif si <= ti:                                       # ★ tie -> the STOP, against the trade
            # gap-through honesty: if the bar OPENED past the stop we get the open, not the level
            fill_pl = min(stop_lvl[si], worst_open[si])
            px = entry + side * fill_pl
            why = "TRAIL" if stop_lvl[si] > -stop_pt + 1e-9 else "STOP"
            if be_pt is not None and abs(stop_lvl[si]) < 1e-9:
                why = "BREAKEVEN"
        else:
            px, why = entry + side * targ_pt, "TARGET"
        return float(px), why, int(self.ts[i0 + k] - ts), float(rmax[k]), float(adv[:k + 1].max())


def run_trades(racer: Racer, sig: pd.DataFrame, *, stop_a: float, targ_a: float, cap_min: int,
               arm_a: float | None = None, trail_a: float | None = None, be_a: float | None = None,
               cooldown_min: int = 15) -> pd.DataFrame:
    """Fire every signal in `sig` (cols: ts, side, entry, atr, ...), one position at a time.

    All widths are in ATR MULTIPLES and converted per-trade at the entry's own ATR — a 3xATR stop is
    36pt in July and 21pt in August, which is the whole point of quoting them this way.
    """
    out, busy_until = [], -1
    for r in sig.itertuples():
        if r.ts < busy_until:
            continue
        atr = float(r.atr)
        if not np.isfinite(atr) or atr <= 0:
            continue
        entry = float(r.entry) + r.side * SLIP
        px, why, held, mfe, mae = racer.race(
            int(r.ts), int(r.side), entry, stop_a * atr,
            targ_a * atr if np.isfinite(targ_a) else np.inf, cap_min,
            None if arm_a is None else arm_a * atr,
            None if trail_a is None else trail_a * atr,
            None if be_a is None else be_a * atr)
        if why == "NO_TAPE":
            continue
        pts = (px - entry) * r.side - SLIP
        net = pts * VPP - FEE
        d = {c: getattr(r, c) for c in sig.columns if c != "Index"}
        d.update(entry_px=entry, exit_px=px, why=why, held_s=held, pts=pts, net=net,
                 mfe=mfe, mae=mae, r_mfe=mfe / atr, r_mae=mae / atr)
        out.append(d)
        busy_until = r.ts + held + cooldown_min * 60
    return pd.DataFrame(out)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# SCORING
# ══════════════════════════════════════════════════════════════════════════════════════════════
def stat(t: pd.DataFrame) -> dict:
    if t is None or not len(t):
        return dict(n=0, net=0.0, win=0.0, per=0.0, med=0.0, best=0.0, worst=0.0, pf=0.0)
    w = t["net"] > 0
    gp, gl = t.loc[w, "net"].sum(), -t.loc[~w, "net"].sum()
    return dict(n=len(t), net=round(t["net"].sum(), 0), win=round(100 * w.mean(), 1),
                per=round(t["net"].mean(), 2), med=round(t["net"].median(), 2),
                best=round(t["net"].max(), 0), worst=round(t["net"].min(), 0),
                pf=round(gp / gl, 2) if gl > 0 else 99.0)


def line(tag: str, s: dict, extra: str = "") -> str:
    return (f"  {tag:<34s} n={s['n']:>4d}  net=${s['net']:>8,.0f}  {s['win']:>5.1f}%w  "
            f"${s['per']:>7.2f}/tr  med=${s['med']:>7.2f}  pf={s['pf']:>5.2f}  {extra}")


def by(t: pd.DataFrame, col: str) -> pd.DataFrame:
    if not len(t):
        return pd.DataFrame()
    rows = [dict(k=k, **stat(g)) for k, g in t.groupby(col)]
    return pd.DataFrame(rows).sort_values("net", ascending=False)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ROBUSTNESS — the only permitted causes of death
# ══════════════════════════════════════════════════════════════════════════════════════════════
def strip_best(t: pd.DataFrame, k: int = 3) -> float:
    """Net with the k best trades deleted. A config that goes red here was 3 trades, not an edge."""
    if len(t) <= k:
        return 0.0
    return round(t["net"].sum() - t.nlargest(k, "net")["net"].sum(), 0)


def loo_days(t: pd.DataFrame) -> pd.DataFrame:
    """Leave-one-day-out: net with each session removed. The worst row is the concentration test."""
    tot = t["net"].sum()
    rows = [dict(day=d, without=round(tot - g["net"].sum(), 0), n_day=len(g),
                 day_net=round(g["net"].sum(), 0)) for d, g in t.groupby("day")]
    return pd.DataFrame(rows).sort_values("without")


def placebo(racer: Racer, pool: pd.DataFrame, n_take: int, reps: int, *, seed: int = 7,
            **exit_kw) -> dict:
    """Discard the same NUMBER of fires at RANDOM, `reps` times.

    ★ This is the control the operator demands for every cut. A filter that keeps 40 of 100 fires
    must beat a coin that keeps 40 of 100 — otherwise it "worked" by trading less, which is a thing
    any random rule does for free."""
    rng = np.random.default_rng(seed)
    nets, pers = [], []
    for _ in range(reps):
        idx = rng.choice(len(pool), size=min(n_take, len(pool)), replace=False)
        s = pool.iloc[np.sort(idx)]
        r = run_trades(racer, s, **exit_kw)
        if len(r):
            nets.append(r["net"].sum())
            pers.append(r["net"].mean())
    if not nets:
        return dict(reps=0)
    nets, pers = np.array(nets), np.array(pers)
    return dict(reps=len(nets), net_mean=round(nets.mean(), 0), net_sd=round(nets.std(), 0),
                net_p95=round(np.percentile(nets, 95), 0), per_mean=round(pers.mean(), 2),
                per_p95=round(np.percentile(pers, 95), 2))


def cost_stress(t: pd.DataFrame, mult: float = 2.0) -> dict:
    """Double the round-trip cost. An edge that is really a cost-model artefact dies here."""
    extra = (FEE + 2 * SLIP * VPP) * (mult - 1.0)
    s = t.copy()
    s["net"] = s["net"] - extra
    return stat(s)
