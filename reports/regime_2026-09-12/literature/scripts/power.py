"""THE POWER TABLE. How big must an MNQ intraday edge be before the data this desk holds could
tell it apart from zero? Measured sd of the signed move over each hold, RTH only, front month."""
import duckdb, glob, numpy as np, pandas as pd
GB="/home/alphabot/gazbot7"; VPP=2.0; FRIC=1.25
con=duckdb.connect()
files=sorted(glob.glob(f"{GB}/data/backfill/MNQ_*_1min.parquet"))
rows=[f"select '{f.split('_')[-2]}' exp, ts,open,high,low,close,volume from read_parquet('{f}')" for f in files]
df=con.execute(f"""
 with a as ({' union all '.join(rows)}),
 t as (select *, cast(to_timestamp(ts) at time zone 'UTC' as date) d from a),
 v as (select d,exp,sum(volume) vv from t group by 1,2),
 fr as (select d,exp from (select *,row_number() over (partition by d order by vv desc) rn from v) where rn=1)
 select t.ts,t.close from t join fr on t.d=fr.d and t.exp=fr.exp order by t.ts""").df()
et=pd.to_datetime(df.ts,unit="s",utc=True).dt.tz_convert("America/New_York")
df["sess"]=et.dt.date; df["hm"]=et.dt.hour*60+et.dt.minute
R=df[(df.hm>=570)&(df.hm<=960)]
ns=R.sess.nunique()
print(f"MNQ RTH 09:30-16:00 ET, {ns} sessions, front month. Friction {FRIC}pt/RT (${FRIC*VPP:.2f}).\n")
print(f"{'hold':>6} {'sd(pt)':>8} {'trades/239d':>12} {'min detectable edge (t=2)':>28} {'as % of hold sd':>16}")
for h in (5,15,30,60,120,240,390):
    moves=[]
    for s,g in R.groupby("sess"):
        c=g.close.values
        if len(c)<=h: continue
        moves.append(c[h::h]-c[0:len(c)-h:h][:len(c[h::h])])
    m=np.concatenate(moves); sd=m.std(ddof=1)
    n=int(390/h)*ns
    mde=2*sd/np.sqrt(n)
    print(f"{h:>5}m {sd:8.2f} {n:12,d} {mde:16.2f} pt  = ${mde*VPP:7.2f} {100*mde/sd:15.2f}%")
print("\nAt ONE trade per session (the desk's actual cadence on a hold-to-close design):")
for hold,sd in ((390,198.95),):
    for n_yrs in (1,2,5,10,16):
        n=239*n_yrs; print(f"  {n_yrs:2d} yr(s) = {n:5,d} trades -> min detectable edge {2*sd/np.sqrt(n):6.2f} pt = ${2*sd/np.sqrt(n)*VPP:7.2f}")
print("\nEquivalently t = Sharpe x sqrt(years). Over this desk's 239-session window:")
for sh in (0.5,0.75,1.0,1.5,2.0,3.0):
    print(f"  annualised Sharpe {sh:4.2f} -> t = {sh*1.0:4.2f} after 1 yr, {sh*2:4.2f} after 4 yrs, {sh*4:4.2f} after 16 yrs")
