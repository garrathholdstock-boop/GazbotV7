import pickle,numpy as np,lightgbm as lgb,feat,time
D=pickle.load(open("rows_NQ.pkl","rb")); meta=D["meta"]
date=np.array([m["date"] for m in meta]); sd=date[D["sid"]]
tr=(sd>="2015-01-01")&(sd<="2019-12-31"); es=(sd>="2020-01-01")&(sd<="2020-12-31")
sub=(D["t"]%2==0)
Xtr,ytr=D["F"][tr&sub],D["lab"][tr&sub]; Xes,yes=D["F"][es&sub],D["lab"][es&sub]
print("train rows",len(ytr),"pos",ytr.mean(),"es rows",len(yes))
prm=dict(objective="binary",learning_rate=0.05,num_leaves=31,min_child_samples=2000,feature_fraction=0.8,bagging_fraction=0.7,bagging_freq=1,lambda_l2=10,verbose=-1,num_threads=4)
t=time.time()
m=lgb.train(prm,lgb.Dataset(Xtr,ytr,feature_name=feat.FN),num_boost_round=600,valid_sets=[lgb.Dataset(Xes,yes)],callbacks=[lgb.early_stopping(40),lgb.log_evaluation(50)])
print("best iter",m.best_iteration,time.time()-t)
m.save_model("model.txt")
imp=sorted(zip(m.feature_importance("gain"),feat.FN),reverse=True); print([(n,int(g/1e3)) for g,n in imp[:12]])
