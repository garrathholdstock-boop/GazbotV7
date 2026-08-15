#!/usr/bin/env python3
"""OPEN-NEWS greenfield — the shared TICK-HONEST engine.

★ THE FEE IS $1.50 PER ROUND TRIP.  MNQ IS $2.00/POINT.  Both are asserted at import so a copy of
this file can never silently inherit the wrong constants (the `FEE, VPP = 5.0, 2.0` trap).

Everything the hunt needs, once:
  * per-day tape (5s bars, 1-min bars, TRADE TICKS) loaded from the frozen cache in data/cache_gf_on
  * a regime label per minute (ATR level x efficiency ratio x range-break) — the desk's vocabulary
  * `simulate()` — walks REAL TICKS forward from a signal; stop/target/trail/time-stop resolved on
    single-price ticks, so there is never a same-bar "which came first" fudge
  * `score()` / `by()` — n / net / win% / $-per-trade, sliced any way you like
"""
from __future__ import annotations

import os
import pickle

import numpy as np
import pandas as pd

VPP = 2.0    # MNQ dollars per point           ← MGC is 10.0; never cross them
FEE = 1.50   # dollars per ROUND TRIP          ← not per side, not $5, not $2
TICK = 0.25  # MNQ minimum price increment
assert (VPP, FEE) == (2.0, 1.50), "cost constants tampered with"

CACHE = "/home/alphabot/gazbot7/data/cache_gf_on"
PKL = f"{CACHE}/days.pkl"

WIN_LO, WIN_HI = 13 * 3600, 15 * 3600          # the OPEN/NEWS clock bucket, in seconds-of-day
RUNWAY = 16 * 3600                             # exits may run to 16:00Z


# ────────────────────────────────────────────────────────────────────────────────────────────
# tape loading
# ────────────────────────────────────────────────────────────────────────────────────────────
def _minute_bars(sod, o, h, l, c, v):
    m = (sod // 60).astype(np.int64)
    df = pd.DataFrame({"m": m, "o": o, "h": h, "l": l, "c": c, "v": v})
    g = df.groupby("m", sort=True)
    return pd.DataFrame({
        "sod": g["m"].first().values * 60,
        "o": g["o"].first().values, "h": g["h"].max().values,
        "l": g["l"].min().values, "c": g["c"].last().values, "v": g["v"].sum().values})


def load_days(force=False):
    """Every day we hold, as a dict d -> {bars5, m1, ticks}. Cached to a pickle; the pickle IS the
    frozen snapshot every candidate reads."""
    if os.path.exists(PKL) and not force:
        with open(PKL, "rb") as f:
            return pickle.load(f)

    import duckdb
    con = duckdb.connect()
    con.execute("SET memory_limit='2GB'; SET threads=3")
    bars = con.execute(f"""SELECT d, sod, open, high, low, close, volume
        FROM read_parquet('{CACHE}/bars5s.parquet') ORDER BY d, sod""").fetchdf()
    ticks = con.execute(f"""SELECT d, sod, ts_ms, price, size, aggressor
        FROM read_parquet('{CACHE}/ticks_win.parquet')
        WHERE sod >= {12*3600+1800} AND sod < {RUNWAY} ORDER BY ts_ms""").fetchdf()

    days = {}
    for d, gb in bars.groupby("d"):
        gb = gb.sort_values("sod")
        m1 = _minute_bars(gb["sod"].values, gb["open"].values, gb["high"].values,
                          gb["low"].values, gb["close"].values, gb["volume"].values)
        days[d] = {"bars5": gb.reset_index(drop=True), "m1": m1, "ticks": None}
    for d, gt in ticks.groupby("d"):
        if d in days:
            days[d]["ticks"] = {"ts": gt["ts_ms"].values.astype(np.int64),
                                "px": gt["price"].values.astype(np.float64),
                                "sz": gt["size"].values.astype(np.float64),
                                "ag": gt["aggressor"].values.astype(object),
                                "sod": gt["sod"].values.astype(np.int64)}
    with open(PKL, "wb") as f:
        pickle.dump(days, f, protocol=4)
    return days


# ────────────────────────────────────────────────────────────────────────────────────────────
# regime — the desk's own vocabulary (ATR level x efficiency ratio x range-break)
# ────────────────────────────────────────────────────────────────────────────────────────────
def regime_frame(m1: pd.DataFrame, atr_n=14, er_n=30, rng_n=60) -> pd.DataFrame:
    """One row per MINUTE: atr (pt), er (Kaufman 30-min), rng60 (hi-lo of last hour), and whether
    the close has just broken that hour's range. Everything is BACKWARD-looking — the value on
    minute t uses only bars <= t, so a signal that reads it is not peeking."""
    h, l, c = m1["h"].values, m1["l"].values, m1["c"].values
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).rolling(atr_n, min_periods=atr_n).mean().values
    dirn = np.abs(c - pd.Series(c).shift(er_n).values)
    vol = pd.Series(np.abs(np.diff(c, prepend=c[0]))).rolling(er_n, min_periods=er_n).sum().values
    er = np.where(vol > 0, dirn / vol, np.nan)
    hh = pd.Series(h).rolling(rng_n, min_periods=20).max().shift(1).values
    ll = pd.Series(l).rolling(rng_n, min_periods=20).min().shift(1).values
    out = m1.copy()
    out["atr"] = atr
    out["er"] = er
    out["hh60"] = hh
    out["ll60"] = ll
    out["rng60"] = hh - ll
    out["brk"] = np.where(c > hh, 1, np.where(c < ll, -1, 0))
    return out


