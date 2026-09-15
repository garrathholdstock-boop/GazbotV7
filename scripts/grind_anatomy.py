#!/usr/bin/env python3
"""THE ANATOMY OF AN ANGLED GRIND — what they are, how long they last, what ends them.

Operator, 2026-09-14: "measure the angled grinds. and measure the types of them and any other
characteristics that define them. volume etc. see if they have anything unique to them."

★ WHY THESE ARE WORTH MEASURING AT ALL. The desk's tunnel model classifies on TRUE RANGE ONLY, so a
slow angled drift - low range per bar, but going somewhere - is filed as a TUNNEL. Measured, 25% of
everything that model calls a tunnel is actually an angled grind. It is a state the desk has never
been able to see, and it is the state the operator's best-described trade of 2026-09-14 sat in
(+$249, ER 0.51, +54pt over the prior 30 minutes).

⚠ DESCRIPTIVE, NOT PREDICTIVE. All four states measured at 49-50% forward. This says what a grind
IS and how long they run, so a human reading the tape has a reference class. It forecasts nothing.
⚠ THE STATE LAGS ITS WINDOW. A W-minute lookback cannot see a grind until W minutes in, and holds
the label up to W minutes after it ends. Durations here are therefore of the LABEL, and the true
episode starts earlier. Reported, not hidden.
"""
from __future__ import annotations
import sys
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import numpy as np, pandas as pd
from tunnel_fit_mgc import front_month_minutes, true_range

W = 15                 # the window the state is measured over
ER_ANGLED = 0.25       # net move / path length: 0 = pure chop, 1 = a straight line
MIN_EP = 5             # an "episode" must hold the label this long to count


def build(symbol="MNQ"):
    bars, rolls = front_month_minutes(verbose=False, symbol=symbol)
    trs = true_range(bars, rolls)
    cl = np.array([b["close"] for b in bars], float)
    vol = np.array([b.get("vol", np.nan) for b in bars], float)   # the key is "vol", not "volume"
    tr = np.array([t if t is not None else np.nan for t in trs], float)
    ts = np.array([b["m"] for b in bars], np.int64)
    n = len(cl)
    er = np.full(n, np.nan); net = np.full(n, np.nan)
    for i in range(W, n):
        w = cl[i-W:i+1]
        net[i] = w[-1] - w[0]
        er[i] = abs(net[i]) / max(np.abs(np.diff(w)).sum(), 1e-9)
    tr_s = pd.Series(tr)
    tr_w = tr_s.rolling(W, min_periods=5).mean().values
    tr_base = tr_s.rolling(240, min_periods=60).median().values
    vol_s = pd.Series(vol)
    vol_w = vol_s.rolling(W, min_periods=5).mean().values
    vol_base = vol_s.rolling(240, min_periods=60).median().values
    quiet = tr_w <= tr_base
    angled = er >= ER_ANGLED
    return dict(ts=ts, cl=cl, tr=tr, er=er, net=net, quiet=quiet, angled=angled,
                tr_w=tr_w, tr_base=tr_base, vol_w=vol_w, vol_base=vol_base, n=n)


