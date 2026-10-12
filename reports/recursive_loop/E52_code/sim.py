import numpy as np
SLIP=0.25; FEE=1.50; PTV=2.0; BIG=10**9
A_GRID=[5,7.5,10,12.5,15,17.5,20,25]
B_GRID=[20,25,30,35,40,50,60,80,100,150]
LEVELS=sorted(set(A_GRID)|set(B_GRID))
CELLS=[(a,b) for a in A_GRID for b in B_GRID if b>a]
def sref(meta):
    v=[m["S"] for m in meta if "2025-01-30"<=m["date"]<="2025-07-24" and m["S"]==m["S"]]
    return float(np.mean(v))
def prep(fl,sess,meta,SREF,norm=True):
    """fl: list of (sid,t,dir). returns dict of arrays per fire."""
    out=[]
    for sid,t,d in fl:
        arr=sess[sid]; m=meta[sid]
        k=SREF/m["S"] if norm else 1.0
        day0=m["day"]*86400
        ts=arr[:,0]
        end=int(np.searchsorted(ts,day0+20*3600+40*60,"left"))-1   # last bar opening before 20:40Z
        if t>=end: continue
        C=arr[:,4]*k; e=C[t]+d*SLIP
        if d>0: fe=arr[t+1:end+1,2]*k-e
        else: fe=e-arr[t+1:end+1,3]*k
        mx=np.maximum.accumulate(fe)
        fill=np.searchsorted(mx,np.array(LEVELS)+SLIP,"left")   # first idx with mx>=x+slip
        fill=np.where(fill<len(mx),fill+t+1,BIG)
        flat=(C[end]-e)*d-SLIP
        out.append((sid,t,end,fill,flat))
    return out
def run_cell(P,a,b,ndays_by_sid):
    ia=LEVELS.index(a); ib=LEVELS.index(b)
    daily={}; busy={}; n=0; skipped=0; hf=0; hfp=0.0; wins=0; hold=0.0
    for sid,t,end,fill,flat in P:      # P sorted by (sid,t)
        if t<=busy.get(sid,-1): skipped+=1; continue
        fa=fill[ia]; fb=fill[ib]
        pa=a if fa<BIG else flat; pb=b if fb<BIG else flat
        xa=fa if fa<BIG else end; xb=fb if fb<BIG else end
        busy[sid]=max(xa,xb)
        usd=(pa+pb)*PTV-2*FEE
        daily[sid]=daily.get(sid,0.0)+usd
        n+=1; wins+=usd>0; hold+=max(xa,xb)-t
        if fb>=BIG: hf+=1; hfp+=usd
    return daily,dict(n=n,skipped=skipped,hf=hf,hfp=hfp,wins=wins,hold=hold)
def stats(daily,nd,info):
    v=np.zeros(nd); 
    for i,(s,u) in enumerate(daily.items()): pass
    return v
def summarize(daily,sids,info):
    v=np.array([daily.get(int(s),0.0) for s in sids])
    nd=len(v); n=info["n"]
    sd=v.std(ddof=1) if nd>1 else np.nan; m=v.mean()
    return dict(n=n,tpd=n/nd,skipped=info["skipped"],usd_per_day=m,daily_sd=sd,days_positive=int((v>0).sum()),worst_day=float(v.min()),
                R=m/sd if sd>0 else np.nan,win=info["wins"]/n if n else np.nan,hf_frac=info["hf"]/n if n else np.nan,
                hf_mean=info["hfp"]/info["hf"] if info["hf"] else np.nan,hold=info["hold"]/n if n else np.nan,ndays=nd,total=v.sum(),
                neg_days=int((v<0).sum()))
