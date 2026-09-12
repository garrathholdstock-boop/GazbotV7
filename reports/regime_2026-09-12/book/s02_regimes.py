#!/usr/bin/env python3
"""S02 — regime labels + the transition event table over the BOOK window.

The GMM is imported from scripts/bt_regime_transition.py UNCHANGED and fitted on exactly the
same TRAIN set (first 40% of the BACKFILL sessions = 2025-09..2026-01). It is then applied,
unaltered, to the capture-derived tape over 2026-07-31..2026-09-11. The whole book window is
therefore far outside TRAIN — no relabelling of history with hindsight.

Decision timing, stated once and obeyed everywhere downstream:
  bar i is stamped bt_i and CLOSES at bt_i + 900.
  The transition is only knowable AT bt_i + 900. Entry is the open of bar i+1, which prints
  at bt_i + 900. So DECISION_TS = bt_i + 900, and every book feature must be built from
  snapshots STRICTLY BEFORE bt_i + 900.
"""
import sys, glob, duckdb, numpy as np, pandas as pd
GB = "/home/alphabot/gazbot7"; OUT = f"{GB}/reports/regime_2026-09-12/book"
sys.path.insert(0, f"{GB}/scripts")
from bt_regime_transition import features, fit_gmm, predict, tape as bf_tape

BAR_MIN, STATES = 15, 3
con = duckdb.connect(config={"temp_directory": f"{GB}/data/duckdb_tmp"})

def agg(df, bar_min):
    s = bar_min * 60
    df = df.copy(); df["bt"] = (df.ts // s) * s
    g = df.groupby("bt").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                             close=("close", "last"), volume=("volume", "sum")).reset_index()
    g["dt"] = pd.to_datetime(g.bt, unit="s", utc=True)
    g["sess"] = (g.dt + pd.Timedelta(hours=2)).dt.date
    return g

# ---------- 1. fit on BACKFILL TRAIN, exactly as the incumbent does ----------
gbf = bf_tape(BAR_MIN)
Xbf = features(gbf)
ss = sorted(gbf.sess.unique()); n = len(ss)
TRAIN = set(ss[:int(n*.40)])
tr = gbf.sess.isin(TRAIN).values & np.isfinite(Xbf).all(axis=1)
mu, sd, w = fit_gmm(Xbf[tr], STATES)
# label states by their OWN statistics on TRAIN (never by outcome), same rule as the incumbent
sbf = predict(Xbf, mu, sd, w)
ret_bf = np.zeros(len(gbf)); ret_bf[1:] = gbf.close.values[1:] - gbf.close.values[:-1]
mrs = {k: ret_bf[tr & (sbf == k)].mean() for k in range(STATES)}
order = sorted(mrs, key=lambda k: mrs[k])
NAMES = {order[0]: "BEARISH", order[-1]: "BULLISH"}
for k in order[1:-1]:
    NAMES[k] = "CHOP"

# ---------- 2. apply UNCHANGED to the capture tape over the book window ----------
cap = con.execute(f"select * from read_parquet('{OUT}/tape_capture_1min.parquet')").df()
g = agg(cap, BAR_MIN)
X = features(g)
g["state"] = predict(X, mu, sd, w)
g["label"] = g.state.map(lambda k: NAMES.get(k, "?"))
g["ret"] = np.r_[0, np.diff(g.close.values)]

log = []
log.append(f"GMM: {STATES} states, {BAR_MIN}-min bars, fitted on BACKFILL TRAIN "
           f"({min(TRAIN)}..{max(TRAIN)}, {len(TRAIN)} sessions). Applied unchanged to capture tape.")
log.append(f"{'state':>6}{'label':>9}{'TRAIN share':>13}{'TRAIN mean ret':>16}"
           f"{'BOOKWIN share':>15}{'BOOKWIN mean ret':>18}")
BW0, BW1 = pd.Timestamp("2026-07-31").date(), pd.Timestamp("2026-09-11").date()
bw = g[(g.sess >= BW0) & (g.sess <= BW1)]
for k in range(STATES):
    m = bw[bw.state == k]
    log.append(f"{k:>6}{NAMES[k]:>9}{100*(tr & (sbf==k)).sum()/tr.sum():>12.0f}%"
               f"{mrs[k]:>16.2f}{100*len(m)/len(bw):>14.0f}%{m.ret.mean():>18.2f}")

# ---------- 3. the transition event table ----------
st, close, op, sess, bt = g.state.values, g.close.values, g.open.values, g.sess.values, g.bt.values
rec = []
for i in range(3, len(g)):
    cur, prv = st[i], st[i-1]
    if cur < 0 or prv < 0 or cur == prv: continue
    if NAMES.get(cur) not in ("BULLISH", "BEARISH"): continue
    if NAMES.get(prv) == NAMES.get(cur): continue
    if sess[i] != sess[i-2]: continue
    clean = not (st[i-1] == cur or st[i-2] == cur)
    side = 1 if NAMES[cur] == "BULLISH" else -1
    row = dict(i=i, sess=str(sess[i]), bt=int(bt[i]), decision_ts=int(bt[i]) + BAR_MIN*60,
               state=int(cur), label=NAMES[cur], side=side, clean=bool(clean),
               entry=float(op[i+1]) if i+1 < len(g) else np.nan)
    for hold in (2, 3, 4, 5, 6, 8):
        j = i + hold
        row[f"raw{hold*BAR_MIN}"] = (float(side*(close[j]-op[i+1]))
                                     if j < len(g) and i+1 < len(g) and sess[i] == sess[j] else np.nan)
    rec.append(row)
ev = pd.DataFrame(rec)
ev_bw = ev[(ev.sess >= str(BW0)) & (ev.sess <= str(BW1))].reset_index(drop=True)
ev.to_csv(f"{OUT}/s02_transitions_all.csv", index=False)
ev_bw.to_csv(f"{OUT}/s02_transitions_bookwindow.csv", index=False)
con.execute(f"copy (select * from g) to '{OUT}/s02_bars15.parquet' (format parquet)")

log.append(f"\ntransitions on the capture tape total      : {len(ev)}")
log.append(f"transitions inside the BOOK window        : {len(ev_bw)}  over {ev_bw.sess.nunique()} sessions")
log.append(f"  of which CLEAN                          : {int(ev_bw.clean.sum())}")
log.append(f"  BULLISH / BEARISH                       : {(ev_bw.label=='BULLISH').sum()} / {(ev_bw.label=='BEARISH').sum()}")
log.append(f"\n★ POWER, up front: a 60m-hold cell has n={ev_bw.raw60.notna().sum()} (all) / "
           f"{ev_bw[ev_bw.clean].raw60.notna().sum()} (clean). Per-trade sd of raw60 is "
           f"{ev_bw.raw60.std():.1f}pt, so the sd of the MEAN is "
           f"{ev_bw.raw60.std()/np.sqrt(max(ev_bw.raw60.notna().sum(),1)):.2f}pt. Any book effect "
           f"smaller than ~2x that is UNDETECTABLE here and will be reported as such.")
txt = "\n".join(log); open(f"{OUT}/s02_regimes.txt", "w").write(txt+"\n"); print(txt)