def episodes(d):
    """Contiguous runs of QUIET+ANGLED, with how each one ended."""
    lab = d["quiet"] & d["angled"] & np.isfinite(d["er"])
    # ★ GAP TOLERANCE. A grind that dips below the threshold for a minute or two is ONE grind to a
    # human eye; without this the median duration is an artefact of the label flickering, not of the
    # tape. Bridging gaps of <= GAP minutes took the median from 8 minutes to what is reported below.
    GAP = 3
    lab = lab.copy()
    i = 0
    while i < len(lab):
        if lab[i]:
            j = i
            while j + 1 < len(lab) and lab[j + 1]:
                j += 1
            k = j + 1
            run = 0
            while k < len(lab) and not lab[k] and run < GAP:
                k += 1; run += 1
            if k < len(lab) and lab[k] and run > 0:
                lab[j+1:k] = True
                i = j + 1
                continue
            i = j + 1
        else:
            i += 1
    out, i, n = [], 0, d["n"]
    while i < n:
        if not lab[i]:
            i += 1; continue
        j = i
        while j + 1 < n and lab[j + 1]:
            j += 1
        if j - i + 1 >= MIN_EP and d["ts"][j] - d["ts"][i] < 86400:
            # how it ENDED: the state one minute after the label drops
            k = min(j + 1, n - 1)
            if not np.isfinite(d["er"][k]):
                end = "unknown"
            elif d["quiet"][k]:
                end = "went STAGNANT (into a tunnel)"
            elif d["angled"][k]:
                end = "ACCELERATED (into a thrust)"
            else:
                end = "turned CHOPPY-LOUD"
            sgn = 1 if d["net"][i] > 0 else -1
            mins = j - i + 1
            travel = sgn * (d["cl"][j] - d["cl"][i])
            out.append({
                "i": i, "mins": mins, "dir": "UP" if sgn > 0 else "DOWN",
                "travel_pt": travel, "pt_per_min": travel / max(mins, 1),
                "er": float(np.nanmean(d["er"][i:j+1])),
                "tr_vs_base": float(np.nanmean(d["tr_w"][i:j+1] / d["tr_base"][i:j+1])),
                "vol_vs_base": float(np.nanmean(d["vol_w"][i:j+1] / d["vol_base"][i:j+1])),
                "hour": int((d["ts"][i] % 86400) // 3600),
                "ended": end,
            })
        i = j + 1
    return pd.DataFrame(out)


def main():
    d = build("MNQ")
    e = episodes(d)
    lab = (d["quiet"] & d["angled"] & np.isfinite(d["er"]))
    print(f"MNQ · {d['n']:,} minutes · {len(e):,} angled-grind episodes "
          f"(>= {MIN_EP} min, W={W}, ER>={ER_ANGLED})")
    print(f"   they occupy {100*lab.sum()/np.isfinite(d['er']).sum():.1f}% of all minutes\n")

    print("HOW LONG THEY LAST (minutes of the LABEL; the true episode starts up to "
          f"{W} min earlier)")
    q = e.mins.quantile([.1, .25, .5, .75, .9, .99])
    print(f"   p10 {q[.1]:>5.0f}   p25 {q[.25]:>5.0f}   MEDIAN {q[.5]:>5.0f}   "
          f"p75 {q[.75]:>5.0f}   p90 {q[.9]:>5.0f}   p99 {q[.99]:>5.0f}   MAX {e.mins.max():>5.0f}")
    print(f"\nHOW FAR THEY TRAVEL (points, in the grind's own direction)")
    t = e.travel_pt.quantile([.1, .25, .5, .75, .9])
    print(f"   p10 {t[.1]:>+6.1f}  p25 {t[.25]:>+6.1f}  MEDIAN {t[.5]:>+6.1f}  "
          f"p75 {t[.75]:>+6.1f}  p90 {t[.9]:>+6.1f}   max {e.travel_pt.max():>+6.1f}")
    print(f"   median rate {e.pt_per_min.median():+.2f} pt/min")

    print(f"\n★ HOW THEY END")
    for k, v in e.ended.value_counts().items():
        print(f"   {k:<34}{v:>6}  {100*v/len(e):>5.1f}%")

    print(f"\n★ ARE THEY DIFFERENT FROM THE TAPE AROUND THEM?")
    print(f"   true range vs its own 4h baseline : {e.tr_vs_base.median():.2f}x")
    print(f"   VOLUME vs its own 4h baseline     : {e.vol_vs_base.median():.2f}x")
    print(f"   (1.00 = indistinguishable from the surrounding tape)")

    print(f"\nBY STEEPNESS (pt/min, the 'angle' he reads off the chart)")
    e2 = e.copy()
    e2["b"] = pd.qcut(e2.pt_per_min.abs(), 4, labels=["shallowest", "Q2", "Q3", "steepest"])
    print(f"{'angle':<13}{'pt/min':>14}{'n':>7}{'median mins':>13}{'median travel':>15}"
          f"{'vol vs base':>13}{'% end stagnant':>16}")
    for k, g in e2.groupby("b", observed=True):
        st = 100*(g.ended.str.startswith("went STAGNANT")).mean()
        print(f"{str(k):<13}{g.pt_per_min.abs().min():>6.2f}-{g.pt_per_min.abs().max():<7.2f}"
              f"{len(g):>7}{g.mins.median():>13.0f}{g.travel_pt.abs().median():>15.1f}"
              f"{g.vol_vs_base.median():>13.2f}{st:>15.0f}%")

    print(f"\nUP vs DOWN")
    for k, g in e.groupby("dir"):
        print(f"   {k:<5} n={len(g):>5}  median {g.mins.median():>4.0f} min  "
              f"travel {g.travel_pt.abs().median():>5.1f}pt  vol {g.vol_vs_base.median():.2f}x")

    print(f"\nWHEN THEY HAPPEN (UTC hour, top 6)")
    for h, v in e.hour.value_counts().head(6).items():
        print(f"   {h:02d}:00Z  {v:>5}  {100*v/len(e):>4.1f}%")
    e.to_csv("/home/alphabot/gazbot7/reports/grind_anatomy_MNQ.csv", index=False)
    print(f"\n   -> reports/grind_anatomy_MNQ.csv")


if __name__ == "__main__":
    raise SystemExit(main())
