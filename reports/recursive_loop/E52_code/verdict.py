import pickle,numpy as np,lightgbm as lgb,fires as FI,sys
D=pickle.load(open("rows_NQ.pkl","rb")); sess=pickle.load(open("sess_NQ.pkl","rb"))["sess"]
meta=D["meta"]; sessd={i:sess[m["day"]] for i,m in enumerate(meta)}
mod=lgb.Booster(model_file="model.txt")
THS=[0.1,0.15,0.2,0.25,0.3,0.35,0.4,0.45,0.5,0.55,0.6,0.65,0.7,0.75,0.8,0.85,0.9]
CS=[0.06,0.08,0.10,0.12,0.15,0.18,0.22,0.26,0.30,0.35,0.40,0.45,0.50]
def curve(B,score,grid):
    ns=len(B["sids"]); R=[]
    for g in grid:
        f=FI.gen_fires(B,score,g,sessd); s=FI.summarize(B,f,ns); R.append((s["prec"],s["lag"],s["rec"],s["fpd"]))
    R=np.array(R,float); o=np.argsort(R[:,0]); return R[o]
def at(R,p):
    x=R[:,0]; 
    if p<x.min() or p>x.max(): return (np.nan,np.nan)
    return (np.interp(p,x,R[:,1]),np.interp(p,x,R[:,2]))
for name,lo,hi in [("TUNE","2021-01-01","2022-12-31"),("CONFIRM-A","2023-01-01","2024-08-11"),("CONFIRM-B","2024-08-12","2025-07-24")]:
    B=FI.load_block(D,lo,hi,mod); M=curve(B,B["score"],THS); C=curve(B,B["dc"],CS)
    print(name,"sessions",len(B["sids"]))
    ok=0
    for p in (0.5,0.6,0.7):
        ml,mr=at(M,p); cl,cr=at(C,p); ratio=ml/cl; good=(ratio<=0.8) and abs(mr-cr)<=0.05; ok+=good
        print("  prec %.1f model lag %.1f rec %.3f | control lag %.1f rec %.3f | ratio %.2f %s"%(p,ml,mr,cl,cr,ratio,"ok" if good else "no"))
    print("  VERDICT",name,"BETTER" if ok>=2 else "NOT BETTER",flush=True)
