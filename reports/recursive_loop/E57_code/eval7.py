import sys,pickle,numpy as np,lightgbm as lgb,fires as FI,sim,rand_ctl,lock
sys.path.insert(0,"/home/alphabot/gazbot7/src")
from gazbot7 import bible
name,lo,hi,inst=sys.argv[1:5]
Dn=pickle.load(open("rows_NQ.pkl","rb")); SREF=sim.sref(Dn["meta"]); del Dn
D=pickle.load(open("rows_%s.pkl"%inst,"rb")); SS=pickle.load(open("sess_%s.pkl"%inst,"rb"))["sess"]
meta=D["meta"]; sessd={i:SS[m["day"]] for i,m in enumerate(meta)}
mod=lgb.Booster(model_file="model.txt"); B=FI.load_block(D,lo,hi,mod); sids=B["sids"]
CELLS=[("C1","control",0.35,18.0,15,10,8),("C2","control",0.35,18.0,15,7.5,6),("C3","control",0.35,18.0,15,10,6),("M1","model",0.7,18.0,30,7.5,6)]
def hr(sid,t): return (sessd[sid][t,0]%86400)/3600
out=[]
for norm in ([True,False] if inst=="MNQ" else [True]):
  for kind,g in (("control",0.35),("model",0.7)):
    f=FI.gen_fires(B,B["score"] if kind=="model" else B["dc"],g,sessd); cut=18.0
    ft=[x for x in f if hr(x[0],x[1])<cut]; fl=sorted((s,t,(1 if sd==1 else -1)) for (s,t,sd,*_) in ft); ff=[(s,t,-d) for s,t,d in fl]
    P=lock.prep_paths(fl,sessd,meta,SREF,norm); PF=lock.prep_paths(ff,sessd,meta,SREF,norm)
    cs=[c for c in CELLS if c[1]==kind]; rng=np.random.default_rng(7); rr={c[0]:[] for c in cs}
    for _ in range(30):
      rf=[x for x in rand_ctl.random_fires(ft,sessd,meta,rng) if hr(x[0],x[1])<cut]; PR=lock.prep_paths(rf,sessd,meta,SREF,norm)
      for c in cs:
        d,i=lock.run_lock(PR,c[4],c[5],c[6]); rr[c[0]].append(sim.summarize(d,sids,i)["usd_per_day"])
    for c in cs:
      d,i=lock.run_lock(P,c[4],c[5],c[6]); s=sim.summarize(d,sids,i)
      d0,i0=lock.run_lock(P,c[4]); s0=sim.summarize(d0,sids,i0)
      d2,i2=lock.run_lock(PF,c[4],c[5],c[6]); s["flip"]=sim.summarize(d2,sids,i2)["usd_per_day"]
      gg=bible.gate({k:s[k] for k in("days_positive","worst_day","daily_sd","usd_per_day")},{k:s0[k] for k in("days_positive","worst_day","daily_sd","usd_per_day")})
      s.update(id=c[0],norm=norm,nolock=s0["usd_per_day"],gate=bool(gg[0] if isinstance(gg,tuple) else gg),rand_mean=float(np.mean(rr[c[0]])),rand_p95=float(np.percentile(rr[c[0]],95)),block=name,locked=i["locked"]); out.append(s)
pickle.dump(out,open("res7_%s.pkl"%name,"wb"))
print(name,"sessions",len(sids))
for x in out:
  print("%s norm=%d %s | tpd %.2f | $/d %+.1f (nolock %+.1f) SD %.0f R %.3f d+ %d/%d worst %+.0f win %.3f stuck %.3f | flip %+.1f rand %+.1f p95 %+.1f | gate-vs-nolock %s"%(
    x["block"],x["norm"],x["id"],x["tpd"],x["usd_per_day"],x["nolock"],x["daily_sd"],x["R"],x["days_positive"],x["ndays"],x["worst_day"],x["win"],x["hf_frac"],x["flip"],x["rand_mean"],x["rand_p95"],x["gate"]))
