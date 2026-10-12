import sys,pickle,numpy as np,lightgbm as lgb,fires as FI,sim,rand_ctl,lock
sys.path.insert(0,"/home/alphabot/gazbot7/src")
from gazbot7 import bible
name,lo,hi,inst=sys.argv[1:5]
Dn=pickle.load(open("rows_NQ.pkl","rb")); SREF=sim.sref(Dn["meta"]); del Dn
D=pickle.load(open("rows_%s.pkl"%inst,"rb")); SS=pickle.load(open("sess_%s.pkl"%inst,"rb"))["sess"]
meta=D["meta"]; sessd={i:SS[m["day"]] for i,m in enumerate(meta)}
mod=lgb.Booster(model_file="model.txt"); B=FI.load_block(D,lo,hi,mod); sids=B["sids"]
L1=[(7.5,6)]
CELLS=[("M1","model",30,L1,None),("F1","model",60,L1+[(15,10)],None),("F2","model",60,L1+[(20,10)],None),("F3","model",60,L1+[(25,10)],None),
       ("T1","model",60,L1,(12.5,5,6)),("C2","control",15,L1,None),("CT","control",15,L1,(12.5,5,6))]
def hr(sid,t): return (sessd[sid][t,0]%86400)/3600
KEYS=("days_positive","worst_day","daily_sd","usd_per_day")
out=[]
for norm in ([True,False] if inst=="MNQ" else [True]):
  M1ref={}
  for kind,g in (("model",0.7),("control",0.35)):
    f=FI.gen_fires(B,B["score"] if kind=="model" else B["dc"],g,sessd)
    ft=[x for x in f if hr(x[0],x[1])<18.0]; fl=sorted((s,t,(1 if sd==1 else -1)) for (s,t,sd,*_) in ft); ff=[(s,t,-d) for s,t,d in fl]
    P=lock.prep_paths(fl,sessd,meta,SREF,norm); PF=lock.prep_paths(ff,sessd,meta,SREF,norm)
    cs=[c for c in CELLS if c[1]==kind]; rng=np.random.default_rng(7); rr={c[0]:[] for c in cs}
    for _ in range(30):
      rf=[x for x in rand_ctl.random_fires(ft,sessd,meta,rng) if hr(x[0],x[1])<18.0]; PR=lock.prep_paths(rf,sessd,meta,SREF,norm)
      for c in cs:
        d,i=lock.run_shape(PR,c[2],c[3],c[4]); rr[c[0]].append(sim.summarize(d,sids,i)["usd_per_day"])
    for c in cs:
      lock.LSLIP=sim.SLIP
      d,i=lock.run_shape(P,c[2],c[3],c[4]); s=sim.summarize(d,sids,i)
      d2,i2=lock.run_shape(PF,c[2],c[3],c[4]); s["flip"]=sim.summarize(d2,sids,i2)["usd_per_day"]
      lock.LSLIP=2.0
      d3,i3=lock.run_shape(P,c[2],c[3],c[4]); s["stress2"]=sim.summarize(d3,sids,i3)["usd_per_day"]
      lock.LSLIP=sim.SLIP
      s.update(id=c[0],norm=norm,block=name,rand_mean=float(np.mean(rr[c[0]])),rand_p95=float(np.percentile(rr[c[0]],95)),sw=i["sw"]); out.append(s)
  m1=[x for x in out if x["id"]=="M1" and x["norm"]==norm][0]
  for x in out:
    if x["norm"]==norm:
      gg=bible.gate({k:x[k] for k in KEYS},{k:m1[k] for k in KEYS}); x["gate_vs_M1"]=bool(gg[0] if isinstance(gg,tuple) else gg)
pickle.dump(out,open("res8_%s.pkl"%name,"wb"))
print(name,"sessions",len(sids))
for x in out:
  print("%s norm=%d %-2s | tpd %.2f | $/d %+.1f stress2 %+.1f SD %.0f R %.3f d+ %d/%d worst %+.0f stuck %.3f | flip %+.1f rand %+.1f p95 %+.1f | gate-vs-M1 %s"%(
    x["block"],x["norm"],x["id"],x["tpd"],x["usd_per_day"],x["stress2"],x["daily_sd"],x["R"],x["days_positive"],x["ndays"],x["worst_day"],x["hf_frac"],x["flip"],x["rand_mean"],x["rand_p95"],x["gate_vs_M1"]))
