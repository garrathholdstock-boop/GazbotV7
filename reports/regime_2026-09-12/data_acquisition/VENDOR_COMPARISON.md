# VENDOR COMPARISON — deep CME futures history for MNQ/NQ + MGC/GC
**2026-09-12 · prices as published on that date · quote-only means genuinely unpublished, not "I didn't look"**

## THE TABLE

| source | earliest 1-min (NQ / MNQ) | gold (GC / MGC) | bars | cost | perpetual? | licence for an individual | free sample big enough to test on? | bulk/API | continuous documented? |
|---|---|---|---|---|---|---|---|---|---|
| **★ HuggingFace `mdelcristo/NQ-F_1min…`** | **NQ 2015-01-01** / none | none | 1-min | **$0** | yes, MIT | MIT, unrestricted | **★ IT IS THE WHOLE DATASET** — 3.67M bars, 2,740 sessions | direct parquet download | no — unadjusted stitched front month, roll gaps visible |
| **★ Databento** | NQ 2010-06-06 / **MNQ 2019-04-14** (inception) | GC 2010-06-06 / MGC 2010-09-12 | ohlcv 1s/1m/1h/1d, trades, mbp, mbo | **$70/GB rate card; ≈$1–20 for 5yr MNQ+NQ+GC+MGC 1-min** | no (metered, but files are yours) | **"a license is not required for historical data"** — no CME fee, no pro/non-pro | **$125 signup credit**, expires 6 months after signup — covers the whole pull 6× over | `databento` py client, batch flat files, DBN/CSV/JSON | **yes** — `.v.0` volume / `.c.0` calendar / `.n.0` open-interest roll. **Not** back-adjusted |
| **★ Portara / CQG Data Factory** | **NQ (ENQ) 1999-06-21** / MNQ 2019-05-06 | **GC 1987-09-03** / MGC 2010-09-17 | tick + 1-min up | **$180 / 20yr, $220 / from inception, PER SYMBOL, one-off** | **yes, perpetual** | one-off purchase, no expiry clause | per-symbol sample viewer (browser, not bulk) | flat files, roll service + formatting included | **yes** — back/forward/ratio/zero-adjusted, configurable roll |
| **Kibot** | NQ 2009-09-27 / MNQ 2019-05-05 | GC 2009-09-27 / **MGC 2010-10-03** | tick, 1s–60m, daily+ | **one-off lifetime: Top-10 1-min $220 (⚠ NQ+GC only, NO micros) · All-futures continuous $520 · +individual contracts $820** | **yes, lifetime** | ⚠ **two computers only**, internal use, no redistribution | ⚠ **equities/ETFs only — NO free futures sample.** Guest account returns `402 Unauthorized` for NQ. Buy-before-you-see | `api.kibot.com` CSV, no header | **unadjusted only**, but **roll offsets published** (ES/NQ 5 days pre-expiry; micros 1 day; GC/MGC 2 days from prior month-end) |
| **FirstRate Data** | **NQ 2008-01-02** / MNQ 2019-05-05 | GC 2008-01-31 / ⚠ **MGC bundle-only, start unpublished** | 1m/5m/30m/1h/1d, no futures tick | ⚠ **archive price is checkout-only/geo-priced.** Published: updates $99.95/yr per ticker, $59.95/mo most-active bundle, $79.95/mo complete bundle | one-off archive + optional paid updates | derivative works OK; no raw republication; single organisation only | **yes — 2 weeks** of real NQ/MNQ/GC 1-min: `frd001.s3.us-east-2.amazonaws.com/frd_sample_futures_{NQ,MNQ,GC}.zip` | zipped CSV, no header | 3 variants (unadjusted/absolute/ratio) but ⚠ **roll trigger published nowhere** |
| **TickData (OneMarketData→KX)** | NQ trades **1999-07** / MNQ 2019-05 | **GC trades 1984-01** / MGC 2010-10 | **ticks only — you build bars** | $180/symbol-yr, $65 at 30+; $1,250 full history 1 symbol. ⚠ **$1,000 minimum first order + $250/yr delivery fee** | yes, no delete-on-expiry | internal modification/aggregation OK, no redistribution | no | self-serve store, TickWrite 7 builds bars + continuous | **yes** — multiple roll methods, ratio + merge-back-adjusted |
| **IQFeed / DTN** | ~2005–2007 for all contracts | same | 1-min, 180d tick (⚠ **8 days** in RTH) | **≈$138/mo** all-in non-pro ($108.15 core + $24.87 futures + $5.25 CME) + $50 startup | **no — live feed, data stops when you stop paying** | ⚠ non-pro waiver requires a **trade-capable third-party front-end**; a bare `pyiqfeed` script does not qualify | 4 days intraday on trial | socket port 9100, `pyiqfeed` | `@NQ#` / `@NQ#C` ⚠ reportedly rolls on **expiry**, not volume — build your own |
| **Barchart** | ~10 years | ~10 years | 1-min via site; API `nearbyMinutes` | Premier **$29.95/mo, $199.95/yr**; OnDemand API **from $500/mo** | no | site ToS forbids automating the download | 30-day Premier trial; free tier is **daily only** | ⚠ **10,000 records per request** = ~7 Globex days → 340+ manual pulls per symbol | stitched, **not** back-adjusted |
| **Massive (ex-Polygon.io)** | 2017 at best | 2017 | 1-min aggregates, S3 flat files | $29/$79/**$199** per mo for 2/5/7+ yrs | no | standard | free tier exists | S3 flat files + REST | advertised, undocumented in the API reference |
| **Norgate Data** | ⚠ **NONE — daily/EOD only** ("we do not provide … intra-day or 'tick' data") | daily NQ 1999-07-12, GC 1979-10-30 | daily only | $148.50/6mo, $270/yr | ⚠ **NO — "data … extracted from it must be deleted after a subscription has expired"**, no written exception | personal use only, no commercial licensing | — | ⚠ NDU is **Windows-only** and must be running | yes, genuinely good — but daily |
| **CME DataMine** | Time&Sales **CME-electronic 1992-06-26** | **COMEX 1999-12-01** | ⚠ **no bar product at any price** — trade prints, resample yourself | ⚠ **unpublished, quote-only.** Per product/month, 1–12 months, 12-month prepaid = 2 free. All sales final | yes | Time&Sales redistribution unrestricted (BBO/Depth may NOT be redistributed) | per-dataset single-day sample files (⚠ could not be verified — cmegroup.com timed out) | REST v2 (⚠ v1 endpoints retired 2025-10-23), SFTP, push-to-S3 | **none** — every expiry, roll it yourself |
| **Dukascopy** | ⚠ **NOT CME.** `USATECHIDXUSD` is Dukascopy's own **cash-index CFD**, m1 from 2011-09 | ⚠ `XAUUSD` is **spot gold**, not COMEX. No gold CFD exists | m1, ticks | $0 | n/a | **no licence exists at all** — nothing grants rights | unlimited | `datafeed.dukascopy.com/.../BID_candles_min_1.bi5` ⚠ **month is ZERO-INDEXED**, closed hour = **200 with 0 bytes**, divisor ÷1000 | n/a — a CFD has no roll |
| **Yahoo v8 chart API** | daily NQ=F 2000-09-18 | daily GC=F 2000-08-30 | 1d unlimited; **1m capped ~8d/request, ~30d lookback**; 1h 730d | $0 | yes | unstated | daily is genuinely unlimited | `query1.finance.yahoo.com/v8/finance/chart/NQ%3DF` (cookie + crumb) | **no splice at all** — a fabricated gap 4×/yr |
| **Nasdaq Data Link / Quandl** | ⚠ **REFUTED** — CHRIS/SCF/SRF/CME/OWF all 404, discovery returns 410 Gone, docs retired 2026-08-31, clients dead since 2022 | — | was **daily only, never intraday** | — | — | — | — | — | — |
| Stooq | ⚠ returns **HTTP 200 with an EMPTY BODY** from this box (PoW/bot wall); `i=` accepts only d/w/m/q/y anyway | — | daily only | $0 | — | Barchart-sourced, i.e. redistributed | no | — | — |
| Alpha Vantage · EODHD · Tiingo · Finnhub · Twelve Data · Marketstack · Intrinio | ⚠ **none carry CME futures.** "Commodities" endpoints are FRED macro series or XAU/USD spot | — | — | — | — | — | — | — | — |
| FRED | ⚠ **carries no futures prices at all** — in FRED "future" means a survey expectation | — | — | — | — | — | — | — | — |
| Kaggle `tgtanalytics/nq-futures-1min-bar-2022-2025` | NQ 2022-12 → 2025-12, ~1.05M rows | none | 1-min | $0, CC0 | yes | CC0 | whole dataset | needs a Kaggle account | no |
| Kaggle `choweric/cme-nasdaq` + `comex-gc` | daily **per-contract OHLC + OPEN INTEREST 2000-2022** | yes | daily | $0, CC BY-SA 4.0 | yes | CC BY-SA | whole dataset | needs a Kaggle account | ★ this is how you BUILD a correct roll calendar |
| Academic mirrors (WRDS, LSEG Tick History, Datastream, Bloomberg) | institution-gated | — | — | — | — | ⚠ **no public mirror of CME intraday exists — the licence forbids redistribution, which is why** | no | — | — |

## FREE SAMPLES BIG ENOUGH TO TEST A HYPOTHESIS ON

1. **★ HuggingFace NQ 1-min 2015-2025 — the only one that is a research corpus rather than a teaser. PULLED AND VALIDATED TONIGHT.**
2. **Databento's $125 signup credit** — technically a free trial, and it is ~6× the whole cost of everything this desk needs. Requires an account and a card on file (not charged). Not taken: that is the operator's call.
3. Kaggle NQ 1-min 2022-2025 (CC0) and the per-contract open-interest dailies — the latter is the missing ingredient for a correct roll calendar.
4. FirstRate 2-week futures samples — enough to inspect a vendor's tape before buying, not enough to test on.
5. Yahoo daily, unlimited, 2000→now. **Pulled tonight** for NQ=F, GC=F, ^NDX.
6. Dukascopy — unlimited but it is a CFD, usable as a bar-*structure* proxy only.

## THREE TRAPS TO CARRY INTO ANY INGEST

1. **SILENT-EMPTY RESPONSES, FOUR VENDORS, ZERO ERRORS.** Yahoo `MGC=F` 1-min returns 7,200 timestamps with ~99% **null** closes. Investing.com `PT1M` returns `{"data":[]}`. Dukascopy closed hours return **HTTP 200 with a zero-byte body**. Stooq returns **HTTP 200 with an empty body** to blocked clients (confirmed from this box). In every case `status == 200` and a non-empty array both report healthy. **Assert on non-null BAR COUNT, never on status.** This is [[an-instrument-that-reports-healthy-about-something-it-does-not-check]] arriving from outside the building.
2. **EVERY "CONTINUOUS" SERIES IS A CONSTRUCTION, AND THEY DISAGREE.** FirstRate publishes no roll rule; Kibot is unadjusted with fixed calendar offsets; Barchart stitches without adjusting; IQFeed's `#C` reportedly rolls on *expiry* rather than volume; Yahoo does not splice at all. Build continuous from individual months and **assert the result** — do not trust the label.
3. **THESE ARE ALL DIFFERENT TAPES.** Databento's bars come from CME MDP 3.0 trade events, Portara's from CQG consolidation, Dukascopy's from one broker's OTC book. [[the-labs-tape-is-not-productions-tape]]: re-measure any survivor against what the desk actually reads before anything routes off it.
4. ⚠ **CME's Time & Sales volume semantics changed in 2011 (unbundling) and again in 2015 (MDP 3.0 Trade Summary re-consolidation).** A volume series spanning 2010-2026 built from raw T&S silently crosses two definition changes.

## COST TO CLOSE THE GAP — ranked by (evidence unlocked) / (dollars + effort)

| rank | action | unlocks | cost | effort |
|---|---|---|---|---|
| **1** | **nothing — use tonight's free pull** | NQ 1-min 2015-2025, 2,740 sessions, 4 regimes | **$0** | **done** |
| **2** | **Databento PAYG** | MNQ 2019→now + NQ/GC 2010→now + MGC, *our actual contracts*, licensed, explicit roll, plugs the 2025-07→09 hole | **≈$1–20, inside the $125 credit → $0 out of pocket** | one signup, card on file, ~1 hour of code. ⚠ credit expires 6 months after signup — **do not sign up until ready to pull** |
| 3 | **Portara**, MNQ+NQ+GC+MGC | NQ back to **1999**, gold to **1987** — regime coverage no API vendor sells; perpetual, roll service included | **$880 one-off** ($220 × 4) | low |
| 4 | Kibot All-Futures 1-min | 83 symbols incl. MNQ + MGC, lifetime | **$520 one-off** | ⚠ two-computer licence; no futures sample to inspect first |
| 5 | FirstRate | NQ/GC from **2008** | unpublished | ⚠ no MGC standalone; no roll rule published |
| — | IQFeed $138/mo · Barchart $199/yr–$500/mo · Massive $199/mo · TickData $1,250+ · Norgate $270/yr | — | **$1,600–$6,000/yr** | **NO.** On a ~$30k account a $2k/yr data bill is **6.7% of equity** — it must clear a bar none of these clear when ranks 1–3 cost $0–$880 once. |

**RECOMMENDATION: rank 1 is already done and unblocks the research now. Take rank 2 when the
operator is willing to create one account — it is the only route to *our own contract* (MNQ/MGC)
at depth, and it is free. Consider rank 3 only if a perpetual, no-vendor-relationship copy going
back to 1999/1987 is wanted. Buy nothing else.**
