import sys,pickle,numpy as np,lightgbm as lgb,fires as FI,sim,rand_ctl
sys.path.insert(0,"/home/alphabot/gazbot7/src")
from gazbot7 import bible
name,lo,hi,inst=sys.argv[1:5]
Dn=pickle.load(open("rows_NQ.pkl","rb")); SREF=sim.sref(Dn["meta"]); del Dn
D=pickle.load(open("rows_%s.pkl"%inst,"rb")); SS=pickle.load(open("sess_%s.pkl"%inst,"rb"))["sess"]
meta=D["meta"]; sessd={i:SS[m["day"]] for i,m in enumerate(meta)}
mod=lgb.Booster(model_file="model.txt"); B=FI.load_block(D,lo,hi,mod); sids=B["sids"]
CELLS=[("model",0.7,18.0,30),("model",0.7,18.0,25),("model",0.7,19.5,30),("control",0.35,18.0,15),("control",0.35,18.0,12.5)]
def hr(sid,t): return (sessd[sid][t,0]%86400)/3600
out=[]
for norm in ([True,False] if inst=="MNQ" else [True]):
  for kind,g in sorted({(c[0],c[1]) for c in CELLS}):
    f=FI.gen_fires(B,B["score"] if kind=="model" else B["dc"],g,sessd)
    for cut in sorted({c[2] for c in CELLS if c[0]==kind}):
      cells=[c[3] for c in CELLS if c[0]==kind and c[2]==cut]
      ft=[x for x in f if hr(x[0],x[1])<cut]
      fl=sorted((s,t,(1 if sd==1 else -1)) for (s,t,sd,*_) in ft); ff=[(s,t,-d) for s,t,d in fl]
      P=sim.prep(fl,sessd,meta,SREF,norm); PF=sim.prep(ff,sessd,meta,SREF,norm)
      rng=np.random.default_rng(7); rr={a:[] for a in cells}
      for _ in range(30):
        rf=[x for x in rand_ctl.random_fires(ft,sessd,meta,rng) if hr(x[0],x[1])<cut]
        PR=sim.prep(rf,sessd,meta,SREF,norm)
        for a in cells:
          d,i=sim.run_cell_1(PR,a); rr[a].append(sim.summarize(d,sids,i)["usd_per_day"])
      for a in cells:
        d,i=sim.run_cell_1(P,a); s=sim.summarize(d,sids,i)
        d2,i2=sim.run_cell_1(PF,a); s["flip"]=sim.summarize(d2,sids,i2)["usd_per_day"]
        s.update(kind=kind,g=g,cut=cut,a=a,norm=norm,rand_mean=float(np.mean(rr[a])),rand_p95=float(np.percentile(rr[a],95)),block=name); out.append(s)
pickle.dump(out,open("res6_%s.pkl"%name,"wb"))
ch=[x for x in out if x["kind"]=="control" and x["a"]==15 and x["norm"]][0]; cd={k:ch[k] for k in("days_positive","worst_day","daily_sd","usd_per_day")}
print(name,"sessions",len(sids))
for x in out:
    isch=(x["kind"]=="control" and x["a"]==15)
    g=None if isch else bible.gate({k:x[k] for k in cd},cd)
    gs="champ" if isch else ("PASS" if (g[0] if isinstance(g,tuple) else g) else "fail")
    print("%s norm=%d %s g%.2f cut%.1f a%s | tpd %.2f | $/d %+.1f SD %.0f R %.3f d+ %d/%d worst %+.0f win %.3f stuck %.3f stuckmean %+.0f | flip %+.1f rand %+.1f p95 %+.1f | gate %s"%(
      x["block"],x["norm"],x["kind"],x["g"],x["cut"],x["a"],x["tpd"],x["usd_per_day"],x["daily_sd"],x["R"],x["days_positive"],x["ndays"],x["worst_day"],x["win"],x["hf_frac"],x["hf_mean"],x["flip"],x["rand_mean"],x["rand_p95"],gs))
