#!/usr/bin/env python3
"""VERIFY the HuggingFace NQ 1-minute tape against this desk's own IBKR tape.

A source that disagrees with our tape on the overlap is not usable. The HF set ends 2025-07-25;
our MNQ 1-MINUTE backfill starts 2025-09-14, so there is NO 1-min overlap. Our MNQ 1-HOUR
backfill starts 2024-12-20 and our 1-DAY starts 2024-09-23 — both overlap the HF set by months.
So the check is: aggregate HF 1-min to 1h/1d and compare against IBKR's own 1h/1d bars.

NQ and MNQ quote the SAME index level (only the multiplier differs: $20/pt vs $2/pt), so a
genuine NQ tape must match our MNQ bars to within a tick or two, not merely correlate.

  PYTHONPATH=src .venv/bin/python reports/regime_2026-09-12/data_acquisition/verify_hf_nq.py
"""
import datetime as dt
import duckdb

GB = "/home/alphabot/gazbot7"
HF = f"read_parquet('{GB}/data/external/hf_nq1min/NQ_1min_*.parquet')"

c = duckdb.connect()
c.execute("SET memory_limit='700MB'"); c.execute("SET threads=2")
c.execute(f"SET temp_directory='{GB}/data/duckdb_tmp'")

def hdr(s): print(f"\n{'='*78}\n{s}\n{'='*78}")

# ─────────────────────────── 1. SESSION / GAP CENSUS ───────────────────────────
hdr("1. SESSION CENSUS — CME session day = 22:00 UTC prior day .. 21:00 UTC")
# CME session convention: a session runs 18:00 ET -> 17:00 ET. Use UTC+2h shift as the session key
sess = c.execute(f"""
  SELECT CAST(timestamp + INTERVAL 2 HOUR AS DATE) AS sess, count(*) AS bars
  FROM {HF} GROUP BY 1 ORDER BY 1""").df()
print(f"sessions: {len(sess):,}   first {sess.sess.iloc[0]}   last {sess.sess.iloc[-1]}")
print(f"bars/session  median {sess.bars.median():.0f}  p05 {sess.bars.quantile(.05):.0f}  "
      f"p95 {sess.bars.quantile(.95):.0f}  max {sess.bars.max()}")
short = sess[sess.bars < 600]
print(f"short sessions (<600 bars, i.e. half-days/holidays): {len(short)}")
# calendar gaps > 4 days = a real hole, same rule gazbot7.lake.coverage() uses
ds = list(sess.sess)
gaps = [(a, b, (b-a).days) for a, b in zip(ds, ds[1:]) if (b-a).days > 4]
print(f"holes >4 calendar days: {len(gaps)}")
for g in gaps[:20]: print("   ", g[0], "..", g[1], f"({g[2]}d)")

hdr("1b. SESSIONS PER YEAR (a CME session, not a calendar day)")
print(c.execute(f"""
  SELECT year(timestamp + INTERVAL 2 HOUR) AS y,
         count(DISTINCT CAST(timestamp + INTERVAL 2 HOUR AS DATE)) AS sessions,
         count(*) AS bars
  FROM {HF} GROUP BY 1 ORDER BY 1""").df().to_string(index=False))

# ─────────────────────────── 2. OVERLAP vs OUR OWN TAPE ────────────────────────
for tf, bucket, ourf in (("1hour", "hour", f"{GB}/data/tape/bars/MNQ/backfill_1hour.parquet"),
                         ("1day",  "day",  f"{GB}/data/tape/bars/MNQ/backfill_1day.parquet")):
    hdr(f"2. OVERLAP CHECK — HF NQ 1-min aggregated to {tf}  vs  our IBKR MNQ {tf}")
    q = f"""
    WITH hf AS (
      SELECT date_trunc('{bucket}', timestamp) AS t,
             max(high) AS h, min(low) AS l,
             last(close ORDER BY timestamp) AS c, sum(volume) AS v
      FROM {HF} GROUP BY 1),
    ours AS (
      SELECT to_timestamp(bar_ts) AT TIME ZONE 'UTC' AS t, high AS h, low AS l,
             close AS c, volume AS v
      FROM read_parquet('{ourf}'))
    SELECT hf.t, hf.c AS hf_close, ours.c AS ib_close, hf.c - ours.c AS d,
           hf.v AS hf_vol, ours.v AS ib_vol
    FROM hf JOIN ours USING (t) ORDER BY hf.t"""
    df = c.execute(q).df()
    if df.empty:
        print("NO OVERLAP"); continue
    d = df.d
    print(f"matched {tf} bars: {len(df):,}   span {df.t.iloc[0]} .. {df.t.iloc[-1]}")
    print(f"close correlation (Pearson) : {df.hf_close.corr(df.ib_close):.10f}")
    print(f"close diff  mean {d.mean():+.4f}  median {d.median():+.4f}  std {d.std():.4f}")
    print(f"            |d| p50 {d.abs().quantile(.5):.4f}  p95 {d.abs().quantile(.95):.4f}  "
          f"max {d.abs().max():.4f}")
    print(f"bars within 1 tick (0.25) : {(d.abs() <= 0.25).mean()*100:.2f}%")
    print(f"bars within 4 ticks (1.00): {(d.abs() <= 1.00).mean()*100:.2f}%")
    print(f"volume ratio HF/IB  median : {(df.hf_vol/df.ib_vol.replace(0, None)).median():.2f}  "
          "(NQ vs MNQ are different contracts — a ratio, not a match, is expected)")
    worst = df.reindex(d.abs().sort_values(ascending=False).index).head(8)
    print("\nworst 8 disagreements:")
    print(worst.to_string(index=False))

# ─────────────────────── 3. THE REGIME POINT — is it multi-regime? ─────────────
hdr("3. REGIME SPREAD — the reason we went looking")
print(c.execute(f"""
  WITH d AS (
    SELECT CAST(timestamp + INTERVAL 2 HOUR AS DATE) AS sess,
           first(open ORDER BY timestamp) AS o, last(close ORDER BY timestamp) AS c
    FROM {HF} GROUP BY 1)
  SELECT year(sess) AS y, count(*) AS sessions,
         round(first(o ORDER BY sess),1) AS open_yr, round(last(c ORDER BY sess),1) AS close_yr,
         round(100.0*(last(c ORDER BY sess)/first(o ORDER BY sess)-1),1) AS pct_change,
         round(100*stddev(ln(c/o)),3) AS daily_vol_pct
  FROM d GROUP BY 1 ORDER BY 1""").df().to_string(index=False))
print("\nOur own 1-min tape for comparison (2025-09-14 .. 2026-08-18):")
print(c.execute(f"""
  WITH d AS (
    SELECT CAST(to_timestamp(bar_ts) + INTERVAL 2 HOUR AS DATE) AS sess,
           first(open ORDER BY bar_ts) AS o, last(close ORDER BY bar_ts) AS c
    FROM read_parquet('{GB}/data/tape/bars/MNQ/backfill_1min.parquet') GROUP BY 1)
  SELECT count(*) AS sessions, round(first(o ORDER BY sess),1) AS open_first,
         round(last(c ORDER BY sess),1) AS close_last,
         round(100.0*(last(c ORDER BY sess)/first(o ORDER BY sess)-1),1) AS pct_change
  FROM d""").df().to_string(index=False))
c.close()
