"""EXIT-LADDER LAB — stage 1: build the EXTENDED unified MNQ tape (V5 archive + V7 capture).

The mid-week first-look was CHOP-DOMINATED (BIG-TREND n=5-25), so the 3.5R+wide-chandelier rung
was untested. This stitches the V5 tick archive (/home/alphabot/alphabot2/data/ticks.db,
2026-07-05..07-17) onto the V7 capture 5s bars (2026-07-15..07-31) so the lab has ~19 trading
days instead of ~11, and enough clean-trend tape for a real BIG-TREND bucket.

Writes scratchpad/tape5s.npz: ts, o, h, l, c, v (5s bars, deduped, ascending).
"""
from __future__ import annotations
import numpy as np, duckdb, os

TICKS = "/home/alphabot/alphabot2/data/ticks.db"
CAP = "/home/alphabot/gazbot7/data/capture.db"
OUT = "/home/alphabot/gazbot7/scratchpad/tape5s.npz"

con = duckdb.connect()
con.execute(f"ATTACH '{TICKS}' AS a (TYPE sqlite, READ_ONLY)")
con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")

cut = int(con.execute("SELECT min(bar_ts) FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'").fetchone()[0])
print("capture 5s starts", cut)

arch = con.execute(f"""
  SELECT CAST(ts_ms/5000 AS BIGINT)*5 AS bts,
         arg_min(price, ts_ms) AS o, max(price) AS h, min(price) AS l,
         arg_max(price, ts_ms) AS cl, sum(size) AS v
  FROM a.trade_tick
  WHERE symbol='MNQ' AND ts_ms < {cut*1000}
  GROUP BY 1 ORDER BY 1
""").df()
print("archive 5s bars", len(arch), arch.bts.min(), arch.bts.max())

capd = con.execute(f"""
  SELECT bar_ts AS bts, open AS o, high AS h, low AS l, close AS cl, volume AS v
  FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts >= {cut} ORDER BY 1
""").df()
print("capture 5s bars", len(capd), capd.bts.min(), capd.bts.max())

import pandas as pd
df = pd.concat([arch, capd], ignore_index=True).drop_duplicates(subset=["bts"], keep="last").sort_values("bts")
print("unified", len(df), df.bts.min(), df.bts.max())
os.makedirs(os.path.dirname(OUT), exist_ok=True)
np.savez_compressed(OUT, ts=df.bts.to_numpy(np.int64), o=df.o.to_numpy(float), h=df.h.to_numpy(float),
                    l=df.l.to_numpy(float), c=df.cl.to_numpy(float), v=df.v.to_numpy(float))
print("wrote", OUT)
