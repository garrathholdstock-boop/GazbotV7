"""Two-stage confirm: break +M, THEN enter only if push-flow SUSTAINS over the next T sec (not being
absorbed). The turn analysis showed runs keep getting bought while pops get absorbed — so require the
buying to continue. Enter at break+T; sweep the sustain-flow floor. ALWAYS reports big-runs-kept.

  PYTHONPATH=src python scripts/afc_flow_sustain.py
"""
from __future__ import annotations
import datetime as dt
import re
import duckdb
import numpy as np
CAP="/home/alphabot/gazbot7/data/capture.db"; CENSUS="/home/alphabot/gazbot7/reports/friday_v7/sections/census_stdout.txt"
SINCE,UNTIL="2026-07-19 22:00:00","2026-07-24 21:00:00"
W,TH,STOP,ARM,TRAIL,HOLD_CAP,ARM_TO=60,150.0,20.0,12.0,12.0,1200,300; FEE, VPP = 1.50, 2.0   # ★2026-08-13 COST FIX — was FEE, VPP = 1.50, 2.0   # ★2026-08-13 COST FIX — was FEE,VPP=5.0,2.0. $5.00 is 3.3x the real
# $1.50 commission. An over-charged fee never looks wrong: it silently kills marginal edges and
# reports a confident NULL. Any conclusion this script produced before today used $5/RT — RE-RUN IT. (unspaced), which is why the
# 08-02 sweep missed it: that pass grepped the SPACED form. $5.00 is 3.3x the real $1.50 commission,
# and an over-charged fee does not look wrong — it silently kills marginal edges and reports a
# confident NULL. Any conclusion this script produced before today was computed at $5/RT: RE-RUN IT.
WIN_PRE,WIN_POST=600,300; M=16.0; T=10; FLOORS=[0,30,50,80,120,160]
def main():
    runs=[]
    for ln in open(CENSUS):
        if ln.rstrip().endswith("FLOW-LED"):
            g=re.match(r"^(\d\d-\d\d \d\d:\d\d)\s+(UP|DN)",ln)
            if g:
                ep=int(dt.datetime.strptime("2026-"+g.group(1),"%Y-%m-%d %H:%M").replace(tzinfo=dt.UTC).timestamp())
                runs.append({"ep":ep,"d":1.0 if g.group(2)=="UP" else -1.0})
    NR=len(runs)
    con=duckdb.connect(); con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    lo=int(con.execute(f"SELECT epoch(TIMESTAMP '{SINCE}')").fetchone()[0]); hi=int(con.execute(f"SELECT epoch(TIMESTAMP '{UNTIL}')").fetchone()[0])
    fdf=con.execute(f"""SELECT CAST(ts_ms/1000 AS BIGINT) s, SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size ELSE 0 END) net
        FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} GROUP BY s ORDER BY s""").df()
    s0,s1=int(fdf.s.min()),int(fdf.s.max()); flow=np.zeros(s1-s0+1); flow[(fdf.s.values-s0).astype(int)]=fdf.net.values
    csum=np.concatenate([[0],np.cumsum(flow)]); F=np.convolve(flow,np.ones(W),"full")[:len(flow)]; secs=np.arange(s0,s1+1); over=np.abs(F)>=TH
    tk=con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} ORDER BY ts_ms""").df()
    tts,tpx=tk.ts_ms.values.astype(np.int64),tk.price.values.astype(float); con.close()
    def fdir(a_s,b_s,d): a,b=max(0,a_s-s0),max(0,b_s-s0); return (csum[min(b,len(csum)-1)]-csum[min(a,len(csum)-1)])*d
    def which(ts_s,d):
        for k,r in enumerate(runs):
            if r["d"]==d and (r["ep"]-WIN_PRE)<=ts_s<=(r["ep"]+WIN_POST): return k
        return -1
    def walk(ei,ep,d):
        peak,armed,et,j=0.0,False,int(tts[ei]),ei+1
        while j<len(tts):
            px,t=tpx[j],int(tts[j]); fav=(px-ep)*d
            if -fav>=STOP: return -STOP*VPP-FEE
            if fav>peak: peak=fav
            if not armed and peak>=ARM: armed=True
            if armed and (peak-fav)>=TRAIL: return fav*VPP-FEE
            if t-et>=HOLD_CAP*1000: return fav*VPP-FEE
            j+=1
        return (tpx[-1]-ep)*d*VPP-FEE
    # collect breakouts with their sustain-flow + entry-at-break+T
    ev=[]; i,n=1,len(secs)
    while i<n:
        if over[i] and not over[i-1]:
            d=1.0 if F[i]>0 else -1.0; si=int(np.searchsorted(tts,(secs[i]+1)*1000,"left"))
            if si>=len(tts): break
            sig_px,sig_ts,ei,j=tpx[si],int(tts[si]),-1,si+1
            while j<len(tts):
                fav=(tpx[j]-sig_px)*d
                if fav>=M: ei=j; break
                if fav<=-M or (int(tts[j])-sig_ts)>=ARM_TO*1000: break
                j+=1
            if ei<0:
                tnsec=int(tts[j]//1000) if j<len(tts) else secs[i]
                while i<n and secs[i]<=tnsec: i+=1
                continue
            brk_s=int(tts[ei])//1000
            pf=fdir(brk_s,brk_s+T,d)                       # sustain-flow after break
            ei2=int(np.searchsorted(tts,(brk_s+T)*1000,"left")); ei2=min(ei2,len(tts)-1)
            pnl=walk(ei2,tpx[ei2],d)
            ev.append({"pf":pf,"pnl":pnl,"run":which(int(secs[i]),d)})
            while i<n and secs[i]<=brk_s+T: i+=1
            continue
        i+=1
    print(f"TWO-STAGE: break +{M:.0f}pt THEN enter only if push-flow over next {T}s >= floor (enter at break+{T}s)\n")
    print(f"  {'flow floor':>12}{'entered':>9}{'net$':>10}{'$/entry':>9}{'win%':>6}{'runs kept':>11}")
    for fl in FLOORS:
        g=[e for e in ev if e["pf"]>=fl]
        if not g: continue
        net=sum(e["pnl"] for e in g); w=100*sum(1 for e in g if e["pnl"]>0)/len(g); c=len({e["run"] for e in g if e["run"]>=0})
        print(f"  {f'>= {fl}':>12}{len(g):>9}${net:>+9.0f}${net/len(g):>+8.1f}{w:>5.0f}%{f'{c}/{NR}':>11}")
    print("\n(want net toward 0/green AND runs-kept high. the flow floor keeps the sustained-buying runs and "
          "cuts the absorbed pops — IF the flow tell is real & leading. ⚠ 1wk in-sample, enter is {T}s late.)")
if __name__=="__main__": main()
