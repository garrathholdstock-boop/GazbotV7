# DATA ACQUISITION — a multi-regime MNQ tape
**2026-09-12 (Sat, venue shut) · data-engineering pass · ACQUISITION, not analysis**

## THE ONE-LINE ANSWER

**YES — and the multi-regime MNQ tape is already on disk and in the lake, for $0.**
A public, MIT-licensed **NQ 1-minute set covering 2015-01-01 → 2025-07-25 (3,666,547 bars,
2,740 CME sessions)** was pulled, validated against an independent referee, and landed as day
partitions under `data/tape/bars/NQ/`. It costs nothing, and it spans the 2018 vol shock,
the COVID crash, the 2022 bear (−32.5%) and the 2023-24 recovery. The remaining gap
(2025-07-25 → 2025-09-14, and MNQ/MGC intraday before 2025) closes for **≈$7 of metered usage
on Databento, inside its $125 signup credit** — i.e. $0 out of pocket, one account signup.

---

## 1. WHAT WAS ACTUALLY PULLED  (all free, nothing paid, nothing signed)

| dataset | symbol / tf | rows | span | where it landed |
|---|---|---|---|---|
| HuggingFace `mdelcristo/NQ-F_1min_OHLCV_Parquet` | **NQ 1min** | **3,666,547** | 2015-01-01 → 2025-07-25 | `data/external/hf_nq1min/` → `data/tape/bars/NQ/` |
| Yahoo chart API `NQ=F` | NQ 1day | 6,560 | 2000-09-18 → 2026-09-11 | `data/external/yahoo/` → `data/tape/bars/NQ/` |
| Yahoo chart API `GC=F` | GC 1day | 6,532 | 2000-08-30 → 2026-09-11 | → `data/tape/bars/GC/` |
| Yahoo chart API `^NDX` | NDX 1day | 6,713 | 2000-01-03 → 2026-09-11 | → `data/tape/bars/NDX/` |
| FirstRate free samples (NDX / SPX / QQQ 1min) | — | 210k (QQQ) | 2022-09-30 → 2023-09-29 | `data/external/firstrate/` — kept as a cross-check only |

Disk: **+112 MB**, 24 GB free after. Nothing paid, no account created, no credential entered,
no IBKR/gateway connection, no `gazbot7-*` service touched.

### Is it real data?
Every independent sanity marker lands:

* 2020 low **6,628.8** (true COVID NQ low ≈6,628) · 2021 high **16,767.5** (ATH ≈16,764) ·
  2022 low **10,484.8** (bear low ≈10,440).
* **Zero** malformed OHLC rows (`high<low`, `close` outside range) in 3.67M bars. **Zero** zero-volume bars.
* Hour-of-day volume profile is textbook CME index futures: trough 03-05 UTC (Asia lull),
  spike at 13:30 UTC (US cash open), second peak 19-20 UTC (equity close) — and the
  **daily maintenance halt shows up as a half-empty 21:00 UTC bucket that migrates with US DST**.
  You do not get that by accident.
* Session census: **2,740 sessions, ZERO holes >4 calendar days**, median 1,365 bars/session,
  16 short sessions (= US half-days and holidays).
* Roll gaps: 0-5 overnight gaps >100 pt per year, max 35-77 pt in 2015-19 scaling to 304-404 pt
  in 2024-25 — i.e. **unadjusted front-month stitched, quarterly roll visible**, the same
  convention our own tape uses. ⚠ Roll days must be excluded or handled by any study.

---

## 2. THE OVERLAP CHECK — and the thing it uncovered

The mission asked for an overlap correlation against our own lake. **It could not be run the
obvious way, and the reason matters more than the check.**

The new set ends **2025-07-25**; our own MNQ **1-minute** tape begins **2025-09-14**.
There is no 1-minute overlap at all. The natural fallback — compare against our MNQ **1-hour**
and **1-day** backfill, which *do* overlap by 7 and 10 months — **failed by 300-700 points.**

So the first question was not "is the new source good" but **"which tape is wrong"**.

