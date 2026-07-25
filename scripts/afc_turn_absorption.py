"""Absorption AT THE TURN — the 20s AFTER +M. If the reverting pops show absorption, they should keep
getting heavy push-flow but FAIL to extend (the far side eats it), while real runs extend on similar
or less flow. Measures, in [break, break+20s]: push-flow (aggressor toward the move), price extension
(max favorable), and flow-per-point (absorption intensity = lots of flow, no progress). Compares RAN
vs REVERTED. This is the operator's 'reversions showed absorption' hypothesis, measured at the turn.

  PYTHONPATH=src python scripts/afc_turn_absorption.py [--m 16] [--post 20]
"""
from __future__ import annotations
import argparse
import datetime as dt
import re
import duckdb
import numpy as np

CAP="/home/alphabot/gazbot7/data/capture.db"
CENSUS="/home/alphabot/gazbot7/reports/friday_v7/sections/census_stdout.txt"
SINCE,UNTIL="2026-07-19 22:00:00","2026-07-24 21:00:00"
W,TH,STOP,ARM,TRAIL,HOLD_CAP,ARM_TO=60,150.0,20.0,12.0,12.0,1200,300
FEE,VPP=5.0,2.0
WIN_PRE,WIN_POST=600,300

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--m",type=float,default=16.0); ap.add_argument("--post",type=int,default=20)
    a=ap.parse_args(); M,POST=a.m,a.post
    runs=[]
    for ln in open(CENSUS):
        if ln.rstrip().endswith("FLOW-LED"):
            g=re.match(r"^(\d\d-\d\d \d\d:\d\d)\s+(UP|DN)",ln)
            if g:
                ep=int(dt.datetime.strptime("2026-"+g.group(1),"%Y-%m-%d %H:%M").replace(tzinfo=dt.UTC).timestamp())
                runs.append({"ep":ep,"d":1.0 if g.group(2)=="UP" else -1.0})
    con=duckdb.connect(); con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    lo=int(con.execute(f"SELECT epoch(TIMESTAMP '{SINCE}')").fetchone()[0]); hi=int(con.execute(f"SELECT epoch(TIMESTAMP '{UNTIL}')").fetchone()[0])
    fdf=con.execute(f"""SELECT CAST(ts_ms/1000 AS BIGINT) s, SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size ELSE 0 END) net
        FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} GROUP BY s ORDER BY s""").df()
    s0,s1=int(fdf.s.min()),int(fdf.s.max()); flow=np.zeros(s1-s0+1); flow[(fdf.s.values-s0).astype(int)]=fdf.net.values
    csum=np.concatenate([[0],np.cumsum(flow)]); F=np.convolve(flow,np.ones(W),"full")[:len(flow)]; secs=np.arange(s0,s1+1); over=np.abs(F)>=TH
    tk=con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} ORDER BY ts_ms""").df()
    tts,tpx=tk.ts_ms.values.astype(np.int64),tk.price.values.astype(float); con.close()
    def fdir(a_s,b_s,d):
        a,b=max(0,a_s-s0),max(0,b_s-s0); return (csum[min(b,len(csum)-1)]-csum[min(a,len(csum)-1)])*d
    def is_run(ts_s,d): return any(r["d"]==d and (r["ep"]-WIN_PRE)<=ts_s<=(r["ep"]+WIN_POST) for r in runs)
    ran,rev=[],[]; i,n=1,len(secs)
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
            brk_px,brk_ts=tpx[ei],int(tts[ei]); brk_s=brk_ts//1000
            # window [break, break+POST]: push-flow, price extension, end move
            we=int(np.searchsorted(tts,(brk_s+POST)*1000,"left")); we=min(we,len(tts)-1)
            seg=tpx[ei:we+1]
            ext=float(((seg-brk_px)*d).max()) if len(seg)>1 else 0.0
            endm=float((tpx[we]-brk_px)*d)
            pf=fdir(brk_s,brk_s+POST,d)
            fp={"pf":pf,"ext":ext,"endm":endm,"absorb":pf/max(ext,1.0)}
            (ran if (is_run(int(secs[i]),d) or endm>0) else rev).append(fp)
            while i<n and secs[i]<=brk_s: i+=1
            continue
        i+=1
    def med(rows,k): return float(np.median([r[k] for r in rows])) if rows else float("nan")
    print(f"ABSORPTION AT THE TURN (M={M:.0f}pt, {POST}s post-break window) — RAN {len(ran)} vs REVERTED {len(rev)}\n")
    print(f"  {'feature':>34}{'RAN median':>13}{'REVERTED median':>18}{'separates?':>12}")
    for name,k in [(f"push-flow in {POST}s after +M","pf"),("price extension after +M (pt)","ext"),
                   (f"net move at +{POST}s (pt)","endm"),("absorption = flow / extension","absorb")]:
        ma,mb=med(ran,k),med(rev,k); sep="← YES" if abs(ma-mb)>0.25*(abs(mb)+1e-9) else ""
        print(f"  {name:>34}{ma:>13.1f}{mb:>18.1f}{sep:>12}")
    print("\n(operator's hypothesis: REVERTED shows high push-flow but low extension = high absorption ratio, "
          "while RAN extends. if 'absorption' diverges (REVERTED >> RAN) it IS the tell — but note ext/endm are "
          "partly the outcome; the usable question is whether push-flow-with-no-extension is detectable fast.)")

if __name__=="__main__": main()
