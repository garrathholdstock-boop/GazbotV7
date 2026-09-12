"""RAW GEOMETRY census — how many of the 600 decision-seconds before each run does each
gate's ENTRY CONDITION hold, with every filter, veto and switch removed? This is the
'why-it-misses' number: it separates 'blocked' from 'never asked'."""
import json, sys
from collections import Counter
sys.path.insert(0,"/home/alphabot/gazbot7/scripts"); sys.path.insert(0,"/home/alphabot/gazbot7/src")
from m2_idle_gates import (bars_at, footprint_at, tape_window, gate_fires, last_tick_px,
                           compute_features, efficiency_ratio, GATES, SIDE, M2, atr_blocks)
import m2_run as R
runs=R.priceable
LONGG=[g for g in GATES if SIDE[g]=="LONG"]; SHORTG=[g for g in GATES if SIDE[g]=="SHORT"]
sec_fire=Counter(); sec_eval=Counter(); run_fire=Counter()
per_run={}
for r in runs:
    elig = LONGG if r["dir"]=="UP" else SHORTG
    hit=Counter()
    for s in range(r["s"]-600, r["s"]+1):
        bars=bars_at(s)
        if len(bars)<6: continue
        px=last_tick_px(s)
        if px is None: continue
        f=compute_features(bars); w=tape_window(s-60,s-1); nf=w[0]-w[1]; fp=footprint_at(s)
        for g in elig:
            sec_eval[g]+=1
            if gate_fires(g,f,nf,fp):
                sec_fire[g]+=1; hit[g]+=1
    for g in elig:
        if hit[g]: run_fire[g]+=1
    per_run[r["t"]]={"dir":r["dir"],"move":r["move"],"hits":dict(hit)}
out={"sec_fire":dict(sec_fire),"sec_eval":dict(sec_eval),"run_fire":dict(run_fire),"per_run":per_run,
     "n_runs":len(runs),"nUP":sum(1 for r in runs if r["dir"]=="UP")}
json.dump(out,open(f"{M2}/geom.json","w"))
for g in GATES:
    e=sec_eval.get(g,0); f=sec_fire.get(g,0)
    print(f"{g:18s} geometry TRUE {f:6d} / {e:6d} decision-seconds = {100*f/max(e,1):5.2f}%   "
          f"fired on {run_fire.get(g,0):2d} runs")