### ★★★ TEST THAT SETTLES IT WITHOUT ANY EXTERNAL SOURCE
Our own 1-hour bars vs our own 1-minute bars — same symbol, same broker, same lake:

```
   n  mean_diff     sd  max_abs  pct_within_1_tick
5483    -392.64 255.72  1004.25              17.89
```

**Two files in our own lake disagree by a mean of 393 points.** They cannot both be right.

### WHY — root cause, confirmed
`backfill_history.py` could only pull expiries **IBKR still lists**. Every contract that was
front-month before ~Oct-2025 had expired and been purged, so it is simply **absent** from
`data/backfill/`. `backfill_to_lake.py` then deduped on `bar_ts` *"keeping the FIRST — the
front-month print"*. With the real front months missing, the first available file is a
**DEFERRED** expiry:

| date | our lake `backfill_1day` | source file | true front (Yahoo NQ=F) | error |
|---|---|---|---|---|
| 2024-09-23 | 20,786.25 (**volume 0, o=h=l=c**) | `MNQ_20251219` — Dec-2025, then **15 months out** | 20,080.00 | **+706** |
| 2024-09-23 | `MNQ_CONTFUT` = 21,388.50 | IBKR continuous | 20,080.00 | **+1,308** |

`backfill_1day`: **76 of 483 bars have volume 0 and open==high==low==close.**
`backfill_1hour`: **1,346 of 8,683 zero-volume, 2,008 flat-OHLC.**

### SCORED AGAINST AN INDEPENDENT REFEREE (Yahoo NQ=F front-month daily, free, 2000-2026)

```
             tape    n  level_corr  mean_diff  median_abs_diff  pct_within_25pt
HF NQ 1-min (new) 2655    0.999962       2.73             6.75             82.1
    OUR MNQ 1-min  233    0.999398      15.11            16.00             67.0
    OUR MNQ 1-day  479    0.997949     269.81           225.25             47.8
```

Daily **return** correlation (the real test — level correlation is trivially ~1 on a trending
series) HF vs referee: **0.92-0.96 every year**, with realised vol matching to 2 decimals
(2022: 1.955% vs 2.042%; 2024: 1.170% vs 1.170%).

**VERDICT: the new source is USABLE and scores BETTER against the referee than our own tape does.
Our long-dated MNQ daily/hourly history is NOT usable and must be withdrawn from research.**

> ⚠ **CORRECTION TO A DESK FACT.** The claim *"the longest series this desk owns is 483 daily bars
> (~1.9 years)"* is wrong in the direction that matters. Of those 483, only the **158 bars from 2026**
> match the front month (corr **1.000000**, mean diff **0.05**, 99.4% within 5 pt). The other 325 are
> a deferred-contract blend. The desk owned **~8 months** of trustworthy daily history, not 1.9 years.
> This is [[an-instrument-that-reports-healthy-about-something-it-does-not-check]] again: the file
> existed, the row count was right, `coverage()` reported it, and every bar was from the wrong contract.

---

## 3. THE REGIME PROBLEM — measured, before and after

| year | sessions | year change | daily vol |
|---|---|---|---|
| 2015 | 269 | +8.3% | 1.09% |
| 2016 | 258 | +5.9% | 1.00% |
| 2017 | 257 | +30.9% | 0.65% |
| 2018 | 258 | **−0.8%** | **1.37%** |
| 2019 | 259 | +38.2% | 1.01% |
| 2020 | 258 | +46.8% | **2.23%** ← COVID |
| 2021 | 259 | +26.7% | 1.18% |
| 2022 | 259 | **−32.5%** | **1.99%** ← the bear |
| 2023 | 258 | +52.9% | 1.08% |
| 2024 | 259 | +24.8% | 1.12% |
| 2025 (part) | 146 | +10.2% | 1.67% |
| **our own tape** | **240** | **+21.4%** | — |

Our entire 1-minute history is one +21.4% bull leg. The new set contains **a −32.5% year, a
−0.8% year, and two years at ~2% daily vol** — the regimes that were structurally absent.

