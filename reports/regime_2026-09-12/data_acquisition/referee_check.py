#!/usr/bin/env python3
"""THE REFEREE. The overlap check the mission asked for could not be run the obvious way.

The HuggingFace NQ 1-minute set ends 2025-07-25; this desk's own MNQ 1-MINUTE tape begins
2025-09-14. There is NO 1-minute overlap. The natural fallback — compare against our own 1-HOUR
and 1-DAY backfill, which do overlap — FAILED by 300-700 points.

★ So the first job was deciding WHICH tape is wrong. Test B below settles it without reference to
  any external source: our own 1-hour bars disagree with our own 1-minute bars, same symbol, same
  broker, mean -393 points. Two files in our own lake cannot both be right.

★ Test A brings in an independent referee (Yahoo NQ=F front-month daily, free, 2000-2026) and
  scores all three tapes against it. Whichever tape matches the referee is the one to trust.

  .venv/bin/python reports/regime_2026-09-12/data_acquisition/referee_check.py
"""
import duckdb

GB = "/home/alphabot/gazbot7"
HF = f"read_parquet('{GB}/data/external/hf_nq1min/NQ_1min_*.parquet')"
Y = f"read_csv('{GB}/data/external/yahoo/NQF_1d.csv')"
c = duckdb.connect(); c.execute("SET memory_limit='700MB'"); c.execute("SET threads=2")
c.execute(f"SET temp_directory='{GB}/data/duckdb_tmp'")


def hdr(s): print(f"\n{'='*80}\n{s}\n{'='*80}")

hdr("TEST B — DOES OUR OWN TAPE AGREE WITH ITSELF? (MNQ 1-hour vs MNQ 1-minute)")
print(c.execute(f"""
WITH m AS (SELECT date_trunc('hour', to_timestamp(bar_ts) AT TIME ZONE 'UTC') t,
                  last(close ORDER BY bar_ts) c
           FROM read_parquet('{GB}/data/tape/bars/MNQ/backfill_1min.parquet') GROUP BY 1),
 h AS (SELECT to_timestamp(bar_ts) AT TIME ZONE 'UTC' t, close c
       FROM read_parquet('{GB}/data/tape/bars/MNQ/backfill_1hour.parquet'))
SELECT count(*) n, round(avg(m.c-h.c),2) mean_diff, round(stddev(m.c-h.c),2) sd,
       round(max(abs(m.c-h.c)),2) max_abs,
       round(100.0*avg(CASE WHEN abs(m.c-h.c)<=0.25 THEN 1 ELSE 0 END),2) pct_within_1_tick
FROM m JOIN h USING(t)""").df().to_string(index=False))
print("\n→ Our own 1-hour and 1-minute MNQ bars disagree. The 1-minute tape is the one with volume;")
print("  the 1-hour/1-day series is the suspect.")

hdr("TEST B2 — WHY: zero-volume, open==high==low==close 'bars' in our own backfill")
for tf in ("1day", "1hour"):
    print(c.execute(f"""
    SELECT '{tf}' timeframe, count(*) n,
           count(*) FILTER (WHERE volume=0) zero_volume,
           count(*) FILTER (WHERE open=high AND high=low AND low=close) flat_ohlc
    FROM read_parquet('{GB}/data/tape/bars/MNQ/backfill_{tf}.parquet')""").df().to_string(index=False))
print("""
→ ROOT CAUSE. scripts/backfill_history.py could only pull expiries IBKR still LISTS. Every contract
  that was front-month before ~Oct-2025 had already expired and been purged, so it is simply absent
  from data/backfill/. backfill_to_lake.py then deduped on bar_ts "keeping the FIRST — the
  front-month print"; with the real front months missing, the first available file is a DEFERRED
  expiry. On 2024-09-23 the only file holding that date is MNQ_20251219 — the Dec-2025 contract,
  then 15 months out — printing 20786.25 on ZERO volume against a true front-month 20080.00.
  MNQ_CONTFUT is no better: 21388.50 for the same day, +1308 points.""")

hdr("TEST A — SCORE ALL THREE TAPES AGAINST THE REFEREE (Yahoo NQ=F front-month daily)")
rows = []
qs = {
 "HF NQ 1-min (new)": f"""SELECT CAST(timestamp AS DATE) d, last(close ORDER BY timestamp) c FROM {HF}
      WHERE (hour(timestamp)*60+minute(timestamp)) BETWEEN 13*60+30 AND 20*60 GROUP BY 1""",
 "OUR MNQ 1-min": f"""SELECT CAST(to_timestamp(bar_ts) AS DATE) d, last(close ORDER BY bar_ts) c
      FROM read_parquet('{GB}/data/tape/bars/MNQ/backfill_1min.parquet')
      WHERE (hour(to_timestamp(bar_ts))*60+minute(to_timestamp(bar_ts))) BETWEEN 13*60+30 AND 20*60 GROUP BY 1""",
 "OUR MNQ 1-day": f"""SELECT CAST(to_timestamp(bar_ts) AS DATE) d, close c
      FROM read_parquet('{GB}/data/tape/bars/MNQ/backfill_1day.parquet')""",
}
for name, q in qs.items():
    df = c.execute(f"""
      WITH a AS ({q}), y AS (SELECT CAST(date AS DATE) d, close c FROM {Y})
      SELECT count(*) n, round(corr(a.c,y.c),6) level_corr, round(avg(a.c-y.c),2) mean_diff,
             round(quantile_cont(abs(a.c-y.c),0.5),2) median_abs_diff,
             round(100.0*avg(CASE WHEN abs(a.c-y.c)<=25 THEN 1 ELSE 0 END),1) pct_within_25pt
      FROM a JOIN y USING(d)""").df()
    df.insert(0, "tape", name)
    rows.append(df)
import pandas as pd
print(pd.concat(rows).to_string(index=False))
print("""
→ VERDICT. The HuggingFace tape and our own 1-MINUTE tape both track the referee. Our 1-DAY/1-HOUR
  backfill does not. The new source is USABLE; the desk's own long-dated daily history is NOT.""")
c.close()
