import pickle,numpy as np,lightgbm as lgb,fires as FI,sim,rand_ctl,pandas as pd
D=pickle.load(open("rows_NQ.pkl","rb")); SS=pickle.load(open("sess_NQ.pkl","rb"))["sess"]
meta=D["meta"]; sessd={i:SS[m["day"]] for i,m in enumerate(meta)}; SREF=sim.sref(meta)
mod=lgb.Booster(model_file="model.txt"); B=FI.load_block(D,"2021-01-01","2022-12-31",mod); sids=B["sids"]
CE=[(12.5,35),(17.5,30),(20,30)]; res=[]
for kind,grid,sc in [("model",[0.6,0.7,0.8],B["score"]),("control",[0.30,0.35,0.40],B["dc"])]:
  for g in grid:
    f=FI.gen_fires(B,sc,g,sessd); fl=sorted((s,t,(1 if sd==1 else -1)) for (s,t,sd,*_) in f); ff=[(s,t,-d) for s,t,d in fl]
    P=sim.prep(fl,sessd,meta,SREF); PF=sim.prep(ff,sessd,meta,SREF)
    for K in (1,2,3,4):
      for a,b in CE:
        d,i=sim.run_cell_k(P,a,b,K); s=sim.summarize(d,sids,i); s["peak"]=i["peak"]
        d2,i2=sim.run_cell_k(PF,a,b,K); s["flip"]=sim.summarize(d2,sids,i2)["usd_per_day"]
        s.update(kind=kind,g=g,K=K,a=a,b=b); res.append(s)
    print(kind,g,"done",flush=True)
pickle.dump(res,open("tune4.pkl","wb"))
r=pd.DataFrame(res); pd.set_option("display.width",250)
cols=["kind","g","K","a","b","tpd","skipped","peak","usd_per_day","daily_sd","R","days_positive","worst_day","hf_frac","flip"]
print(r[(r.kind=="model")&(r.g==0.7)][cols].round(3).to_string())
print(r[r.tpd>=0.5].sort_values("R",ascending=False)[cols].head(12).round(3).to_string())
