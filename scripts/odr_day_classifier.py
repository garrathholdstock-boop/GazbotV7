#!/usr/bin/env python3
"""THE OPEN RIDER (odr_*) as a DAY-DETECTION problem — replay + causal day classifier.

The operator, 2026-08-14: "open rider best shadow again ... but i know they bleed on other days.
thats where im saying we need detection some how to block open rider if conditions arent juicy."

The forward shadow book is only FIVE days (08-10..08-14), which cannot separate a real day
classifier from noise. But odr is a pure CLOCK rider — no signal, no gate, just "every N minutes
between 13:00 and 14:45 UTC, go with the sign of the last 15 minutes" — so it is fully
deterministic and can be REPLAYED over every day of tape we hold. That turns n=5 days into ~40.

What this does:
  1. Rebuild 1m bars from the 5s lake (06-19..08-14, V5 + lake + hot), ATR-14 halt-aware.
  2. Replay all four ungated cells (cadence 5/10 x stop 2.0/3.0 xATR, target = 2R coupled).
  3. VALIDATE the replay against the 5 days of real forward shadow trades before trusting it.
  4. Compute per-day features knowable BEFORE 13:00 UTC (causal), plus the 13:00-13:30 opening
     range as a separate LATER-INFORMATION arm (it is not available to the 13:00 entry).
  5. Score every single-feature day rule, and PLACEBO-CONTROL it against removing the same NUMBER
     of days at random.

READ-ONLY. Costs: $1.50/round-trip, $2.00/point (MNQ), 1 lot.

  cd /home/alphabot/gazbot7 && PYTHONPATH=src:scripts ./.venv/bin/python scripts/odr_day_classifier.py
"""
from __future__ import annotations
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.lake import connect

VPP, FEE = 2.0, 1.5           # $2.00/point MNQ, $1.50 per ROUND TRIP
WIN_START, WIN_END = 13 * 3600, 14 * 3600 + 45 * 60
LOOKBACK_MIN = 15
TARGET_R = 2.0
TIME_CAP_S = 45 * 60
CELLS = [("odr_c5_s20", 5, 2.0), ("odr_c5_s30", 5, 3.0),
         ("odr_c10_s20", 10, 2.0), ("odr_c10_s30", 10, 3.0)]
OUT = "/home/alphabot/gazbot7/data/odr_day_classifier.json"


# ─────────────────────────────── tape ───────────────────────────────
def load_minutes() -> pd.DataFrame:
    """1m OHLC for every day, aggregated from the 5s lake so all ~40 days share one construction."""
    con = connect(symbol="MNQ")
    df = con.execute("""
        SELECT CAST(bar_ts - bar_ts % 60 AS BIGINT) m,
               arg_min(open, bar_ts) o, max(high) h, min(low) l,
               arg_max(close, bar_ts) c, sum(volume) v
        FROM bars WHERE timeframe='5s' GROUP BY 1 ORDER BY 1""").df()
    con.close()
    df["day"] = pd.to_datetime(df.m, unit="s", utc=True).dt.strftime("%Y-%m-%d")
    return df


def load_5s() -> pd.DataFrame:
    """5s OHLC — the exit path. Finer than 1m; stop assumed to win any same-bar stop/target race."""
    con = connect(symbol="MNQ")
    df = con.execute("""SELECT bar_ts t, open o, high h, low l, close c
                        FROM bars WHERE timeframe='5s' ORDER BY bar_ts""").df()
    con.close()
    df["day"] = pd.to_datetime(df.t, unit="s", utc=True).dt.strftime("%Y-%m-%d")
    return df


