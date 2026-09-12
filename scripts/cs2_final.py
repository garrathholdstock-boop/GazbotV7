"""CHOP-SCALP step 10 — the remaining numbers the write-up needs."""
import glob, json, os, sys
import duckdb, numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from cs2_common import OUT, GB, VPP, FEE, load_events
from cs2_sweep import sequential

con = duckdb.connect()
D = sorted(os.path.basename(f)[:-8] for f in glob.glob(f"{GB}/data/tape/ticks/MNQ/2026-*.parquet"))
FS = ["2026-07-31"] + [d for d in D if d >= "2026-08-03"]
vol = {}
for s in ("ticks", "book", "depth", "quotes"):
    files = [f"{GB}/data/tape/{s}/MNQ/{d}.parquet" for d in FS]
    files = [f for f in files if os.path.exists(f)]
    vol[s] = int(con.execute(f"SELECT count(*) FROM read_parquet({files!r})").fetchone()[0])
print("[tape volume, 17 full-stack days]", {k: f"{v:,}" for k, v in vol.items()})

d = load_events()
CHOP = d.regime.isin(("CHOP", "DEAD_CHOP"))
print(f"[events] {len(d):,} candidates, {int(CHOP.sum()):,} on chop tape, {d.date.nunique()} days")

# --- why exhaustion_signal never fires on chop tape
n20 = d.net20.abs()[CHOP]
print(f"\n[exhaustion_signal net_min=400 vs the chop tape] "
      f"|net20| median={n20.median():.0f} p90={n20.quantile(.90):.0f} p99={n20.quantile(.99):.0f} "
      f"share>=400: {(n20>=400).mean():.3%}")
both = CHOP & (d.net20.abs() >= 400) & (d.mv20.abs() <= 2.0)
print(f"  |net20|>=400 AND |move20|<=2pt: {int(both.sum())} of {int(CHOP.sum())} "
      f"({both.sum()/CHOP.sum():.3%});  + wall1>=1.5: {int((both & (d.f_wall1>=1.5)).sum())}")

# --- per-chop-day for the finalists  (operator: must hold on ALL the chop days, not one)
days = pd.read_csv(f"{OUT}/regime_days.csv")
chop_days = [x for x in days[days.daytype == "CHOP"].date if x in set(d.date)]
print(f"\n[chop days in the full-stack window] {chop_days}")
FIN = {
 "CT13 close@30m-ext + 20s thrust>=4  (6/10)": (CHOP & (d.f_extC30 > 0) & (d.f_mv20 >= 4.0), 6.0, 10.0),
 "CT16 close@30m-ext + 20s thrust>=5  (8/10)": (CHOP & (d.f_extC30 > 0) & (d.f_mv20 >= 5.0), 8.0, 10.0),
 "CT15 CT13 + 41ms refill >= median   (8/10)": (CHOP & (d.f_extC30 > 0) & (d.f_mv20 >= 4.0)
                                                & (d.f_refill >= d.f_refill[CHOP].median()), 8.0, 10.0),
}
res = {}
for lab, (m, tp, sp) in FIN.items():
    parts = [sequential(g.sort_values("dts"), tp, sp) for _, g in d[m].groupby("date")]
    o = pd.concat(parts, ignore_index=True)
    cd = o[o.date.isin(chop_days)]
    per = cd.groupby("date").usd.agg(["size", "sum"])
    res[lab] = {"chop_day_n": int(len(cd)), "chop_day_net": round(float(cd.usd.sum()), 2),
                "chop_day_per_day": round(float(cd.usd.sum() / len(chop_days)), 2),
                "days_traded": int(cd.date.nunique()), "days_available": len(chop_days),
                "per_chop_day": {k: [int(v["size"]), round(float(v["sum"]), 2)] for k, v in per.iterrows()},
                "days_green": int((per["sum"] > 0).sum())}
    print(f"\n  {lab}")
    print(f"    on the {len(chop_days)} CHOP days: n={res[lab]['chop_day_n']} net=${res[lab]['chop_day_net']} "
          f"= ${res[lab]['chop_day_per_day']}/chop-day  (traded {res[lab]['days_traded']}/{len(chop_days)} of them, "
          f"green on {res[lab]['days_green']})")
    print(f"    {res[lab]['per_chop_day']}")

# --- full grave list from the sweep
S = pd.read_csv(f"{OUT}/sweep.csv")
g = S.groupby("label").agg(cells=("per_tr", "size"), pos=("per_tr", lambda s: int((s > 0).sum())),
                           med_ptr=("per_tr", "median"), max_ptr=("per_tr", "max"),
                           med_n=("n", "median")).round(3).sort_values("med_ptr", ascending=False)
print("\n[grave list]"); print(g.to_string())
json.dump({"vol": vol, "chop_days": chop_days, "finalists": res}, open(f"{OUT}/final.json", "w"), indent=1)
