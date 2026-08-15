#!/usr/bin/env python3
"""OPEN-NEWS greenfield — the five invented entry signals, and their tick-honest backtests.

None of these is a port of a live gate. Each is built from scratch around ONE claim about what makes
13:00-15:00Z different from the rest of the tape.

  ORX      opening-range expansion — the 13:00-13:30 range is the day's first real auction; the first
           5s CLOSE beyond it, by a buffer, is the ignition.  (trigger for the +236 / +124 monsters)
  VPOP     volatility pop — the first 1-min bar whose true range clears k x ATR14 AND closes on its
           own extreme.  Aimed straight at the detection-latency problem: fire on the ignition bar,
           not 119pt into the move.
  SQZGO    ORX, but only on days whose 12:30-13:30 pre-open range is COMPRESSED.  Fewer, cleaner.
  FBURST   flow burst — 60s net-aggressor z >= k with price agreeing.  A tape-order signal, not a
           price one.
  VWRC     VWAP reclaim drive — session VWAP from 13:00; price crosses it and holds N seconds with
           the 30-min ER above a floor.

Writes every trade to reports/friday_v7/sections/gf_on_trades_<cand>.json and the scoreboard to
gf_on_cands.json
"""
from __future__ import annotations

import json
import sys

import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import gf_on_engine as E  # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"


# ────────────────────────────────────────────────────────────────────────────────────────────
# signal generators — each returns [(sod, direction, meta), ...] for ONE day
# ────────────────────────────────────────────────────────────────────────────────────────────
def sig_orx(dd, *, or_lo=13 * 3600, or_hi=13 * 3600 + 1800, buf_frac=0.10, max_trades=1,
            require_expand=None):
    b = dd["bars5"]
    sod = b["sod"].values
    hi = b["high"].values
    lo = b["low"].values
    cl = b["close"].values
    m = (sod >= or_lo) & (sod < or_hi)
    if m.sum() < 200:
        return []
    rh, rl = float(hi[m].max()), float(lo[m].min())
    rng = rh - rl
    if rng <= 0:
        return []
    if require_expand is not None:
        # the range must itself be big enough to matter — a dead 30 min gives a meaningless break
        if rng < require_expand:
            return []
    buf = buf_frac * rng
    out = []
    live = (sod >= or_hi) & (sod < E.WIN_HI)
    for i in np.where(live)[0]:
        if len(out) >= max_trades:
            break
        # ★ sod is the bar's START. A 5s bar's CLOSE is not knowable until start+5 — entering at the
        # first tick after `sod` would be a 5-second look-ahead, which on an ignition bar is exactly
        # where the money is. +5 everywhere a 5s close is read.
        if cl[i] > rh + buf:
            out.append((int(sod[i]) + 5, +1, {"rng": rng, "lvl": rh}))
        elif cl[i] < rl - buf:
            out.append((int(sod[i]) + 5, -1, {"rng": rng, "lvl": rl}))
    return out


def sig_vpop(dd, *, k=2.0, close_frac=0.70, max_trades=3, lo=13 * 3600, hi=E.WIN_HI):
    rf = dd["rf"]
    s = rf["sod"].values
    o, h, l, c = rf["o"].values, rf["h"].values, rf["l"].values, rf["c"].values
    atr = rf["atr"].values
    out = []
    for i in range(len(s)):
        if not (lo <= s[i] < hi):
            continue
        if len(out) >= max_trades:
            break
        if np.isnan(atr[i]) or atr[i] <= 0:
            continue
        tr = h[i] - l[i]
        if tr < k * atr[i] or tr <= 0:
            continue
        pos = (c[i] - l[i]) / tr
        if pos >= close_frac:
            out.append((int(s[i]) + 60, +1, {"tr": tr, "atr": atr[i], "lo": l[i], "hi": h[i]}))
        elif pos <= 1 - close_frac:
            out.append((int(s[i]) + 60, -1, {"tr": tr, "atr": atr[i], "lo": l[i], "hi": h[i]}))
    return out


def preopen_range(dd, lo=12 * 3600 + 1800, hi=13 * 3600):
    b = dd["bars5"]
    sod = b["sod"].values
    m = (sod >= lo) & (sod < hi)
    if m.sum() < 200:
        return None
    return float(b["high"].values[m].max() - b["low"].values[m].min())


