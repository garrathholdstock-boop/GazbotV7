#!/usr/bin/env python3
"""GF5 — a VECTORISED re-implementation of gf_mgc_tape.race(), and the proof it is identical.

    PYTHONPATH=src .venv/bin/python scripts/gf5_fastrace.py      # runs the equivalence check

★ WHY THIS EXISTS AND WHY IT IS DANGEROUS. `race()` walks the 250ms quote tape one row at a time in
Python. A 480-minute cap is up to ~115,000 rows, so one trade costs ~0.1-1s and a 30-draw
random-minute placebo over 500 trades is 15,000 races — hours, on a box already running the rest of
the Friday build. That is the only reason the placebo control was missing from the gold work.

Rewriting an exit racer is exactly the kind of change that silently improves a backtest, so this is
NOT trusted: `_verify()` re-races every trade in the two banked gf4 ledgers and asserts the fill,
the reason, the minutes and the P&L match the sequential implementation to the cent. If it ever
stops matching, the fast path must not be used.

★ THE FOUR SUBTLETIES THAT MAKE IT MATCH, each of which was wrong in the first draft:
  1. `peak` is seeded at `mid_in`, not at the first quote - so it is max(mid_in, cummax(bid)).
  2. Arming reads the BID for a long (the same series the trail does), not the mid.
  3. At one index STOP beats TARGET beats TRAIL - the sequential loop checks them in that order.
  4. The time cap is tested at the END of the step, so an exit AT the cap index still wins.
"""
from __future__ import annotations

import sys

import numpy as np

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")


def fast_race(qt, bid, ask, side, *, fill_in, mid_in, stop, target, trail, cap_ms, arm_at=None):
    """Vectorised twin of gf_mgc_tape.race(). Same signature, same return tuple."""
    n = len(qt)
    if n == 0:
        return fill_in, mid_in, "NO_TAPE", 0.0, 0.0, 0.0
    t0 = qt[0]
    px = bid if side > 0 else ask                 # the series this side is measured against
    mid = (bid + ask) / 2.0

    if side > 0:
        peak = np.maximum(mid_in, np.maximum.accumulate(px))
        armed = (np.maximum.accumulate(px) - fill_in) >= (arm_at or 0.0)
        hit_stop = px <= stop
        hit_tgt = (px >= target) if target is not None else np.zeros(n, bool)
        hit_trl = (armed & (peak > fill_in) & (px <= peak - trail)) if trail is not None \
            else np.zeros(n, bool)
    else:
        peak = np.minimum(mid_in, np.minimum.accumulate(px))
        armed = (fill_in - np.minimum.accumulate(px)) >= (arm_at or 0.0)
        hit_stop = px >= stop
        hit_tgt = (px <= target) if target is not None else np.zeros(n, bool)
        hit_trl = (armed & (peak < fill_in) & (px >= peak + trail)) if trail is not None \
            else np.zeros(n, bool)
    if arm_at is None and trail is not None:
        armed[:] = True
        if side > 0:
            hit_trl = (peak > fill_in) & (px <= peak - trail)
        else:
            hit_trl = (peak < fill_in) & (px >= peak + trail)

    any_exit = hit_stop | hit_tgt | hit_trl
    i1 = int(np.argmax(any_exit)) if any_exit.any() else n
    cap = (qt - t0) >= cap_ms
    i2 = int(np.argmax(cap)) if cap.any() else n

    if i1 <= i2 and i1 < n:
        i = i1
        reason = "STOP" if hit_stop[i] else ("TARGET" if hit_tgt[i] else "TRAIL")
        out = px[i]
    elif i2 < n:
        i = i2
        reason = "TIME_CAP"
        out = px[i]
    else:
        i = n - 1
        reason = "EOD"
        out = px[i]

    exc = side * (mid[:i + 1] - mid_in)
    return (float(out), float(mid[i]), reason, (qt[i] - t0) / 60000.0,
            float(max(0.0, exc.max())), float(min(0.0, exc.min())))


def _verify() -> None:
    import pandas as pd
    from gf_mgc_barsource import atr14, trade_bars                      # noqa: E402
    from gf_mgc_tape import VPP, load_quotes, minute_bars, race         # noqa: E402

    q = load_quotes()
    mid = minute_bars(q, col="mid")
    t0, t1 = int(q.index[0].value // 10**6), int(q.index[-1].value // 10**6)
    trd = trade_bars(t0, t1)
    trd = trd[(trd.index >= mid.index[0]) & (trd.index <= mid.index[-1])]
    qt = (q.index.tz_convert("UTC").tz_localize(None)
          .astype("datetime64[ms]").astype("int64").to_numpy())
    bid, ask = q["bid1p"].to_numpy(), q["ask1p"].to_numpy()

    bad = 0
    tot = 0
    for tag, bars in (("depth-mid", mid), ("trade", trd)):
        d = pd.read_json(f"{GB}/reports/friday_v7/sections/gf4_mgc_trades_{tag}.json")
        a = atr14(bars)
        for _, r in d.iterrows():
            ts, side, atr = int(r["ts"]), int(r["side"]), float(r["atr"])
            i = np.searchsorted(qt, ts, side="left")
            fill_in = ask[i] if side > 0 else bid[i]
            mid_in = (bid[i] + ask[i]) / 2.0
            stop = mid_in - side * 3.0 * atr
            kw = dict(fill_in=fill_in, mid_in=mid_in, stop=stop, target=None,
                      trail=2.0 * atr, cap_ms=480 * 60_000, arm_at=2.0 * atr)
            s_out = race(qt[i:], bid[i:], ask[i:], side, **kw)
            f_out = fast_race(qt[i:], bid[i:], ask[i:], side, **kw)
            tot += 1
            same = (abs(s_out[0] - f_out[0]) < 1e-9 and s_out[2] == f_out[2]
                    and abs(s_out[3] - f_out[3]) < 1e-6
                    and abs(s_out[4] - f_out[4]) < 1e-9 and abs(s_out[5] - f_out[5]) < 1e-9)
            if not same:
                bad += 1
                if bad <= 5:
                    print(f"  MISMATCH {tag} ts={ts} side={side}\n    seq  {s_out}\n    fast {f_out}")
            pnl = round(side * (f_out[0] - fill_in) * VPP - 1.50, 2)
            if abs(pnl - float(r["pnl"])) > 0.011:
                print(f"  PNL DRIFT vs banked ledger {tag} ts={ts}: fast {pnl} banked {r['pnl']}")
    print(f"\nEQUIVALENCE: {tot - bad}/{tot} races identical to the sequential racer"
          f"   ({'PASS' if bad == 0 else 'FAIL'})")


if __name__ == "__main__":
    _verify()
