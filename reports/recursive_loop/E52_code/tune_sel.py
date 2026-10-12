import pickle,numpy as np,pandas as pd,lightgbm as lgb,fires as FI,sim,rand_ctl
sys_bible=__import__("sys"); sys_bible.path.insert(0,"/home/alphabot/gazbot7/src")
from gazbot7 import bible
r=pd.DataFrame(pickle.load(open("tune_grid.pkl","rb"))); nf=r[~r.flip]
ok=nf[nf.tpd>=0.5]
champ=ok[ok.kind=="control"].sort_values("R",ascending=False).iloc[0]
print("CHAMPION (best control by R):",champ[["g","a","b","tpd","usd_per_day","daily_sd","R","days_positive","worst_day"]].to_dict())
cd=dict(days_positive=champ.days_positive,worst_day=champ.worst_day,daily_sd=champ.daily_sd,usd_per_day=champ.usd_per_day)
passes=[]
for _,x in ok[ok.kind=="model"].iterrows():
    g,why=bible.gate(dict(days_positive=x.days_positive,worst_day=x.worst_day,daily_sd=x.daily_sd,usd_per_day=x.usd_per_day),cd)
    if g: passes.append(x)
print("model cells passing gate vs champion on TUNE:",len(passes),"of",len(ok[ok.kind=="model"]))
# also the gate result for the top-3 model by R and the 12.5/35 at best theta
top=ok[ok.kind=="model"].sort_values("R",ascending=False).head(3)
for _,x in top.iterrows():
    print("top model",x.g,x.a,x.b,"R %.3f $/d %.1f"%(x.R,x.usd_per_day),bible.gate(dict(days_positive=x.days_positive,worst_day=x.worst_day,daily_sd=x.daily_sd,usd_per_day=x.usd_per_day),cd)[1])
# RANDOM control
D=pickle.load(open("rows_NQ.pkl","rb")); SS=pickle.load(open("sess_NQ.pkl","rb"))["sess"]
meta=D["meta"]; sessd={i:SS[m["day"]] for i,m in enumerate(meta)}; SREF=sim.sref(meta)
mod=lgb.Booster(model_file="model.txt"); B=FI.load_block(D,"2021-01-01","2022-12-31",mod)
for kind,g,sc,cells in [("model",0.7,B["score"],[(20,30),(25,30),(17.5,30),(12.5,35)]),("control",0.35,B["dc"],[(15,80),(17.5,80),(12.5,35)])]:
    f=FI.gen_fires(B,sc,g,sessd); rc=rand_ctl.random_ctl(f,cells,sessd,meta,SREF,B["sids"])
    for c in cells:
        x=r[(r.kind==kind)&(r.g==g)&(r.a==c[0])&(r.b==c[1])]
        print(kind,g,c,"actual $/d %.1f | flip %.1f | random mean %.1f p95 %.1f"%(x[~x.flip].usd_per_day.iloc[0],x[x.flip].usd_per_day.iloc[0],*rc[c]))
