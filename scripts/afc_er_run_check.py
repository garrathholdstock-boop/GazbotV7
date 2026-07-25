import datetime as dt, re
import duckdb, numpy as np
CAP="/home/alphabot/gazbot7/data/capture.db"; CENSUS="/home/alphabot/gazbot7/reports/friday_v7/sections/census_stdout.txt"
runs=[]
for ln in open(CENSUS):
    if ln.rstrip().endswith("FLOW-LED"):
        g=re.match(r"^(\d\d-\d\d \d\d:\d\d)\s+(UP|DN)\s+([+-]?\d+)",ln)
        if g:
            ep=int(dt.datetime.strptime("2026-"+g.group(1),"%Y-%m-%d %H:%M").replace(tzinfo=dt.UTC).timestamp())
            runs.append({"tm":g.group(1),"d":g.group(2),"mv":int(g.group(3)),"ep":ep})
con=duckdb.connect(); con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
lo=min(r["ep"] for r in runs)-3600; hi=max(r["ep"] for r in runs)+600
bdf=con.execute(f"""WITH b AS (SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl FROM c.bars
  WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={lo-2400} AND bar_ts<{hi} GROUP BY 1) SELECT m,cl FROM b ORDER BY m""").df()
con.close()
mins=bdf.m.values.astype(np.int64); cls=bdf.cl.values.astype(float); idx={int(m):i for i,m in enumerate(mins)}
def er(ep):
    i=idx.get(int(ep-ep%60))
    if i is None or i<30: return None
    seg=cls[i-30:i+1]; tot=np.abs(np.diff(seg)).sum()
    return abs(seg[-1]-seg[0])/tot if tot>0 else 0.0
bands={"[0.0-0.1) chop":0,"[0.1-0.2) chop":0,"[0.2+) trend":0,"no-data":0}
print("  FLOW-LED run       ER    band")
for r in runs:
    e=er(r["ep"])
    if e is None: b="no-data"
    elif e<0.1: b="[0.0-0.1) chop"
    elif e<0.2: b="[0.1-0.2) chop"
    else: b="[0.2+) trend"
    bands[b]+=1
    print(f"  {r['tm']} {r['d']} {r['mv']:+5}  {('—' if e is None else f'{e:.2f}'):>5}   {b}")
print("\n  ── how many of the runs are in the BOTTOM 2 ER bands (ER<0.2)? ──")
low=bands["[0.0-0.1) chop"]+bands["[0.1-0.2) chop"]
for k,v in bands.items(): print(f"   {k:>16}: {v}")
print(f"\n  >>> {low} of {len(runs)} FLOW-LED runs are in the bottom-2 ER bands (ER<0.2).")
