"""CHOP-SCALP 2026-08-29 — THE PRIZE, re-priced with this week's book.

Where does the live desk actually lose money? A chop scalper only has something to recover if the
desk is DONATING on chop tape. Attributes every live MNQ trade to the regime of the 30-min block it
OPENED in, and reports the two books separately.

★ day_rider is a SEPARATE BOOK on the same IB account taking its own size (two-books memory); it is
  never folded into the tournament figure.
★ A/B legs are a SCALE-OUT of ONE signal, not two experiments -- signal counts are reported as well
  as leg counts so the trade count is not doubled.
"""
import json, sqlite3, sys
import numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
OUT2 = f"{GB}/reports/friday_v7/sections/cs2"
OUT3 = f"{GB}/reports/friday_v7/sections/cs3"

blocks = pd.read_csv(f"{OUT2}/regime_blocks.csv")
days = pd.read_csv(f"{OUT2}/regime_days.csv")
con = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
tr = pd.read_sql("SELECT * FROM trades WHERE symbol='MNQ'", con)
flagged = int(tr.data_quality.notna().sum())
tr = tr[tr.data_quality.isna()]
tr["ts"] = (pd.to_datetime(tr.opened_at, utc=True, format="mixed")
            - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds().astype("int64")
tr["blk"] = (tr.ts // 1800) * 1800
tr["date"] = pd.to_datetime(tr.ts, unit="s", utc=True).dt.strftime("%Y-%m-%d")
tr = tr.merge(blocks[["blk", "regime", "atr_rel", "er30"]], on="blk", how="left")
tr = tr.merge(days[["date", "daytype", "us_eff"]], on="date", how="left")
tr["book"] = np.where(tr.gate.fillna("").str.startswith("day_rider"), "day_rider", "tournament")
tr["sig"] = tr.gate.fillna("").str.replace(r"_[AB]$", "", regex=True)
print(f"[trades] {len(tr)} clean MNQ rows ({flagged} data_quality-flagged excluded)")

res = {"flagged_excluded": flagged}
WINS = [("THIS WEEK 08-24..08-28", "2026-08-24", "2026-08-28"),
        ("FULL 07-31..08-28",      "2026-07-31", "2026-08-28")]
for lab, lo, hi in WINS:
    w = tr[(tr.date >= lo) & (tr.date <= hi)]
    print(f"\n=== {lab} ===")
    dd = {}
    for bk in ("tournament", "day_rider"):
        s = w[w.book == bk]
        nsig = s.groupby(["date", "sig", "opened_at"]).ngroups
        print(f"  {bk}: {len(s)} legs / ~{nsig} signals   net=${s.pnl_usd.sum():,.2f}")
        by = s.groupby("regime").agg(n=("id", "size"), net=("pnl_usd", "sum"),
                                     win=("pnl_usd", lambda x: (x > 0).mean()))
        for r, v in by.sort_values("net").iterrows():
            print(f"     {r:10s} n={int(v['n']):4d} net=${v['net']:>10,.2f} "
                  f"${v['net']/v['n']:>8.2f}/leg  win={v['win']:.0%}")
        byd = s.groupby("daytype").agg(n=("id", "size"), net=("pnl_usd", "sum"))
        print(f"     by daytype: " + "  ".join(
            f"{k}: n={int(v['n'])} ${v['net']:,.2f}" for k, v in byd.iterrows()))
        dd[bk] = {"legs": len(s), "signals": nsig, "net": round(float(s.pnl_usd.sum()), 2),
                  "by_regime": {k: {"n": int(v["n"]), "net": round(float(v["net"]), 2)}
                                for k, v in by.iterrows()},
                  "by_daytype": {k: {"n": int(v["n"]), "net": round(float(v["net"]), 2)}
                                 for k, v in byd.iterrows()}}
    res[lab] = dd

# per-day, this week
print("\n=== per-day, 08-24..08-28 ===")
w = tr[tr.date >= "2026-08-24"]
p = w.pivot_table(index="date", columns="book", values="pnl_usd", aggfunc=["size", "sum"]).fillna(0)
dt = days.set_index("date").daytype
for dte in sorted(w.date.unique()):
    t = w[(w.date == dte) & (w.book == "tournament")]
    r = w[(w.date == dte) & (w.book == "day_rider")]
    print(f"  {dte} [{dt.get(dte,'?'):5s}]  tournament: {len(t):2d} legs ${t.pnl_usd.sum():>9,.2f}   "
          f"day_rider: {len(r):2d} ${r.pnl_usd.sum():>9,.2f}")
res["this_week_days"] = {dte: {"daytype": str(dt.get(dte, "?")),
                               "tournament": [int((w.date == dte).sum() and len(w[(w.date == dte) & (w.book == 'tournament')])),
                                              round(float(w[(w.date == dte) & (w.book == "tournament")].pnl_usd.sum()), 2)],
                               "day_rider": [len(w[(w.date == dte) & (w.book == "day_rider")]),
                                             round(float(w[(w.date == dte) & (w.book == "day_rider")].pnl_usd.sum()), 2)]}
                         for dte in sorted(w.date.unique())}

# how much of the tape IS chop, per day
blocks["date"] = blocks.date.astype(str)
tape = blocks.groupby(["date", "regime"]).size().unstack(fill_value=0)
tape["chop_frac"] = (tape.get("CHOP", 0) + tape.get("DEAD_CHOP", 0)) / tape.sum(axis=1)
res["tape_chop_frac"] = {k: round(float(v), 3) for k, v in tape.chop_frac.items()}
print("\n=== chop fraction of the tape, this week ===")
print(tape.chop_frac[tape.index >= "2026-08-24"].round(3).to_string())
json.dump(res, open(f"{OUT3}/prize.json", "w"), indent=1)
print(f"\n[wrote] {OUT3}/prize.json")
