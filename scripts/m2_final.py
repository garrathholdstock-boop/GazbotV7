import json,sys
from collections import Counter, defaultdict
sys.path.insert(0,"/home/alphabot/gazbot7/scripts"); sys.path.insert(0,"/home/alphabot/gazbot7/src")
from m2_idle_gates import price_fire, M2, GATES, SIDE
import m2_run as R
res=json.load(open(f"{M2}/results.json")); geom=json.load(open(f"{M2}/geom.json"))
cs=json.load(open("/home/alphabot/gazbot7/reports/friday_v7/sections/census_summary.json"))
top15={x["time"] for x in cs["top15"]}; top25={x["time"] for x in cs["top25"]}
runs=R.priceable; byrun={r["t"]:r for r in runs}
out={}
for arm in ("A_as_live","D_ungated"):
    rows=[]
    for x in res["arms"][arm]["per_run"]:
        for g,f in x["fires"].items():
            # cost-stress: 1 MNQ tick (0.25pt) adverse on entry AND exit
            st=price_fire(g,f["side"],f["s"],f["atr"],slip_pt=0.25)
            rows.append({"run":x["run"],"dir":x["dir"],"move":x["move"],"ceil":x["ceil"],
                         "cluster":x["cluster"],"block":x["block"],"gate":g,"atr":f["atr"],
                         "er":f["er"],"regime":f["regime"],"lead_s":f["lead_s"],
                         "usd":f["usd"],"entry":f["entry_px"],"lots":f["lots"],
                         "usd_stress":st["usd"] if st else None,
                         "cap_pct":100.0*f["usd"]/x["ceil"]})
    tot=sum(r["usd"] for r in rows); n=len(rows)
    wins=sum(1 for r in rows if r["usd"]>0)
    strip=sorted(rows,key=lambda r:-r["usd"])[3:]
    day=defaultdict(lambda:[0,0.0]); reg=defaultdict(lambda:[0,0.0])
    blk=defaultdict(lambda:[0,0.0]); clu=defaultdict(lambda:[0,0.0]); gat=defaultdict(lambda:[0,0.0])
    for r in rows:
        for d,k in ((day,r["run"][:5]),(reg,r["regime"]),(blk,r["block"]),(clu,r["cluster"]),(gat,r["gate"])):
            d[k][0]+=1; d[k][1]+=r["usd"]
    hit15=len({r["run"] for r in rows} & top15); hit25=len({r["run"] for r in rows} & top25)
    out[arm]={"rows":rows,"n":n,"usd":round(tot,2),"win":wins,
              "per_fire":round(tot/n,2) if n else 0,
              "usd_stress":round(sum(r["usd_stress"] for r in rows if r["usd_stress"] is not None),2),
              "strip3":round(sum(r["usd"] for r in strip),2),"strip3_n":len(strip),
              "runs_touched":len({r["run"] for r in rows}),
              "big15":f"{hit15}/{len(top15 & set(byrun))}","big25":f"{hit25}/{len(top25 & set(byrun))}",
              "by_day":{k:[v[0],round(v[1],2)] for k,v in sorted(day.items())},
              "by_regime":{k:[v[0],round(v[1],2)] for k,v in sorted(reg.items())},
              "by_block":{k:[v[0],round(v[1],2)] for k,v in sorted(blk.items())},
              "by_cluster":{k:[v[0],round(v[1],2)] for k,v in sorted(clu.items())},
              "by_gate":{k:[v[0],round(v[1],2)] for k,v in sorted(gat.items())}}
    print(arm,"n",n,"$",round(tot,2),"win",wins,"stress",out[arm]["usd_stress"],
          "strip3",out[arm]["strip3"],"big15",out[arm]["big15"],"big25",out[arm]["big25"])
    print("  day",out[arm]["by_day"]); print("  reg",out[arm]["by_regime"])
    print("  blk",out[arm]["by_block"]); print("  clu",out[arm]["by_cluster"])
# ceiling accounting
out["ceiling"]={"sat_all":cs["ceiling"],"priceable_ceiling":sum(r["ceil"] for r in runs),
                "n_priceable":len(runs),"n_sat":cs["sat_out"],"runs":cs["runs"]}
out["geom"]=geom
json.dump(out,open(f"{M2}/final.json","w"))
print("ceiling on the 61 priceable sat-out runs $",out["ceiling"]["priceable_ceiling"])
