import sys,pickle,numpy as np,lightgbm as lgb,fires as FI,sim,lock,pandas as pd
sys.path.insert(0,"/home/alphabot/gazbot7/src")
from gazbot7 import bible
D=pickle.load(open("rows_NQ.pkl","rb")); SS=pickle.load(open("sess_NQ.pkl","rb"))["sess"]
meta=D["meta"]; sessd={i:SS[m["day"]] for i,m in enumerate(meta)}; SREF=sim.sref(meta)
mod=lgb.Booster(model_file="model.txt"); B=FI.load_block(D,"2021-01-01","2022-12-31",mod); sids=B["sids"]
CELLS=[("model",0.7,18.0,25),("model",0.7,18.0,30),("model",0.7,19.5,30),("control",0.35,18.0,15),("control",0.35,18.0,12.5)]
def hr(sid,t): return (sessd[sid][t,0]%86400)/3600
res=[]
for kind,g in sorted({(c[0],c[1]) for c in CELLS}):
  f=FI.gen_fires(B,B["score"] if kind=="model" else B["dc"],g,sessd)
  for cut in sorted({c[2] for c in CELLS if c[0]==kind}):
    ft=[x for x in f if hr(x[0],x[1])<cut]; fl=sorted((s,t,(1 if sd==1 else -1)) for (s,t,sd,*_) in ft); ff=[(s,t,-d) for s,t,d in fl]
    P=lock.prep_paths(fl,sessd,meta,SREF); PF=lock.prep_paths(ff,sessd,meta,SREF)
    for a in [c[3] for c in CELLS if c[0]==kind and c[2]==cut]:
      # counts first: stuck trades that had reached +m
      cnt={}
      st=[x for x in P if not (np.maximum.accumulate(x[3])>=a+0.25).any()]
      for m in (7.5,10,12.5,15,20): cnt[m]=np.mean([ (x[3].max()>=m+0.25) for x in st]) if st else np.nan
      print(kind,g,cut,a,"stuck n",len(st),"of",len(P),"share that reached +m:",{k:round(v,2) for k,v in cnt.items()},flush=True)
      for m,k in [(None,None)]+[(m,k) for m in (7.5,10,12.5,15,20) for k in (2.5,4,6,8) if k<m and m<a]:
        d,i=lock.run_lock(P,a,m,k); s=sim.summarize(d,sids,i); s["locked"]=i["locked"]
        d2,i2=lock.run_lock(PF,a,m,k); s["flip"]=sim.summarize(d2,sids,i2)["usd_per_day"]
        s.update(kind=kind,g=g,cut=cut,a=a,m=m,k=k); res.append(s)
pickle.dump(res,open("tune7.pkl","wb"))
r=pd.DataFrame(res); pd.set_option("display.width",250)
cols=["kind","cut","a","m","k","tpd","locked","hf_frac","usd_per_day","daily_sd","R","days_positive","worst_day","flip"]
base=r[r.m.isna()]; print(base[cols].round(3).to_string())
lk=r[r.m.notna()]
def gp(x):
  b=base[(base.kind==x.kind)&(base.cut==x.cut)&(base.a==x.a)].iloc[0]; cd={q:b[q] for q in("days_positive","worst_day","daily_sd","usd_per_day")}
  g=bible.gate({q:x[q] for q in cd},cd); return bool(g[0] if isinstance(g,tuple) else g)
lk=lk.assign(gate=lk.apply(gp,axis=1))
print("lock cells passing gate vs no-lock:",lk.gate.sum(),"of",len(lk))
print(lk.sort_values("R",ascending=False)[cols+["gate"]].head(14).round(3).to_string())
for kd in("model","control"): print(kd); print(lk[lk.kind==kd].sort_values("R",ascending=False)[cols+["gate"]].head(4).round(3).to_string())
