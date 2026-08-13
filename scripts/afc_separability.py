"""Definitive separability test: can ANY combination of the AT-BREAK (leading) footprint features
predict whether a breakout is a run or a reverting pop? Fisher linear discriminant, train on the
first 60% (by time), test AUC on the last 40% (honest out-of-sample), plus per-feature AUC. Features
are all measured signal->+M (available at entry): time-to-M, velocity, flow-during, flow-rate,
flow-accel, pullback, 60s pre-flow. AUC ~0.5 on test = the tape genuinely can't tell them apart in
any linear combination; meaningfully >0.5 = a combination worth a real filter.

  PYTHONPATH=src python scripts/afc_separability.py
"""
from __future__ import annotations
import numpy as np
import duckdb
CAP="/home/alphabot/gazbot7/data/capture.db"
SINCE,UNTIL="2026-07-19 22:00:00","2026-07-24 21:00:00"
W,TH,STOP,ARM,TRAIL,HOLD_CAP,ARM_TO,M=60,150.0,20.0,12.0,12.0,1200,300,16.0; FEE, VPP = 1.50, 2.0   # ★2026-08-13 COST FIX — was FEE, VPP = 1.50, 2.0   # ★2026-08-13 COST FIX — was FEE,VPP=5.0,2.0. $5.00 is 3.3x the real
# $1.50 commission. An over-charged fee never looks wrong: it silently kills marginal edges and
# reports a confident NULL. Any conclusion this script produced before today used $5/RT — RE-RUN IT. (unspaced), which is why the
# 08-02 sweep missed it: that pass grepped the SPACED form. $5.00 is 3.3x the real $1.50 commission,
# and an over-charged fee does not look wrong — it silently kills marginal edges and reports a
# confident NULL. Any conclusion this script produced before today was computed at $5/RT: RE-RUN IT.
def main():
    con=duckdb.connect(); con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    lo=int(con.execute(f"SELECT epoch(TIMESTAMP '{SINCE}')").fetchone()[0]); hi=int(con.execute(f"SELECT epoch(TIMESTAMP '{UNTIL}')").fetchone()[0])
    fdf=con.execute(f"""SELECT CAST(ts_ms/1000 AS BIGINT) s, SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size ELSE 0 END) net
        FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} GROUP BY s ORDER BY s""").df()
    s0,s1=int(fdf.s.min()),int(fdf.s.max()); flow=np.zeros(s1-s0+1); flow[(fdf.s.values-s0).astype(int)]=fdf.net.values
    csum=np.concatenate([[0],np.cumsum(flow)]); F=np.convolve(flow,np.ones(W),"full")[:len(flow)]; secs=np.arange(s0,s1+1); over=np.abs(F)>=TH
    tk=con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} ORDER BY ts_ms""").df()
    tts,tpx=tk.ts_ms.values.astype(np.int64),tk.price.values.astype(float); con.close()
    def fdir(a_s,b_s,d): a,b=max(0,a_s-s0),max(0,b_s-s0); return (csum[min(b,len(csum)-1)]-csum[min(a,len(csum)-1)])*d
    def walk(ei,d):
        ep,et,peak,armed,j=tpx[ei],int(tts[ei]),0.0,False,ei+1
        while j<len(tts):
            px,t=tpx[j],int(tts[j]); fav=(px-ep)*d
            if -fav>=STOP: return -STOP*VPP-FEE
            if fav>peak: peak=fav
            if not armed and peak>=ARM: armed=True
            if armed and (peak-fav)>=TRAIL: return fav*VPP-FEE
            if t-et>=HOLD_CAP*1000: return fav*VPP-FEE
            j+=1
        return (tpx[-1]-ep)*d*VPP-FEE
    X,y,ts=[],[],[]; i,n=1,len(secs)
    while i<n:
        if over[i] and not over[i-1]:
            d=1.0 if F[i]>0 else -1.0; si=int(np.searchsorted(tts,(secs[i]+1)*1000,"left"))
            if si>=len(tts): break
            sig_px,sig_ts,ei,j,pull=tpx[si],int(tts[si]),-1,si+1,0.0
            while j<len(tts):
                fav=(tpx[j]-sig_px)*d; pull=max(pull,-fav)
                if fav>=M: ei=j; break
                if fav<=-M or (int(tts[j])-sig_ts)>=ARM_TO*1000: break
                j+=1
            if ei<0:
                tnsec=int(tts[j]//1000) if j<len(tts) else secs[i]
                while i<n and secs[i]<=tnsec: i+=1
                continue
            brk_ts=int(tts[ei]); dtM=max((brk_ts-sig_ts)/1000.0,0.1)
            fdur=fdir(sig_ts//1000,brk_ts//1000+1,d); fpre=fdir(sig_ts//1000-60,sig_ts//1000,d)
            X.append([dtM, M/dtM, ei-si, fdur, fdur/dtM, fdur/(abs(fpre)+1), fpre, pull])
            y.append(1.0 if walk(ei,d)>0 else 0.0); ts.append(sig_ts)
            while i<n and secs[i]<=brk_ts//1000: i+=1
            continue
        i+=1
    X=np.array(X); y=np.array(y); ts=np.array(ts)
    order=np.argsort(ts); X,y=X[order],y[order]
    cut=int(len(X)*0.6); Xtr,ytr,Xte,yte=X[:cut],y[:cut],X[cut:],y[cut:]
    mu,sd=Xtr.mean(0),Xtr.std(0)+1e-9; Ztr,Zte=(Xtr-mu)/sd,(Xte-mu)/sd
    def auc(sc,lab):
        o=np.argsort(sc); r=np.empty(len(sc)); r[o]=np.arange(1,len(sc)+1)
        np_,nn=lab.sum(),(1-lab).sum()
        return (r[lab==1].sum()-np_*(np_+1)/2)/(np_*nn) if np_*nn else 0.5
    # Fisher LDA on train
    m1,m0=Ztr[ytr==1].mean(0),Ztr[ytr==0].mean(0)
    Sw=np.cov(Ztr[ytr==1].T)*(ytr.sum()-1)+np.cov(Ztr[ytr==0].T)*((1-ytr).sum()-1)
    w=np.linalg.pinv(Sw+np.eye(Sw.shape[0])*1e-3)@(m1-m0)
    feats=["time_to_M","velocity","ticks","flow_during","flow_rate","flow/preflow","pre_flow_60s","pullback"]
    print(f"SEPARABILITY — can leading at-break features predict run vs pop? {len(X)} breakouts, "
          f"{y.mean()*100:.0f}% profitable. train {cut}/test {len(Xte)} (time-split, out-of-sample)\n")
    print(f"  LDA (best linear combo)  test AUC = {auc(Zte@w,yte):.3f}   [0.50 = coin-flip / no signal]")
    print(f"  train AUC = {auc(Ztr@w,ytr):.3f}  (train>>test = overfit, no real signal)\n")
    print("  per-feature test AUC (0.50 = useless):")
    for k,f in enumerate(feats):
        a=auc(Zte[:,k],yte); print(f"     {f:>14}  {max(a,1-a):.3f}")
    print("\n(if LDA test AUC <=~0.55 the runs are unpredictable from the tape in ANY linear combination — "
          "the definitive answer. >0.60 = a real multivariate edge to build on. 1wk in-sample-ish, honest split.)")
if __name__=="__main__": main()
