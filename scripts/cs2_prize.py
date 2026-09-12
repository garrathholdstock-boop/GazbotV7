"""CHOP-SCALP step 2 — THE PRIZE. Where does the live desk actually lose its money?

Attributes every live MNQ trade to the 30-min regime block it OPENED in (cs2/regime_blocks.csv)
and reports net / n / $-per-trade per regime, per day-type and per session. This is the number a
chop scalper has to beat: if the desk is not donating in chop, a chop scalper has nothing to
recover and the honest answer is "fix the filter, not the gate".

★ day_rider is a SEPARATE BOOK on the same IB account and takes its own size; it is reported on its
  own line and EXCLUDED from the tournament figure, per the two-books memory.
"""
import json, sqlite3
import numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/reports/friday_v7/sections/cs2"

blocks = pd.read_csv(f"{OUT}/regime_blocks.csv")
days = pd.read_csv(f"{OUT}/regime_days.csv")
con = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
tr = pd.read_sql("SELECT * FROM trades WHERE symbol='MNQ' AND data_quality IS NULL", con)
# ⚠ pandas 2 keeps the parsed UNIT (datetime64[us] here), so `.astype("int64")//10**9` is off by
# 1000x and silently empties the frame. Convert through total_seconds().
tr["ts"] = (pd.to_datetime(tr.opened_at, utc=True, format="mixed")
            - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds().astype("int64")
tr["blk"] = (tr.ts // 1800) * 1800
tr["date"] = pd.to_datetime(tr.ts, unit="s", utc=True).dt.strftime("%Y-%m-%d")
tr["hh"] = pd.to_datetime(tr.ts, unit="s", utc=True).dt.hour
tr = tr.merge(blocks[["blk", "regime", "atr", "er30"]], on="blk", how="left")
tr = tr.merge(days[["date", "daytype", "us_eff"]], on="date", how="left")
tr["book"] = np.where(tr.gate.fillna("").str.startswith("day_rider"), "day_rider", "tournament")

res = {}
for win, lo, hi in [("ALL_07-31..08-24", "2026-07-31", "2026-08-24"),
                    ("WEEK_08-17..08-21", "2026-08-17", "2026-08-21")]:
    w = tr[(tr.date >= lo) & (tr.date <= hi)]
    d = {}
    for bk in ("tournament", "day_rider"):
        s = w[w.book == bk]
        d[bk] = {
            "n": int(len(s)), "net": round(float(s.pnl_usd.sum()), 2),
            "by_regime": {k: {"n": int(v["n"]), "net": round(float(v["net"]), 2),
                              "per_tr": round(float(v["net"] / v["n"]), 2), "win": round(float(v["win"]), 3)}
                          for k, v in s.groupby("regime").agg(
                              n=("id", "size"), net=("pnl_usd", "sum"),
                              win=("pnl_usd", lambda x: (x > 0).mean())).iterrows()},
            "by_daytype": {k: {"n": int(v["n"]), "net": round(float(v["net"]), 2)}
                           for k, v in s.groupby("daytype").agg(
                               n=("id", "size"), net=("pnl_usd", "sum")).iterrows()},
            "by_day": {k: {"n": int(v["n"]), "net": round(float(v["net"]), 2)}
                       for k, v in s.groupby("date").agg(
                           n=("id", "size"), net=("pnl_usd", "sum")).iterrows()},
        }
    res[win] = d

# tape budget: how much of the tape IS chop, per day
blocks["date"] = blocks.date.astype(str)
tape = blocks.groupby(["date", "regime"]).size().unstack(fill_value=0)
tape["chop_frac"] = (tape.get("CHOP", 0) + tape.get("DEAD_CHOP", 0)) / tape.sum(axis=1)
res["tape_chop_frac"] = {k: round(float(v), 3) for k, v in tape.chop_frac.items()}
json.dump(res, open(f"{OUT}/prize.json", "w"), indent=1)

print("=== TOURNAMENT (excl. day_rider), by regime of the OPENING block ===")
for win in ("ALL_07-31..08-24", "WEEK_08-17..08-21"):
    print(f"\n--- {win} ---")
    for bk in ("tournament", "day_rider"):
        d = res[win][bk]
        print(f"  {bk}: n={d['n']} net=${d['net']}")
        for r, v in sorted(d["by_regime"].items(), key=lambda x: x[1]["net"]):
            print(f"     {r:10s} n={v['n']:4d} net=${v['net']:>9.2f}  ${v['per_tr']:>7.2f}/tr  win={v['win']:.0%}")
        print(f"     daytype: {d['by_daytype']}")
print("\n=== per-day tape chop fraction ===")
print(tape.chop_frac.round(3).to_string())
