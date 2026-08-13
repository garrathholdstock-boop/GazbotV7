"""Separability v2 — book-inclusive + NON-LINEAR. Adds L2 book features (far-side depth at signal, at
+M, refill-vs-vanish) to the at-break tape features, and tests THREE separators out-of-sample (honest
time-split): linear tape-only, linear tape+book, and a hand-rolled depth-2 gradient-boosted-tree
(captures interactions LDA can't). If any test AUC clears ~0.60 there's a real combination to build on;
all near 0.50 = the runs are unpredictable from everything we capture, linearly or not.

  PYTHONPATH=src python scripts/afc_separability2.py
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import duckdb
CAP="/home/alphabot/gazbot7/data/capture.db"
SINCE,UNTIL="2026-07-19 22:00:00","2026-07-24 21:00:00"
W,TH,STOP,ARM,TRAIL,HOLD_CAP,ARM_TO,M=60,150.0,20.0,12.0,12.0,1200,300,16.0; FEE, VPP = 1.50, 2.0   # ★2026-08-13 COST FIX — was FEE, VPP = 1.50, 2.0   # ★2026-08-13 COST FIX — was FEE,VPP=5.0,2.0. $5.00 is 3.3x the real
# $1.50 commission. An over-charged fee never looks wrong: it silently kills marginal edges and
# reports a confident NULL. Any conclusion this script produced before today used $5/RT — RE-RUN IT. (unspaced), which is why the
# 08-02 sweep missed it: that pass grepped the SPACED form. $5.00 is 3.3x the real $1.50 commission,
# and an over-charged fee does not look wrong — it silently kills marginal edges and reports a
# confident NULL. Any conclusion this script produced before today was computed at $5/RT: RE-RUN IT.
def auc(sc,lab):
    o=np.argsort(sc); r=np.empty(len(sc)); r[o]=np.arange(1,len(sc)+1)
    p,q=lab.sum(),(1-lab).sum(); return (r[lab==1].sum()-p*(p+1)/2)/(p*q) if p*q else 0.5
def best_split(X,g,idx):
    best=[None,0.0,np.inf,None,None]
    for f in range(X.shape[1]):
        v=X[idx,f]
        for thr in np.unique(np.quantile(v,[.2,.4,.5,.6,.8])):
            L=idx[v<=thr]; R=idx[v>thr]
            if len(L)<15 or len(R)<15: continue
            sse=((g[L]-g[L].mean())**2).sum()+((g[R]-g[R].mean())**2).sum()
            if sse<best[2]: best=[f,thr,sse,L,R]
    return best
def fit_d2(X,g,idx):
    f,thr,_,L,R=best_split(X,g,idx)
    if f is None: return ("leaf",float(g[idx].mean()))
    def child(c):
        cf,cthr,_,cL,cR=best_split(X,g,c)
        if cf is None: return ("leaf",float(g[c].mean()))
        return ("node",cf,cthr,("leaf",float(g[cL].mean())),("leaf",float(g[cR].mean())))
    return ("node",f,thr,child(L),child(R))
def pred(t,X):
    if t[0]=="leaf": return np.full(len(X),t[1])
    _,f,thr,l,r=t; m=X[:,f]<=thr; out=np.empty(len(X)); out[m]=pred(l,X[m]); out[~m]=pred(r,X[~m]); return out
def gbm(Xtr,ytr,Xte,rounds=120,lr=0.1):
    p=np.zeros(len(Xtr)); pt=np.zeros(len(Xte))
    for _ in range(rounds):
        g=ytr-1/(1+np.exp(-p)); t=fit_d2(Xtr,g,np.arange(len(Xtr)))
        p+=lr*pred(t,Xtr); pt+=lr*pred(t,Xte)
    return pt
def main():
    con=duckdb.connect(); con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    lo=int(con.execute(f"SELECT epoch(TIMESTAMP '{SINCE}')").fetchone()[0]); hi=int(con.execute(f"SELECT epoch(TIMESTAMP '{UNTIL}')").fetchone()[0])
    bstart=int(con.execute("SELECT min(ts_ms) FROM c.book WHERE symbol='MNQ'").fetchone()[0])
    fdf=con.execute(f"""SELECT CAST(ts_ms/1000 AS BIGINT) s, SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size ELSE 0 END) net
        FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} GROUP BY s ORDER BY s""").df()
    s0,s1=int(fdf.s.min()),int(fdf.s.max()); flow=np.zeros(s1-s0+1); flow[(fdf.s.values-s0).astype(int)]=fdf.net.values
    csum=np.concatenate([[0],np.cumsum(flow)]); F=np.convolve(flow,np.ones(W),"full")[:len(flow)]; secs=np.arange(s0,s1+1); over=np.abs(F)>=TH
    tkf=con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} ORDER BY ts_ms""").df()
    tts,tpx=tkf.ts_ms.values.astype(np.int64),tkf.price.values.astype(float)
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
    rows=[]; i,n=1,len(secs)
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
            rows.append({"ts":sig_ts,"bt":brk_ts,"d":d,"y":1.0 if walk(ei,d)>0 else 0.0,
                "dtM":dtM,"vel":M/dtM,"ticks":ei-si,"fdur":fdur,"frate":fdur/dtM,"fratio":fdur/(abs(fpre)+1),"fpre":fpre,"pull":pull})
            while i<n and secs[i]<=brk_ts//1000: i+=1
            continue
        i+=1
    df=pd.DataFrame(rows)
    con.execute("CREATE TABLE snap AS SELECT ts_ms, COALESCE(SUM(CASE WHEN side='bid' THEN size END),0) bid, COALESCE(SUM(CASE WHEN side='ask' THEN size END),0) ask FROM c.book WHERE symbol='MNQ' AND level<=3 GROUP BY ts_ms HAVING bid>0 AND ask>0")
    q=pd.DataFrame({"qid":range(len(df)*2),"ts":list(df.ts)+list(df.bt)}); con.register("q",q)
    dep=con.execute("SELECT q.qid,s.bid,s.ask FROM q ASOF JOIN snap s ON s.ts_ms<=q.ts").df(); con.close()
    dm={int(r.qid):(r.bid,r.ask) for r in dep.itertuples()}
    far0=[];far_chg=[];near_chg=[]
    for k,r in df.iterrows():
        s_=dm.get(k); b_=dm.get(k+len(df))
        if not s_ or not b_: far0.append(np.nan);far_chg.append(np.nan);near_chg.append(np.nan); continue
        f0=s_[1] if r.d>0 else s_[0]; f1=b_[1] if r.d>0 else b_[0]; n0=s_[0] if r.d>0 else s_[1]; n1=b_[0] if r.d>0 else b_[1]
        far0.append(f0); far_chg.append((f1-f0)/f0 if f0>0 else np.nan); near_chg.append((n1-n0)/n0 if n0>0 else np.nan)
    df["far0"],df["far_chg"],df["near_chg"]=far0,far_chg,near_chg
    df=df.sort_values("ts").reset_index(drop=True)
    tape=["dtM","vel","ticks","fdur","frate","fratio","fpre","pull"]; book=["far0","far_chg","near_chg"]
    def run(cols,label,nonlin=False,sub=None):
        d=df.dropna(subset=cols) if sub is None else df.loc[sub].dropna(subset=cols)
        cut=int(len(d)*0.6); tr,te=d.iloc[:cut],d.iloc[cut:]
        Xtr,Xte=tr[cols].values,te[cols].values; ytr,yte=tr.y.values,te.y.values
        mu,sd=Xtr.mean(0),Xtr.std(0)+1e-9; Ztr,Zte=(Xtr-mu)/sd,(Xte-mu)/sd
        if nonlin:
            sc=gbm(Ztr,ytr,Zte); a=auc(sc,yte)
        else:
            m1,m0=Ztr[ytr==1].mean(0),Ztr[ytr==0].mean(0)
            Sw=np.cov(Ztr[ytr==1].T)*(ytr.sum()-1)+np.cov(Ztr[ytr==0].T)*((1-ytr).sum()-1)
            w=np.linalg.pinv(np.atleast_2d(Sw)+np.eye(len(cols))*1e-3)@(m1-m0); a=auc(Zte@w,yte)
        print(f"  {label:<40} n={len(d):<5} test AUC = {a:.3f}")
    print(f"SEPARABILITY v2 — {len(df)} breakouts, {df.y.mean()*100:.0f}% profitable. book-covered: {df.far0.notna().sum()}\n")
    run(tape,"linear (LDA) — tape only")
    run(tape+book,"linear (LDA) — tape + BOOK")
    run(tape,"NON-LINEAR (GBM depth-2) — tape only",nonlin=True)
    run(tape+book,"NON-LINEAR (GBM depth-2) — tape + BOOK",nonlin=True)
    print("\n(<=~0.55 = no separable signal even non-linearly with the book — definitive. >0.60 = a real combo.)")
if __name__=="__main__": main()
