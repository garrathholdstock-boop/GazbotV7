"""CHOP-SCALP 2026-08-29 — THE CEILING, and the exhaustion_short lineage on chop tape.

(A) THE CEILING. The oracle (side = sign of the realised 60s move) is the most any 60-second-horizon
    chop-turn scalper could earn on this tape: perfect direction, real fills, real fees. Every
    candidate is then quoted as a FRACTION OF THAT CEILING, which is the honest way to say how much
    of the available money a filter actually captures.

(B) THE LINEAGE. The operator named exhaustion_short -- built from L2 footprints -- as the model.
    So: do that gate's OWN thresholds ever occur on chop tape? If the footprint condition it is
    built on essentially never fires when the tape is ranging, "port the lineage" was never on the
    table, and that is a fact about the tape rather than a failure of the search.
"""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from cs2_common import OUT, VPP, FEE, load_events
from cs3_race import sequential_live
from gf_cs_lib import ticks

OUT3 = "/home/alphabot/gazbot7/reports/friday_v7/sections/cs3"
d = load_events()
CHOP = d.regime.isin(("CHOP", "DEAD_CHOP"))
days_meta = pd.read_csv(f"{OUT}/regime_days.csv")
CHOP_DAYS = sorted(set(days_meta[days_meta.daytype == "CHOP"].date) & set(d.date))

mv = np.full(len(d), np.nan)
for day, g in d.groupby("date"):
    tt, pp = ticks(day)
    i0 = np.searchsorted(tt, g.dts.values, side="left")
    i1 = np.searchsorted(tt, g.dts.values + 60, side="left")
    ok = (i0 < len(tt)) & (i1 < len(tt)) & (i1 > i0)
    mv[g.index.values] = np.where(ok, pp[np.clip(i1,0,len(pp)-1)] - pp[np.clip(i0,0,len(pp)-1)], np.nan)
d["fwd60"] = mv

def run(frame, mask, tp, sp):
    sub = frame[mask]
    if not len(sub): return None
    return pd.concat([sequential_live(g, tp, sp) for _, g in sub.groupby("date")], ignore_index=True)

# ---- (A) the ceiling, on CHOP DAYS only ---------------------------------------------
orc = d.copy()
side = np.where(orc.fwd60 > 0, "LONG", "SHORT")
raw = d.entry.values + np.where(d.side.values == "SHORT", 0.25, -0.25)
orc["entry"] = raw + np.where(side == "LONG", 0.25, -0.25)
orc["side"] = side
TP, SP = 5.0, 5.0
o = run(orc, CHOP & np.isfinite(orc.fwd60) & orc.date.isin(CHOP_DAYS), TP, SP)
ceil_total = float(o.usd.sum()); ceil_ptr = float(o.usd.mean()); ceil_n = len(o)
per_day = ceil_total / len(CHOP_DAYS)
print(f"=== (A) THE CEILING — oracle 60s direction, {TP}/{SP}, on the {len(CHOP_DAYS)} chop days ===")
print(f"  n={ceil_n}  net=${ceil_total:,.2f}  ${ceil_ptr:.2f}/trade  win={(o.usd>0).mean():.0%}")
print(f"  = ${per_day:,.2f} per chop day WITH PERFECT 60-SECOND FORESIGHT")
print(f"  the +$250 bar is {250/per_day:.0%} of that ceiling")
res = {"ceiling": dict(tp=TP, sp=SP, n=ceil_n, net=round(ceil_total, 2), ptr=round(ceil_ptr, 3),
                       per_chop_day=round(per_day, 2), chop_days=CHOP_DAYS,
                       bar250_as_frac_of_ceiling=round(250/per_day, 4))}

THR = float(d.f_mv60[CHOP].quantile(0.95))
CANDS = {
  "CT20 60s thrust q95":      (CHOP & (d.f_mv60 >= THR), 8.0, 10.0),
  "CT13 close@30m-ext + 4pt": (CHOP & (d.f_extC30 > 0) & (d.f_mv20 >= 4.0), 6.0, 10.0),
  "CT0  naive fade":          (CHOP, 6.0, 10.0),
}
print(f"\n  conversion of the ceiling on chop days:")
conv = {}
for lab, (m, tp, sp) in CANDS.items():
    oo = run(d, m & d.date.isin(CHOP_DAYS), tp, sp)
    if oo is None: continue
    net = float(oo.usd.sum())
    print(f"    {lab:28s} n={len(oo):4d} net=${net:>9.2f}  = {net/ceil_total:>7.1%} of the ceiling")
    conv[lab] = dict(n=len(oo), net=round(net, 2), frac_of_ceiling=round(net/ceil_total, 4))
res["conversion"] = conv

# ---- (B) exhaustion_short's own thresholds on chop tape -----------------------------
print(f"\n=== (B) exhaustion_short's LITERAL footprint condition on chop tape ===")
n20 = d.net20.abs()[CHOP]
print(f"  |20s aggressor net| on chop tape:  median={n20.median():.0f}  p90={n20.quantile(.90):.0f}  "
      f"p99={n20.quantile(.99):.0f}  p99.9={n20.quantile(.999):.0f}")
print(f"  the gate's floor is net_min=400.  share of chop ticks clearing it: {(n20>=400).mean():.3%}")
both = CHOP & (d.net20.abs() >= 400) & (d.mv20.abs() <= 2.0)
wall = both & (d.f_wall1 >= 1.5)
print(f"  + the STALL term (|60s move| <= 2pt): {int(both.sum())} of {int(CHOP.sum())} chop events "
      f"({both.sum()/CHOP.sum():.3%})")
print(f"  + the absorbing wall (wall1 >= 1.5): {int(wall.sum())} events over {d[wall].date.nunique()} days "
      f"= {wall.sum()/max(len(CHOP_DAYS),1):.2f} per chop day")
res["lineage"] = dict(net20_median=float(n20.median()), net20_p99=float(n20.quantile(.99)),
                      share_ge_400=round(float((n20 >= 400).mean()), 5),
                      n_literal=int(both.sum()), n_literal_plus_wall=int(wall.sum()),
                      chop_events=int(CHOP.sum()))
if wall.sum() >= 10:
    for tp, sp in ((5.0, 5.0), (6.0, 10.0), (8.0, 10.0)):
        oo = run(d, wall, tp, sp)
        if oo is not None and len(oo) >= 8:
            print(f"    costed {tp}/{sp}: n={len(oo)} ${oo.usd.sum():.2f} ${oo.usd.mean():.3f}/tr "
                  f"win={(oo.usd>0).mean():.0%}")
            res.setdefault("lineage_costed", []).append(
                dict(tp=tp, sp=sp, n=len(oo), net=round(float(oo.usd.sum()), 2),
                     ptr=round(float(oo.usd.mean()), 3)))
else:
    print(f"    -> too few to cost. The lineage does not transfer because the CONDITION does not occur.")
json.dump(res, open(f"{OUT3}/ceiling.json", "w"), indent=1)
print(f"\n[wrote] {OUT3}/ceiling.json")
