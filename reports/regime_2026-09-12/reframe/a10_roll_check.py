"""A10. ★ ROLL CONTAMINATION AUDIT — the thing that could have invalidated sections 1 and 2.

The lake's front month is chosen PER DATE BY VOLUME. On a roll date the series jumps from the
expiring contract to the deferred one, and for an equity index in contango that jump is the carry
- on the order of hundreds of MNQ points per quarter. Nothing in the loader flags it, the two bars
either side are one minute apart so a time-gap filter does not catch it, and if a roll lands inside
the overnight window it is booked as free P&L by the overnight arm.

This finds every roll date, measures the jump, and re-states section 2 with rolls EXCLUDED.
"""
import duckdb, glob, numpy as np, pandas as pd
GB="/home/alphabot/gazbot7"; OUT=f"{GB}/reports/regime_2026-09-12/reframe"
con=duckdb.connect()
for sym,vpp,fric in [("MNQ",2.0,1.25),("MGC",10.0,0.45)]:
    files=sorted(glob.glob(f"{GB}/data/backfill/{sym}_*_1min.parquet"))
    rows=[f"select '{f.split('_')[-2]}' exp, ts,close,volume from read_parquet('{f}')" for f in files]
    d=con.execute(f"""
      with a as ({' union all '.join(rows)}),
      t as (select *, cast(to_timestamp(ts) at time zone 'UTC' as date) d from a),
      v as (select d,exp,sum(volume) vv from t group by 1,2),
      fr as (select d,exp from (select *,row_number() over (partition by d order by vv desc) rn from v) where rn=1)
      select t.ts,t.close,t.exp from t join fr on t.d=fr.d and t.exp=fr.exp order by t.ts""").df()
    d["et"]=pd.to_datetime(d.ts,unit="s",utc=True).dt.tz_convert("America/New_York")
    m=d.et.dt.hour*60+d.et.dt.minute
    d["tdate"]=np.where(m>=18*60,(d.et+pd.Timedelta(days=1)).dt.date,d.et.dt.date)
    d["mlin"]=np.where(m>=18*60,m-18*60,m+360)
    d["roll"]=d.exp!=d.exp.shift()
    d.loc[0,"roll"]=False
    r=d[d.roll]
    print(f"\n=== {sym}: {len(r)} front-month changes in {d.tdate.nunique()} sessions ===")
    jumps=[]
    for i in r.index:
        prev=d.close.iloc[i-1]; jump=d.close.iloc[i]-prev
        jumps.append(jump)
        print(f"  {d.et.iloc[i]}  {d.exp.iloc[i-1]}->{d.exp.iloc[i]}  jump {jump:+9.2f} pt = ${jump*vpp:+9.0f}  mlin {d.mlin.iloc[i]:>4} ({'OVERNIGHT 16:00-09:30' if (d.mlin.iloc[i]>=22*60 or d.mlin.iloc[i]<15*60+30) else 'inside US cash'})")
    print(f"  total roll jump booked as price change: {sum(jumps):+.2f} pt = ${sum(jumps)*vpp:+,.0f} on one lot")
    # ---- restate the bucket table with rolls neutralised
    d["chg"]=d.close.diff()
    d.loc[d.ts.diff()>300,"chg"]=np.nan
    raw=d.chg.sum()
    d.loc[d.roll,"chg"]=np.nan
    adj=d.chg.sum()
    print(f"  session-sum of 1-min changes: RAW {raw:+.2f} pt   ROLL-ADJUSTED {adj:+.2f} pt   difference {raw-adj:+.2f}")
    def bk(x):
        if x< 8*60:    return "1 ASIA 18:00-02:00"
        if x<15*60+30: return "2 EU   02:00-09:30"
        if x<22*60:    return "3 US   09:30-16:00"
        return "4 LATE 16:00-17:00"
    d["bk"]=d.mlin.map(bk)
    g=d.groupby("bk").chg.agg(net_pt_ROLLADJ="sum",gross_abs=lambda s:s.abs().sum())
    g["net_usd_1lot"]=g.net_pt_ROLLADJ*vpp; g["pct_of_movement"]=100*g.gross_abs/g.gross_abs.sum()
    print(g.round(2).to_string())
    g.round(3).to_csv(f"{OUT}/a10_{sym}_buckets_rolladj.csv")
    # ---- restate the arms, dropping any session whose overnight window contains a roll
    at=lambda gg,x:(np.nan if gg[gg.mlin<=x].empty else gg.close[gg.mlin<=x].iloc[-1])
    recs=[]
    for td,gg in d.groupby("tdate"):
        gg=gg.sort_values("mlin")
        recs.append(dict(tdate=td,p1600=at(gg,22*60),p0930=at(gg,15*60+30),
                         roll_after1600=bool(gg.roll[gg.mlin>=22*60].any()),
                         roll_before0930=bool(gg.roll[gg.mlin<15*60+30].any()),
                         roll_intra=bool(gg.roll[(gg.mlin>=15*60+30)&(gg.mlin<22*60)].any())))
    s=pd.DataFrame(recs).sort_values("tdate").reset_index(drop=True)
    s["p0930_next"]=s.p0930.shift(-1); s["roll_next_before0930"]=s.roll_before0930.shift(-1).fillna(False)
    s["ONITE"]=s.p0930_next-s.p1600; s["INTRA"]=s.p1600-s.p0930
    s["onite_dirty"]=s.roll_after1600 | s.roll_next_before0930
    ok=s.dropna(subset=["ONITE"])
    print(f"\n  ONITE arm, {sym}: {ok.onite_dirty.sum()} of {len(ok)} sessions have a roll inside the overnight window")
    for lab,sub in [("ALL (as reported in §2)",ok),("ROLL-CLEAN",ok[~ok.onite_dirty])]:
        v=sub.ONITE.values-fric; t=v.mean()/(v.std(ddof=1)/np.sqrt(len(v)))
        print(f"    {lab:<24} n={len(v):>3}  net {v.mean():>7.2f}pt = ${v.mean()*vpp:>7.2f}/session  t={t:>5.2f}  total ${v.sum()*vpp:>8,.0f}")
    oki=s.dropna(subset=["INTRA"])
    for lab,sub in [("ALL",oki),("ROLL-CLEAN",oki[~oki.roll_intra])]:
        v=sub.INTRA.values-fric; t=v.mean()/(v.std(ddof=1)/np.sqrt(len(v)))
        print(f"    INTRA {lab:<18} n={len(v):>3}  net {v.mean():>7.2f}pt = ${v.mean()*vpp:>7.2f}/session  t={t:>5.2f}  total ${v.sum()*vpp:>8,.0f}")
