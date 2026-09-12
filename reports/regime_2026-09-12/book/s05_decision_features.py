#!/usr/bin/env python3
"""S05 — the DECISION-POINT feature table.

One row per 15-min bar boundary in the book window. The decision at bar i is taken at
T = bt_i + 900 (that is when bar i's close is known and when bar i+1's open prints).
EVERY feature is built from per-minute rows m with m + 60 <= T, i.e. the 15 minutes
[bt_i, bt_i+900). No minute straddles T. Nothing from bar i+1 onward is touched.

WHY NOT A +/-2 MINUTE WINDOW: an earlier study here straddled a pivot and could not separate
"a thin book let price move" from "the move consumed the book". This window ENDS at the decision.

MATCHED CONTROLS: book depth is 40 overnight and 80 in US hours, so a day-median comparison
conflates time-of-day with signal. Every feature is emitted three ways:
  raw            — the number itself
  _zs            — z-scored against THE SAME SESSION's own 15-min windows
  _ztod          — z-scored against THE SAME 15-MINUTE-OF-DAY SLOT across the OTHER sessions
                   (leave-one-out, so a window never contributes to its own control)
"""
import glob, duckdb, numpy as np, pandas as pd
GB = "/home/alphabot/gazbot7"; OUT = f"{GB}/reports/regime_2026-09-12/book"
W = "/tmp/claude-0/-root/7d23ea02-1a64-45f1-9faa-faa8101cea4d/scratchpad"
con = duckdb.connect(config={"temp_directory": f"{GB}/data/duckdb_tmp", "memory_limit": "800MB"})

bk = f"read_parquet('{W}/bookfeat/*.parquet')"
tk = f"read_parquet('{W}/tickfeat/*.parquet')"
bars = f"read_parquet('{OUT}/s02_bars15.parquet')"

# per-minute book+tick joined, then folded into the 15-min window that PRECEDES each decision.
q = f"""
with b as (select * from {bk}), t as (select * from {tk}),
mn as (select coalesce(b.m,t.m) m, b.*, t.buyv, t.sellv, t.vol, t.ntr, t.max_sz
       from b full outer join t on b.m=t.m),
w as (
 select (m - m % 900) as bt,
   -- levels
   avg(db3_mean) db3, avg(da3_mean) da3, avg(b0s_mean) b0s, avg(a0s_mean) a0s,
   avg(spread_mean) spread, avg(bslope_px) bpx, avg(aslope_px) apx,
   sum(n_snap) nsnap, sum(n_chg) nchg,
   -- order flow imbalance, full window and last 5 minutes only
   sum(ofi_sum) ofi, sum(case when m % 900 >= 600 then ofi_sum end) ofi5,
   sum(n_ofi) nofi,
   -- aggressive trade flow
   sum(buyv) buyv, sum(sellv) sellv, sum(vol) vol, sum(ntr) ntr,
   sum(case when m % 900 >= 600 then buyv end) buyv5,
   sum(case when m % 900 >= 600 then sellv end) sellv5,
   -- depth TREND inside the window: last 5 min vs first 5 min
   avg(case when m % 900 >= 600 then db3_mean+da3_mean end) dep_late,
   avg(case when m % 900 <  300 then db3_mean+da3_mean end) dep_early,
   count(*) nmin,
   -- ★ THE FRESHEST CAUSAL OBSERVATION: the LAST snapshot of the LAST minute in the window.
   --   That snapshot is strictly inside [bt, bt+900) — it is the newest book state a decision
   --   at bt+900 is allowed to see. Averaging 15 minutes of a mean-reverting quantity washes
   --   it out, so the last read is kept separately rather than folded in.
   arg_max(db3_last, m) db3_L, arg_max(da3_last, m) da3_L,
   arg_max(b0s_last, m) b0s_L, arg_max(a0s_last, m) a0s_L,
   avg(case when m % 900 >= 600 then db3_last end) db3_5,
   avg(case when m % 900 >= 600 then da3_last end) da3_5
 from mn group by 1)
select * from w where nmin >= 12
"""
d = con.execute(q).df()

