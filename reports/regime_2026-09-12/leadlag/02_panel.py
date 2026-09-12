#!/usr/bin/env python3
"""Joint MNQ/MGC 1-min panel on the overlapping sessions, with CAUSAL-safe return columns.

Rules enforced here:
 - returns are computed ONLY between strictly consecutive minutes of the SAME session and the
   SAME contract expiry (no return is ever taken across a roll or across the daily halt).
 - a minute is kept only if BOTH instruments printed a bar in it (no forward-fill, which would
   manufacture zero returns and bias any lead-lag toward the more liquid leg).
"""
import duckdb, os, json
REPO="/home/alphabot/gazbot7"; OUT=f"{REPO}/reports/regime_2026-09-12/leadlag"
con=duckdb.connect(config={'memory_limit':'700MB','threads':2})

con.execute(f"create view fq as select * from '{OUT}/front_MNQ_1min.parquet'")
con.execute(f"create view fg as select * from '{OUT}/front_MGC_1min.parquet'")

con.execute("""
create or replace table panel as
with q as (select ts, sday, expiry, close as q_c, high as q_h, low as q_l, open as q_o, volume as q_v from fq),
     g as (select ts, sday, expiry, close as g_c, high as g_h, low as g_l, open as g_o, volume as g_v from fg)
select q.ts, q.sday, q.expiry as q_exp, g.expiry as g_exp,
       q_o,q_h,q_l,q_c,q_v, g_o,g_h,g_l,g_c,g_v
from q join g on q.ts=g.ts and q.sday=g.sday
order by q.ts
""")

# returns, strictly consecutive minutes within the same session+expiry
con.execute("""
create or replace table pan as
select *,
  lag(ts) over w as pts,
  case when ts - lag(ts) over w = 60 then q_c - lag(q_c) over w end as q_dp,   -- MNQ points
  case when ts - lag(ts) over w = 60 then g_c - lag(g_c) over w end as g_dp,   -- MGC points
  case when ts - lag(ts) over w = 60 then ln(q_c/lag(q_c) over w) end as q_r,
  case when ts - lag(ts) over w = 60 then ln(g_c/lag(g_c) over w) end as g_r
from panel
window w as (partition by sday, q_exp, g_exp order by ts)
""")

n=con.execute("select count(*) from pan").fetchone()[0]
sess=con.execute("select count(distinct sday) from pan").fetchone()[0]
rng=con.execute("select min(to_timestamp(ts))::date, max(to_timestamp(ts))::date from pan").fetchone()
both=con.execute("select count(*) from pan where q_r is not null and g_r is not null").fetchone()[0]
# coverage vs MNQ-only minutes
nq=con.execute(f"select count(*) from fq where sday in (select distinct sday from pan)").fetchone()[0]
con.execute(f"copy pan to '{OUT}/panel_1min.parquet' (format parquet)")

# per-hour coverage
cov=con.execute("""select (ts%86400)//3600 as utc_hour, count(*) n,
   avg(q_v) mnq_vol, avg(g_v) mgc_vol from pan group by 1 order by 1""").df()
cov.to_csv(f"{OUT}/02_coverage_by_hour.csv", index=False)
d=dict(joint_minutes=n, sessions=sess, first=str(rng[0]), last=str(rng[1]),
       minutes_with_both_returns=both, mnq_minutes_in_those_sessions=nq,
       joint_coverage_pct=round(100*n/nq,2))
json.dump(d, open(f"{OUT}/02_panel.json","w"), indent=2)
print(json.dumps(d,indent=2))
print(cov.to_string())
