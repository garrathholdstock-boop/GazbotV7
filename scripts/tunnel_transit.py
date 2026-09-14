#!/usr/bin/env python3
"""THE TRANSIT — how far does price travel between tunnels, once it has left one?

★ THIS IS THE OPERATOR'S OWN MODEL, and it is the one version of the tunnel work never tested.
He described today's two winning trades: "i saw that usual persistent downward grind on the first
one, and then i saw it upward after it left the tunnel at the bottom, and i thought from what ive
seen historically they will continue for a while until they hit the next tunnel."

So he is NOT using the tunnel to pick direction - he reads the grind for that. He is using it as a
TARGET: leave one tunnel, travel to the next, get out there. STATE.md ss1c says exactly this is the
only version left standing and untested: "the tunnel as a FILTER on when to look, with direction
supplied by something else - his own read."

⚠ WHAT WAS ALREADY REFUTED, AND IS NOT RE-TESTED HERE: the break as a DIRECTION forecast (0.44-0.53
across every cell, MNQ and MGC) and as an EXCURSION-SIZE forecast against a matched-hour control
(1.02x). This measures something different - the DISTANCE TO THE NEXT COMPRESSION, which is a
target question, not a direction question.

THE CONTROL: the identical measurement started at RANDOM minutes rather than at breaks. If transits
from a tunnel exit are no longer than transits from an arbitrary moment, the tunnel adds nothing to
the target and the idea is decoration.
"""
from __future__ import annotations
import sys
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import numpy as np, pandas as pd
from tunnel_fit_mgc import (front_month_minutes, true_range, observations, fit_hmm,
                            filter_quiet, tunnels_and_breaks, _atr14)

MIN_TUNNEL = 25          # the live watcher's own arming threshold
rng = np.random.default_rng(31)


def next_tunnel_start(post, i, min_len=10):
    """The first minute of the next QUIET run of at least min_len after index i."""
    run = 0
    for j in range(i + 1, len(post)):
        p = post[j]
        if p is not None and p >= 0.5:
            run += 1
            if run >= min_len:
                return j - run + 1
        else:
            run = 0
    return None


def transits(bars, trs, post, starts, sides):
    """For each start, walk to the next tunnel and record the journey."""
    out = []
    for i, side in zip(starts, sides):
        j = next_tunnel_start(post, i)
        if j is None or j <= i + 1:
            continue
        e = bars[i]["close"]
        seg = bars[i + 1:j + 1]
        if len(seg) < 2:
            continue
        hi = max(b["hi"] for b in seg); lo = min(b["lo"] for b in seg)
        end = seg[-1]["close"]
        sgn = 1 if side == "UP" else -1
        atr = _atr14(trs, i) or np.nan
        out.append({"mins": j - i,
                    "to_next_tunnel": sgn * (end - e),        # what "exit at the next tunnel" gets
                    "mfe": sgn * (hi - e) if sgn > 0 else sgn * (lo - e),
                    "mae": (e - lo) if sgn > 0 else (hi - e),
                    "atr": atr})
    return pd.DataFrame(out)


def describe(df, label, vpp=2.0, cost=1.25):
    if not len(df):
        print(f"  {label}: nothing"); return
    t = df.to_next_tunnel
    print(f"\n  {label}  (n={len(df)})")
    print(f"    minutes to the next tunnel : median {df.mins.median():>6.0f}  "
          f"p25 {df.mins.quantile(.25):>5.0f}  p75 {df.mins.quantile(.75):>5.0f}")
    print(f"    travel in the break's own direction, at the next tunnel:")
    print(f"       median {t.median():>+7.1f}pt   mean {t.mean():>+7.1f}pt   "
          f"share positive {100*(t > 0).mean():>3.0f}%")
    print(f"    IF DIRECTION IS SUPPLIED CORRECTLY (|travel|, the upper bound his read could reach):")
    print(f"       median {t.abs().median():>7.1f}pt = ${t.abs().median()*vpp:>6.0f}   "
          f"mean {t.abs().mean():>7.1f}pt = ${t.abs().mean()*vpp:>6.0f}")
    print(f"    best excursion along the way (MFE): median {df.mfe.median():>6.1f}pt   "
          f"worst adverse (MAE): median {df.mae.median():>5.1f}pt")


def main():
    for sym in ("MNQ", "MGC"):
        print(f"\n{'='*76}\n{sym}\n{'='*76}")
        try:
            bars, rolls = front_month_minutes(verbose=False, symbol=sym)
        except Exception as e:
            print(f"  cannot load {sym}: {type(e).__name__}: {e}"); continue
        trs = true_range(bars, rolls)
        x = observations(trs)
        n = len(x); cut = int(n * 0.6)
        mu, sd, A, _ll = fit_hmm(x[:cut])                 # fit on the first 60%, apply to all
        post = filter_quiet(x, mu, sd, A)
        tuns, brks = tunnels_and_breaks(bars, trs, post, min_tunnel=MIN_TUNNEL)
        print(f"  {len(bars):,} minutes · {len(tuns):,} tunnels · {len(brks):,} armed breaks")
        real = transits(bars, trs, post, [b["i"] for b in brks],
                        [b["side"] if b["side"] != "BOTH" else "UP" for b in brks])
        describe(real, "FROM A TUNNEL BREAK")
        # CONTROL: identical measurement from random minutes, same count, random side
        idx = rng.choice(np.arange(100, len(bars) - 100), size=min(len(brks) * 3, 5000),
                         replace=False)
        ctl = transits(bars, trs, post, list(idx),
                       list(rng.choice(["UP", "DOWN"], size=len(idx))))
        describe(ctl, "CONTROL — random minutes, random side")
        if len(real) and len(ctl):
            a, b = real.to_next_tunnel.abs(), ctl.to_next_tunnel.abs()
            print(f"\n    ★ |travel| from a break vs from a random minute: "
                  f"{a.median():.1f}pt vs {b.median():.1f}pt = {a.median()/max(b.median(),1e-9):.2f}x")
            print(f"    ★ time to the next tunnel: {real.mins.median():.0f}min vs "
                  f"{ctl.mins.median():.0f}min")


if __name__ == "__main__":
    raise SystemExit(main())
