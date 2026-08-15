"""CHOP-DAY SCALP — Step 4: the tick-honest backtest engine.

One position at a time.  Entry at the 5s bar CLOSE (never its open), market, filled
at the next real print crossed one tick adverse.  Exit resolved by a first-touch race
on the real tick path: the stop fills one tick BEYOND its trigger, the target only
fills if a print goes one tick THROUGH it.  $2.00/pt, $1.50 per ROUND TRIP.

Gate candidates are declared in CANDIDATES; each is a pure function of the trailing
feature row, so nothing can see the future.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import gf_cs_lib as L

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/cs"

MIN_RANGE_ATR = 1.5
POS_HI, POS_LO = 0.90, 0.10


def prep(day: str) -> pd.DataFrame:
    f = L.feat(day)
    f = f.dropna(subset=["atr20", "er30", "vwap30", "hi30", "lo30",
                         "bid5", "ask5", "vwap30_10m"]).copy()
    f = f[(f["atr20"] > 0) & (f["hi30"] > f["lo30"]) & (f["bid5"] > 0) & (f["ask5"] > 0)]
    f["pos30"] = (f["close"] - f["lo30"]) / (f["hi30"] - f["lo30"])
    f["rng_atr"] = (f["hi30"] - f["lo30"]) / f["atr20"]
    f["vslope"] = (f["vwap30"] - f["vwap30_10m"]) / f["atr20"]
    f["vs_flat"] = f["vslope"].abs()
    f["stretch"] = (f["close"] - f["vwap30"]) / f["atr20"]
    f["dlt_n"] = f["dlt60s"] / f["tvol60s"].replace(0, np.nan)
    f["absorb"] = f["dlt60s"].abs() / (f["mv60s"].abs() + 1.0)
    f["at"] = np.where(f["pos30"] >= POS_HI, "HIGH",
                       np.where(f["pos30"] <= POS_LO, "LOW", ""))
    f["side"] = np.where(f["at"] == "HIGH", "SHORT", "LONG")
    hi = f["at"] == "HIGH"
    f["farwall"] = np.where(hi, f["ask5"] / f["bid5"], f["bid5"] / f["ask5"])
    f["farwall_l1"] = np.where(hi, f["ask1s"] / f["bid1s"].replace(0, np.nan),
                               f["bid1s"] / f["ask1s"].replace(0, np.nan))
    f["far_refill"] = np.where(hi, f["dask5_30s"] / f["ask5_5m"].replace(0, np.nan),
                               f["dbid5_30s"] / f["bid5_5m"].replace(0, np.nan))
    f["near_refill"] = np.where(hi, f["dbid5_30s"] / f["bid5_5m"].replace(0, np.nan),
                                f["dask5_30s"] / f["ask5_5m"].replace(0, np.nan))
    f["push"] = np.where(hi, f["dlt_n"], -f["dlt_n"])
    f["prog"] = np.where(hi, f["mv60s"], -f["mv60s"])
    f["day"] = day
    f["tod"] = np.where(((f["t"] % 86400) >= 13.5 * 3600)
                        & ((f["t"] % 86400) < 20 * 3600), "US", "ON")
    return f[(f["at"] != "") & (f["rng_atr"] >= MIN_RANGE_ATR)].copy()


# --------------------------------------------------------------------------
# the candidates.  each returns a boolean mask over the prepared frame.
# --------------------------------------------------------------------------
def ct1_flatline(f, er=0.09, **k):
    """CT-1 FLATLINE — control.  Range extreme inside a dead 30-min structure.
    NO book input at all.  This is the yardstick every L2 candidate must beat."""
    return f["er30"] < er


def ct2_thinwall(f, er=0.09, wall=0.92, **k):
    """CT-2 THINWALL — CT-1 + the continuation side of the book is THIN relative to
    the side we are leaning on.  (This is the INVERSE of the operator's brief; it is
    what the race actually pointed at.)"""
    return (f["er30"] < er) & (f["farwall"] <= wall)


def ct3_exhaust(f, er=0.30, wall=1.5, push=0.05, prog=2.0, flat=0.5, **k):
    """CT-3 EXHAUST-CT — the operator's brief, implemented literally: heavy aggressor
    delta into the extreme, price refuses to follow, a WALL on the continuation side,
    and a FLAT VWAP.  exhaustion_short's footprint, transplanted."""
    return ((f["er30"] < er) & (f["farwall"] >= wall) & (f["push"] >= push)
            & (f["prog"].abs() <= prog) & (f["vs_flat"] <= flat))


def ct4_pushfade(f, er=0.30, slope=0.7, rng=4.7, **k):
    """CT-4 PUSHFADE — a sharp 10-minute push into the edge of a 30-minute structure
    that is going nowhere.  Regime says range, the trigger is the thrust."""
    return (f["er30"] < er) & (f["vs_flat"] >= slope) & (f["rng_atr"] >= rng)


def ct5_deplete(f, er=0.09, refill=-0.066, **k):
    """CT-5 DEPLETE — CT-1 + the continuation side of the book is DRAINING (30s size
    change below its 5-minute mean)."""
    return (f["er30"] < er) & (f["far_refill"] <= refill)


def ct6_book_and_push(f, er=0.09, wall=0.92, slope=0.7, **k):
    """CT-6 THINWALL+PUSH — CT-2 plus the sharp-push trigger of CT-4."""
    return (f["er30"] < er) & (f["farwall"] <= wall) & (f["vs_flat"] >= slope)


