#!/usr/bin/env python3
"""OPEN-NEWS greenfield 2026-09-11 — STEP 0: INTERROGATE THE CLUSTER LABEL ITSELF.

Before inventing any signal to catch OPEN/NEWS runs, ask what the label IS. `cluster()` in
run_census.py files a run as OPEN/NEWS when:  13<=hour<15  AND no |flow z|>=1  AND amp<=0.30.
That is a CLOCK plus two NEGATIVES. This script measures, over the FULL parquet lake:
  * the base rate of the label over every minute of tape (is it a footprint or most of the window?)
  * the run rate inside it, vs the bare clock and vs all tape  ->  the LIFT that matters
No trading here. Just: does the label carry information a bare clock does not.
"""
from __future__ import annotations
import numpy as np, pandas as pd, duckdb

C = '/home/alphabot/gazbot7/data/cache_on0911'
W5 = 180          # 15 min in 5s bars
STEP = 12         # anchor every 60s
FLOW_Z, LOOK, MINB = 1.0, 120, 30     # census constants: |z|>=1, 2h lookback, >=30 buckets
AMP_HI = 0.30

con = duckdb.connect(); con.execute("SET memory_limit='2GB'; SET threads=3")
bars = con.execute(f"SELECT d, sod, bar_ts, open, high, low, close FROM read_parquet('{C}/bars5s.parquet') ORDER BY bar_ts").fetchdf()
flow = con.execute(f"SELECT m, netflow FROM read_parquet('{C}/flow1m.parquet') ORDER BY m").fetchdf()

fmap = dict(zip(flow.m.values, flow.netflow.values))
fm = flow.m.values; fv = flow.netflow.values.astype(float)
# rolling mean/std of the 1-min net-flow over the trailing 2h, on the CONTIGUOUS minute axis
fs = pd.Series(fv, index=fm)
full = fs.reindex(range(int(fm.min()), int(fm.max())+1))
mu = full.rolling(LOOK, min_periods=MINB).mean().shift(1)
sd = full.rolling(LOOK, min_periods=MINB).std().shift(1)
cnt = full.rolling(LOOK, min_periods=1).count().shift(1)

rows = []
for d, g in bars.groupby('d', sort=True):
    g = g.reset_index(drop=True)
    c = g.close.values; h = g.high.values; lo = g.low.values; ts = g.bar_ts.values; sod = g.sod.values
    n = len(g)
    if n < W5 + 60: continue
    # typical 15-min range on THIS day's tape (the census's per-census unit)
    rng = np.array([h[i:i+W5].max() - lo[i:i+W5].min() for i in range(0, n-W5, STEP)])
    for i in range(60, n - W5, STEP):
        t = int(ts[i])
        if t % 60: continue            # anchor on minute boundaries so flow buckets line up
        m = t // 60
        fl = fmap.get(m-1)             # net aggressor flow in the 60s BEFORE
        z = None
        if fl is not None and (m-1) in mu.index and not np.isnan(mu.get(m-1, np.nan)) \
           and not np.isnan(sd.get(m-1, np.nan)) and sd.get(m-1) > 0 and cnt.get(m-1, 0) >= MINB:
            z = (fl - mu[m-1]) / sd[m-1]
        amp = 100.0 * (h[i-60:i].max() - lo[i-60:i].min()) / c[i] if c[i] else None
        mv = c[i+W5] - c[i]
        rows.append((d, int(sod[i]), t, fl, z, amp, mv,
                     float(h[i:i+W5].max()-lo[i:i+W5].min())))
df = pd.DataFrame(rows, columns=['d','sod','ts','flow','fz','amp','mv15','rng15'])
df['hour'] = df.sod // 3600
# threshold: 1.5 x the MEDIAN 15-min range, computed on the WHOLE lake (the census does it per-window)
typ = df.rng15.median()
thr = 1.5 * typ
df['run'] = df.mv15.abs() >= thr
print(f"anchors {len(df):,} over {df.d.nunique()} days | typical 15m range {typ:.1f}pt | run thr {thr:.1f}pt")

def label(r):
    if r.flow is not None and not pd.isna(r.fz) and abs(r.fz) >= FLOW_Z:
        return 'FLOW-LED' if (r.flow > 0) == (r.mv15 > 0) else 'VACUUM'
    if r.amp is not None and not pd.isna(r.amp) and r.amp > AMP_HI:
        return 'VOL-EXPANSION'
    if 13 <= r.hour < 15:
        return 'OPEN/NEWS'
    return 'UNCLASS'
df['lab'] = df.apply(label, axis=1)

base = df.run.mean()
print(f"\nALL TAPE: {len(df):,} anchors, run rate {base:.4%}")
print(f"\n{'label':<16}{'anchors':>9}{'share':>8}{'runs':>7}{'runrate':>9}{'lift':>7}")
for L, g in df.groupby('lab'):
    print(f"{L:<16}{len(g):>9,}{len(g)/len(df):>7.1%}{g.run.sum():>7}{g.run.mean():>9.2%}{g.run.mean()/base:>7.2f}")

win = df[(df.hour >= 13) & (df.hour < 15)]
on = win[win.lab == 'OPEN/NEWS']
print(f"\n── THE CLOCK vs THE LABEL ──")
print(f"bare clock 13-15Z      : {len(win):>7,} anchors ({len(win)/len(df):.1%} of tape), run rate {win.run.mean():.2%}, lift {win.run.mean()/base:.2f}x")
print(f"OPEN/NEWS (clock+2 nots): {len(on):>7,} anchors ({len(on)/len(df):.1%} of tape), run rate {on.run.mean():.2%}, lift {on.run.mean()/base:.2f}x")
print(f"OPEN/NEWS share OF ITS OWN WINDOW: {len(on)/len(win):.1%}")
print(f"★ LIFT OF THE LABEL OVER THE BARE CLOCK: {on.run.mean()/win.run.mean():.3f}x")
rest = win[win.lab != 'OPEN/NEWS']
print(f"the 13-15Z anchors the label THREW AWAY: {len(rest):,}, run rate {rest.run.mean():.2%}")
for L,g in rest.groupby('lab'):
    print(f"   in-window {L:<14} n={len(g):>6,} runrate {g.run.mean():.2%}")

# hour-by-hour run lift, so the 13-15 edge can be seen against every other hour
print(f"\n── RUN RATE BY HOUR (UTC) — is 13-15 really the densest? ──")
hh = df.groupby('hour').agg(n=('run','size'), runs=('run','sum'), rate=('run','mean'))
hh['lift'] = hh['rate']/base
for h, r in hh.iterrows():
    bar = '#' * int(r['lift']*10)
    print(f"  {h:02d}Z  n={r['n']:>6,.0f}  runs={r['runs']:>4.0f}  rate={r['rate']:6.2%}  lift={r['lift']:5.2f}  {bar}")
df.to_parquet(f'{C}/anchors.parquet')
print(f"\nanchors -> {C}/anchors.parquet")
