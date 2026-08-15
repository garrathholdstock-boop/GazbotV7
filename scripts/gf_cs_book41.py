"""CHOP-DAY SCALP — the 41ms book, which sees what the 250ms sample cannot.

capture.db's `book` table is event-driven at ~41ms and 4 levels deep (MNQ only,
2026-07-31 onward).  depth.db is a 250ms SAMPLE, so it misses fleeting quotes — and
"is this wall real or is it being pulled and re-posted" is exactly a fleeting-quote
question.  This builds per-5s REPLENISHMENT statistics from the raw event stream:

    refills  — number of level-1 size INCREASES  (a defended wall re-posts)
    pulls    — number of level-1 size DECREASES
    added / removed — the contracts behind those moves

Output: reports/friday_v7/sections/cs/feat41/<day>.parquet
"""
from __future__ import annotations

import os
import sys

from gazbot7.lake import connect

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/cs/feat41"
DAYS41 = ["2026-07-31", "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06",
          "2026-08-07", "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13",
          "2026-08-14"]

SQL = """
WITH l1 AS (
    SELECT ts_ms, side, size
    FROM book
    WHERE symbol='MNQ' AND level=1
      AND ts_ms >= epoch_ms(TIMESTAMP '{d} 00:00:00')
      AND ts_ms <  epoch_ms(TIMESTAMP '{d} 00:00:00' + INTERVAL 1 DAY)
),
seq AS (
    SELECT ts_ms, side, size,
           lag(size) OVER (PARTITION BY side ORDER BY ts_ms) AS prev
    FROM l1
),
agg AS (
    SELECT ts_ms/1000 - (ts_ms/1000) % 5 AS t, side,
           count(*)                                        AS upd,
           sum(CASE WHEN size > prev THEN 1 ELSE 0 END)     AS refills,
           sum(CASE WHEN size < prev THEN 1 ELSE 0 END)     AS pulls,
           sum(greatest(size - prev, 0))                    AS added,
           sum(greatest(prev - size, 0))                    AS removed,
           max(size)                                        AS mx,
           avg(size)                                        AS av
    FROM seq WHERE prev IS NOT NULL GROUP BY 1, 2
)
SELECT t,
       sum(CASE WHEN side='bid' THEN upd     ELSE 0 END) AS b_upd,
       sum(CASE WHEN side='ask' THEN upd     ELSE 0 END) AS a_upd,
       sum(CASE WHEN side='bid' THEN refills ELSE 0 END) AS b_refill,
       sum(CASE WHEN side='ask' THEN refills ELSE 0 END) AS a_refill,
       sum(CASE WHEN side='bid' THEN pulls   ELSE 0 END) AS b_pull,
       sum(CASE WHEN side='ask' THEN pulls   ELSE 0 END) AS a_pull,
       sum(CASE WHEN side='bid' THEN added   ELSE 0 END) AS b_added,
       sum(CASE WHEN side='ask' THEN added   ELSE 0 END) AS a_added,
       sum(CASE WHEN side='bid' THEN removed ELSE 0 END) AS b_removed,
       sum(CASE WHEN side='ask' THEN removed ELSE 0 END) AS a_removed,
       sum(CASE WHEN side='bid' THEN mx      ELSE 0 END) AS b_max,
       sum(CASE WHEN side='ask' THEN mx      ELSE 0 END) AS a_max,
       sum(CASE WHEN side='bid' THEN av      ELSE 0 END) AS b_avg,
       sum(CASE WHEN side='ask' THEN av      ELSE 0 END) AS a_avg
FROM agg GROUP BY 1 ORDER BY 1
"""


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    con = connect()
    for d in (sys.argv[1:] or DAYS41):
        con.execute(f"COPY ({SQL.format(d=d)}) TO '{OUT}/{d}.parquet' (FORMAT PARQUET)")
        n = con.execute(f"SELECT count(*), sum(a_upd+b_upd) FROM '{OUT}/{d}.parquet'").fetchone()
        print(f"{d}  buckets={n[0]:6d}  l1_updates={int(n[1]):,}", flush=True)


if __name__ == "__main__":
    main()
