#!/usr/bin/env python3
"""Pass-2: robustness on the standout looser-climax config + ToD/ATR-ceiling filters."""
from __future__ import annotations
import sys, datetime as dt
sys.path.insert(0,"/home/alphabot/gazbot7/scripts")
import rehab_capitulation_long as R
R.init()

def day(t): return dt.datetime.fromtimestamp(t["entry_ms"]/1000, dt.UTC).strftime("%m-%d")
def robust(tr, label):
    net=sum(t["pnl"] for t in tr); n=len(tr)
    print(R.summarize(tr,label))
    for k in [1,2,3]:
        s=sorted(tr,key=lambda x:x["pnl"],reverse=True)[k:]
        print(f"      strip-best-{k}: ${sum(t['pnl'] for t in s):+.0f} (n={len(s)})")
    days=sorted(set(day(t) for t in tr))
    for dd in days:
        rest=[t for t in tr if day(t)!=dd]
        print(f"      LODO -{dd}: ${sum(t['pnl'] for t in rest):+.0f} (n={len(rest)})")
    # per day
    from collections import defaultdict
    d=defaultdict(list)
    for t in tr: d[day(t)].append(t)
    print("      per-day: "+"  ".join(f"{k}:${sum(x['pnl'] for x in v):+.0f}(n{len(v)})" for k,v in sorted(d.items())))

def seg(tr,fn,title):
    from collections import defaultdict
    d=defaultdict(list)
    for t in tr: d[fn(t)].append(t)
    print(f"   -- {title} --")
    for k in sorted(d): print("      "+R.summarize(d[k],str(k)))

C20=dict(climax_min=2.0,dom_min=0.6,require_flip=True)
C20d7=dict(climax_min=2.0,dom_min=0.7,require_flip=True)
LIVE=dict(climax_min=2.5,dom_min=0.6,require_flip=True)
LOOSE=dict(climax_min=2.5,dom_min=0.6,require_flip=False)

print("############ LOOSE (no flip) scalp 1.0R — the standout n=32 ############")
tr=R.run_sim(LOOSE, dict(kind="scalp",r=1.0))
robust(tr,"LOOSE scalp1.0R")
seg(tr,R.regime,"regime"); seg(tr,R.tod,"tod")
print("\n############ LOOSE scalp 1.0R  ON-only ############")
robust([t for t in R.run_sim(LOOSE,dict(kind="scalp",r=1.0)) if R.tod(t)=="ON"],"LOOSE1.0R ON-only")
print("\n############ LOOSE R-sweep robustness ############")
for r in [0.5,1.0,1.5]:
    robust(R.run_sim(LOOSE,dict(kind="scalp",r=r)),f"LOOSE scalp {r}R")
print("\n############ LOOSE climax2.0 scalp1.0R ############")
robust(R.run_sim(dict(climax_min=2.0,dom_min=0.6,require_flip=False),dict(kind="scalp",r=1.0)),"LOOSE climax2.0 1.0R")


print("############ STANDOUT: climax2.0/dom0.6/flip scalp 2R ############")
tr=R.run_sim(C20, dict(kind="scalp",r=2.0))
robust(tr,"climax2.0/dom0.6 scalp2R")
seg(tr,R.regime,"regime"); seg(tr,R.tod,"tod")
print("\n   dump:")
for t in sorted(tr,key=lambda x:x["entry_ms"]):
    print(f"      {dt.datetime.fromtimestamp(t['entry_ms']/1000,dt.UTC).strftime('%m-%d %H:%M')} {R.tod(t)} "
          f"{R.regime(t):14} atr={t['atr']:4.1f} er={t['er']:.2f} {t['reason']:8} ${t['pnl']:+6.1f}")

print("\n############ climax2.0/dom0.7 scalp 2R ############")
robust(R.run_sim(C20d7,dict(kind="scalp",r=2.0)),"climax2.0/dom0.7 scalp2R")

print("\n############ FILTER: OVERNIGHT-ONLY (bench US 13:30-20:00) ############")
for cfg,nm in [(LIVE,"LIVE2.5"),(C20,"climax2.0")]:
    tr=[t for t in R.run_sim(cfg,dict(kind="scalp",r=2.0)) if R.tod(t)=="ON"]
    robust(tr,f"{nm} ON-only scalp2R")

print("\n############ FILTER: ATR CEILING (fade only atr<=16) ############")
for cfg,nm in [(LIVE,"LIVE2.5"),(C20,"climax2.0")]:
    tr=[t for t in R.run_sim(cfg,dict(kind="scalp",r=2.0)) if t["atr"]<=16]
    robust(tr,f"{nm} atr<=16 scalp2R")

print("\n############ CANDIDATE POLICY: climax2.0 + ON-only + atr<=18, R-sweep ############")
for r in [1.5,2.0,2.5,3.0]:
    tr=[t for t in R.run_sim(C20,dict(kind="scalp",r=r)) if R.tod(t)=="ON" and t["atr"]<=18]
    print("   "+R.summarize(tr,f"policy scalp {r}R"))
tr=[t for t in R.run_sim(C20,dict(kind="scalp",r=2.5)) if R.tod(t)=="ON" and t["atr"]<=18]
robust(tr,"POLICY climax2.0/ON/atr<=18 scalp2.5R")
