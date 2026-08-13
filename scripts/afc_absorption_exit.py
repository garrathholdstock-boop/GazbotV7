"""Absorption-EXIT: enter at +M (breakout-confirm), then if the move STALLS in the first T sec (fails
to make +K more) — the absorption signature — BAIL at market (small loss) instead of riding to the
-20 stop. Real runs extend immediately so they never bail (they ride); absorbed pops stall and exit
small. Attacks the -\$45 stops (97% of the bleed) directly, keeps runs by construction. Reports runs-kept.

  PYTHONPATH=src python scripts/afc_absorption_exit.py
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
WIN_PRE,WIN_POST=600,300; M=16.0
GRID=[(8,4),(8,6),(12,4),(12,6),(12,8),(20,8)]   # (bail deadline sec, required continuation pts)
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
    F=np.convolve(flow,np.ones(W),"full")[:len(flow)]; secs=np.arange(s0,s1+1); over=np.abs(F)>=TH
    tk=con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} ORDER BY ts_ms""").df()
    tts,tpx=tk.ts_ms.values.astype(np.int64),tk.price.values.astype(float); con.close()
    def which(ts_s,d):
        for k,r in enumerate(runs):
            if r["d"]==d and (r["ep"]-WIN_PRE)<=ts_s<=(r["ep"]+WIN_POST): return k
        return -1
    # precompute the breakout entries (entry idx, d, run) once
    entries=[]; i,n=1,len(secs)
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
            entries.append((ei,d,which(int(secs[i]),d)))
            while i<n and secs[i]<=int(tts[ei])//1000: i+=1
            continue
        i+=1
    def walk(ei,d,BT,K):
        ep,et,peak,armed,bailed,j=tpx[ei],int(tts[ei]),0.0,False,False,ei+1
        while j<len(tts):
            px,t=tpx[j],int(tts[j]); fav=(px-ep)*d
            # absorption bail: past the deadline without making +K → stall → exit now
            if (not bailed) and (t-et)>=BT*1000 and peak<K:
                return fav*VPP-FEE, "bail"
            if -fav>=STOP: return -STOP*VPP-FEE, "stop"
            if fav>peak: peak=fav
            if not armed and peak>=ARM: armed=True
            if armed and (peak-fav)>=TRAIL: return fav*VPP-FEE, "trail"
            if t-et>=HOLD_CAP*1000: return fav*VPP-FEE, "time"
            j+=1
        return (tpx[-1]-ep)*d*VPP-FEE, "time"
    print(f"ABSORPTION-EXIT: enter +{M:.0f}pt, BAIL if not +K within T sec (else chandelier+stop). {len(entries)} entries.\n")
    print(f"  {'bail T/K':>10}{'net$':>10}{'$/tr':>8}{'win%':>6}{'bailed':>8}{'avg loser':>11}{'runs kept':>11}")
    for BT,K in GRID:
        res=[walk(ei,d,BT,K) for ei,d,_ in entries]
        rk=[r for r,_ in res]; net=sum(rk); w=100*sum(1 for x in rk if x>0)/len(rk)
        nb=sum(1 for _,why in res if why=="bail"); losers=[x for x in rk if x<0]
        caught=len({run for (ei,d,run),(pnl,_) in zip(entries,res) if run>=0 and pnl>0}) or len({run for (ei,d,run) in entries if run>=0})
        c=len({run for (ei,d,run) in entries if run>=0})
        print(f"  {f'{BT}s/{K}pt':>10}${net:>+9.0f}${net/len(rk):>+7.1f}{w:>5.0f}%{nb:>8}${np.mean(losers) if losers else 0:>+10.1f}{f'{c}/{NR}':>11}")
    print("\n(the bail turns -\$45 stops into small exits IF pops stall & runs extend. want net->green, avg-loser "
          "shrinking, runs-kept high. all-runs are entered ({c}/{NR}); bail only changes their EXIT. ⚠ 1wk in-sample.)")
if __name__=="__main__": main()