def ct7_stall(f, er=0.30, wall=1.5, prog=2.0, **k):
    """CT-7 STALL — what the CT-3 sweep actually pointed at once the dead weight was
    stripped: price STALLS at the range extreme (|60s move| <= 2pt) with a moderate
    wall on the continuation side.  No delta term, no VWAP-flatness term — the sweep
    said neither of those carries anything."""
    return (f["er30"] < er) & (f["farwall"] >= wall) & (f["prog"].abs() <= prog)


def ct8_stall_nobook(f, er=0.30, prog=2.0, **k):
    """CT-8 STALL-NO-BOOK — CT-7 with the book term DELETED.  This is the control that
    decides whether L2 earns its keep at all, or whether the whole thing is the price
    stall."""
    return (f["er30"] < er) & (f["prog"].abs() <= prog)


def ct9_best(f, er=0.30, wall=1.5, prog=2.0, push=0.0, **k):
    """CT-9 STALL+PUSH — the single best cell of the 108-cell CT-3 sweep, chosen on the
    in-sample leg only: a moderate wall, aggression at least neutral INTO the extreme,
    and price stalling.  The VWAP-flatness term is gone (the sweep says it is inert).
    This is the candidate the out-of-sample leg has to judge."""
    return ((f["er30"] < er) & (f["farwall"] >= wall)
            & (f["push"] >= push) & (f["prog"].abs() <= prog))


CANDIDATES = {
    "CT-1 FLATLINE": ct1_flatline,
    "CT-2 THINWALL": ct2_thinwall,
    "CT-3 EXHAUST-CT": ct3_exhaust,
    "CT-4 PUSHFADE": ct4_pushfade,
    "CT-5 DEPLETE": ct5_deplete,
    "CT-6 THINWALL+PUSH": ct6_book_and_push,
    "CT-7 STALL": ct7_stall,
    "CT-8 STALL-NO-BOOK": ct8_stall_nobook,
    "CT-9 STALL+PUSH": ct9_best,
}


def run_day(day, mask_fn, k_stop, k_tgt, hold, cooldown=120.0, feats=None,
            ticks=None, params=None, flip=False, shuffle_seed=None):
    """Backtest one day.  Returns a list of trade dicts."""
    f = feats if feats is not None else prep(day)
    tt, pp = ticks if ticks is not None else L.ticks(day)
    m = mask_fn(f, **(params or {}))
    cand = f[m]
    if shuffle_seed is not None:            # placebo: keep the times, shuffle the side
        rng = np.random.default_rng(shuffle_seed)
        sides = rng.permutation(cand["side"].to_numpy())
    else:
        sides = cand["side"].to_numpy()
    trades, busy_until = [], -1e18
    for i, (t, atr, side) in enumerate(zip(cand["t"].to_numpy(),
                                           cand["atr20"].to_numpy(), sides)):
        t_dec = t + 5.0                      # decide at the bar close
        if t_dec < busy_until:
            continue
        if flip:
            side = "LONG" if side == "SHORT" else "SHORT"
        e = L.entry_fill(tt, pp, t_dec, side)
        if e is None:
            continue
        entry, t_ent = e
        sl, tg = k_stop * atr, k_tgt * atr
        if side == "SHORT":
            stop_px, tgt_px = entry + sl, entry - tg
            hit, t_hit, _ = L.race(tt, pp, t_ent, stop_px, tgt_px - L.TICK, hold)
            if hit == "UP" or hit == "BOTH":
                exit_px, reason = stop_px + L.TICK, "STOP"
            elif hit == "DN":
                exit_px, reason = tgt_px, "TARGET"
            else:
                exit_px, reason = _last_px(tt, pp, t_ent + hold), "TIME"
        else:
            stop_px, tgt_px = entry - sl, entry + tg
            hit, t_hit, _ = L.race(tt, pp, t_ent, tgt_px + L.TICK, stop_px, hold)
            if hit == "DN" or hit == "BOTH":
                exit_px, reason = stop_px - L.TICK, "STOP"
            elif hit == "UP":
                exit_px, reason = tgt_px, "TARGET"
            else:
                exit_px, reason = _last_px(tt, pp, t_ent + hold), "TIME"
        if exit_px is None or not np.isfinite(exit_px):
            continue
        net = L.pnl_usd(side, entry, exit_px)
        row = cand.iloc[i]
        trades.append(dict(day=day, t=t_dec, side=side, entry=entry, exit=exit_px,
                           reason=reason, net=net, atr=atr, secs=t_hit - t_ent,
                           er30=row["er30"], vs_flat=row["vs_flat"],
                           farwall=row["farwall"], rng_atr=row["rng_atr"],
                           tod=row["tod"], at=row["at"]))
        busy_until = max(t_hit, t_ent) + cooldown
    return trades


def _last_px(tt, pp, t_end):
    i = np.searchsorted(tt, t_end, side="right") - 1
    return pp[i] if i >= 0 else None


def backtest(name, k_stop, k_tgt, hold, days=None, params=None, cache=None, **kw):
    fn = CANDIDATES[name] if isinstance(name, str) else name
    days = days or L.DAYS
    out = []
    for d in days:
        c = cache.setdefault(d, (prep(d), L.ticks(d))) if cache is not None \
            else (prep(d), L.ticks(d))
        out += run_day(d, fn, k_stop, k_tgt, hold, feats=c[0], ticks=c[1],
                       params=params, **kw)
    return pd.DataFrame(out)
