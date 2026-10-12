import pickle,numpy as np,lightgbm as lgb
D=pickle.load(open("rows_NQ.pkl","rb")); SS=pickle.load(open("sess_NQ.pkl","rb"))["sess"]; meta=D["meta"]
n=len(D["t"]); y=np.full(n,np.nan,np.float32)
sid=D["sid"]; t=D["t"]; side=D["side"]
for s in np.unique(sid):
    a,b=np.searchsorted(sid,s,"left"),np.searchsorted(sid,s,"right")
    arr=SS[meta[s]["day"]]; ts=arr[:,0]; d0=meta[s]["day"]*86400
    end=int(np.searchsorted(ts,d0+20*3600+40*60))-1
    S=meta[s]["S"]
    if not (S==S): continue
    tt=t[a:b]; ok=tt<end
    d=np.where(side[a:b]==1,1.0,-1.0)
    v=(arr[end,4]-arr[np.minimum(tt,end),4])*d/S
    v[~ok]=np.nan
    y[a:b]=np.clip(v,-1,1)
np.save("y2.npy",y); print("label done",np.nanmean(y),np.nanstd(y))
date=np.array([m["date"] for m in meta])[sid]
okr=~np.isnan(y)
tr=okr&(t%2==0)&(date>="2015-01-01")&(date<="2019-12-31")
va=okr&(date>="2020-01-01")&(date<="2020-12-31")
P=dict(objective="regression",learning_rate=0.05,num_leaves=31,min_child_samples=2000,feature_fraction=0.8,bagging_fraction=0.7,bagging_freq=1,lambda_l2=10,num_threads=4,verbose=-1)
dt=lgb.Dataset(D["F"][tr],y[tr]); dv=lgb.Dataset(D["F"][va],y[va])
m=lgb.train(P,dt,600,valid_sets=[dv],callbacks=[lgb.early_stopping(40),lgb.log_evaluation(50)])
m.save_model("model2.txt"); print("best",m.best_iteration)
p=m.predict(D["F"][va]); print("val corr",np.corrcoef(p,y[va])[0,1],"pred sd",p.std())
