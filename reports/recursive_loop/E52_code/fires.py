import numpy as np, pickle
def load_block(D,lo,hi,model=None):
    date=np.array([m["date"] for m in D["meta"]]); sd=date[D["sid"]]
    k=(sd>=lo)&(sd<=hi); idx=np.flatnonzero(k)
    o=np.lexsort((D["t"][idx],D["sid"][idx])); idx=idx[o]
    B=dict(sid=D["sid"][idx],side=D["side"][idx],t=D["t"][idx],p=D["p"][idx],lab=D["lab"][idx],room=D["room"][idx],dc=D["dc"][idx],F=D["F"][idx])
    B["score"]=model.predict(B["F"],num_threads=4).astype(np.float32) if model is not None else None
    sids=np.unique(B["sid"]); B["sids"]=sids
    B["bounds"]={int(s):(a,b) for s,a,b in zip(sids,np.searchsorted(B["sid"],sids,"left"),np.searchsorted(B["sid"],sids,"right"))}
    B["lo"],B["hi"]=lo,hi
    return B
def gen_fires(B,score,th,sess,meta_days=None):
    """returns list of fires (sid,t,side,p,lab,lag_min,dc,room,row)"""
    out=[]
    for s in B["sids"]:
        a,b=B["bounds"][int(s)]
        m=np.flatnonzero(score[a:b]>=th)
        if len(m)==0: continue
        m=m+a
        key=B["side"][m].astype(np.int64)*4096+B["p"][m]
        _,fi=np.unique(key,return_index=True); fi=np.sort(fi); ev=m[fi]
        # order by t then higher score
        ev=ev[np.lexsort((-score[ev],B["t"][ev]))]
        d=sess[int(s)]; H,L=d[:,2],d[:,3]
        last_p=-1;last_side=-1
        for r in ev:
            sd=int(B["side"][r]); p=int(B["p"][r])
            if p<=last_p: continue
            if sd==last_side:
                lp=int(lastp_)  # last pivot index
                beyond=(H[p]>H[lp]) if sd==0 else (L[p]<L[lp])
                if not beyond: continue
            out.append((int(s),int(B["t"][r]),sd,p,int(B["lab"][r]),int(B["t"][r])-p,float(B["dc"][r]),float(B["room"][r]),int(r)))
            last_p=p;last_side=sd;lastp_=p
    return out
def summarize(B,fires,nsess):
    n=len(fires)
    if n==0: return dict(fpd=0,prec=np.nan,rec=np.nan,lag=np.nan,lagpt=np.nan,room=np.nan,fast30=np.nan)
    lab=np.array([f[4] for f in fires]); lag=np.array([f[5] for f in fires]); dc=np.array([f[6] for f in fires]); room=np.array([f[7] for f in fires])
    tp=lab==1
    reach=B.setdefault("_reach",len(np.unique(B["sid"][B["lab"]==1].astype(np.int64)*10**8+B["side"][B["lab"]==1].astype(np.int64)*10**6+B["p"][B["lab"]==1])))
    tfires=len({(f[0],f[2],f[3]) for f in fires if f[4]==1})
    return dict(fpd=n/nsess,prec=tp.mean(),rec=tfires/reach,lag=float(np.median(lag[tp])) if tp.any() else np.nan,
                lagpt=float(np.median(dc[tp])) if tp.any() else np.nan,room=float(np.nanmedian(room[tp])) if tp.any() else np.nan,fast30=float((lag[tp]<=30).mean()) if tp.any() else np.nan)
