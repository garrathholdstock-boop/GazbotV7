#!/usr/bin/env python3
"""REV3 — the 55s confirm scored on the LIVE gate's OWN money, not the mirror's.

rev2_absveto55_overlap.py established the overlap (4 of 11 live signals). This asks the
question that actually decides the promotion: of abs_veto_short's own booked -$170.00 this
week, how much sits in the 4 signals the 55-second confirm would have KEPT and how much in
the 7 it would have REFUSED? That is an apples-to-apples filter test on the live ruler --
no mirror pricing, no over-fire bias, no upper bound.
"""
import datetime as dt, json, sqlite3, collections

GB="/home/alphabot/gazbot7"
MATCH_S=240; WEEK=("2026-08-17","2026-08-21")

c=sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro",uri=True); c.row_factory=sqlite3.Row
rows=[dict(r) for r in c.execute(
    "SELECT opened_at,closed_at,entry_price,qty,pnl_usd,exit_reason,gate FROM trades "
    "WHERE gate LIKE 'abs_veto_short%' AND date(closed_at) BETWEEN ? AND ? "
    "AND data_quality IS NULL ORDER BY opened_at",WEEK)]
sig={}
for r in rows:
    t=round(dt.datetime.fromisoformat(r["opened_at"]).timestamp())
    near=[x for x in sig if abs(x-t)<=5]; t=near[0] if near else t
    s=sig.setdefault(t,dict(ts=t,entry=r["entry_price"],lots=0,pnl=0.0,day=r["closed_at"][:10],reasons=[]))
    s["lots"]+=r["qty"]; s["pnl"]+=r["pnl_usd"]; s["reasons"].append(r["exit_reason"])
live=sorted(sig.values(),key=lambda s:s["ts"])

s2=sqlite3.connect(f"file:{GB}/data/shadow.db?mode=ro",uri=True); s2.row_factory=sqlite3.Row
conf=[r["entry_ts"] for r in s2.execute(
    "SELECT entry_ts,side FROM shadow_trades WHERE strategy='abs_veto_55s' AND data_quality IS NULL")
    if str(r["side"]).upper().startswith("S")]

for s in live:
    s["kept"]=any(abs(s["ts"]-x)<=MATCH_S for x in conf)

def rep(sub,label):
    n=len(sub); net=sum(x["pnl"] for x in sub); lots=sum(x["lots"] for x in sub)
    w=sum(1 for x in sub if x["pnl"]>0)
    best=max((x["pnl"] for x in sub),default=0)
    byday=collections.defaultdict(float)
    for x in sub: byday[x["day"]]+=x["pnl"]
    loo=min((net-v for v in byday.values()),default=net)
    print(f"  {label:<34} n={n:<3} lots={lots:<5.0f} net={net:+9.2f}  $/sig={net/n if n else 0:+8.2f}  "
          f"win={100*w/n if n else 0:5.1f}%  strip-best-1={net-best:+9.2f}  worst-LOO={loo:+9.2f}")
    return dict(arm=label,n=n,lots=lots,net=round(net,2),per=round(net/n,2) if n else None,
                win=round(100*w/n,1) if n else None,strip_best1=round(net-best,2),worst_loo=round(loo,2))

print(f"abs_veto_short live signals {WEEK[0]}..{WEEK[1]}: {len(live)} signals, "
      f"{sum(x['lots'] for x in live):.0f} lots, booked {sum(x['pnl'] for x in live):+,.2f}\n")
print("Split by whether the 55-second continuation confirm would have KEPT the signal:")
out=[rep(live,"ALL live signals (as traded)"),
     rep([x for x in live if x["kept"]],"KEPT by the 55s confirm"),
     rep([x for x in live if not x["kept"]],"REFUSED by the 55s confirm")]
print("\nper signal:")
for s in live:
    print(f"  {dt.datetime.fromtimestamp(s['ts'],dt.UTC):%m-%d %H:%M}Z  {s['entry']:>10,.2f}  "
          f"{s['lots']:.0f}L  {s['pnl']:+8.2f}  {'KEPT' if s['kept'] else 'refused'}  "
          f"{','.join(sorted(set(s['reasons'])))}")
json.dump(dict(week=WEEK,match_s=MATCH_S,arms=out,
               signals=[{k:v for k,v in s.items() if k!='reasons'} for s in live]),
          open(f"{GB}/reports/friday_v7/sections/rev3_absveto_confirm_on_live.json","w"),indent=1)