# ---- signed & scale-free features ----------------------------------------------------------
eps = 1e-9
d["imb3"]      = (d.db3 - d.da3) / (d.db3 + d.da3 + eps)          # static 3-level imbalance
d["imb_touch"] = (d.b0s - d.a0s) / (d.b0s + d.a0s + eps)          # touch imbalance
d["ofi_n"]     = d.ofi / (d.db3 + d.da3 + eps)                    # OFI, depth-normalised
d["ofi5_n"]    = d.ofi5 / (d.db3 + d.da3 + eps)                   # last-5-min OFI
d["tsi"]       = (d.buyv - d.sellv) / (d.buyv + d.sellv + eps)    # trade-sign imbalance
d["tsi5"]      = (d.buyv5 - d.sellv5) / (d.buyv5 + d.sellv5 + eps)
d["slope_asym"] = (d.apx - d.bpx) / (d.apx + d.bpx + eps)         # which side is gappier
d["imb3_L"]    = (d.db3_L - d.da3_L) / (d.db3_L + d.da3_L + eps)  # freshest 3-level imbalance
d["imbT_L"]    = (d.b0s_L - d.a0s_L) / (d.b0s_L + d.a0s_L + eps)  # freshest touch imbalance
d["imb3_5"]    = (d.db3_5 - d.da3_5) / (d.db3_5 + d.da3_5 + eps)  # last-5-min 3-level imbalance
# ---- unsigned / level features (the "when", not the "which way") ---------------------------
d["depth"]     = d.db3 + d.da3
d["depth_tr"]  = d.dep_late / (d.dep_early + eps)
d["qint"]      = d.nchg / (d.nsnap + eps)
d["spd"]       = d.spread
d["trade_sz"]  = d.vol / (d.ntr + eps)

SIGNED = ["imb3", "imb_touch", "imb3_L", "imbT_L", "imb3_5", "ofi_n", "ofi5_n", "tsi", "tsi5", "slope_asym"]
LEVEL  = ["depth", "depth_tr", "qint", "spd", "trade_sz"]
FEATS  = SIGNED + LEVEL

g = con.execute(f"select bt, sess, close, open, state, label from {bars}").df()
d = d.merge(g, on="bt", how="inner")
d["dt"] = pd.to_datetime(d.bt, unit="s", utc=True)
d["slot"] = (d.dt.dt.hour * 60 + d.dt.dt.minute) // 15      # 15-min-of-day slot

# ---- MATCHED CONTROLS -----------------------------------------------------------------------
for f in FEATS:
    s = d.groupby("sess")[f]
    d[f + "_zs"] = (d[f] - s.transform("mean")) / (s.transform("std") + eps)
    # leave-one-out by session within the same time-of-day slot
    gg = d.groupby("slot")[f]
    n, tot, sq = gg.transform("count"), gg.transform("sum"), gg.transform(lambda x: (x**2).sum())
    loo_n = n - 1
    loo_m = (tot - d[f]) / loo_n.replace(0, np.nan)
    loo_v = (sq - d[f]**2) / loo_n.replace(0, np.nan) - loo_m**2
    d[f + "_ztod"] = (d[f] - loo_m) / (np.sqrt(loo_v.clip(lower=0)) + eps)

con.execute(f"copy (select * from d) to '{OUT}/s05_decision_features.parquet' (format parquet)")
rep = [f"decision-point windows: {len(d)} over {d.sess.nunique()} sessions "
       f"({d.sess.min()}..{d.sess.max()})",
       f"signed features: {SIGNED}", f"level features : {LEVEL}", "",
       "raw feature summary (sanity):", d[FEATS].describe().T.to_string(),
       "", "session-dependence being controlled for — mean DEPTH by 15-min-of-day slot:"]
tod = d.groupby(d.dt.dt.hour)["depth"].mean()
rep.append("  " + "  ".join(f"{h:02d}h:{v:.0f}" for h, v in tod.items()))
txt = "\n".join(rep); open(f"{OUT}/s05_features.txt", "w").write(txt + "\n"); print(txt)