**The Mesfin 2026 replication window (947 trading days, 2021-2025) is now fully covered:
2021-01-01 → 2025-07-25 is ~1,140 sessions of 1-minute bars.**

---

## 4. WHAT IT WOULD COST TO CLOSE THE REST

Priced honestly for a solo desk running micros on ~$30k. A $2,000/yr data bill is **6.7% of the
account** — it is not a rounding error and nothing here recommends one.

| rank | buy | unlocks | cost | verdict |
|---|---|---|---|---|
| **1** | **Nothing.** Use what was pulled tonight. | 2015-2025 NQ 1-min, 4 regimes, 2,740 sessions | **$0** | **DO THIS FIRST.** It answers the question that is currently blocking every research line. |
| **2** | **Databento**, pay-as-you-go, **$70/GB** OHLCV-1m | MNQ (from 2019-04-14), NQ + GC (from 2010-06-06), MGC — native, licensed, roll-documented, plugs the 2025-07→09 hole and gives *our actual contract* rather than NQ | **≈$7**, inside the **$125 signup credit** → **$0 out of pocket** | **DO THIS SECOND.** Requires creating an account and storing a card (not charged). I did not sign up — that is the operator's call. |
| 3 | FirstRate Data one-off futures bundle | perpetual, buy-once NQ/GC 1-min | low hundreds, perpetual | Only if Databento's credit runs out. Perpetual licence is the attraction. |
| 4 | CME DataMine Time & Sales | CME-electronic back to **1992-06-26**, COMEX to 1999-12-01 | **unpublished, quote-only**; per-product per-month, 12-month prepaid = 2 months free; all sales final | **Only if research genuinely needs pre-2010.** No bar product exists at any price — you buy trade prints and resample. ⚠ Volume semantics changed in **2011** and again in **2015**; a 2010-2026 volume series silently crosses two definition changes. |
| 5 | Massive (ex-Polygon.io) | futures GA only 2026-05-28; history to 2017 | **$199/mo** to reach past Sep-2021 | **NO.** $2,388/yr for less history than tonight's free pull. |
| — | Nasdaq Data Link / Quandl | — | — | **REFUTED.** CHRIS, SCF, SRF, CME, OWF all 404; database discovery returns 410 Gone; docs retired 2026-08-31; clients unmaintained since 2022. It never sold intraday CME bars anyway. |

**Recommendation, ranked by (evidence unlocked)/(dollars + effort): take rank 1 now, rank 2 when
the operator is willing to create one account. Buy nothing else.**

---

## 5. THE LOADER — `scripts/external_to_lake.py`

Lands an external tape in the lake's own `bars` schema
(`symbol, timeframe, bar_ts, open, high, low, close, volume`).

### ★★★ The trap it avoids, which `backfill_to_lake.py` only dodges by luck
`lake.connect()` reads a symbol's parquet **only if `_lake_days()` finds at least one
`YYYY-MM-DD.parquet`**:

```python
lake_days = _lake_days(stream, symbol)   # DAY-NAMED basenames only
if lake_days:                            # <-- THE GATE
    parts.append("... read_parquet('{base}/bars/{symbol}/*.parquet')")
```

