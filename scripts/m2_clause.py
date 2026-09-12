"""CLAUSE-LEVEL autopsy for the two totally-silent shorts: which rule kills them?"""
import json,sys
from collections import Counter
sys.path.insert(0,"/home/alphabot/gazbot7/scripts"); sys.path.insert(0,"/home/alphabot/gazbot7/src")
from m2_idle_gates import (bars_at, footprint_at, tape_window, last_tick_px, compute_features, M2)
from gazbot7.slot_strategy import _RGV_SHORT
from gazbot7.footprint import FootprintCfg
import m2_run as R
runs=[r for r in R.priceable if r["dir"]=="DN"]
P=_RGV_SHORT; cfg=FootprintCfg()
c=Counter(); n=0
ec=Counter(); en=0
for r in runs:
    for s in range(r["s"]-600, r["s"]+1):
        bars=bars_at(s)
        if len(bars)<6: continue
        if last_tick_px(s) is None: continue
        f=compute_features(bars); fp=footprint_at(s); n+=1; en+=1
        # ── rgv_short clauses, in gate order ──
        slope=f.vwap_slope_atr
        if f.atr_pct>0.09 or abs(slope)>1.0: c["1 regime stand-down (atr_pct>9% or |slope|>1)"]+=1
        elif f.atr < P["atr_min"]:           c[f"2 atr_min {P['atr_min']:.0f} (ATR too small)"]+=1
        elif f.ext_atr < P["ext_min"]:       c[f"3 ext_min {P['ext_min']} (not stretched above VWAP)"]+=1
        elif f.net_atr_5 > -P["turn_atr"]:   c[f"4 turn_atr {P['turn_atr']} (no fresh down-turn)"]+=1
        else:                                c["FIRES"]+=1
        # ── exhaustion_short clauses ──
        ns, mv = fp["net_signed"], fp["price_move_pt"]
        if abs(ns) < cfg.net_min:                 ec[f"1 |20s net flow| < {cfg.net_min:.0f}"]+=1
        elif abs(mv) > cfg.move_max:              ec[f"2 price moved > {cfg.move_max}pt (not absorption)"]+=1
        elif fp["bid1_size"]<=0 or fp["ask1_size"]<=0: ec["3 no L1 book"]+=1
        elif ns <= 0:                             ec["4 flow SELL-heavy -> the fade is LONG, not SHORT"]+=1
        elif fp["ask1_size"] < cfg.wall_ratio*fp["bid1_size"]: ec[f"5 no ask wall (>= {cfg.wall_ratio}x bid)"]+=1
        else:                                     ec["FIRES"]+=1
print(f"rgv_short — first failing clause over {n:,} DN decision-seconds")
for k,v in sorted(c.items()): print(f"   {k:55s} {v:7,d}  {100*v/n:6.2f}%")
print(f"\nexhaustion_short — first failing clause over {en:,} DN decision-seconds")
for k,v in sorted(ec.items()): print(f"   {k:55s} {v:7,d}  {100*v/en:6.2f}%")
json.dump({"rgv_short":dict(c),"exhaustion_short":dict(ec),"n":n},open(f"{M2}/clause.json","w"))