def regime_label(atr, er, brk, atr_lo, atr_hi):
    """Five buckets, keyed on ATR LEVEL + ER + RANGE-BREAK — never the clock alone."""
    if atr is None or np.isnan(atr) or er is None or np.isnan(er):
        return "unknown"
    if er >= 0.45:
        return "clean-trend"
    if er >= 0.25:
        return "building"
    if atr >= atr_hi:
        return "violent-whipsaw"
    if atr <= atr_lo:
        return "dead-chop"
    return "normal-chop"


def attach_regimes(days, lo_q=0.33, hi_q=0.67):
    """ATR terciles measured across the WHOLE in-window tape, so 'high ATR' means high for this
    instrument in this window, not high for this day."""
    allatr = []
    for d, dd in days.items():
        rf = regime_frame(dd["m1"])
        dd["rf"] = rf
        sel = (rf["sod"] >= WIN_LO) & (rf["sod"] < WIN_HI)
        allatr.append(rf.loc[sel, "atr"].dropna().values)
    a = np.concatenate([x for x in allatr if len(x)])
    lo, hi = float(np.quantile(a, lo_q)), float(np.quantile(a, hi_q))
    for d, dd in days.items():
        rf = dd["rf"]
        rf["regime"] = [regime_label(x, y, z, lo, hi)
                        for x, y, z in zip(rf["atr"], rf["er"], rf["brk"])]
        dd["rmap"] = dict(zip(rf["sod"].values, rf["regime"].values))
        dd["amap"] = dict(zip(rf["sod"].values, rf["atr"].values))
        dd["emap"] = dict(zip(rf["sod"].values, rf["er"].values))
    return lo, hi


# ────────────────────────────────────────────────────────────────────────────────────────────
# execution — tick by tick, no same-bar ambiguity
# ────────────────────────────────────────────────────────────────────────────────────────────
def simulate(tk, sig_sod, direction, *, stop_pt, target_pt=None, trail_arm=None, trail_pt=None,
             time_stop_sod=None, slip_ticks=1.0, be_arm=None):
    """Walk REAL trade ticks from the first tick strictly after `sig_sod`.

    direction  +1 long / -1 short
    stop_pt    hard stop distance in points from entry
    target_pt  optional fixed target
    trail_arm  arm a trailing stop once MFE >= this many points …
    trail_pt   … then trail `trail_pt` behind the best price
    be_arm     move the stop to breakeven once MFE >= this many points
    slip_ticks adverse slippage applied to BOTH entry and exit, in MNQ ticks (0.25pt each)

    Returns None if the day has no tick tape, else a dict with entry/exit/pnl (net of $1.50 RT).
    """
    if tk is None:
        return None
    i = int(np.searchsorted(tk["sod"], sig_sod, side="right"))
    if i >= len(tk["sod"]):
        return None
    slip = slip_ticks * TICK
    ent = tk["px"][i] + direction * slip
    ent_sod = int(tk["sod"][i])
    stop = ent - direction * stop_pt
    best = ent
    armed_trail = False
    tstop = time_stop_sod if time_stop_sod is not None else RUNWAY - 1

    px = tk["px"]
    sod = tk["sod"]
    n = len(px)
    j = i + 1
    while j < n and sod[j] <= tstop:
        p = px[j]
        # favourable excursion first (updates the trail), then the stop test on the SAME tick.
        if direction * (p - best) > 0:
            best = p
            if trail_arm is not None and direction * (best - ent) >= trail_arm:
                armed_trail = True
            if be_arm is not None and direction * (best - ent) >= be_arm:
                stop = max(stop, ent) if direction > 0 else min(stop, ent)
        if armed_trail:
            t = best - direction * trail_pt
            stop = max(stop, t) if direction > 0 else min(stop, t)
        if direction > 0 and p <= stop:
            return _close(ent, ent_sod, stop, int(sod[j]), direction, slip, best, "STOP")
        if direction < 0 and p >= stop:
            return _close(ent, ent_sod, stop, int(sod[j]), direction, slip, best, "STOP")
        if target_pt is not None and direction * (p - ent) >= target_pt:
            return _close(ent, ent_sod, ent + direction * target_pt, int(sod[j]), direction, slip,
                          best, "TARGET")
        j += 1
    # j is the first tick PAST the time stop (or the end of tape) — the last tradeable tick is j-1.
    # Closing on px[j] would fill the time stop at a price that had not printed yet.
    k = max(i, min(j - 1, n - 1))
    return _close(ent, ent_sod, px[k], int(sod[k]), direction, slip, best, "TIME")


