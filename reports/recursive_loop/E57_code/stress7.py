import sys,pickle,numpy as np,lightgbm as lgb,fires as FI,sim,lock
Dn=pickle.load(open("rows_NQ.pkl","rb")); SREF=sim.sref(Dn["meta"]); del Dn
def hr(sessd,sid,t): return (sessd[sid][t,0]%86400)/3600
tot={}
for name,lo,hi,inst in [("TUNE","2021-01-01","2022-12-31","NQ"),("CONFIRM_A","2023-01-01","2024-08-11","NQ"),("CONFIRM_B","2024-08-12","2025-07-24","NQ"),("SEALED","2025-09-15","2026-03-08","MNQ")]:
  D=pickle.load(open("rows_%s.pkl"%inst,"rb")); SS=pickle.load(open("sess_%s.pkl"%inst,"rb"))["sess"]
  meta=D["meta"]; sessd={i:SS[m["day"]] for i,m in enumerate(meta)}
  B=FI.load_block(D,lo,hi,lgb.Booster(model_file="model.txt")); sids=B["sids"]
  f=FI.gen_fires(B,B["score"],0.7,sessd); ft=[x for x in f if hr(sessd,x[0],x[1])<18.0]
  fl=sorted((s,t,(1 if sd==1 else -1)) for (s,t,sd,*_) in ft); P=lock.prep_paths(fl,sessd,meta,SREF)
  row=[]
  for ls in (0.25,1.0,2.0,3.0):
    lock.LSLIP=ls; d,i=lock.run_lock(P,30,7.5,6); s=sim.summarize(d,sids,i); row.append((ls,round(s["usd_per_day"],1),s["days_positive"],s["ndays"]))
    tot.setdefault(ls,[]).append((s["usd_per_day"],s["ndays"]))
  print(name,row,flush=True)
for ls,v in tot.items():
  v=v[1:]; print("pooled later blocks, lock slip",ls,"=> $/day",round(sum(a*n for a,n in v)/sum(n for a,n in v),1))
