import pickle,numpy as np,lightgbm as lgb,fires as FI,sim,json,sys
D=pickle.load(open("rows_NQ.pkl","rb")); SS=pickle.load(open("sess_NQ.pkl","rb"))["sess"]
meta=D["meta"]; sessd={i:SS[m["day"]] for i,m in enumerate(meta)}
SREF=sim.sref(meta); print("SREF",SREF)
mod=lgb.Booster(model_file="model.txt")
B=FI.load_block(D,"2021-01-01","2022-12-31",mod); sids=B["sids"]
res=[]
def fl(fires,flip=False):
    f=[(s,t,(1 if sd==1 else -1)*(-1 if flip else 1)) for (s,t,sd,*_) in fires]
    f.sort(); return f
for kind,grid,score in [("model",[0.3,0.4,0.5,0.6,0.7,0.8,0.9],B["score"]),("control",[0.15,0.18,0.22,0.26,0.30,0.35,0.40],B["dc"])]:
    for g in grid:
        fires=FI.gen_fires(B,score,g,sessd)
        for flip in (False,True):
            P=sim.prep(fl(fires,flip),sessd,meta,SREF)
            for a,b in sim.CELLS:
                d,info=sim.run_cell(P,a,b,None); r=sim.summarize(d,sids,info)
                r.update(kind=kind,g=g,a=a,b=b,flip=flip,nfires=len(fires)); res.append(r)
        print(kind,g,"done",len(fires),flush=True)
pickle.dump(res,open("tune_grid.pkl","wb"))
