import sys,pickle,pandas as pd
sys.path.insert(0,"/home/alphabot/gazbot7/src")
from gazbot7 import bible
r=pd.DataFrame(pickle.load(open("tune8.pkl","rb")))
b=r[(r["shape"]=="S0")&(r.a==30)].iloc[0]
cd={q:b[q] for q in("days_positive","worst_day","daily_sd","usd_per_day")}
def gp(x):
  g=bible.gate({q:x[q] for q in cd},cd); return bool(g[0] if isinstance(g,tuple) else g)
r["gate"]=r.apply(gp,axis=1)
pd.set_option("display.width",250)
cols=["shape","a","tag","tpd","sw","hf_frac","usd_per_day","daily_sd","R","days_positive","worst_day","flip"]
print(r[r.gate].sort_values("R",ascending=False)[cols].round(3).to_string())
print("M1 sw",b.sw,"locked",b.locked)
print(r[(r["shape"]=="S2")].sort_values("R",ascending=False)[cols+["gate"]].head(6).round(3).to_string())
