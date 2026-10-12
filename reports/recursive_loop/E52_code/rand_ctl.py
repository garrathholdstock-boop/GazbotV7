import numpy as np,sim
def random_fires(fires,sessd,meta,rng):
    cnt={}
    for f in fires: cnt[f[0]]=cnt.get(f[0],0)+1
    out=[]
    for s,n in cnt.items():
        a=sessd[s]; d0=meta[s]["day"]*86400
        idx=np.flatnonzero((a[:,0]>=d0+6*3600)&(a[:,0]<d0+19*3600+30*60))
        if len(idx)==0: continue
        ts=rng.choice(idx,size=min(n,len(idx)),replace=False)
        for t in ts: out.append((s,int(t),int(rng.choice([-1,1]))))
    out.sort(); return out
def random_ctl(fires,cells,sessd,meta,SREF,sids,ndraw=30,seed=7):
    rng=np.random.default_rng(seed); res={c:[] for c in cells}
    for _ in range(ndraw):
        P=sim.prep(random_fires(fires,sessd,meta,rng),sessd,meta,SREF)
        for c in cells:
            d,info=sim.run_cell(P,c[0],c[1],None); res[c].append(sim.summarize(d,sids,info)["usd_per_day"])
    return {c:(float(np.mean(v)),float(np.percentile(v,95))) for c,v in res.items()}