`backfill_1min.parquet` does not parse as a date, so it contributes nothing to `lake_days`.
For MNQ/MGC the glob still fires **because `tape_mirror.py` has been laying down day partitions
nightly for weeks** — the backfill rides in on their coat-tails. For a brand-new symbol like NQ
with no nightly mirror, `lake_days` is empty, the gate is false, and a perfectly correct 43 MB
file is **never read**. That is the 2026-08-18 failure (*"pulled data nobody can query is the same
as not pulling it"*), one directory further along.

→ **So this loader writes day partitions.** Verified via the real API, not by reading the diff:

```
── gazbot7.lake.coverage() for NQ ──
  bars  days=7190  weeks=1438.0  lake=7190  span=2000-09-18..2026-09-11  gaps=3

── gazbot7.lake.connect(symbol='NQ') sees ──
timeframe       n
     1min 3666547
     1day    6560
```

Other things it gets right, each because getting it wrong is silent:
* **`--merge`** — a day partition is per *(stream, symbol)*, **not per timeframe**. Landing the
  daily series into a symbol that already holds 1-minute day files must UNION, never overwrite:
  a plain `COPY` would delete that day's 1-minute bars and leave a file that still reads fine.
* **Live capture wins** — an existing day file is never overwritten by an external source unless
  `--force`, which is correct only for a symbol the desk does not itself capture (NQ, not MNQ).
* **Write-verify** — row count read back after every `COPY`, mismatch deleted, plus `--audit` to
  drop anything a killed run left truncated (one corrupt parquet fails the **whole glob**, making
  the entire symbol unqueryable).
* **Stage once, then slice** — the naive per-day loop re-read all 11 sources and re-ran the dedupe
  window function 3,287 times: measured **13 s/day ≈ 12 hours**. Staging into one temp table first
  is the identical output in **22 seconds**. Memory-capped at 700 MB with spill to `data/duckdb_tmp`.

### Usage
```
PYTHONPATH=src .venv/bin/python scripts/external_to_lake.py --source hf_nq1min --force
PYTHONPATH=src .venv/bin/python scripts/external_to_lake.py --source yahoo_1d --file NQF_1d.csv --symbol NQ --merge
PYTHONPATH=src .venv/bin/python scripts/external_to_lake.py --verify --symbol NQ
```

---

## 6. CAVEATS ON THE NEW TAPE — read before using it

1. **It is NQ, not MNQ.** Same index level, same tick, different multiplier ($20/pt vs $2/pt) and
   different liquidity. Fine for signal/regime research; **do not** take its volume or spread as
   MNQ's. Any P&L must use MNQ's own **$1.50/RT**.
2. **Provenance is unstated.** The HF repo carries an MIT licence and no README beyond it. It is
   validated by behaviour (referee + structure + sanity markers), not by a vendor guarantee.
   Treat it as a **research tape, never as venue truth** — IBKR remains the truth.
3. **Unadjusted, stitched front month.** Roll gaps are real and visible ~4×/year. Exclude roll days
   or handle the gap; an overnight-gap study run naively will find the roll and call it an edge.
4. **224 duplicated timestamps** in the raw set (0.006%) — the loader keeps the higher-volume print.
5. **Gap 2025-07-25 → 2025-09-14** between this tape and our own. Do not assume contiguity across
   that seam; it is the same shape as the documented V5→V7 tick hole.
6. **Gold is daily-only.** No free COMEX gold intraday source was found. GC 1-day 2000-2026 is
   landed; **MGC intraday before 2025-07 remains open** and is the strongest argument for the
   Databento signup.
7. **Inode cost**: the daily-only symbols (GC, NDX) are 6,532 / 6,713 one-row files each, ~26 MB.
   Ugly but required by the lake's day-partition gate, and trivial against 24 GB free.

## 7. ACTIONS FOR THE DESK (not taken tonight — operator's call)

1. **Quarantine `data/tape/bars/MNQ/backfill_1day.parquet` and `backfill_1hour.parquet`** and any
   study that read them. They are a deferred-contract blend before 2026. The 1-minute file is fine.
2. **Fix `backfill_to_lake.py`'s dedupe** — `QUALIFY row_number() OVER (PARTITION BY bar_ts ORDER BY ts)`
   orders by the partition key itself, so the `ORDER BY` is a **no-op tie** and "keep the FIRST" resolves
   to file read order, not the front month. It must rank by expiry-vs-bar-date (or by volume).
3. **Never re-derive the 483-daily-bar figure.** It is ~158.

---

## 8. ★★★ THE TAPE WORKS — AND IT IMMEDIATELY CONTRADICTED A FOUNDING NUMBER

The acquisition's whole justification was: *"a 60-minute long entered at a RANDOM time in the London
session makes **+11.25 pt/trade** on our tape — every long-side result here is contaminated by drift."*

First thing done with the new tape: run that test on **both tapes with identical code** —
overlapping minute-start entries, London 07:00-11:59 UTC, hold exactly 60 minutes, require the exit
bar to be exactly 60 minutes later.

```
OUR MNQ 1-min (2025-09-14..2026-08-18)       n= 72,000  mean=  +1.506 pt/trade  sd=54.05
NEW NQ 1-min (2015-01-01..2025-07-25)        n=767,697  mean=  +0.128 pt/trade  sd=25.67
NEW NQ 1-min, 2021-2025 (Mesfin window)      n=353,030  mean=  +0.076 pt/trade  sd=33.49
```

**Two findings, and they point opposite ways.**

1. ✅ **THE CONTAMINATION IS REAL.** Our one-regime tape pays a random London long **12×** what a
   multi-regime tape pays (+1.506 vs +0.128), and at **2.1× the dispersion**. By year the
   multi-regime figure flips sign — 2018 −0.07, 2022 −0.16, 2025 −1.13 against 2024 +0.90. A
   long-side result tuned on our window is fitted to a drift that does not survive out of regime.
   The acquisition was the right call.

2. ⚠ **BUT +11.25 pt/trade DOES NOT REPRODUCE.** The same construction on the same tape gives
   **+1.506**, about 7× smaller. A sanity bound agrees with the small number: our tape ran
   24,351 → 29,560 over 240 sessions = **+21.7 pt/session**, and a 60-minute slice of a ~23-hour
   session cannot be worth half of that. Whoever derived +11.25 was measuring something else —
   a different hold length, a different bar size, per-session rather than per-minute entries, or
   dollars rather than points. **Re-derive it before it is used or quoted again.**
   [[a-live-instruments-founding-number-must-be-re-derived]] — tunnel_watch's 1.75× shipped,
   ran 9 hours, and was 1.02×. This is the same shape, caught before it shipped.

The direction of the argument survives; the magnitude does not. Nothing here should be quoted at
+11.25.

---

## 9. PROVENANCE CHALLENGE — "isn't that HF set just scraped Yahoo?"

A reasonable objection was raised: the repo is named `NQ-F`, which implies accumulated Yahoo `NQ=F`.
**If true it would void the whole validation, because Yahoo daily was my referee** — I would have been
scoring a tape against its own source. Tested three ways; the hypothesis fails all three.

1. **Yahoo pads, this tape omits.** Yahoo returns a full session grid with `null` closes for empty
   minutes. This set has **zero** null/zero-volume bars and a *variable* bar count per session
   (2023: min 1,138, mean 1,371.5, only 217 of 257 sessions at the full 1,380). Minutes with no
   trades are **absent**, which is the signature of a trade-aggregated exchange feed, not a Yahoo grid.
2. **The big gaps are news, not rolls.** If it were unspliced Yahoo, the largest overnight gaps
   would land on the four quarterly roll dates. The actual top gaps are **2025-04-14 (+404),
   2025-04-07 (−383), 2025-02-03 (−371), 2025-06-13 (−356), 2022-02-28 (−288)** — the April-2025
   tariff shock and the Feb-2022 invasion. Those are real market events.
3. **Volume reconciles to NQ's true ADV.** 2019 **419k/day**, 2022 **638k/day**, 2024 **571k/day** —
   correct magnitude *and* correct trend for NQ. A scrape of Yahoo's unreliable minute volume would
   not land there.
4. **Mechanically, it could not have been built.** Yahoo's 1-minute endpoint is hard-capped at
   ~8 days per request and **~30 days of lookback** (HTTP 422 beyond — measured). A 2015-2025
   1-minute series cannot be retrieved from it retroactively at all; it would require ten years of
   uninterrupted daily scraping.

**The referee stands.** Provenance is still formally unstated and the tape is still validated by
behaviour rather than by a vendor guarantee — caveat 2 in §6 holds — but it is not a Yahoo derivative.
