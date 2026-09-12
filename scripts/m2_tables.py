import json, sys, math
from collections import Counter, defaultdict
sys.path.insert(0,"/home/alphabot/gazbot7/scripts"); sys.path.insert(0,"/home/alphabot/gazbot7/src")
M2="/home/alphabot/gazbot7/reports/friday_v7/sections/m2"
res=json.load(open(f"{M2}/results.json")); ex=json.load(open(f"{M2}/extra.json"))
import m2_run as R
runs=R.priceable
nUP=sum(1 for r in runs if r["dir"]=="UP"); nDN=len(runs)-nUP
print("UP",nUP,"DN",nDN,"total",len(runs))
LONGG=["grind_long","capitulation_long","abs_veto_long"]; SHORTG=["rgv_short","exhaustion_short","abs_veto_short"]
elig_n={g:(nUP if g in LONGG else nDN) for g in LONGG+SHORTG}
print("eligible windows per gate:",elig_n)

def binom_p(k,n,p):
    # P(X >= k) upper tail
    from math import comb
    return sum(comb(n,i)*p**i*(1-p)**(n-i) for i in range(k,n+1))

for arm in ("A_as_live","D_ungated"):
    a=res["arms"][arm]
    print(f"\n===== {arm} =====")
    tot=0.0; rows=[]
    for x in a["per_run"]:
        for g,f in x["fires"].items():
            tot+=f["usd"]
            rows.append((x["run"],x["dir"],x["move"],x["ceil"],x["cluster"],x["block"],g,
                         round(f["atr"],1),round(f["er"],3),f["regime"],f["lead_s"],
                         round(f["usd"],2),[ (l["lot"][-1],round(l["usd"],2),l["why"],round(l["hold_min"],1)) for l in f["lots"]]))
    for r in sorted(rows): print(r)
    print("TOTAL $",round(tot,2),"fires",len(rows))
    pl=ex["placebo"]["as_live" if arm=="A_as_live" else "ungated"]
    print("--- placebo vs pre-run rate ---")
    for g in LONGG+SHORTG:
        k=sum(1 for r in rows if r[6]==g); n=elig_n[g]
        pk=pl["fires"].get(g,0); pn=pl["windows"]
        p=pk/pn if pn else 0
        pv=binom_p(k,n,p) if p>0 else (1.0 if k==0 else 0.0)
        print(f"  {g:18s} pre-run {k:2d}/{n:2d} = {100*k/n:5.1f}%   placebo {pk:3d}/{pn} = {100*p:5.1f}%   P(X>={k}) = {pv:.3f}")
    print("  placebo $:",pl["usd"],"tot",round(sum(pl["usd"].values()),2))
