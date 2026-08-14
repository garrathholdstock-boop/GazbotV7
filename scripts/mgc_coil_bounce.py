#!/usr/bin/env python3
"""MGC GREENFIELD #2 — the COIL BOUNCER. Built from scratch; shares no logic with any existing gate.

    PYTHONPATH=src .venv/bin/python scripts/mgc_coil_bounce.py [--continuation] [--placebo]

★★ WHY THIS IS A GENUINELY DIFFERENT GATE, not the session-anchor one wearing a hat.
`mgc_session_anchor.py` triggers on the CLOCK (a fixed institutional time) and takes whichever side
the opening-range break chooses. This one has **no clock at all**. It triggers on a STATE of the
tape — volatility compression — and takes its side from where price sits inside that compression.
Different trigger, different side-selection, different exit target. The only thing they share is the
tick-race harness and the cost model, which is how it should be: two gates measured on one ruler.

★ THE MECHANISM. Gold coils: a 20-minute range that collapses relative to its own recent norm. The
claim under test is the classic one — inside a coil, an excursion to the EDGE is more likely to
revert to the middle than to continue out of it. That is a REVERSION claim and it is falsifiable:
`--continuation` runs the identical machinery on the opposite side, which is the control that says
whether the edge means anything at all or the tape is simply drifting.

★ WHY IT IS WORTH TESTING DESPITE THE FADER NULL. `mgc_fader.py` faded EXTENSION — price a long way
from VWAP — and found nothing (Hurst 0.489, a random walk). That is a different claim. Extension
asks "is price far from fair?"; compression asks "is price PINNED?" A random walk has no exploitable
memory of direction, but a coil is a statement about VOLATILITY, and gold's volatility is the one
thing the earlier work found to be genuinely predictable: *"gold's runs are SIZE-predictable"*, ATR
separating runs from ordinary tape at d=+0.80. This gate tries to trade the one feature that IS
real, instead of the direction feature that is not.

★ DISCIPLINE. Parameters are fixed below BEFORE any result is looked at. The core is a SINGLE cell.
`--placebo` compares it against the same number of entries taken at random times on the same days —
the control the prior gold work insists on, because removing or selecting 40% of trades looks
brilliant whenever the selected 40% happened to win.

★ Exits raced on TICKS. MGC is $10/pt and the fee is $1.50/RT: gold's R is ~$16 against MNQ's
$30-50, so a fixed fee is about twice as regressive here.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from mgc_session_anchor import Trade, atr, load, minute_bars, race, score  # noqa: E402

VPP, FEE_RT = 10.0, 1.50

# ── parameters, fixed before looking ──────────────────────────────────────────
COIL_MIN = 20           # the window whose range defines the coil
NORM_MIN = 120          # the recent norm the coil is measured against
COMPRESS = 0.60         # coil range must be <= this × its own 2h median  → "compressed"
EDGE_PCT = 0.85         # entry when price reaches the outer 15% of the coil
STOP_ATR = 1.0          # beyond the coil edge
TIME_CAP_MIN = 60       # a coil trade that has not worked in an hour is not working
MIN_GAP_MIN = 30        # no re-entry within this many minutes (keeps trades independent)


def coil_signals(m: pd.DataFrame, *, continuation: bool = False) -> list[tuple]:
    """Yield (timestamp, side, entry, stop, target, atr) for every coil-edge event.

    side is the direction we TRADE: for the reversion form, toward the coil middle.
    """
    a = atr(m)
    hi = m["high"].rolling(COIL_MIN).max()
    lo = m["low"].rolling(COIL_MIN).min()
    rng = hi - lo
    norm = rng.rolling(NORM_MIN).median()

    out = []
    last_ts = None
    for ts in m.index:
        r, n, a_v = rng.get(ts, np.nan), norm.get(ts, np.nan), a.get(ts, np.nan)
        if not (np.isfinite(r) and np.isfinite(n) and np.isfinite(a_v)) or n <= 0 or r <= 0 or a_v <= 0:
            continue
        if r > COMPRESS * n:                      # not compressed → not a coil
            continue
        if last_ts is not None and (ts - last_ts).total_seconds() < MIN_GAP_MIN * 60:
            continue
        h, l = hi[ts], lo[ts]
        px = m["close"][ts]
        pos = (px - l) / (h - l)                  # 0 = bottom of coil, 1 = top
        mid = (h + l) / 2.0

        if pos >= EDGE_PCT:
            side = -1                             # at the TOP → fade down toward the middle
        elif pos <= 1 - EDGE_PCT:
            side = +1
        else:
            continue
        if continuation:
            side = -side                          # the control: break out of the coil instead

        entry = float(px)
        stop = entry - side * STOP_ATR * a_v
        # Reversion target is the coil MIDDLE — the whole claim. Continuation targets the same
        # distance the other way, so both forms risk and seek identical amounts.
        target = mid if not continuation else entry + side * abs(entry - mid)
        out.append((ts, side, entry, stop, float(target), float(a_v)))
        last_ts = ts
    return out


def backtest(m: pd.DataFrame, ticks: pd.DataFrame, *, continuation=False,
             jitter: bool = False, seed: int = 0) -> list[Trade]:
    tk = ticks["ts_ms"].to_numpy()
    px = ticks["price"].to_numpy()
    sigs = coil_signals(m, continuation=continuation)

    if jitter:
        # ★ PLACEBO: same COUNT of entries per day, at random minutes of that day, same side mix.
        # Anything that beats this is doing better than "trade gold this often"; anything that does
        # not is measuring the tape, not the signal.
        rng_ = np.random.default_rng(seed)
        by_day: dict = {}
        for s in sigs:
            by_day.setdefault(s[0].date(), []).append(s)
        newsigs = []
        for day, ss in by_day.items():
            dm = m[m.index.date == day]
            if len(dm) < 30:
                continue
            picks = rng_.choice(len(dm) - 1, size=min(len(ss), len(dm) - 1), replace=False)
            for (ts0, side, _e, _s, _t, a_v), i in zip(ss, picks):
                ts = dm.index[i]
                e = float(dm["close"].iloc[i])
                newsigs.append((ts, side, e, e - side * STOP_ATR * a_v,
                                e + side * abs(_t - _e), a_v))
        sigs = newsigs

    out = []
    for ts, side, entry, stop, target, _a in sigs:
        # ★★ THE BAR LABEL IS ITS LEFT EDGE. pandas `resample` stamps the 10:00-10:01 bar as 10:00,
        # but its close (and its high/low) are only known at 10:01. Racing from `ts` would replay the
        # very minute the decision was made — a look-ahead that hands the trade a minute of known
        # future. Enter at the bar's CLOSE, so the race starts where the information ends.
        e_ms = int(ts.value // 10**6) + 60_000
        j = np.searchsorted(tk, e_ms)
        k = np.searchsorted(tk, e_ms + TIME_CAP_MIN * 60000 + 1)
        xp, why, mins = race(tk[j:k], px[j:k], side, entry, stop, target, None,
                             TIME_CAP_MIN * 60000)
        out.append(Trade(str(ts.date()), "COIL", side, entry, xp, why, mins))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--continuation", action="store_true", help="control: break OUT of the coil")
    ap.add_argument("--placebo", action="store_true")
    a = ap.parse_args()

    bars, ticks = load()
    m = minute_bars(bars)
    print(f"  MGC {m.index.min():%Y-%m-%d} .. {m.index.max():%Y-%m-%d} · "
          f"{m.index.normalize().nunique()} days · {len(ticks):,} ticks · ${VPP:.0f}/pt · ${FEE_RT}/RT")
    print(f"  COIL: {COIL_MIN}m range <= {COMPRESS} x its {NORM_MIN}m median · "
          f"edge {EDGE_PCT:.0%} · stop {STOP_ATR}xATR · target = coil MID · cap {TIME_CAP_MIN}m\n")

    for label, cont in (("REVERSION (fade the edge, target the middle)", False),
                        ("CONTINUATION (break out of the coil)  [control]", True)):
        tr = backtest(m, ticks, continuation=cont)
        s = score(tr)
        rs = pd.Series([t.pnl for t in tr])
        med = rs.median() if len(rs) else 0.0
        print(f"  {label}")
        print(f"    n={s['n']:<4} days={s['days']:<3} green={s.get('green_days',0):<3} "
              f"win={s['win']:>5.1f}%  exp=${s['exp']:>7.2f}  total=${s['total']:>9.2f}  "
              f"strip-best-day=${s['strip_best_day']:>8.2f}  median=${med:>7.2f}")
        if cont is False and a.placebo and s["n"]:
            reals = s["total"]
            pl = [score(backtest(m, ticks, jitter=True, seed=i))["total"] for i in range(12)]
            beaten = sum(1 for p in pl if p >= reals)
            print(f"    placebo (12 random-time sets, same count/day): "
                  f"median ${np.median(pl):,.0f}, beaten {beaten}/12 → "
                  f"{'NO information' if beaten >= 3 else 'the COIL carries it'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
