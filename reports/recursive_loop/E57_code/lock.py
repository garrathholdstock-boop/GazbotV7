import numpy as np
from sim import SLIP,FEE,PTV
LSLIP=SLIP
def prep_paths(fl,sess,meta,SREF,norm=True):
    out=[]
    for sid,t,d in fl:
        arr=sess[sid]; m=meta[sid]; k=SREF/m["S"] if norm else 1.0
        end=int(np.searchsorted(arr[:,0],m["day"]*86400+20*3600+40*60,"left"))-1
        if t>=end: continue
        C=arr[:,4]*k; e=C[t]+d*SLIP
        H=arr[t+1:end+1,2]*k; L=arr[t+1:end+1,3]*k
        if d>0: fh=H-e; fl_=L-e
        else: fh=e-L; fl_=e-H
        flat=(C[end]-e)*d-SLIP
        out.append((sid,t,end,fh,fl_,flat))
    return out
def run_lock(P,a,m=None,k=None):
    daily={}; busy={}; n=0; skipped=0; hf=0; hfp=0.0; wins=0; hold=0.0; locked=0
    for sid,t,end,fh,fl_,flat in P:
        if t<=busy.get(sid,-1): skipped+=1; continue
        cm=np.maximum.accumulate(fh)
        j=int(np.searchsorted(cm,a+SLIP,"left")); j=j if j<len(cm) else None
        pnl=None; x=None
        if m is not None:
            i0=int(np.searchsorted(cm,m+SLIP,"left"))
            if i0<len(cm):
                tail=fl_[i0+1:]
                hit=np.flatnonzero(tail<=k)
                L=(i0+1+int(hit[0])) if len(hit) else None
                if L is not None and (j is None or j>=L+0) and not (j is not None and j<=i0):
                    pnl=k-LSLIP; x=t+1+L; locked+=1
        if pnl is None:
            if j is not None: pnl=a; x=t+1+j
            else: pnl=flat; x=end
        stuck=(pnl==flat and j is None and x==end)
        usd=pnl*PTV-FEE; busy[sid]=x
        daily[sid]=daily.get(sid,0.0)+usd; n+=1; wins+=usd>0; hold+=x-t
        if stuck: hf+=1; hfp+=usd
    return daily,dict(n=n,skipped=skipped,hf=hf,hfp=hfp,wins=wins,hold=hold,locked=locked)
