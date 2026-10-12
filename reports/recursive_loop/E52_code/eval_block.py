import sys,pickle,numpy as np,lightgbm as lgb,fires as FI,sim,rand_ctl,json
name,lo,hi,inst=sys.argv[1:5]
sys.path.insert(0,"/home/alphabot/gazbot7/src")
from gazbot7 import bible
Dn=pickle.load(open("rows_NQ.pkl","rb")); SREF=sim.sref(Dn["meta"]); del Dn
D=pickle.load(open("rows_%s.pkl"%inst,"rb")); SS=pickle.load(open("sess_%s.pkl"%inst,"rb"))["sess"]
meta=D["meta"]; sessd={i:SS[m["day"]] for i,m in enumerate(meta)}
mod=lgb.Booster(model_file="model.txt"); B=FI.load_block(D,lo,hi,mod); sids=B["sids"]
print(name,"sessions",len(sids),"SREF",round(SREF,1))
CELLS=[("model",0.7,20,30),("model",0.7,25,30),("model",0.7,17.5,30),("model",0.7,12.5,35),("control",0.35,15,80),("control",0.35,12.5,35)]
out=[]
for norm in ([True,False] if inst=="MNQ" else [True]):
  for kind,g in sorted({(c[0],c[1]) for c in CELLS}):
    fires=FI.gen_fires(B,B["score"] if kind=="model" else B["dc"],g,sessd)
    cells=[(c[2],c[3]) for c in CELLS if c[0]==kind and c[1]==g]
    fl=sorted((s,t,(1 if sd==1 else -1)) for (s,t,sd,*_) in fires); ff=[(s,t,-d) for s,t,d in fl]
    P=sim.prep(fl,sessd,meta,SREF,norm); PF=sim.prep(ff,sessd,meta,SREF,norm)
    # random
    rng=np.random.default_rng(7); rr={c:[] for c in cells}
    for _ in range(30):
        PR=sim.prep(rand_ctl.random_fires(fires,sessd,meta,rng),sessd,meta,SREF,norm)
        for c in cells:
            d,i=sim.run_cell(PR,c[0],c[1],None); rr[c].append(sim.summarize(d,sids,i)["usd_per_day"])
    for c in cells:
        d,i=sim.run_cell(P,c[0],c[1],None); s=sim.summarize(d,sids,i)
        d2,i2=sim.run_cell(PF,c[0],c[1],None); s2=sim.summarize(d2,sids,i2)
        s.update(kind=kind,g=g,a=c[0],b=c[1],norm=norm,flip=s2["usd_per_day"],rand_mean=float(np.mean(rr[c])),rand_p95=float(np.percentile(rr[c],95)),nfires=len(fires),block=name)
        out.append(s)
pickle.dump(out,open("res_%s.pkl"%name,"wb"))
ch=[x for x in out if x["kind"]=="control" and x["a"]==15 and x["norm"]][0]
cd={k:ch[k] for k in("days_positive","worst_day","daily_sd","usd_per_day")}
for x in out:
    g,why=bible.gate({k:x[k] for k in cd},cd) if not(x["kind"]=="control" and x["a"]==15) else (None,"champion")
    print("%s norm=%d %s g%.2f %s/%s | n=%d tpd %.2f skip %d | $/d %+.1f SD %.0f R %.3f d+ %d/%d worst %+.0f win %.3f hf %.3f hfmean %+.0f | flip %+.1f rand %+.1f p95 %+.1f | gate: %s"%(
      x["block"],x["norm"],x["kind"],x["g"],x["a"],x["b"],x["n"],x["tpd"],x["skipped"],x["usd_per_day"],x["daily_sd"],x["R"],x["days_positive"],x["ndays"],x["worst_day"],x["win"],x["hf_frac"],x["hf_mean"],x["flip"],x["rand_mean"],x["rand_p95"],"champ" if g is None else ("PASS" if g else "fail")))
