import numpy as np, pickle, sys
WINS=(45,90,180,360)
FN=["dclose","dlow","datr","age","logage","spd","mom5","mom15","mom30","runup","runup_age","pre30","ldom","bounce","lowerhigh","t_since_trough","trough_pace",
    "vol_ret","vol_spike","tod","rs","pos","atrs","dcl_over_dlow","trough_frac"]
def zigzag(H,L,T):
    n=len(H); tops=[];bots=[];dirn=0
    hi=H[0];hi_i=0;lo=L[0];lo_i=0
    for i in range(1,n):
        if dirn==0:
            if H[i]>hi: hi=H[i];hi_i=i
            if L[i]<lo: lo=L[i];lo_i=i
            if hi-L[i]>=T: tops.append(hi_i);dirn=-1;lo=L[i];lo_i=i
            elif H[i]-lo>=T: bots.append(lo_i);dirn=1;hi=H[i];hi_i=i
        elif dirn==1:
            if H[i]>hi: hi=H[i];hi_i=i
            elif hi-L[i]>=T: tops.append(hi_i);dirn=-1;lo=L[i];lo_i=i
        else:
            if L[i]<lo: lo=L[i];lo_i=i
            elif H[i]-lo>=T: bots.append(lo_i);dirn=1;hi=H[i];hi_i=i
    return tops,bots
def sptab(x,mode):
    n=len(x); K=max(1,int(np.floor(np.log2(n)))+1); tab=np.zeros((K,n),dtype=np.int32); tab[0]=np.arange(n)
    for k in range(1,K):
        h=1<<(k-1); a=tab[k-1]; b=np.empty(n,dtype=np.int32); b[:n-h]=a[h:]; b[n-h:]=a[n-h:]
        xa=x[a];xb=x[b]
        pick=(xb<xa) if mode=="min" else (xb>xa)
        tab[k]=np.where(pick,b,a)
    return tab
def q(tab,x,a,b,mode):
    ln=b-a+1; k=np.floor(np.log2(ln)).astype(np.int64)
    i1=tab[k,a]; i2=tab[k,b-(1<<k)+1]
    pick=(x[i2]<x[i1]) if mode=="min" else (x[i2]>x[i1])
    return np.where(pick,i2,i1)
def side_rows(H,L,C,V,rel,S,atr,lab_idx,trow):
    n=len(H); tabH=sptab(H,"max"); tabL=sptab(L,"min")
    ps=[]
    for W in WINS:
        a=np.maximum(0,trow-W+1); ps.append(q(tabH,H,a,trow,"max"))
    T=np.tile(trow,len(WINS)); P=np.concatenate(ps)
    key=T.astype(np.int64)*4096+P; _,ui=np.unique(key,return_index=True)
    T=T[ui];P=P[ui]; m=(P<T); T=T[m];P=P[m]
    Hp=H[P]; dclose=(Hp-C[T])/S; m=dclose>=0.03; T=T[m];P=P[m];Hp=Hp[m];dclose=dclose[m]
    if len(T)==0: return None
    qi=q(tabL,L,P+1,T,"min"); tr=L[qi]
    hs_i=q(tabH,H,qi,T,"max"); hs=H[hs_i]
    dlow=(Hp-tr)/S; age=(T-P).astype(float)
    cs=np.concatenate([[0],np.cumsum(V)])
    def mom(k): return (C[np.maximum(T-k,0)]-C[T])/S
    a0=np.maximum(0,P-120); ri=q(tabL,L,a0,P,"min"); runup=(Hp-L[ri])/S
    pre30=(Hp-C[np.maximum(P-30,0)])/S
    pgi=np.full(n,-1); st=[]
    for i in range(n):
        while st and H[st[-1]]<=H[i]: st.pop()
        pgi[i]=st[-1] if st else -1; st.append(i)
    ldom=np.minimum(P-pgi[P],360).astype(float)
    vret=(cs[T+1]-cs[P+1])/np.maximum(T-P,1); a1=np.maximum(0,P-30); vrun=(cs[P+1]-cs[a1])/np.maximum(P+1-a1,1)+1e-9
    a2=np.maximum(0,P-60); vbase=(cs[a1]-cs[a2])/np.maximum(a1-a2,1)+1e-9
    a3=np.maximum(0,P-1); b3=np.minimum(T,P+1); vpk=(cs[b3+1]-cs[a3])/(b3-a3+1)
    rmax=np.maximum.accumulate(H); rmin=np.minimum.accumulate(L)
    rs=(rmax[T]-rmin[T])/S; pos=(Hp-rmin[T])/np.maximum(rmax[T]-rmin[T],1e-9)
    F=np.column_stack([dclose,dlow,(Hp-C[T])/np.maximum(atr[T],1e-9),age,np.log1p(age),dclose/(age+1),mom(5),mom(15),mom(30),runup,(P-ri).astype(float),pre30,ldom,
        (C[T]-tr)/np.maximum(Hp-tr,1e-9),(Hp-hs)/S,(T-qi).astype(float),dlow/np.maximum(qi-P,1),vret/vrun,vpk/vbase,rel[T]/3600.0,rs,pos,atr[T]/S,dclose/np.maximum(dlow,1e-9),(T-qi).astype(float)/np.maximum(age,1)]).astype(np.float32)
    lab=np.isin(P,lab_idx).astype(np.int8)
    return T,P,F,lab,dclose