def sig_sqzgo(dd, *, pct_cut, **kw):
    """ORX gated on a COMPRESSED pre-open hour. pct_cut is an absolute point threshold that the
    caller derives from the sample's own distribution (passed in, never fitted inside)."""
    pr = preopen_range(dd)
    if pr is None or pr > pct_cut:
        return []
    return sig_orx(dd, **kw)


def sig_fburst(dd, *, z=2.0, lookback=2 * 3600, min_buckets=30, max_trades=3,
               agree=True, lo=13 * 3600, hi=E.WIN_HI):
    tk = dd["ticks"]
    if tk is None:
        return []
    s, px, sz, ag = tk["sod"], tk["px"], tk["sz"], tk["ag"]
    signed = np.where(ag == "buy", sz, np.where(ag == "sell", -sz, 0.0))
    bucket = s // 60
    ub = np.unique(bucket)
    sums = np.zeros(len(ub))
    idx = np.searchsorted(ub, bucket)
    np.add.at(sums, idx, signed)
    px_last = np.zeros(len(ub))
    px_first = np.zeros(len(ub))
    for k, b in enumerate(ub):
        sel = bucket == b
        px_first[k] = px[sel][0]
        px_last[k] = px[sel][-1]
    out = []
    for k, b in enumerate(ub):
        t = int(b * 60)
        if not (lo <= t < hi) or len(out) >= max_trades:
            continue
        prev = (ub * 60 >= t - lookback) & (ub * 60 < t)
        if prev.sum() < min_buckets:
            continue
        mu, sd = sums[prev].mean(), sums[prev].std(ddof=1)
        if sd <= 0:
            continue
        zz = (sums[k] - mu) / sd
        if abs(zz) < z:
            continue
        d = 1 if sums[k] > 0 else -1
        moved = px_last[k] - px_first[k]
        if agree and np.sign(moved) != d:
            continue
        out.append((t + 60, d, {"z": float(zz), "flow": float(sums[k])}))
    return out


