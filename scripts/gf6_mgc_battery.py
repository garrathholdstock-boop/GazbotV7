"""GF6 — the robustness battery, run on the EDGE OVER THE CONSTANT, not on the raw number.

Gold's US session carried a real downward drift across this year ($8.17 a trade at a 2-hour hold from
shorting at random). A candidate that inherits that drift is a directional bet on gold falling, not a
gate. So every candidate is scored twice: RAW $/trade, and EDGE = raw minus the same-side constant
measured on the same segment. The battery is run on the EDGE.

  split-half      does the sign hold in both halves of the year, independently
  by-month        how many of the 12 months are the right sign
  strip-best      drop the best 1 and best 3 SESSIONS
  LODO            leave one session out, worst case
  placebo         same number of firings drawn at random from the same segment, 400 draws
"""
from __future__ import annotations
import numpy as np, pandas as pd
from gf6_mgc_map import load, VPP, COST

OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf6"

CANDS = [
    # name,                   sess,     trigger, side, hold
    ("rev-short  US fade-up",   "US",     "up", -1, 120),
    ("rev-short  US fade-up",   "US",     "up", -1,  60),
    ("mom-long   LDN follow-up", "LONDON", "up", +1, 120),
    ("mom-short  ASIA follow-dn", "ASIA",  "dn", -1, 120),
    ("mom-short  ASIA follow-dn", "ASIA",  "dn", -1,  60),
    ("rev-long   LDN fade-dn",  "LONDON", "dn", +1,  30),
    ("rev-long   US fade-dn",   "US",     "dn", +1, 120),
    ("mom-short  US follow-dn", "US",     "dn", -1,  60),
]

def prep(w=30, k=1.0):
    d = load()
    d["up"] = d[f"ret{w}"] >= k * d.atr60 * np.sqrt(w / 14)
    d["dn"] = d[f"ret{w}"] <= -k * d.atr60 * np.sqrt(w / 14)
    return d

def run(d, sess, trig, side, h):
    s = d[d.sess == sess]
    f = s[f"fwd{h}"]; ok = f.notna()
    m = s[trig] & ok
    pnl = pd.Series(side * f[m].values * VPP - COST, index=s.sday[m].values)
    const = (side * f[ok] * VPP - COST)
    cs = pd.Series(const.values, index=s.sday[ok].values)
    return pnl, cs

def stats(pnl, cs, rng):
    by = pnl.groupby(level=0).mean(); bysum = pnl.groupby(level=0).sum()
    base = cs.mean()
    days = sorted(pnl.index.unique()); mid = len(days) // 2
    h1 = pnl[pnl.index.isin(days[:mid])]; h2 = pnl[pnl.index.isin(days[mid:])]
    c1 = cs[cs.index.isin(days[:mid])]; c2 = cs[cs.index.isin(days[mid:])]
    mo = pd.Series(pnl.values, index=[x[:7] for x in pnl.index])
    cmo = pd.Series(cs.values, index=[x[:7] for x in cs.index])
    medge = mo.groupby(level=0).mean() - cmo.groupby(level=0).mean()
    # strip best sessions by TOTAL contribution
    order = bysum.sort_values(ascending=False).index
    strip1 = pnl[~pnl.index.isin(order[:1])].mean() - base
    strip3 = pnl[~pnl.index.isin(order[:3])].mean() - base
    loo = min(pnl[~pnl.index.isin([dd])].mean() - base for dd in days)
    # placebo: same n drawn at random from the same segment
    n = len(pnl); vals = cs.values
    pl = np.array([vals[rng.choice(len(vals), n, replace=False)].mean() for _ in range(400)])
    return dict(n=n, days=len(days), raw=pnl.mean(), const=base, edge=pnl.mean() - base,
                med=float(np.median(pnl)), win=float((pnl > 0).mean()),
                h1=h1.mean() - c1.mean(), h2=h2.mean() - c2.mean(),
                mo_pos=int((medge > 0).sum()), mo_n=len(medge),
                strip1=strip1, strip3=strip3, loo_worst=loo,
                placebo_pct=float((pl < pnl.mean()).mean() * 100))

def main():
    d = prep(); rng = np.random.default_rng(23)
    rows = []
    for name, sess, trig, side, h in CANDS:
        pnl, cs = run(d, sess, trig, side, h)
        r = stats(pnl, cs, rng); r.update(cand=name, hold=h); rows.append(r)
    r = pd.DataFrame(rows)[["cand", "hold", "n", "days", "raw", "const", "edge", "med", "win",
                            "h1", "h2", "mo_pos", "mo_n", "strip1", "strip3", "loo_worst",
                            "placebo_pct"]]
    r.to_csv(f"{OUT}/battery.csv", index=False)
    pd.set_option("display.width", 250)
    print(r.round(2).to_string(index=False))

if __name__ == "__main__":
    main()
