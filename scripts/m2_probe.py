"""PROBE — the roster has THREE momentum gates and only ONE of them (abs_veto_short) can
take a DOWN run. grind_short exists in the codebase (slot_strategy.grind_long_short_slots)
but is not on the live slate. Fire it, mirror-identical to live grind_long, at the 32 DOWN
sat-out runs. Same 10-min pre-window, same tick-honest exit stack, same costs."""
import json,sys
from collections import Counter
sys.path.insert(0,"/home/alphabot/gazbot7/scripts"); sys.path.insert(0,"/home/alphabot/gazbot7/src")
import m2_idle_gates as M
from m2_idle_gates import (bars_at, footprint_at, tape_window, last_tick_px, compute_features,
                           efficiency_ratio, price_fire, LOTS, BASE, M2, replay_lot, TK_TS, TK_PX, VPP, FEE)
from gazbot7.deciders import gate_grind, ATR_FLOOR
from dataclasses import replace
import m2_run as R
from bisect import bisect_left

runs=[r for r in R.priceable if r["dir"]=="DN"]
# grind_short = the live grind_long spec, side flipped; same exit_overrides lots
GS_A = replace(LOTS["grind_long"][0], tag="grind_short_A", side="SHORT")
GS_B = replace(LOTS["grind_long"][1], tag="grind_short_B", side="SHORT")
P = BASE["grind_long"].params

for atr_floor in (22.0, 0.0):
    fires=[]; secs=0; fire_secs=0
    for r in runs:
        got=False
        for s in range(r["s"]-600, r["s"]+1):
            if got: break
            bars=bars_at(s)
            if len(bars)<6: continue
            px=last_tick_px(s)
            if px is None: continue
            f=compute_features(bars); w=tape_window(s-60,s-1); nf=w[0]-w[1]; secs+=1
            e=gate_grind(f, tape_net=nf, **P)
            if not (e and e.side=="SHORT"): continue
            fire_secs+=1
            if atr_floor and f.atr < atr_floor: continue
            i=bisect_left(TK_TS, s*1000)
            ems, epx = int(TK_TS[i]), float(TK_PX[i])
            lots=[]
            for spec in (GS_A, GS_B):
                pt,why,ts = replay_lot(spec,"SHORT",ems,epx,f.atr)
                lots.append({"lot":spec.tag,"pt":pt,"usd":pt*VPP-FEE,"why":why,
                             "hold_min":(ts-ems)/60000.0})
            fires.append({"run":r["t"],"move":r["move"],"ceil":r["ceil"],"cluster":r["cluster"],
                          "atr":round(f.atr,1),"er":round(efficiency_ratio(bars),3),
                          "lead_s":r["s"]-s,"usd":sum(l["usd"] for l in lots),"lots":lots})
            got=True
    tot=sum(x["usd"] for x in fires)
    print(f"grind_short  ATR floor {atr_floor:>4.0f}: {len(fires):2d} fires on {len(runs)} DOWN runs "
          f"({fire_secs} of {secs} decision-seconds fired)  ${tot:,.2f}  "
          f"win {sum(1 for x in fires if x['usd']>0)}/{len(fires)}  "
          f"strip3 ${sum(x['usd'] for x in sorted(fires,key=lambda z:-z['usd'])[3:]):,.2f}")
    for x in fires: print("   ",x["run"],x["move"],x["cluster"],"atr",x["atr"],"er",x["er"],
                          "lead",x["lead_s"],"$",round(x["usd"],2),[(l["lot"][-1],round(l["usd"],2),l["why"]) for l in x["lots"]])
    json.dump(fires,open(f"{M2}/grind_short_{int(atr_floor)}.json","w"))
