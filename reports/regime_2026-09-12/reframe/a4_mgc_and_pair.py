"""A4. Does 'the drift is outside the US cash session' replicate on the OTHER instrument this desk
already streams, and are the two overnight legs independent enough to be worth holding together?

MGC: micro gold, $10 per $1.00 move. This desk's own cost constant for a MARKETABLE round trip is
MGC_FEE_RT = $4.50 (0.30 spread crossed once = $3.00, + $1.50 commission) = 0.45 gold points.
Same exchange clock (18:00-17:00 America/New_York), same arms, same day-block bootstrap.
"""
import duckdb, numpy as np, pandas as pd
OUT="/home/alphabot/gazbot7/reports/regime_2026-09-12/reframe"
rng=np.random.default_rng(11)
con=duckdb.connect()

def build(sym,vpp,fric_usd):
    d=con.execute(f"select ts,close from read_parquet('{OUT}/tape_{sym}_1min.parquet') order by ts").df()
    d["et"]=pd.to_datetime(d.ts,unit="s",utc=True).dt.tz_convert("America/New_York")
    m=d.et.dt.hour*60+d.et.dt.minute
    d["tdate"]=np.where(m>=18*60,(d.et+pd.Timedelta(days=1)).dt.date,d.et.dt.date)
    d["mlin"]=np.where(m>=18*60,m-18*60,m+360)
    d["chg"]=d.close.diff(); d.loc[d.ts.diff()>300,"chg"]=np.nan
    def bk(x):
        if x< 8*60:    return "1 ASIA 18:00-02:00"
        if x<15*60+30: return "2 EU   02:00-09:30"
        if x<22*60:    return "3 US   09:30-16:00"
        return "4 LATE 16:00-17:00"
    d["bk"]=d.mlin.map(bk)
    g=d.groupby("bk").chg.agg(net_pt="sum",gross_abs=lambda s:s.abs().sum())
    g["net_usd_1lot"]=g.net_pt*vpp; g["pct_of_movement"]=100*g.gross_abs/g.gross_abs.sum()
    print(f"\n=== {sym}: where the points were made, {d.tdate.nunique()} CME sessions, {d.tdate.min()}..{d.tdate.max()} ===")
    print(g.round(2).to_string()); print(f"  TOTAL {d.chg.sum():.2f} pt = ${d.chg.sum()*vpp:,.0f} on one lot")
    at=lambda gg,x:(np.nan if gg[gg.mlin<=x].empty else gg[gg.mlin<=x].close.iloc[-1])
    rows=[]
    for td,gg in d.groupby("tdate"):
        gg=gg.sort_values("mlin")
        rows.append(dict(tdate=td,p1600=at(gg,22*60),p0930=at(gg,15*60+30)))
    s=pd.DataFrame(rows).sort_values("tdate").reset_index(drop=True)
    s["p0930_next"]=s.p0930.shift(-1)
    s["ONITE"]=s.p0930_next-s.p1600; s["INTRA"]=s.p1600-s.p0930
    s=s.dropna(subset=["ONITE","INTRA"]).reset_index(drop=True)
    fr=fric_usd/vpp
    for a in ("ONITE","INTRA"):
        v=s[a].values-fr; t=v.mean()/(v.std(ddof=1)/np.sqrt(len(v)))
        th=np.array_split(np.arange(len(v)),3)
        per=" ".join(f"P{i+1} {v[x].mean()*vpp:+7.1f}" for i,x in enumerate(th))
        print(f"  {a:<6} n={len(v):>3}  net {v.mean():>7.3f}pt = ${v.mean()*vpp:>7.2f}/session  sd ${v.std(ddof=1)*vpp:>7.0f}  t={t:>5.2f}  total ${v.sum()*vpp:>8,.0f}   {per}")
    s["usd_ONITE"]=s.ONITE*vpp - fric_usd; s["usd_INTRA"]=s.INTRA*vpp - fric_usd
    return s[["tdate","usd_ONITE","usd_INTRA"]].rename(columns={"usd_ONITE":f"{sym}_ONITE","usd_INTRA":f"{sym}_INTRA"})

a=build("MNQ",2.0,1.25*2.0)
b=build("MGC",10.0,4.50)
j=a.merge(b,on="tdate",how="inner")
print(f"\n=== PAIRED, {len(j)} common trade dates ===")
print("correlation of the two overnight legs (daily $):",round(j.MNQ_ONITE.corr(j.MGC_ONITE),3))
for cols,lab in [ (["MNQ_ONITE"],"MNQ overnight alone"),
                  (["MGC_ONITE"],"MGC overnight alone"),
                  (["MNQ_ONITE","MGC_ONITE"],"both overnight, 1 lot each") ]:
    v=j[cols].sum(axis=1).values; t=v.mean()/(v.std(ddof=1)/np.sqrt(len(v)))
    eq=np.cumsum(v)
    print(f"  {lab:<28} mean ${v.mean():>7.2f}/session sd ${v.std(ddof=1):>7.0f} t={t:>5.2f} total ${v.sum():>8,.0f} maxDD ${(np.maximum.accumulate(eq)-eq).max():>7,.0f}")
j.to_csv(f"{OUT}/a4_paired_overnight_usd.csv",index=False)
