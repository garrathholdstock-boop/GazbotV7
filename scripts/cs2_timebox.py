"""CHOP-SCALP step 9 — the purest sign test, and two more families.

(a) FORWARD RETURN, no stop, no target: from every chop-tape turn candidate, what is the signed
    move at +60 / +120 / +300 / +600 / +900s? If the chop tape reverts at all this is where it
    shows, unpolluted by any exit choice. This is also the whole TIMEBOX family in one table.
(b) CT21 RE-TEST — fade a touch of the 60-min edge that does NOT make a new 30-min extreme.
(c) The +$200-300-a-chop-day arithmetic.
"""
import glob, json, os, sys
import duckdb, numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from cs2_common import OUT, GB, VPP, FEE, SLIP_STOP_PT, load_events
from cs2_sweep import sequential

d = load_events()
CHOP = d.regime.isin(("CHOP", "DEAD_CHOP"))
con = duckdb.connect()
HOR = [60, 120, 300, 600, 900]

# ---------------- (a) forward returns
fw = {h: np.full(len(d), np.nan) for h in HOR}
for day, g in d.groupby("date"):
    t = con.execute(f"SELECT ts_ms, price FROM read_parquet('{GB}/data/tape/ticks/MNQ/{day}.parquet') "
                    f"WHERE symbol='MNQ' ORDER BY ts_ms").df()
    ts = t.ts_ms.values; pr = t.price.values
    e0 = np.searchsorted(ts, g.dts.values * 1000, side="left")
    ok = e0 < len(ts)
    ent = np.where(ok, pr[np.clip(e0, 0, len(pr) - 1)], np.nan)
    sgn = np.where(g.side.values == "SHORT", -1.0, 1.0)
    for h in HOR:
        j = np.clip(np.searchsorted(ts, (g.dts.values + h) * 1000, side="left"), 0, len(pr) - 1)
        fw[h][g.index.values] = (pr[j] - ent) * sgn
for h in HOR:
    d[f"fw{h}"] = fw[h]

print("=== (a) FORWARD RETURN from a chop-tape turn candidate, signed TO THE FADE (points) ===")
print("    a positive mean = the fade is right; the fee is $1.50 = 0.75 pt round trip\n")
rows = []
pops = {"all chop turns": CHOP,
        "+ closed at 30m extreme": CHOP & (d.f_extC30 > 0),
        "+ closed at 30m ext & 20s thrust>=4": CHOP & (d.f_extC30 > 0) & (d.f_mv20 >= 4),
        "+ wall1>=1.5 (absorption)": CHOP & (d.f_wall1 >= 1.5),
        "+ wall5>=1.3": CHOP & (d.f_wall5 >= 1.3),
        "+ 41ms refill >= median": CHOP & (d.f_refill >= d.f_refill[CHOP].median()),
        "+ vwap-flat <= 0.5 ATR": CHOP & (d.f_vwap_flat <= 0.5),
        "ALL TAPE (any regime)": pd.Series(True, index=d.index)}
for lab, m in pops.items():
    r = {"population": lab, "n": int(m.sum())}
    for h in HOR:
        v = d[f"fw{h}"][m].dropna()
        se = v.std() / max(len(v) ** 0.5, 1)
        r[f"+{h}s"] = f"{v.mean():+.3f}±{se:.3f}"
        r[f"t{h}"] = round(float(v.mean() / se), 2) if se > 0 else np.nan
    rows.append(r)
FW = pd.DataFrame(rows)
print(FW[["population", "n"] + [f"+{h}s" for h in HOR]].to_string(index=False))
print("\n    t-statistics:")
print(FW[["population", "n"] + [f"t{h}" for h in HOR]].to_string(index=False))

# ---------------- (b) CT21 re-test
print("\n=== (b) CT21 RE-TEST — a touch of the 60-min edge that does NOT make a new 30-min extreme ===")
near = (d.close - d.lo60).abs()
edge = np.where(d.side == "SHORT", (d.hi60 - d.close), (d.close - d.lo60))
d["f_edge_dist"] = edge / d.atr14
EXITS = [(t, s) for t in (3.0, 4.0, 5.0, 6.0, 8.0, 10.0) for s in (4.0, 6.0, 8.0, 10.0)]
for tag, m in (("CT21 retest (<=0.25 ATR from the 60m edge, no new 30m extreme)",
                CHOP & (d.f_edge_dist <= 0.25) & (d.f_extC30 == 0)),
               ("CT22 retest + 20s thrust>=4", CHOP & (d.f_edge_dist <= 0.25) & (d.f_extC30 == 0) & (d.f_mv20 >= 4))):
    ptrs, ns = [], []
    for tp, sp in EXITS:
        parts = [sequential(g.sort_values("dts"), tp, sp) for _, g in d[m].groupby("date")]
        o = pd.concat(parts, ignore_index=True)
        if len(o) < 12:
            continue
        ptrs.append(o.usd.mean()); ns.append(len(o))
    if ptrs:
        print(f"  {tag}: events={int(m.sum())} cells={len(ptrs)} positive={int((np.array(ptrs)>0).sum())} "
              f"median $/tr={np.median(ptrs):+.3f} max={np.max(ptrs):+.3f} median n={int(np.median(ns))}")
    else:
        print(f"  {tag}: events={int(m.sum())} — too few to grid")

# ---------------- (c) the arithmetic
print("\n=== (c) THE +$200-300-A-CHOP-DAY ARITHMETIC ===")
blocks = pd.read_csv(f"{OUT}/regime_blocks.csv")
cb = blocks[blocks.regime.isin(("CHOP", "DEAD_CHOP"))]
days = pd.read_csv(f"{OUT}/regime_days.csv")
chop_days = sorted(days[days.daytype == "CHOP"].date)
arith = {
    "chop_blocks": int(len(cb)), "chop_blocks_per_day": round(len(cb) / blocks.date.nunique(), 1),
    "median_chop_block_range_pt": round(float(cb.rng.median()), 2),
    "median_chop_block_atr_pt": round(float(cb.atr.median()), 2),
    "median_chop_block_abs_net_pt": round(float(cb.net.abs().median()), 2),
    "chop_day_list": chop_days,
}
for lab, m in (("CT13 L30C k4", CHOP & (d.f_extC30 > 0) & (d.f_mv20 >= 4)),
               ("CT15 +refill", CHOP & (d.f_extC30 > 0) & (d.f_mv20 >= 4) & (d.f_refill >= d.f_refill[CHOP].median()))):
    n = int(m.sum()); per_day = n / d.date.nunique()
    arith[lab] = {"events": n, "per_day": round(per_day, 2),
                  "trades_needed_for_250_at_6usd": round(250 / 6.077, 1),
                  "usd_per_trade_needed_at_this_rate": round(250 / per_day, 1),
                  "points_per_trade_needed": round(250 / per_day / VPP, 1)}
print(json.dumps(arith, indent=1))
json.dump({"forward": FW.to_dict("records"), "arith": arith}, open(f"{OUT}/timebox.json", "w"), indent=1, default=str)
