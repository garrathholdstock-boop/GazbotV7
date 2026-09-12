import duckdb, glob
GB="/home/alphabot/gazbot7"
SPEC={"MNQ":dict(vpp=2.0, tick=0.25, fee=1.50, sprd_ticks=1.0),
      "MGC":dict(vpp=10.0, tick=0.10, fee=1.50, sprd_ticks=3.0)}
con=duckdb.connect()
for sym,s in SPEC.items():
    files=sorted(glob.glob(f"{GB}/data/backfill/{sym}_*_1min.parquet"))
    rows=[f"select '{f.split('_')[-2]}' exp, ts,open,high,low,close,volume from read_parquet('{f}')" for f in files]
    q=f"""
    with a as ({' union all '.join(rows)}),
    t as (select *, cast(to_timestamp(ts) at time zone 'UTC' as date) d,
                 hour(to_timestamp(ts) at time zone 'UTC') h from a),
    v as (select d,exp,sum(volume) vv from t group by 1,2),
    fr as (select d,exp from (select *,row_number() over (partition by d order by vv desc) rn from v) where rn=1),
    f as (select t.* from t join fr on t.d=fr.d and t.exp=fr.exp),
    rth as (select d, max(high)-min(low) rng, sum(volume) vol, count(*) n
            from f where h>=13 and h<20 group by 1)
    select count(*) as ndays, median(rng) med_rng, quantile_cont(rng,0.25) q25, quantile_cont(rng,0.75) q75,
           median(vol) med_vol, min(d) d0, max(d) d1
    from rth where n>200"""
    r=con.execute(q).fetchone()
    days,med,q25,q75,vol,d0,d1=r
    cost=s["fee"]+s["sprd_ticks"]*s["tick"]*s["vpp"]
    print(f"{sym}: days={days} {d0}..{d1}  RTH(13-19Z) range median={med:.2f}pt "
          f"(IQR {q25:.2f}-{q75:.2f})  = ${med*s['vpp']:.2f}/contract")
    print(f"   RT cost = ${cost:.2f} (fee ${s['fee']:.2f} + {s['sprd_ticks']} tick(s) x ${s['tick']*s['vpp']:.2f})"
          f"  -> cost / median RTH range = {100*cost/(med*s['vpp']):.2f}%   median RTH volume={vol:,.0f}")
