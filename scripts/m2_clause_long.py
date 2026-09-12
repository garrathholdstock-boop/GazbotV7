"""CLAUSE-LEVEL autopsy for the three LONG gates on the UP sat-out runs."""
import json,sys
from collections import Counter
sys.path.insert(0,"/home/alphabot/gazbot7/scripts"); sys.path.insert(0,"/home/alphabot/gazbot7/src")
from m2_idle_gates import bars_at, footprint_at, tape_window, last_tick_px, compute_features, M2
import m2_run as R
runs=[r for r in R.priceable if r["dir"]=="UP"]
g=Counter(); cp=Counter(); av=Counter(); n=0
SLOPE_MIN, EXT_LO, EXT_HI = 0.4, 0.3, 4.0                # grind_long live params (fast_slope)
CLIMAX, DOM = 2.5, 0.6                                   # capitulation_long live params
THR, AMP = 1.5, 0.0004                                   # abs_veto_long live params
for r in runs:
    for s in range(r["s"]-600, r["s"]+1):
        bars=bars_at(s)
        if len(bars)<6: continue
        if last_tick_px(s) is None: continue
        f=compute_features(bars); fp=footprint_at(s); n+=1
        w=tape_window(s-60,s-1); nf=w[0]-w[1]
        # grind_long (LONG leg): fast slope >= 0.4 AND 0.3 <= ext <= 4.0 AND tape_net >= 0
        if f.vwap_slope_fast < SLOPE_MIN:  g[f"1 fast VWAP slope < {SLOPE_MIN} (no established up-trend)"]+=1
        elif f.ext_atr < EXT_LO:           g[f"2 ext < {EXT_LO} ATR (price not yet riding above VWAP)"]+=1
        elif f.ext_atr > EXT_HI:           g[f"3 ext > {EXT_HI} ATR (already stretched)"]+=1
        elif nf < 0.0:                     g["4 tape_net < 0 (net sellers)"]+=1
        else:                              g["FIRES"]+=1
        # capitulation_long: sell-climax + price down + buyers flipping
        tot=fp["cap_sell"]+fp["cap_buy"]
        if fp["cap_base"]<=0 or tot<=0:    cp["0 no tape"]+=1
        elif fp["cap_dpx"]>=0:             cp["1 price not falling over the 20s window"]+=1
        elif fp["cap_sell"]/fp["cap_base"]<CLIMAX: cp[f"2 sell volume < {CLIMAX}x its 180s baseline (no climax)"]+=1
        elif fp["cap_sell"]/tot<DOM:       cp[f"3 sells < {DOM:.0%} of flow (not one-sided)"]+=1
        elif not fp["cap_flip"]:           cp["4 no flip (buyers not taking over in the last 10s)"]+=1
        else:                              cp["FIRES"]+=1
        # abs_veto_long raw thrust: net_atr_5 >= 1.5 AND atr_pct >= 0.0004 AND vol surge
        if f.net_atr_5 < THR:              av[f"1 5-bar net move < {THR} ATR (no thrust)"]+=1
        elif f.atr_pct < AMP:              av[f"2 amp_floor: ATR < {AMP:.2%} of price (thin tape)"]+=1
        elif not f.vol_surge:              av["3 no volume surge on the latest bar"]+=1
        else:                              av["FIRES"]+=1
for name,c in (("grind_long",g),("capitulation_long",cp),("abs_veto_long",av)):
    print(f"\n{name} — first failing clause over {n:,} UP decision-seconds")
    for k,v in sorted(c.items()): print(f"   {k:60s} {v:7,d}  {100*v/n:6.2f}%")
json.dump({"grind_long":dict(g),"capitulation_long":dict(cp),"abs_veto_long":dict(av),"n":n},
          open(f"{M2}/clause_long.json","w"))