def sig_vwrc(dd, *, hold_s=60, er_min=0.25, max_trades=3, lo=13 * 3600, hi=E.WIN_HI):
    b = dd["bars5"]
    sod = b["sod"].values
    cl = b["close"].values
    vol = b["volume"].values.astype(float)
    m = sod >= 13 * 3600
    if m.sum() < 100:
        return []
    tp = cl[m]
    vv = np.maximum(vol[m], 1e-9)
    vwap = np.cumsum(tp * vv) / np.cumsum(vv)
    ss = sod[m]
    above = tp > vwap
    emap = dd["emap"]
    out = []
    need = max(1, hold_s // 5)
    for i in range(need, len(ss)):
        t = int(ss[i])
        if not (lo <= t < hi) or len(out) >= max_trades:
            continue
        if not above[i - need - 1] and all(above[i - need:i + 1]):
            d = +1
        elif above[i - need - 1] and not any(above[i - need:i + 1]):
            d = -1
        else:
            continue
        er = emap.get(t // 60 * 60 - 60, np.nan)   # ★ last COMPLETED minute, never the live one
        if np.isnan(er) or er < er_min:
            continue
        out.append((t + 5, d, {"er": float(er)}))   # ★ +5: the 5s close is known at start+5
    return out


# ────────────────────────────────────────────────────────────────────────────────────────────
# runner
# ────────────────────────────────────────────────────────────────────────────────────────────
def run(days, siggen, *, stop_mode, stop_k=1.0, target_r=None, trail_arm_r=None, trail_r=None,
        be_arm_r=None, slip_ticks=1.0, time_stop=E.WIN_HI + 3600, tick_days_only=True, sigkw=None):
    """stop_mode: 'atr' (stop_k x ATR14) | 'struct' (the signal's own level) | 'range' (frac of the
    opening range).  target/trail are expressed in R = the stop distance, so a sweep of R is a sweep
    of SHAPE, not of an arbitrary point count."""
    sigkw = sigkw or {}
    trades = []
    for d in sorted(days):
        dd = days[d]
        if tick_days_only and dd["ticks"] is None:
            continue
        for sod, direction, meta in siggen(dd, **sigkw):
            # ★ the minute bar starting at sod//60*60 does not CLOSE until 60s later, so its ATR/ER
            # are unknowable at signal time. Step back one full minute. Sizing a stop off a bar that
            # has not happened yet is the quietest look-ahead there is.
            mkey = sod // 60 * 60 - 60
            atr = dd["amap"].get(mkey, np.nan)
            if np.isnan(atr) or atr <= 0:
                continue
            if stop_mode == "atr":
                stop_pt = stop_k * atr
            elif stop_mode == "struct":
                lvl = meta.get("lo") if direction > 0 else meta.get("hi")
                stop_pt = stop_k * atr if lvl is None else None
                if lvl is not None:
                    stop_pt = None      # resolved after entry price is known -> use atr fallback
                    stop_pt = stop_k * atr
            elif stop_mode == "range":
                stop_pt = stop_k * meta.get("rng", atr)
            else:
                raise ValueError(stop_mode)
            stop_pt = max(stop_pt, 4 * E.TICK)
            t = E.simulate(dd["ticks"], sod, direction,
                           stop_pt=stop_pt,
                           target_pt=None if target_r is None else target_r * stop_pt,
                           trail_arm=None if trail_arm_r is None else trail_arm_r * stop_pt,
                           trail_pt=None if trail_r is None else trail_r * stop_pt,
                           be_arm=None if be_arm_r is None else be_arm_r * stop_pt,
                           time_stop_sod=time_stop, slip_ticks=slip_ticks)
            if t is None:
                continue
            t["day"] = d
            t["regime"] = dd["rmap"].get(mkey, "unknown")
            t["atr"] = float(atr)
            t["er"] = float(dd["emap"].get(mkey, np.nan))
            t["stop_pt"] = float(stop_pt)
            t["sig_sod"] = sod
            t["meta"] = {k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                         for k, v in meta.items()}
            trades.append(t)
    return trades


def tod(t):
    s = t["entry_sod"]
    if s < 13 * 3600 + 1800:
        return "13:00-13:30 pre-open"
    if s < 14 * 3600:
        return "13:30-14:00 open drive"
    return "14:00-15:00 post-open"


if __name__ == "__main__":
    days = E.load_days()
    lo, hi = E.attach_regimes(days)
    prs = sorted(x for x in (preopen_range(days[d]) for d in days if days[d]["ticks"] is not None)
                 if x is not None)
    sqz_cut = prs[len(prs) // 3]
    print(f"ATR terciles {lo:.1f}/{hi:.1f}   pre-open-range 33rd pct = {sqz_cut:.1f}pt  (n={len(prs)})")

    CANDS = {
        "ORX":    (sig_orx,    dict(stop_mode="range", stop_k=0.5, target_r=2.0), {}),
        "VPOP":   (sig_vpop,   dict(stop_mode="atr", stop_k=1.0, target_r=2.0), {}),
        "SQZGO":  (sig_sqzgo,  dict(stop_mode="range", stop_k=0.5, target_r=2.0), dict(pct_cut=sqz_cut)),
        "FBURST": (sig_fburst, dict(stop_mode="atr", stop_k=1.0, target_r=2.0), {}),
        "VWRC":   (sig_vwrc,   dict(stop_mode="atr", stop_k=1.0, target_r=2.0), {}),
    }
    board = {}
    for name, (sg, kw, sigkw) in CANDS.items():
        tr = run(days, sg, sigkw=sigkw, **kw)
        board[name] = {"headline": E.score(tr),
                       "by_regime": E.by(tr, lambda t: t["regime"]),
                       "by_tod": E.by(tr, tod),
                       "by_dir": E.by(tr, lambda t: "LONG" if t["dir"] > 0 else "SHORT"),
                       "by_day": E.by(tr, lambda t: t["day"])}
        json.dump(tr, open(f"{SEC}/gf_on_trades_{name}.json", "w"), indent=0, default=float)
        s = board[name]["headline"]
        print(f"\n═══ {name}  n={s['n']}  net=${s['net']:+.0f}  win={s['win']}%  $/tr={s['per']}")
        print(E.table(board[name]["by_regime"], "regime"))
        print(E.table(board[name]["by_tod"], "time-of-day"))
    json.dump({"atr_terciles": [lo, hi], "sqz_cut": sqz_cut, "board": board},
              open(f"{SEC}/gf_on_cands.json", "w"), indent=1, default=float)
    print(f"\n→ {SEC}/gf_on_cands.json")
