"""CHOP-SCALP 2026-08-29 — the R-sweep in R units, the +$200-300 arithmetic, and a POSITIVE CONTROL.

Three things the verdict needs:
 (1) the operator asked to "bank at ~0.5R/1R -- sweep the exact R". The grid is in points; this
     restates it as R = target/stop so the answer is in his units.
 (2) the +$200-300-per-chop-day bar, priced against the measured firing rate. Selectivity and a
     dollar target are in tension and the tension is arithmetic, not opinion.
 (3) a POSITIVE CONTROL. A harness that can only print losses is not evidence. The identical race,
     cost model and sequencing are pointed at trend tape with a CONTINUATION rule; if that comes back
     positive, the negative chop numbers are a finding and not a bug.
"""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from cs2_common import OUT, VPP, FEE, load_events
from cs3_race import sequential_live

OUT3 = "/home/alphabot/gazbot7/reports/friday_v7/sections/cs3"
d = load_events()
CHOP = d.regime.isin(("CHOP", "DEAD_CHOP"))
days_meta = pd.read_csv(f"{OUT}/regime_days.csv")
CHOP_DAYS = sorted(set(days_meta[days_meta.daytype == "CHOP"].date) & set(d.date))
res = {"chop_days": CHOP_DAYS}
print(f"[chop days in the 21-day full-stack window] {CHOP_DAYS}")

def ev(mask, tp, sp, days=None):
    sub = d[mask & d.date.isin(days)] if days is not None else d[mask]
    if not len(sub): return None
    o = pd.concat([sequential_live(g, tp, sp) for _, g in sub.groupby("date")], ignore_index=True)
    return o if len(o) else None

# ---- (1) THE R SWEEP, in R units ----------------------------------------------------
print("\n=== 1. THE R SWEEP — target expressed as R = target/stop, on chop tape ===")
THR = float(d.f_mv60[CHOP].quantile(0.95))
RULES = {
  "CT20  60s thrust q95 into a 10m extreme": CHOP & (d.f_mv60 >= THR),
  "CT13  close@30m-ext + 20s thrust>=4pt":   CHOP & (d.f_extC30 > 0) & (d.f_mv20 >= 4.0),
  "CT0   naive chop fade (control)":         CHOP,
}
STOPS = [3.0, 5.0, 8.0]
RS = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
rows = []
for lab, m in RULES.items():
    for sp in STOPS:
        for R in RS:
            tp = round(sp * R, 2)
            o = ev(m, tp, sp)
            if o is None or len(o) < 15: continue
            rows.append(dict(rule=lab, stop_pt=sp, R=R, target_pt=tp, n=len(o),
                             net=round(float(o.usd.sum()), 2), ptr=round(float(o.usd.mean()), 3),
                             win=round(float((o.usd > 0).mean()), 3)))
RSW = pd.DataFrame(rows)
RSW.to_csv(f"{OUT3}/r_sweep.csv", index=False)
for lab in RULES:
    s = RSW[RSW.rule == lab]
    if not len(s): continue
    print(f"\n  {lab}")
    print("   " + s.pivot_table(index="stop_pt", columns="R", values="ptr").round(2)
          .to_string().replace("\n", "\n   "))
    print(f"   best cell ${s.ptr.max():.3f}/tr   positive cells {int((s.ptr>0).sum())}/{len(s)}")
res["r_sweep"] = {lab: dict(cells=int((RSW.rule == lab).sum()),
                            pos=int(((RSW.rule == lab) & (RSW.ptr > 0)).sum()),
                            best=round(float(RSW[RSW.rule == lab].ptr.max()), 3),
                            med=round(float(RSW[RSW.rule == lab].ptr.median()), 3)) for lab in RULES}

# ---- (2) THE +$200-300 ARITHMETIC ---------------------------------------------------
print("\n=== 2. THE BAR — what a +$250 chop day actually requires ===")
blocks = pd.read_csv(f"{OUT}/regime_blocks.csv")
cb = blocks[blocks.regime.isin(("CHOP", "DEAD_CHOP"))]
med_rng = float(cb.rng.median())
print(f"  median 30-min CHOP block range: {med_rng:.2f} pt  (n={len(cb)} blocks)")
arith = {"median_chop_block_range_pt": round(med_rng, 2)}
for lab, m in RULES.items():
    sub = d[m & d.date.isin(CHOP_DAYS)]
    rate = len(sub) / max(len(CHOP_DAYS), 1)
    need250 = 250.0 / rate if rate else float("nan")
    print(f"  {lab[:42]:42s} fires {rate:5.2f}x/chop-day -> needs ${need250:8.2f}/trade "
          f"= {need250/VPP:6.1f} pt  ({need250/VPP/med_rng:.0%} of a whole 30-min block range)")
    arith[lab] = dict(per_chop_day=round(rate, 2), need_usd_per_trade=round(need250, 2),
                      need_pt=round(need250 / VPP, 1))
# and the other way: at the best measured $/trade, how many trades a day would it take?
best_ptr = float(RSW.ptr.max())
print(f"\n  Best $/trade anywhere in the R sweep: ${best_ptr:.3f}. "
      f"{'To reach +$250/day would need ' + str(round(250/best_ptr)) + ' trades/day.' if best_ptr>0 else 'It is NEGATIVE, so no trade count reaches +$250 — more trades means more loss.'}")
arith["best_ptr_anywhere"] = round(best_ptr, 3)
res["arithmetic"] = arith

# ---- (3) POSITIVE CONTROL -----------------------------------------------------------
print("\n=== 3. POSITIVE CONTROL — same harness, same fee, TREND tape, CONTINUATION not fade ===")
# Our events are turn candidates signed to the FADE. Flipping the side turns them into breakout
# continuation entries. On TREND blocks that should make money if the machinery is sound.
TREND = d.regime == "TREND"
dc = d.copy()
dc["side"] = np.where(dc.side.values == "SHORT", "LONG", "SHORT")   # trade WITH the break
# entry was filled adverse for the fade; re-cross for the flipped side
dc["entry"] = d.entry.values + np.where(d.side.values == "SHORT", 0.50, -0.50)
def ev2(mask, tp, sp):
    sub = dc[mask]
    if not len(sub): return None
    return pd.concat([sequential_live(g, tp, sp) for _, g in sub.groupby("date")], ignore_index=True)
ctl = []
for tp, sp in [(8.0, 5.0), (10.0, 5.0), (12.0, 6.0), (15.0, 8.0), (20.0, 10.0)]:
    o = ev2(TREND & (dc.f_mv60 <= -6.0), tp, sp)     # break with a real 60s thrust behind it
    if o is None or len(o) < 15: continue
    ctl.append(dict(tp=tp, sp=sp, n=len(o), net=round(float(o.usd.sum()), 2),
                    ptr=round(float(o.usd.mean()), 3), win=round(float((o.usd > 0).mean()), 3)))
C = pd.DataFrame(ctl)
if len(C):
    print(C.to_string(index=False))
    print(f"  positive cells: {int((C.ptr>0).sum())}/{len(C)}   best ${C.ptr.max():.3f}/tr")
    res["positive_control"] = dict(cells=len(C), pos=int((C.ptr > 0).sum()),
                                   best=round(float(C.ptr.max()), 3),
                                   med=round(float(C.ptr.median()), 3), rows=ctl)
else:
    print("  (too few trend-block events to control on)")
    res["positive_control"] = None
json.dump(res, open(f"{OUT3}/arith.json", "w"), indent=1)
print(f"\n[wrote] {OUT3}/arith.json")