def session(s,Sd,day):
    ts=s[:,0]; rel=ts-day*86400
    H,L,C,V=s[:,2],s[:,3],s[:,4],np.nan_to_num(s[:,5])
    n=len(H); end=int(np.searchsorted(rel,20*3600+2400))
    tops,bots=zigzag(H[:end],L[:end],0.4*Sd)
    tr=np.maximum(H[1:]-L[1:],np.abs(H[1:]-C[:-1])); tr=np.concatenate([[H[0]-L[0]],tr])
    atr=np.convolve(tr,np.ones(14)/14,mode="full")[:n]; atr[:13]=tr[:13].mean() if n>13 else tr.mean()
    win=np.flatnonzero((rel>=6*3600)&(rel<19.5*3600))
    out=[]
    for side in (0,1):
        if side==0: Hh,Lh,Ch,lab_idx,opp=H,L,C,tops,bots
        else: Hh,Lh,Ch,lab_idx,opp=-L,-H,-C,bots,tops
        r=side_rows(Hh,Lh,Ch,V,rel,Sd,atr,np.array(lab_idx,dtype=np.int64),win)
        if r is None: continue
        T,P,F,lab,dc=r
        room=np.full(len(T),np.nan,dtype=np.float32)
        for j in np.flatnonzero(lab==1):
            nxt=[o for o in opp if o>P[j]]
            if nxt:
                o=nxt[0]; room[j]=(C[T[j]]-L[o]) if side==0 else (H[o]-C[T[j]])
        out.append((np.full(len(T),side,dtype=np.int8),T.astype(np.int32),P.astype(np.int32),F,lab,room,dc.astype(np.float32)))
    if not out: return None
    return [np.concatenate(z) for z in zip(*out)]+[len(tops)+len(bots)]
SESS=None
def init(name):
    global SESS
    SESS=pickle.load(open(f"sess_{name}.pkl","rb"))["sess"]
def do(args):
    name,i,day,Sd=args
    try: r=session(SESS[day],Sd,day)
    except Exception as e: return (i,None,repr(e))
    return (i,r,None)
if __name__=="__main__":
    import multiprocessing as mp
    name=sys.argv[1]; P=pickle.load(open(f"sess_{name}.pkl","rb")); meta=P["meta"]
    jobs=[(name,i,m["day"],m["S"]) for i,m in enumerate(meta) if m["nwin"]>=600 and m["jump"]<=0.015 and not np.isnan(m["S"])]
    with mp.Pool(4,initializer=init,initargs=(name,)) as pool: res=pool.map(do,jobs,chunksize=8)
    rows=[];err=[]
    for (i,r,e) in res:
        if r is None: err.append((i,e)); continue
        side,T,Pv,F,lab,room,dc,npiv=r; k=len(T)
        rows.append((np.full(k,i,dtype=np.int32),side,T,Pv,F,lab,room,dc,npiv))
    D={k:np.concatenate([r[j] for r in rows]) for j,k in enumerate(["sid","side","t","p","F","lab","room","dc"])}
    D["npiv"]={int(r[0][0]):int(r[8]) for r in rows}; D["meta"]=meta; D["err"]=err
    pickle.dump(D,open(f"rows_{name}.pkl","wb"),protocol=4)
    print(name,"sessions used",len(rows),"errors",len(err),err[:2],"rows",len(D["t"]),"pos rate",D["lab"].mean(),"F",D["F"].shape)
