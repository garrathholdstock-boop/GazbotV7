import sys,pickle,numpy as np,lightgbm as lgb,fires as FI,sim,lock,pandas as pd
sys.path.insert(0,"/home/alphabot/gazbot7/src")
from gazbot7 import bible
D=pickle.load(open("rows_NQ.pkl","rb")); SS=pickle.load(open("sess_NQ.pkl","rb"))["sess"]
meta=D["meta"]; sessd={i:SS[m["day"]] for i,m in enumerate(meta)}; SREF=sim.sref(meta)
B=FI.load_block(D,"2021-01-01","2022-12-31",lgb.Booster(model_file="model.txt")); sids=B["sids"]
def hr(sid,t): return (sessd[sid][t,0]%86400)/3600
f=FI.gen_fires(B,B["score"],0.7,sessd); ft=[x for x in f if hr(x[0],x[1])<18.0]
fl=sorted((s,t,(1 if sd==1 else -1)) for (s,t,sd,*_) in ft); ff=[(s,t,-d) for s,t,d in fl]
P=lock.prep_paths(fl,sessd,meta,SREF); PF=lock.prep_paths(ff,sessd,meta,SREF)
shapes=[]
for a in (30,40,60): shapes.append(("S0",a,[(7.5,6)],None,""))
for a in (30,40,60):
  for m2 in (15,20,25):
    for k2 in (10,14,18):
      if k2<m2-2: shapes.append(("S2",a,[(7.5,6),(m2,k2)],None,"m2=%s k2=%s"%(m2,k2)))
  for mt in (12.5,15,20):
    for g in (5,7.5,10): shapes.append(("ST",a,[(7.5,6)],(mt,g,6),"mt=%s g=%s"%(mt,g)))
res=[]
for name,a,lad,tr,tag in shapes:
  d,i=lock.run_shape(P,a,lad,tr); s=sim.summarize(d,sids,i); s["sw"]=i["sw"]; s["locked"]=i["locked"]
  d2,i2=lock.run_shape(PF,a,lad,tr); s["flip"]=sim.summarize(d2,sids,i2)["usd_per_day"]
  s.update(shape=name,a=a,tag=tag); res.append(s)
pickle.dump(res,open("tune8.pkl","wb"))
r=pd.DataFrame(res); pd.set_option("display.width",250)
cols=["shape","a","tag","tpd","sw","hf_frac","usd_per_day","daily_sd","R","days_positive","worst_day","flip"]
b=r[(r["shape"]=="S0")&(r.a==30)].iloc[0]; print("M1 check:",round(b.usd_per_day,2),round(b.R,3),b.days_positive)
cd={q:b[q] for q in("days_positive","worst_day","daily_sd","usd_per_day")}
def gp(x):
  g=bible.gate({q:x[q] for q in cd},cd); return bool(g[0] if isinstance(g,tuple) else g)
r["gate"]=r.apply(gp,axis=1); print("pass gate vs M1:",int(r.gate.sum()),"of",len(r))
print(r[r.tpd>=0.5].sort_values("R",ascending=False)[cols+["gate"]].head(15).round(3).to_string())
print(r[r["shape"]=="S0"][cols].round(3).to_string())
