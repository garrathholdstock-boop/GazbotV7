import sys,pickle,numpy as np,lightgbm as lgb,fires as FI,sim,pandas as pd
sys.path.insert(0,"/home/alphabot/gazbot7/src")
from gazbot7 import bible
D=pickle.load(open("rows_NQ.pkl","rb")); SS=pickle.load(open("sess_NQ.pkl","rb"))["sess"]
meta=D["meta"]; sessd={i:SS[m["day"]] for i,m in enumerate(meta)}; SREF=sim.sref(meta)
mod=lgb.Booster(model_file="model.txt"); B=FI.load_block(D,"2021-01-01","2022-12-31",mod); sids=B["sids"]
CUTS=[19.5,19.0,18.5,18.0,17.0,16.0]; CE=[(12.5,35),(17.5,30),(20,30)]; res=[]
def hr(sid,t): return (sessd[sid][t,0]%86400)/3600
for kind,grid,sc in [("model",[0.6,0.7,0.8],B["score"]),("control",[0.30,0.35,0.40],B["dc"])]:
  for g in grid:
    f=FI.gen_fires(B,sc,g,sessd); fl0=sorted((s,t,(1 if sd==1 else -1)) for (s,t,sd,*_) in f)
    for cut in CUTS:
      fl=[x for x in fl0 if hr(x[0],x[1])<cut]; ff=[(s,t,-d) for s,t,d in fl]
      P=sim.prep(fl,sessd,meta,SREF); PF=sim.prep(ff,sessd,meta,SREF)
      for a,b in CE:
        d,i=sim.run_cell(P,a,b,None); s=sim.summarize(d,sids,i)
        d2,i2=sim.run_cell(PF,a,b,None); s["flip"]=sim.summarize(d2,sids,i2)["usd_per_day"]
        s.update(kind=kind,g=g,cut=cut,a=a,b=b); res.append(s)
pickle.dump(res,open("tune5.pkl","wb"))
r=pd.DataFrame(res); pd.set_option("display.width",250)
cols=["kind","g","cut","a","b","tpd","usd_per_day","daily_sd","R","days_positive","worst_day","hf_frac","flip"]
print(r[(r.g.isin([0.7,0.35]))&(r.a==17.5)][cols].round(3).to_string())
print(r[(r.g.isin([0.7,0.35]))&(r.a==12.5)][cols].round(3).to_string())
ch=r[(r.kind=="model")&(r.g==0.7)&(r.cut==19.5)&(r.a==17.5)].iloc[0]; cd={k:ch[k] for k in("days_positive","worst_day","daily_sd","usd_per_day")}
for kind in ("model","control"):
  sub=r[(r.kind==kind)&(r.tpd>=0.5)]
  gp=[(g,why) for g,why in [(bible.gate({k:x[k] for k in cd},cd),x) for _,x in sub.iterrows()]]
  n=sum(1 for g,_ in gp if (g[0] if isinstance(g,tuple) else g)); print(kind,"gate-pass vs champion:",n,"of",len(sub))
print(r[r.tpd>=0.5].sort_values("R",ascending=False)[cols].head(10).round(3).to_string())
