#!/usr/bin/env python3
"""S04 — per-MINUTE MNQ trade-flow features for ONE day (aggressive flow, a different object
from resting depth). Minute m covers [m, m+60); a decision at T may read m only if m+60 <= T."""
import sys, duckdb
GB = "/home/alphabot/gazbot7"
src, dst = sys.argv[2], sys.argv[3]
con = duckdb.connect(config={"temp_directory": f"{GB}/data/duckdb_tmp", "memory_limit": "500MB",
                             "threads": "2"})
Q = f"""
select cast((ts_ms - ts_ms % 60000)/1000 as bigint) m,
  sum(case when aggressor='buy'  then size else 0 end) buyv,
  sum(case when aggressor='sell' then size else 0 end) sellv,
  sum(size) vol, count(*) ntr,
  sum(case when aggressor='buy' then size else 0 end)
    - sum(case when aggressor='sell' then size else 0 end) as tsi_raw,
  avg(size) avg_sz,
  max(size) max_sz
from read_parquet('{src}') where symbol='MNQ' group by 1 order by 1
"""
con.execute(f"copy ({Q}) to '{dst}' (format parquet)")
n = con.execute(f"select count(*) from read_parquet('{dst}')").fetchone()[0]
print(f"{sys.argv[1]} ticks minutes={n}")
