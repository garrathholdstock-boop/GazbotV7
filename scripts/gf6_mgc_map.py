"""GF6 MAP — before inventing a single gold gate, ask the tape which of the four cells can exist.

For every minute we ask: given the last `w` minutes moved `k` ATRs, what does the NEXT `h` minutes do?
That one measurement answers all four cells at once, because the four cells are two triggers seen from
two sides:

    ret_w >= +k*ATR   ->  going WITH it is MOMENTUM-LONG,  going against it is REVERSION-SHORT
    ret_w <= -k*ATR   ->  going WITH it is MOMENTUM-SHORT, going against it is REVERSION-LONG

Reported in DOLLARS per trade at MGC's $10/point net of a $3.50 round trip (a $1.50 commission plus
one tick of slippage a leg), so a number here is directly comparable with a gate.

⚠ Every minute is a sample and they overlap heavily, so the t-stat is meaningless. Significance is a
SESSION block bootstrap: resample whole trading days with replacement, 400 times.
"""
from __future__ import annotations
import numpy as np, pandas as pd

OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf6"
VPP, FEE, SLIP = 10.0, 1.50, 0.20      # $/pt, $/round trip, points of slippage per round trip
COST = FEE + SLIP * VPP                # $3.50
START = "2025-10-01"                   # before this the only contract IBKR serves is a BACK month:
                                       # 15% of 2025-08 minutes have zero true range.

def load():
    df = pd.read_pickle(f"{OUT}/mgc_min.pkl")
    df = df[df.sday >= START].copy()
    mix = df.groupby("sday").ex.nunique()
    df = df[df.sday.map(mix).eq(1)]              # drop the 5 roll-day sessions outright
    df["atr_bp"] = 1e4 * df.atr60 / df.close
    # causal volatility regime: today's ATR against the median of the 5 PREVIOUS sessions
    smed = df.groupby("sday").atr_bp.median()
    prev = smed.shift(1).rolling(5, min_periods=3).median()
    df["atr_rel"] = df.atr_bp / df.sday.map(prev)
    def sess(m):
        if m < 7 * 60: return "ASIA"
        if m < 13 * 60 + 30: return "LONDON"
        if m < 20 * 60: return "US"
        return "LATE"
    df["sess"] = df.hhmm.map(sess)
    return df

def boot(days, vals, n=400, seed=7):
    """session block bootstrap of the mean; returns (lo,hi) 5-95%."""
    rng = np.random.default_rng(seed)
    d = pd.DataFrame({"d": days, "v": vals}).dropna()
    if d.empty: return (np.nan, np.nan)
    grp = {k: g.v.values for k, g in d.groupby("d")}
    keys = list(grp)
    out = []
    for _ in range(n):
        pick = rng.choice(len(keys), len(keys), replace=True)
        cat = np.concatenate([grp[keys[i]] for i in pick])
        out.append(cat.mean())
    return tuple(np.percentile(out, [5, 95]))

def main():
    df = load()
    print(f"sessions={df.sday.nunique()} {df.sday.min()} -> {df.sday.max()}  rows={len(df)}\n")
    rows = []
    for w in (15, 30, 60):
        for k in (0.5, 1.0, 1.5):
            trig_up = df[f"ret{w}"] >= k * df.atr60 * np.sqrt(w / 14)
            trig_dn = df[f"ret{w}"] <= -k * df.atr60 * np.sqrt(w / 14)
            for h in (30, 60, 120, 240):
                f = df[f"fwd{h}"]
                for name, mask, sign in (("UP", trig_up, +1), ("DN", trig_dn, -1)):
                    m = mask & f.notna() & df.atr60.notna()
                    if m.sum() < 200: continue
                    pnl = sign * f[m] * VPP - COST          # the MOMENTUM side
                    lo, hi = boot(df.sday[m].values, pnl.values)
                    rows.append(dict(w=w, k=k, h=h, trig=name, n=int(m.sum()),
                                     mom=pnl.mean(), rev=(-sign * f[m] * VPP - COST).mean(),
                                     lo=lo, hi=hi, win=float((pnl > 0).mean())))
    r = pd.DataFrame(rows)
    r.to_csv(f"{OUT}/map_blanket.csv", index=False)
    print("=== BLANKET (all tape) — $/trade, momentum side; rev = the same trigger faded ===")
    print(r.round(2).to_string(index=False))
    return df, r

if __name__ == "__main__":
    main()


def conditional(df, w=30, k=1.0, hs=(30, 60, 120, 240)):
    """The same measurement, SEGMENTED — the only reading the backtest discipline allows."""
    d = df.copy()
    d["atr_b"] = pd.cut(d.atr_rel, [0, .8, 1.25, 99], labels=["CALM", "NORMAL", "HOT"])
    d["er_b"] = pd.cut(d.er60, [-.01, .08, .20, 1.01], labels=["CHOP", "MID", "TREND"])
    out = []
    for h in hs:
        f = d[f"fwd{h}"]
        for sname, sub in d.groupby("sess", observed=True):
            for ab, s2 in sub.groupby("atr_b", observed=True):
                for eb, s3 in s2.groupby("er_b", observed=True):
                    up = s3[f"ret{w}"] >= k * s3.atr60 * np.sqrt(w / 14)
                    dn = s3[f"ret{w}"] <= -k * s3.atr60 * np.sqrt(w / 14)
                    ff = f.loc[s3.index]
                    base_l = (ff * VPP - COST).mean()          # the best CONSTANT, this segment
                    base_s = (-ff * VPP - COST).mean()
                    for tname, m, sg in (("UP", up, +1), ("DN", dn, -1)):
                        mm = m & ff.notna()
                        if mm.sum() < 300: continue
                        mom = (sg * ff[mm] * VPP - COST)
                        lo, hi = boot(s3.sday[mm].values, mom.values, n=200)
                        out.append(dict(h=h, sess=sname, atr=str(ab), er=str(eb), trig=tname,
                                        n=int(mm.sum()), days=int(s3.sday[mm].nunique()),
                                        mom=mom.mean(), rev=-mom.mean() - 2 * COST,
                                        lo=lo, hi=hi, const_l=base_l, const_s=base_s))
    r = pd.DataFrame(out)
    r.to_csv(f"{OUT}/map_conditional.csv", index=False)
    return r


if __name__ == "__main__" and True:
    import sys
    if "--cond" in sys.argv:
        d = load()
        r = conditional(d)
        pd.set_option("display.width", 220)
        surv = r[(r.lo > 0) | (r.hi < 0)].copy()
        surv["edge"] = np.where(surv.lo > 0, "MOMENTUM", "REVERSION")
        surv["net"] = np.where(surv.lo > 0, surv.mom, surv.rev)
        surv["beats_const"] = surv.net - np.where(
            surv.trig.eq("UP") == (surv.edge == "MOMENTUM"), surv.const_l, surv.const_s)
        print("=== SEGMENTS whose 5-95%% block-bootstrap band EXCLUDES zero ===")
        print(surv.sort_values("net", ascending=False).round(2).to_string(index=False))
