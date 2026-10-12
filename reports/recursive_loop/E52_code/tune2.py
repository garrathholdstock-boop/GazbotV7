import pickle,numpy as np,lightgbm as lgb,fires as FI,sim,pandas as pd
D=pickle.load(open("rows_NQ.pkl","rb")); SS=pickle.load(open("sess_NQ.pkl","rb"))["sess"]
meta=D["meta"]; sessd={i:SS[m["day"]] for i,m in enumerate(meta)}; SREF=sim.sref(meta)
m1=lgb.Booster(model_file="model.txt"); m2=lgb.Booster(model_file="model2.txt")
B=FI.load_block(D,"2021-01-01","2022-12-31",m1); B["p2"]=m2.predict(B["F"],num_threads=4).astype(np.float32); sids=B["sids"]
print("p2 quantiles",np.percentile(B["p2"],[1,10,50,90,99]).round(3))
res=[]
CE=[(12.5,35),(17.5,30),(20,30),(25,30),(20,50),(30,60)]
for th in [0.5,0.6,0.7,0.8]:
  for phi in [None,0.0,0.05,0.10]:
    sc=B["score"] if phi is None else np.where(B["p2"]>=phi,B["score"],-1).astype(np.float32)
    f=FI.gen_fires(B,sc,th,sessd); fl=sorted((s,t,(1 if sd==1 else -1)) for (s,t,sd,*_) in f); ff=[(s,t,-d) for s,t,d in fl]
    P=sim.prep(fl,sessd,meta,SREF); PF=sim.prep(ff,sessd,meta,SREF)
    lab=np.array([x[4] for x in f]) if f else np.array([0])
    for a,b in CE:
        if (a,b) not in [(c) for c in CE]: continue
        d,i=sim.run_cell(P,a,b,None); s=sim.summarize(d,sids,i)
        d2,i2=sim.run_cell(PF,a,b,None); s["flip"]=sim.summarize(d2,sids,i2)["usd_per_day"]
        s.update(th=th,phi=phi,a=a,b=b,nfires=len(f),prec=float(lab.mean()),fpd=len(f)/len(sids)); res.append(s)
    print(th,phi,len(f),"prec %.3f"%lab.mean(),flush=True)
pickle.dump(res,open("tune2.pkl","wb"))
r=pd.DataFrame(res); pd.set_option("display.width",250)
cols=["th","phi","a","b","fpd","prec","n","tpd","usd_per_day","daily_sd","R","days_positive","worst_day","hf_frac","flip"]
print(r[(r.a==17.5)&(r.b==30)][cols].round(3).to_string())
print(r[(r.a==12.5)&(r.b==35)][cols].round(3).to_string())
