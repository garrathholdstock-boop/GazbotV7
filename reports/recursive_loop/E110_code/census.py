"""E110 PHASE 0 — the widest-net census (spec: reports/recursive_loop/E110_change.txt, amendment A1).

One row per candidate entry: every 5-min slot from session open + 30 min to 19:40Z inside a confirmed leg of the
FROZEN detector, direction = the leg's, entry = close of the last closed 1-min bar. Features are causal (bars closed
before the slot); outcomes and hindsight leg labels are stored beside them and are never features.
Descriptive only: nothing here is selected, ranked or applied. Read-only on the desk.

    nice -n 19 .venv/bin/python reports/recursive_loop/E110_code/census.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import inspect
import os
import sys
import time
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import pandas as pd

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
import mil_detector_fit as DF  # noqa: E402

K = 11
SHA = "af0ace53e6dc9faa"
UTC = dt.timezone.utc
PARIS, NY = ZoneInfo("Europe/Paris"), ZoneInfo("America/New_York")
NQ_DIR, MNQ_DIR = f"{GB}/data/tape/bars/NQ", f"{GB}/data/tape/bars/MNQ"
OUT_PARQUET = f"{GB}/data/research/E110_census.parquet"
OUT_TURNS = f"{GB}/data/research/E110_turns.parquet"
TARGETS = (12.5, 25.0, 37.5, 50.0)     # today's points, from the fill
ADV, THRU, FEE, PV, QTY = 0.25, 0.25, 6.0, 2.0, 4
ROLL_MIN_PCT = 0.40
DROP_SPAN = ("2025-06-12", "2025-06-20")   # A1 3(b): NQ mid-session splice + 505-min hole
MNQ_5S_FROM = int(dt.datetime(2026, 8, 18, 22, 0, tzinfo=UTC).timestamp())
SREF_SPAN = ("2025-01-30", "2025-07-24")


def ts(d: str) -> int:
    return int(dt.datetime.fromisoformat(d + "T00:00:00+00:00").timestamp())


def sess_of(t):
    """Session key = UTC date of (t + 2h): the 22:00Z (EDT) / 23:00Z (EST) open belongs to the next day."""
    return (np.asarray(t) + 7200) // 86400


# ── data ─────────────────────────────────────────────────────────────────────────────────────────────
def load() -> list[dict]:
    con = duckdb.connect()
    con.execute("SET memory_limit='1500MB'; SET threads=2")
    nq = con.execute(f"""SELECT bar_ts, open, high, low, close, volume FROM read_parquet('{NQ_DIR}/*.parquet')
                         WHERE timeframe='1min' ORDER BY bar_ts""").fetchnumpy()
    bf = con.execute(f"""SELECT bar_ts, open, high, low, close, volume FROM read_parquet('{MNQ_DIR}/backfill_1min.parquet')
                         WHERE timeframe='1min' AND bar_ts < {MNQ_5S_FROM} ORDER BY bar_ts""").fetchnumpy()
    s5 = con.execute(f"""SELECT (bar_ts//60)*60 AS bar_ts, arg_min(open, bar_ts) AS open, max(high) AS high, min(low) AS low,
                                arg_max(close, bar_ts) AS close, sum(volume) AS volume
                         FROM read_parquet('{MNQ_DIR}/2026-*.parquet', union_by_name=true)
                         WHERE timeframe='5s' AND bar_ts >= {MNQ_5S_FROM} GROUP BY 1 ORDER BY 1""").fetchnumpy()
    mnq = {k: np.concatenate([bf[k], s5[k]]) for k in bf}
    segs = []
    d0, d1 = ts(DROP_SPAN[0]) // 86400, ts(DROP_SPAN[1]) // 86400
    s = sess_of(nq["bar_ts"])
    keep = (s < d0) | (s > d1)
    dropped = {"nq_sessions_dropped": int(len(np.unique(s[~keep]))), "nq_bars_dropped": int((~keep).sum())}
    for name, m in (("NQ-a", s < d0), ("NQ-b", s > d1)):
        segs.append({"name": name, "inst": "NQ", **{k: np.asarray(nq[k][m], dtype=np.float64) for k in nq}})
    segs.append({"name": "MNQ", "inst": "MNQ", **{k: np.asarray(mnq[k], dtype=np.float64) for k in mnq}})
    for g in segs:
        g["bar_ts"] = g["bar_ts"].astype(np.int64)
    return segs, dropped


def third_friday(y: int, m: int) -> dt.date:
    d = dt.date(y, m, 15)
    return d + dt.timedelta(days=(4 - d.weekday()) % 7)


def back_adjust(g: dict) -> list[dict]:
    """A1 3(a): in each [3rd Fri - 12d, 3rd Fri + 1d] window the largest POSITIVE session-open gap >= 0.40% is the roll;
    every earlier bar is shifted additively by it."""
    t, o, c = g["bar_ts"], g["open"], g["close"]
    gap_i = np.flatnonzero(np.diff(t) > 900) + 1
    sess = sess_of(t)
    rolls = []
    years = range(dt.datetime.fromtimestamp(t[0], UTC).year, dt.datetime.fromtimestamp(t[-1], UTC).year + 1)
    for y in years:
        for mth in (3, 6, 9, 12):
            tf = third_friday(y, mth)
            lo, hi = (tf - dt.timedelta(days=12)).toordinal(), (tf + dt.timedelta(days=1)).toordinal()
            best = None
            for i in gap_i:
                sd = (dt.date(1970, 1, 1) + dt.timedelta(days=int(sess[i]))).toordinal()
                if lo <= sd <= hi:
                    gp = o[i] - c[i - 1]
                    if gp > 0 and gp / c[i - 1] * 100 >= ROLL_MIN_PCT and (best is None or gp > best[1]):
                        best = (i, gp)
            if best:
                rolls.append({"seg": g["name"], "at": dt.datetime.fromtimestamp(int(t[best[0]]), UTC).strftime("%Y-%m-%d %H:%MZ"),
                              "gap_pts": round(float(best[1]), 2), "gap_pct": round(float(best[1] / c[best[0] - 1] * 100), 2),
                              "i": int(best[0]), "sess": int(sess[best[0]])})
    adj = np.zeros(len(t))
    for r in rolls:
        adj[: r["i"]] += r["gap_pts"]
    for k in ("open", "high", "low", "close"):
        g[k] = g[k] + adj
    g["roll_sess"] = {r["sess"] for r in rolls}
    return rolls


# ── detector ─────────────────────────────────────────────────────────────────────────────────────────
def detector_sha() -> str:
    return hashlib.sha256((inspect.getsource(DF.atr14) + inspect.getsource(DF.zigzag)).encode()).hexdigest()[:16]


def run_detector(t, h, l, c):
    bars = list(zip(t.tolist(), h.tolist(), l.tolist(), c.tolist()))
    atr = DF.atr14(bars)
    piv = DF.zigzag(bars, atr, lambda leg, a: K * a)
    return np.array(atr), piv


def ffill_grid(t, h, l, c):
    """A1 4 sensitivity: fill missing minutes INSIDE a session (gaps <= 30 min) with flat bars at the last close."""
    tt, hh, ll, cc = [t[0]], [h[0]], [l[0]], [c[0]]
    for i in range(1, len(t)):
        g = (t[i] - t[i - 1]) // 60
        if 1 < g <= 30:
            for k in range(1, g):
                tt.append(t[i - 1] + 60 * k); hh.append(c[i - 1]); ll.append(c[i - 1]); cc.append(c[i - 1])
        tt.append(t[i]); hh.append(h[i]); ll.append(l[i]); cc.append(c[i])
    return np.array(tt), np.array(hh), np.array(ll), np.array(cc)


def turn_agreement(pa, pb, tol=900):
    """share of pa's pivots that have a same-direction pivot in pb within tol seconds"""
    if not pa:
        return float("nan")
    tb = np.array([p[0] for p in pb]); db = np.array([p[2] for p in pb])
    hit = 0
    for p in pa:
        j = np.searchsorted(tb, p[0])
        for k in (j - 1, j, j + 1):
            if 0 <= k < len(tb) and abs(tb[k] - p[0]) <= tol and db[k] == p[2]:
                hit += 1
                break
    return hit / len(pa)


def sessions(g: dict):
    """session index ranges, keys, and S_day = mean high-low of the PRIOR 20 sessions (needs >= 10 prior)."""
    t, h, l = g["bar_ts"], g["high"], g["low"]
    sess = sess_of(t)
    sb = np.flatnonzero(np.r_[True, sess[1:] != sess[:-1]])
    se = np.r_[sb[1:], len(t)]
    s_rng = np.array([h[a:b].max() - l[a:b].min() for a, b in zip(sb, se)])
    s_day = np.full(len(sb), np.nan)
    for i in range(len(sb)):
        prev = s_rng[max(0, i - 20):i]
        if len(prev) >= 10:
            s_day[i] = prev.mean()
    return sb, se, sess[sb], s_day


def s_ref(g: dict) -> float:
    _, _, keys, s_day = sessions(g)
    m = (keys >= ts(SREF_SPAN[0]) // 86400) & (keys <= ts(SREF_SPAN[1]) // 86400) & np.isfinite(s_day)
    return float(s_day[m].mean())


# ── census ───────────────────────────────────────────────────────────────────────────────────────────
def period_of(sess_day: int, inst: str) -> str:
    d = dt.date(1970, 1, 1) + dt.timedelta(days=int(sess_day))
    if inst == "MNQ":
        return "FORWARD"
    return "TRAIN" if d < dt.date(2023, 1, 1) else "TEST"


def census_segment(g: dict, sref: float):
    t, o, h, l, c, v = (g[k] for k in ("bar_ts", "open", "high", "low", "close", "volume"))
    n = len(t)
    atr, piv = run_detector(t, h, l, c)
    g["piv"] = piv
    sess = sess_of(t)
    sb, se, s_keys, s_day = sessions(g)
    # pivots
    p_ts = np.array([p[0] for p in piv], dtype=np.int64)
    p_px = np.array([p[1] for p in piv])
    p_dir = np.array([p[2] for p in piv], dtype=np.int64)
    p_cts = np.array([p[3] for p in piv], dtype=np.int64)
    p_idx = np.searchsorted(t, p_ts)
    # completed leg sizes, known at the confirm of the NEXT pivot
    leg_done_t = p_cts[1:]
    leg_size = np.abs(p_px[1:] - p_px[:-1])
    # session-cumulative hi/lo
    cumhi, cumlo = np.empty(n), np.empty(n)
    for a, b in zip(sb, se):
        cumhi[a:b] = np.maximum.accumulate(h[a:b]); cumlo[a:b] = np.minimum.accumulate(l[a:b])
    csv = np.r_[0.0, np.cumsum(v)]
    rows = []
    for si, (a, b) in enumerate(zip(sb, se)):
        if not np.isfinite(s_day[si]):
            continue
        k = sref / s_day[si]
        day = int(s_keys[si])
        d_date = dt.date(1970, 1, 1) + dt.timedelta(days=day)
        d0 = day * 86400
        flat_t = d0 + 20 * 3600 + 40 * 60
        e = int(np.searchsorted(t, flat_t, "left")) - 1          # last bar opening before 20:40Z
        if e <= a:
            continue
        open_t = int(t[a])
        if open_t > d0 + 3600:          # session must open the evening before (22:00/23:00Z)
            continue
        veto_t = int(dt.datetime(d_date.year, d_date.month, d_date.day, 5, tzinfo=PARIS).timestamp())
        edt = dt.datetime(d_date.year, d_date.month, d_date.day, 12, tzinfo=NY).utcoffset() == dt.timedelta(hours=-4)
        # trailing 250-session median completed-leg size
        lo_t = int(t[sb[max(0, si - 250)]])
        mk = (leg_done_t >= lo_t) & (leg_done_t < open_t)
        med_leg = float(np.median(leg_size[mk])) if mk.sum() >= 20 else np.nan
        s_first = (open_t // 300 + 6) * 300                        # first :x0/:x5 slot >= open + 30 min
        last_slot = d0 + 19 * 3600 + 35 * 60
        for s in range(s_first, last_slot + 1, 300):
            j = int(np.searchsorted(t, s - 60, "right")) - 1        # last bar whose close is known at s
            if j < a or j + 1 > e:
                continue
            kp = int(np.searchsorted(p_cts, s - 60, "right")) - 1   # current confirmed leg
            if kp < 0:
                continue
            d = int(p_dir[kp]); pi = int(p_idx[kp]); start_px = p_px[kp]
            entry = c[j]
            if d > 0:
                ext_c, ext_h = c[pi:j + 1].max(), h[pi:j + 1].max()
            else:
                ext_c, ext_h = c[pi:j + 1].min(), l[pi:j + 1].min()
            leg_ext = d * (ext_c - start_px)
            off = d * (ext_c - entry) / leg_ext if leg_ext > 0 else np.nan
            shi, slo = cumhi[j], cumlo[j]
            rng = shi - slo
            pos = ((entry - slo) if d > 0 else (shi - entry)) / rng if rng > 0 else np.nan
            j360 = int(np.searchsorted(t, s - 21600, "left"))
            h360, l360 = h[j360:j + 1].max(), l[j360:j + 1].min()
            pos360 = ((entry - l360) if d > 0 else (h360 - entry)) / (h360 - l360) if h360 > l360 else np.nan
            i30, i10 = int(np.searchsorted(t, s - 1800, "left")), int(np.searchsorted(t, s - 600, "left"))
            r30 = h[i30:j + 1].max() - l[i30:j + 1].min() if j >= i30 else np.nan
            r10 = h[i10:j + 1].max() - l[i10:j + 1].min() if j >= i10 else np.nan
            vol30 = csv[j + 1] - csv[i30]
            # ── outcomes (labels) ──
            ph, pl, tp = h[j + 1:e + 1], l[j + 1:e + 1], t[j + 1:e + 1]
            fav = (ph - entry) if d > 0 else (entry - pl)
            adv = (entry - pl) if d > 0 else (ph - entry)
            fav_t, adv_t = fav * k - ADV, adv * k + ADV               # today's pts from the fill
            cf = np.maximum.accumulate(fav_t)
            hits = {}
            for T in TARGETS:
                w = np.flatnonzero(cf >= T + THRU)
                hits[T] = int(w[0]) if len(w) else -1
            hi375 = hits[37.5]
            mae_hit = float(np.max(adv_t[: hi375 + 1])) if hi375 >= 0 else float(np.max(adv_t))
            final = d * (c[e] - entry) * k - ADV
            usd_all = (QTY * PV * 37.5 if hi375 >= 0 else QTY * PV * final) - FEE
            usd_h = sum(PV * (T if hits[T] >= 0 else final) for T in TARGETS) - FEE
            # hindsight leg end
            if kp + 1 < len(piv):
                fe, fe_t = p_px[kp + 1], int(p_ts[kp + 1])
                tot = d * (fe - start_px)
                run_left = d * (fe - entry) / tot if tot > 0 else np.nan
                to_turn = (fe_t - s) / 60
            else:
                fe, run_left, to_turn = np.nan, np.nan, np.nan
            rows.append((
                g["inst"], day, s, d, float(entry), float(atr[j]), float(k), float(s_day[si]),
                (s - int(t[j]) - 60) / 60,                                   # staleness of the entry bar
                float(leg_ext * k), float(leg_ext / atr[j]) if atr[j] > 0 else np.nan,
                float(leg_ext / med_leg) if med_leg and np.isfinite(med_leg) else np.nan,
                float(off), float(d * (ext_h - entry) * k), (s - int(p_ts[kp])) / 60, (s - int(p_cts[kp])) / 60,
                float(pos), float(pos360), float(rng / s_day[si]), float(vol30),
                float(r10 / r30) if r30 and r30 > 0 else np.nan,
                s >= 2 * 3600 + d0 and s < d0 + 13 * 3600 + 1800 and s >= veto_t,
                s >= d0 + 6 * 3600 and s < d0 + 19 * 3600 + 2400,
                s >= veto_t, bool(edt), day in g["roll_sess"] or (day - 1) in g["roll_sess"] or (day - 3) in g["roll_sess"],
                *[(int(tp[hits[T]]) + 60 - s) / 60 if hits[T] >= 0 else np.nan for T in TARGETS],
                mae_hit, float(adv_t.max()), float(fav_t.max()), float(final), float(usd_all), float(usd_h),
                float(run_left), float(to_turn), float((fe - start_px) * d * k) if np.isfinite(fe) else np.nan,
            ))
    return rows


COLS = ["inst", "sess", "slot_ts", "dir", "entry", "atr", "k", "s_day", "stale_min",
        "leg_ext_pts", "leg_ext_atr", "leg_ext_frac", "off_extreme", "off_extreme_hi_pts", "leg_age_min", "since_confirm_min",
        "pos_in_range", "pos_in_range_360", "range_frac", "vol30", "stall",
        "in_live_window", "in_leg_window", "after_veto", "edt", "roll_adj",
        "hit12_min", "hit25_min", "hit37_min", "hit50_min",
        "mae_to_hit", "mae_flat", "mfe_flat", "final_pts", "usd_allout", "usd_h", "run_left", "min_to_turn", "leg_total_pts"]


def rvol(df: pd.DataFrame) -> pd.Series:
    """rvol30 = vol30 / median vol30 at the same time-of-day over the prior 20 sessions (same instrument)."""
    tod = df["slot_ts"] % 86400
    out = pd.Series(np.nan, index=df.index)
    for (_inst, _tod), grp in df.groupby([df["inst"], tod], sort=False):
        base = grp["vol30"].shift(1).rolling(20, min_periods=10).median()
        out.loc[grp.index] = grp["vol30"] / base
    return out


def main():
    t0 = time.time()
    assert detector_sha() == SHA, f"detector sha {detector_sha()} != {SHA}"
    segs, dropped = load()
    rolls = []
    for g in segs:
        rolls += back_adjust(g)
    print("rolls back-adjusted:", len(rolls))
    for r in rolls:
        print("  ", r["seg"], r["at"], f"+{r['gap_pts']}pt", f"{r['gap_pct']}%")
    sref = s_ref(segs[0])          # 2025-01-30..07-24 lies in NQ-a
    print("S_ref", round(sref, 1), "| dropped", dropped)
    rows, sens = [], {}
    for g in segs:
        r = census_segment(g, sref)
        rows += r
        print(f"  {g['name']}: {len(g['bar_ts']):,} bars, {len(g['piv']):,} turns, {len(r):,} candidates  ({time.time()-t0:.0f}s)")
    df = pd.DataFrame(rows, columns=COLS)
    df["period"] = [period_of(s, i) for s, i in zip(df["sess"], df["inst"])]
    df["rvol30"] = rvol(df)
    os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
    con = duckdb.connect()
    con.register("df", df)
    con.execute(f"COPY df TO '{OUT_PARQUET}' (FORMAT PARQUET)")
    tr = [(g["inst"], g["name"], *p) for g in segs for p in g["piv"]]
    tdf = pd.DataFrame(tr, columns=["inst", "seg", "pivot_ts", "pivot_px", "new_dir", "confirm_ts", "confirm_px"])
    con.register("tdf", tdf)
    con.execute(f"COPY tdf TO '{OUT_TURNS}' (FORMAT PARQUET)")
    # sensitivity: forward-filled minute grid, NQ-a only (the long sparse block)
    g = segs[0]
    ft = ffill_grid(g["bar_ts"], g["high"], g["low"], g["close"])
    _, pf = run_detector(*ft)
    sens = {"bars": len(g["bar_ts"]), "bars_ffill": len(ft[0]), "turns": len(g["piv"]), "turns_ffill": len(pf),
            "agree_census_in_ffill": turn_agreement(g["piv"], pf), "agree_ffill_in_census": turn_agreement(pf, g["piv"])}
    meta = {"rolls": rolls, "dropped": dropped, "sref": sref, "sensitivity": sens, "rows": len(df),
            "built_at": dt.datetime.now(UTC).isoformat(), "sha": SHA}
    import json
    json.dump(meta, open(f"{GB}/data/research/E110_census_meta.json", "w"), indent=1, default=str)
    print("sensitivity", sens)
    print(f"wrote {len(df):,} rows -> {OUT_PARQUET} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