def atr14(o, h, l, c, mins, n=14):
    """ATR-14, halt-aware: the two gap terms only count when bars are genuinely adjacent (60s)."""
    tr = np.zeros(len(c))
    tr[0] = h[0] - l[0]
    for i in range(1, len(c)):
        rng = h[i] - l[i]
        if mins[i] - mins[i - 1] == 60:
            tr[i] = max(rng, abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        else:
            tr[i] = rng
    return pd.Series(tr).rolling(n, min_periods=1).mean().values


# ─────────────────────────── the replay ───────────────────────────
def replay_day(mday: pd.DataFrame, sday: pd.DataFrame, cadence: int, stop_k: float):
    """One day, one cell. Returns list of trades. Mirrors shadow.py::_rider_entry exactly."""
    mins = mday.m.values.astype(np.int64)
    c = mday.c.values.astype(float)
    a = atr14(mday.o.values.astype(float), mday.h.values.astype(float),
              mday.l.values.astype(float), c, mins)
    idx = {int(m): i for i, m in enumerate(mins)}
    st, sh, sl, sc = (sday.t.values.astype(np.int64), sday.h.values.astype(float),
                      sday.l.values.astype(float), sday.c.values.astype(float))

    trades, flat_at = [], 0
    day0 = (int(mins[0]) // 86400) * 86400
    for sec in range(WIN_START, WIN_END, 60):
        if (sec // 60) % max(cadence, 1):
            continue                                    # not a cadence boundary
        ts = day0 + sec
        if ts < flat_at:
            continue                                    # still in a position
        i = idx.get(ts)
        if i is None or i < LOOKBACK_MIN:
            continue
        mom = c[i] - c[i - LOOKBACK_MIN]
        if mom == 0:
            continue                                    # dead flat is SKIPPED, not sent short
        side = 1 if mom > 0 else -1
        atr = a[i]
        if not np.isfinite(atr) or atr <= 0:
            continue
        entry = c[i]
        stop_d = stop_k * atr
        targ_d = stop_d * TARGET_R                      # target coupled to the stop (decouple=False)
        stop = entry - side * stop_d
        targ = entry + side * targ_d

        k = np.searchsorted(st, ts)                     # walk the 5s path forward
        cap_ts = ts + TIME_CAP_S
        px, why, xts = None, "TIME_CAP", cap_ts
        while k < len(st) and st[k] <= cap_ts:
            hi, lo = sh[k], sl[k]
            hit_stop = lo <= stop if side > 0 else hi >= stop
            hit_targ = hi >= targ if side > 0 else lo <= targ
            if hit_stop:                                # stop wins a same-bar race (conservative)
                px, why, xts = stop, "STOP", int(st[k])
                break
            if hit_targ:
                px, why, xts = targ, "TARGET", int(st[k])
                break
            k += 1
        if px is None:
            j = np.searchsorted(st, cap_ts)
            j = min(j, len(st) - 1)
            px, xts = sc[j], int(st[j])
        pnl = side * (px - entry) * VPP - FEE
        trades.append(dict(day=mday.day.iloc[0], ts=ts, side="LONG" if side > 0 else "SHORT",
                           entry=entry, atr=atr, exit=px, exit_ts=xts, reason=why, pnl=pnl))
        flat_at = xts + 1
    return trades


# ───────────────────── causal pre-13:00 day features ─────────────────────
def day_features(mday: pd.DataFrame, prev_close: float | None):
    """Everything knowable STRICTLY BEFORE 13:00 UTC — the instant the rider's first entry fires."""
    mins = mday.m.values.astype(np.int64)
    day0 = (int(mins[0]) // 86400) * 86400
    pre = mday[mday.m < day0 + WIN_START]
    if len(pre) < 60:
        return None
    c = pre.c.values.astype(float)
    h, l, o = pre.h.values.astype(float), pre.l.values.astype(float), pre.o.values.astype(float)
    a = atr14(o, h, l, c, pre.m.values.astype(np.int64))

    path = np.abs(np.diff(c)).sum()
    net = c[-1] - c[0]
    f = dict(
        atr_1300=a[-1],                                     # ATR-14 at the moment of the first entry
        on_range=h.max() - l.min(),                         # overnight (pre-13:00) range
        on_net=abs(net),
        on_er=abs(net) / path if path > 0 else 0.0,         # efficiency: net / total path
        on_roundtrip=path / (h.max() - l.min()) if h.max() > l.min() else 0.0,
    )
    last2 = pre[pre.m >= day0 + WIN_START - 7200]           # the 2h run-in to the open
    if len(last2) >= 30:
        c2 = last2.c.values.astype(float)
        p2 = np.abs(np.diff(c2)).sum()
        f["run_in_er"] = abs(c2[-1] - c2[0]) / p2 if p2 > 0 else 0.0
        f["run_in_range"] = last2.h.max() - last2.l.min()
    else:
        f["run_in_er"], f["run_in_range"] = np.nan, np.nan
    f["gap"] = abs(c[0] - prev_close) if prev_close else np.nan
    return f


def opening_range(mday: pd.DataFrame):
    """13:00-13:30 range — NOT causal for the 13:00 entry. Reported separately and labelled."""
    mins = mday.m.values.astype(np.int64)
    day0 = (int(mins[0]) // 86400) * 86400
    w = mday[(mday.m >= day0 + WIN_START) & (mday.m < day0 + WIN_START + 1800)]
    if len(w) < 20:
        return np.nan
    return w.h.max() - w.l.min()


def main():
    print("loading tape …")
    m, s = load_minutes(), load_5s()
    days = sorted(d for d in m.day.unique() if m[m.day == d].shape[0] >= 600)
    print(f"usable days: {len(days)}  ({days[0]} .. {days[-1]})")

    # ── replay ──
    rows, per_day = [], {}
    prev_c = None
    for d in days:
        md, sd = m[m.day == d], s[s.day == d]
        tot = []
        for name, cad, sk in CELLS:
            tr = replay_day(md, sd, cad, sk)
            for t in tr:
                t["cell"] = name
            tot += tr
        rows += tot
        feats = day_features(md, prev_c)
        if feats is not None:
            feats["or_1300_1330"] = opening_range(md)
            feats["day"] = d
            feats["net"] = sum(t["pnl"] for t in tot)
            feats["n"] = len(tot)
            per_day[d] = feats
        prev_c = md.c.iloc[-1]

    T = pd.DataFrame(rows)
    D = pd.DataFrame(per_day.values()).set_index("day")
    T.to_json("/home/alphabot/gazbot7/data/odr_replay_trades.json", orient="records")

    print("\n═══ REPLAY, per day (all 4 ungated cells, 1 lot each) ═══")
    print(D[["n", "net"]].round(1).to_string())
    print(f"\nreplay total: n={len(T)} net=${T.pnl.sum():,.0f}  "
          f"green days {(D.net > 0).sum()}/{len(D)}")

    D.to_json(OUT, orient="index")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