def simulate_fast(tk, sig_sod, direction, *, stop_pt, target_pt=None, trail_arm=None, trail_pt=None,
                  time_stop_sod=None, slip_ticks=1.0, be_arm=None):
    """Vectorised twin of `simulate` — same rules, same answers (cross-checked in gf_on_verify.py),
    ~200x faster, which is what makes an honest parameter SWEEP affordable rather than a token one.

    The equivalence rests on one detail: the loop updates the running best BEFORE testing the stop on
    that same tick, so the stop level at tick j legitimately includes tick j's own extreme. The
    cumulative maximum does exactly that, which is why `np.maximum.accumulate` is the right operator
    and a shifted version would be a different (and wrong) strategy."""
    if tk is None:
        return None
    sod, px = tk["sod"], tk["px"]
    i = int(np.searchsorted(sod, sig_sod, side="right"))
    if i >= len(px):
        return None
    tstop = time_stop_sod if time_stop_sod is not None else RUNWAY - 1
    end = int(np.searchsorted(sod, tstop, side="right"))
    if end <= i + 1:
        end = min(i + 2, len(px))
    slip = slip_ticks * TICK
    ent = px[i] + direction * slip
    ent_sod = int(sod[i])
    seg = px[i + 1:end]
    if len(seg) == 0:
        return _close(ent, ent_sod, px[i], ent_sod, direction, slip, ent, "TIME")

    d = float(direction)
    run_best = np.maximum.accumulate(seg) if d > 0 else np.minimum.accumulate(seg)
    run_best = np.maximum(run_best, ent) if d > 0 else np.minimum(run_best, ent)
    mfe = d * (run_best - ent)

    NEG = -np.inf if d > 0 else np.inf
    lvl = np.full(len(seg), float(ent - d * stop_pt))
    if trail_arm is not None and trail_pt is not None:
        t = np.where(mfe >= trail_arm, run_best - d * trail_pt, NEG)
        lvl = np.maximum(lvl, t) if d > 0 else np.minimum(lvl, t)
    if be_arm is not None:
        b = np.where(mfe >= be_arm, float(ent), NEG)
        lvl = np.maximum(lvl, b) if d > 0 else np.minimum(lvl, b)
    lvl = np.maximum.accumulate(lvl) if d > 0 else np.minimum.accumulate(lvl)

    hit_stop = np.flatnonzero(seg <= lvl) if d > 0 else np.flatnonzero(seg >= lvl)
    js = hit_stop[0] if len(hit_stop) else len(seg)
    if target_pt is not None:
        ht = np.flatnonzero(d * (seg - ent) >= target_pt)
        jt = ht[0] if len(ht) else len(seg)
    else:
        jt = len(seg)

    if js <= jt and js < len(seg):
        return _close(ent, ent_sod, float(lvl[js]), int(sod[i + 1 + js]), direction, slip,
                      float(run_best[js]), "STOP")
    if jt < len(seg):
        return _close(ent, ent_sod, float(ent + d * target_pt), int(sod[i + 1 + jt]), direction,
                      slip, float(run_best[jt]), "TARGET")
    k = len(seg) - 1
    return _close(ent, ent_sod, float(seg[k]), int(sod[i + 1 + k]), direction, slip,
                  float(run_best[k]), "TIME")


def _close(ent, ent_sod, exit_px, exit_sod, direction, slip, best, reason):
    ex = exit_px - direction * slip
    pts = direction * (ex - ent)
    return {"entry": float(ent), "entry_sod": ent_sod, "exit": float(ex), "exit_sod": exit_sod,
            "dir": int(direction), "pts": float(pts), "net": float(pts * VPP - FEE),
            "mfe": float(direction * (best - ent)), "reason": reason,
            "held_s": exit_sod - ent_sod}


# ────────────────────────────────────────────────────────────────────────────────────────────
# scoring
# ────────────────────────────────────────────────────────────────────────────────────────────
def score(trades) -> dict:
    if not trades:
        return {"n": 0, "net": 0.0, "win": None, "per": None, "gross": 0.0}
    net = sum(t["net"] for t in trades)
    w = sum(1 for t in trades if t["net"] > 0)
    return {"n": len(trades), "net": round(net, 2), "win": round(100 * w / len(trades), 1),
            "per": round(net / len(trades), 2),
            "gross": round(sum(t["pts"] for t in trades) * VPP, 2)}


def by(trades, key):
    out = {}
    for t in trades:
        out.setdefault(key(t), []).append(t)
    return {k: score(v) for k, v in sorted(out.items(), key=lambda x: str(x[0]))}


def table(d, label="key"):
    rows = [f"| {label} | n | net $ | win% | $/trade |", "|---|---:|---:|---:|---:|"]
    for k, s in d.items():
        wn = "—" if s["win"] is None else f"{s['win']:.0f}%"
        pr = "—" if s["per"] is None else f"{s['per']:+.2f}"
        rows.append(f"| {k} | {s['n']} | {s['net']:+.0f} | {wn} | {pr} |")
    return "\n".join(rows)
