#!/usr/bin/env python3
"""ROLL CONTAMINATION - measured on this study's own tape (sibling agent flagged +1,135pt).

A trade cannot straddle a contract change (entries require sess[i]==sess[i+hold], and the front
month is picked per calendar DAY). But the FEATURES can: ret4/ret8/path/atr are rolling windows
that cross the day boundary, so on a roll day d4/d8 is computed ACROSS A CONTRACT CHANGE - and
d4/d8 is precisely what decides the state label.

Reported: the roll dates, the price step at each, how many entries sit within 8 bars of one, and
every headline cell recomputed with those entries removed.
"""
import sys, os, glob, datetime as dt
sys.path.insert(0, os.path.dirname(__file__))
import regimelab as R, numpy as np, pandas as pd, duckdb

GB = "/home/alphabot/gazbot7"
files = sorted(glob.glob(f"{GB}/data/backfill/MNQ_*_1min.parquet"))
rows = [f"select '{f.split('_')[-2]}' exp, ts, close, volume from read_parquet('{f}')"
        for f in files]
con = duckdb.connect()
fm = con.execute(f"""
 with a as ({' union all '.join(rows)}),
 t as (select *, cast(to_timestamp(ts) as date) d from a),
 v as (select d,exp,sum(volume) vv, count(*) nb from t group by 1,2)
 select d,exp,vv from (select *,row_number() over (partition by d order by vv desc) rn from v)
 where rn=1 order by d""").df()
fm["prev"] = fm.exp.shift()
rolls = fm[(fm.prev.notna()) & (fm.exp != fm.prev)]
print("FRONT-MONTH MAP - roll dates (the day the highest-volume expiry changes)")
print(rolls.to_string(index=False))

# the price STEP at each roll: last close of the old contract vs first close of the new, same minute
steps = []
for _, r in rolls.iterrows():
    q = con.execute(f"""
      with a as ({' union all '.join(rows)})
      select exp, ts, close from a
      where cast(to_timestamp(ts) as date) = date '{r.d}' and exp in ('{r.exp}','{r.prev}')
      order by ts""").df()
    piv = q.pivot_table(index="ts", columns="exp", values="close").dropna()
    if len(piv):
        step = float((piv[r.exp] - piv[r.prev]).mean())
        steps.append(dict(date=str(r.d), old=r.prev, new=r.exp, mean_basis_pt=round(step, 2),
                          overlap_min=len(piv)))
S = pd.DataFrame(steps)
print("\nCONTRACT BASIS AT EACH ROLL (new minus old, same minute, that day)")
print(S.to_string(index=False))
print(f"\n  TOTAL basis stepped through by the stitched series: "
      f"{S.mean_basis_pt.sum():.1f} pt over {len(S)} rolls")
S.to_csv(f"{R.ART}/tables/roll_basis.csv", index=False)

ROLLDAYS = set(pd.to_datetime(rolls.d).dt.date)
print("\nROLL DAYS:", sorted(ROLLDAYS))

# ── how many entries sit within 8 bars of the stitch, and does removing them move anything? ──
CELLS = [
  ("INCUMBENT 15m/3/base clean2 90m", dict(bar=15, K=3, fs="base", clean=2, hold=6, win=None)),
  ("INCUMBENT 15m/3/base clean2 60m", dict(bar=15, K=3, fs="base", clean=2, hold=4, win=None)),
  ("GRIDA 30m/3/base_vol c2 EUUS 180m", dict(bar=30, K=3, fs="base_vol", clean=2, hold=6,
                                             win=(480, 1200))),
  ("GRIDA 30m/3/base_vol c2 LDN 180m", dict(bar=30, K=3, fs="base_vol", clean=2, hold=6,
                                            win=(480, 810))),
]
out = []
gc = {}
for nm, c in CELLS:
    if c["bar"] not in gc:
        gc = {c["bar"]: R.load_bars(c["bar"])}
    g = gc[c["bar"]]
    M = R.Model(c["bar"], c["K"], c["fs"], g=g)
    idx = R.signals(M, clean=c["clean"], win=c["win"])
    T = R.trades(M, idx, hold=c["hold"], friction=1.25)
    # a bar is contaminated if any of the 8 bars behind it (the longest feature window plus the
    # 20-bar ATR is checked separately) lies on the other side of a roll boundary
    day = pd.to_datetime(g.dt).dt.date.values
    bad_bar = np.zeros(len(g), bool)
    for k in range(len(g)):
        pass
    isroll = np.isin(day, list(ROLLDAYS))
    ri = np.where(isroll)[0]
    contam = np.zeros(len(g), bool)
    for j in ri:
        contam[max(0, j - 20):min(len(g), j + 21)] = True     # 20 bars either side of a roll bar
    dirty = contam[T.i.values]
    Tc = T[~dirty]
    lo, mid, hi = R.day_block_boot(T, friction=1.25, draws=1500)
    lo2, mid2, hi2 = R.day_block_boot(Tc, friction=1.25, draws=1500)
    out.append(dict(cell=nm, n=len(T), n_near_roll=int(dirty.sum()),
                    pct=round(100 * dirty.mean(), 2), net_all=mid, net_clean=mid2,
                    delta=mid2 - mid, clean_lo=lo2, clean_hi=hi2))
D = pd.DataFrame(out)
D.to_csv(f"{R.ART}/tables/roll_robustness.csv", index=False)
print("\nENTRIES NEAR A ROLL, AND THE RESULT WITH THEM REMOVED (+/-20 bars of the stitch)")
print(D.round(2).to_string(index=False))
