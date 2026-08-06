# Memory index

- ★★★ **CRITICAL INFRA — READ `/root/CLAUDE.md` FIRST.** You are the PERMANENT GAZBOT V7 router (5-min). On start: verify `gazbot7-router-tick.timer` + `PINNED`; read the scored **bad-call ledger** + `tail router_trial_log.txt`. Review ledger ~4-hourly.

## Method rules (read before any study)
- [★★MFE is NOT a win rate](mfe-is-not-a-win-rate.md) — "reached N R" ignores whether the STOP came first. Compute the RACE.
- [★★Friday findings need ADVERSARIAL re-derivation](friday-findings-need-adversarial-rederivation.md) — 4 recs re-derived, 1 survived. Placebo/independent-tag/strip-best first.
- [★★Judge on EXPECTANCY not win-rate](friday-report-judge-on-expectancy-not-winrate.md) — kill only on robustness (placebo/strip-best/LOO/OOS); name WHICH test.
- [★Exit-lab paired method OVERSTATES](exit-lab-paired-method-overstates.md) — overlapping positions swing $5,076 vs sequential; biases toward tight Rs.
- [★Backtest per regime-segment NOT blanket](backtest-per-regime-segment-not-blanket.md) — score each config on its HOME tape; test the POLICY.
- [Sims on tick price, always](sims-on-tick-price.md) / [Backtest 5s+250ms](backtest-on-5s-250ms-persist-all.md) — 5s bars had 87% flush-loss; 250ms robust.
- [Shadow sim understates losses](shadow-sim-understates-losses.md) — live losses 1.1–3.1× modeled; every shadow loss = a FLOOR.
- [★RULE DuckDB+pandas for analytics](duckdb-pandas-for-analytics.md) — never raw sqlite row-loops; ATTACH READ_ONLY→window/ASOF→.df()
- [Verify desk facts — never guess](verify-desk-facts-never-guess.md) — curl/query LIVE first.
- [★★Operator wants FINAL deliverables only](operator-wants-final-deliverables-only.md) — no progress pings; one message when done. Exception: a blocker only he can clear.
- [★★★READ THE TAPE FIRST — shadow is CONFIRMATION, checked LAST](read-the-tape-first-shadow-is-confirmation.md) — the shadow board is BACKWARD-looking; leading with it trades the regime that just ended. On 08-06 it put the desk short at the low and flat through +297pt.
- [★★★GO FIND THE PRICE YOURSELF](go-find-the-price-yourself.md) — STANDING ORDER: query raw bars/ticks and build structure/VWAP/ATR yourself. Never form a view from desk_view, router_watch, open_hour_watch or the shadow table.

## Venue truth & costs
- [★★MNQ fee is $1.50/RT — never $5](mnq-fee-is-150-per-round-trip.md) — 487 fills. A fixed fee is REGRESSIVE on thin-edge gates. Grep every harness's fee constant.
- [★Cost-autopsy: desk bleeds DIRECTION not cost](execution-cost-autopsy-stage1.md) — passive-entry KILLED; STOP-slippage ≈$1,200 leak.
- [Futures trade multiplier recording](futures-trade-multiplier-recording.md) — exit multiplier defaults 1.0→wrong P&L; con_id backstop.
- [Futures contract roll](futures-contract-roll.md) — Sep'26; re-roll before ~2026-09-13 (MCL earlier).

## Router / regime judgement
- [★★★RUN STATE is the PRIMARY discriminator](run-state-is-the-primary-discriminator.md) — in-run aligned +$10.34/tr vs chop −$28.43/tr, a $39/tr spread; flat through 18 of 26 runs. `runstate.py` reports state, Claude decides. **⚠THE BENCH/ARM ASYMMETRY INVERTS INSIDE A RUN.** In-sample + late.
- [★★★ASIA (00-07 UTC) BENCHED PERMANENTLY + the 75-min window](session-time-blocks-mnq.md) — shadow n=1840 at −$3.17/tr. Config-level (`no_open_asia`), NEW ENTRIES ONLY. ⚠ "don't trade before the US open" was REFUTED (pre-open −$1.75 vs US −$1.93); LONDON is the desk's ONLY positive block. Expectancy lives 13:30-14:45 (+$8.93/tr, passes the full battery); the late session is NOT reliably bad.
- [★★Intelligent routing, NOT blanket benching](intelligent-routing-not-blanket-benching.md) — arming is half the job; flat through a window is a COST. Segregate by regime.
- [★★Some days STAY OUT (fully flat = a WIN)](some-days-stay-out-fully-flat.md) — violent roundtrip chop pays no one; go flat EARLY, don't thrash.
- [★★Validate a STAY-OUT with the shadow book](validate-stay-out-with-the-shadow-book.md) — sum the day's shadow = the counterfactual. A real ER/ATR break can still be untradeable.
- [★★US OPEN = don't bench the trend-rider](us-open-dont-bench-trend-rider.md) — on a trending day HOLD aligned momentum through open stop-outs; bench only if STRUCTURE breaks.
- [★★US OPEN = arm VETO-gates not CHURNERS](us-open-arm-veto-gates-not-churners.md) — veto-gates ≈0-cost armed; churners buy the reversal.
- [★Re-arm momentum needs ER-CLIMB not delta-blip](rearm-momentum-needs-er-climb-not-delta-blip.md) — judge REGIME, not one flow blip.
- [★★VOL-EXPANSION is the binding leg](vol-expansion-is-the-binding-leg.md) — sustained ER on ATR<~15 decays in 20-35min; fooled 2 ticks in one session. ⚠ER across the 21:00 halt is structurally inflated.
- [★Router-benching LESSONS](router-benching-lessons-0729.md) — bench by MECHANISM not side; SHADOW-FIRST; don't thrash grind.
- [★Router full-roster PIN = silent no-op](router-full-roster-pin-is-silent-noop.md) — check PINNED + last APPLIED, not just the timer.
- [★★Router trial DAY 2](router-trial-day2-findings-0730.md) — 07-29 +$638, 07-30 +$586. grind ER floor 0.35 real; abs_veto NO floor.
- [★Low-vol grind = UNTRADEABLE](low-vol-grind-untradeable-stay-flat.md) — flat at new highs is CORRECT. Re-arm only on ATR≥18.
- [★Router-tune TRIAL setup](router-tune-trial.md) / [★LIVE direction-router](direction-router-live.md) / [Router NOT managing exhaustion_short](router-exhaustion-short-null.md)
- [⚠Shadow board is NOT a regime router](shadow-board-as-regime-router.md) — title = the REJECTED idea; switching on shadow P&L is "trading the equity curve" (autocorr ≈0 momentum, −0.16 rgv). Shadow = incubation + correlation monitor ONLY. / [Direction × regime × gate](direction-regime-gate-enablement.md) / [Regime/chop-veto momentum](regime-chop-veto-momentum.md)
- [★Intraday gate-disable + hourly watch](intraday-gate-disable-hourly-sweep.md) — hour_watch.py 2-tier; auto-reactivate Paris midnight.
- [Regime detector impossible→passive](regime-detector-impossible-passive-pivot.md) — regime unpredictable at minute scale; react, don't predict.

## Gates & exits
- [★★★DAY RIDER live in PAPER from 08-06](day-rider-live-paper.md) — SECOND desk, own service+timers. Detect 13:38-14:09 (eff>=.15 & rt>=.45), 2 lots, trail armed at +150, **FLAT 20:40 UTC — never 21:00 (that IS the halt)**. NEVER HOLD OVERNIGHT. Anchor=cash open (CME anchor gives ZERO detections).
- [★★Exits are EXIT-PROOF — holding wins](exits-are-exit-proof.md) — 25 variants, 4 families, all ≤ holding. Stops impossible (winner MAEs to 511pt). Only the armed trail helps. The tail IS the price.
- [★★Dual-slot SCALE-OUT LIVE](dual-slot-scaleout-live.md) — every gate→Lot A fixed-R scalp + Lot B chandelier; also the per-gate EXIT OVERRIDES axis (`exit_overrides.json`). ★backtest exits UNRELIABLE 5-10x.
- [★★Quiet-tape CLIP live](quiet-tape-clip-live.md) — ATR<22 → both lots clip ($40 / 1.75R floored $60). Frozen at entry; nipc exempt.
- [★★Stop-width A/B 1.0 vs 2.0 LIVE](stop-width-ab-2x-live.md) — 1.5x REFUTED. ⚠exit_scalp COUPLES target to stop width. Config-epoch + k=1.0 reproduction check mandatory.
- [★★NIPC's $395 drag DIAGNOSED](nipc-395-drag-diagnosed.md) — trigger-TIMING 59% + one lost exit race 38%. NOT slippage. ⚠n=16.
- [★★exhaustion_short LIVE = roll-over FADER](exhaustion-short-live-fader-success.md) — judge LIVE not shadow. [counter-veto not ER-floor](exhaustion-short-counter-veto.md).
- [★abs_veto promoted to paper](abs-veto-live-promotion.md) — thrust+55s-veto; per-side chop-floor cut bleed −958→−68.
- [★LIVE per-gate ER favourable-condition gate](er-favourable-condition-gate-live.md) — grind FLOOR .35, abs_veto NO floor, capit/exh CEIL.
- [★Chandelier momentum-exit tuning](chandelier-momentum-exit-tuning.md) — tail beyond 2R = 52% of profit; tightening start_k=TRAP.
- [★Regime-3-exit selector LIVE](exit-selector-regime-live.md) — exit WIDTH by regime-at-entry. +$756 OOS.
- [★Gates two-sided + per-side tuning](gates-two-sided-per-side-tuning.md) — never relegate a direction, tune the SIDE.
- [★rgv tune+filter both dirs](rgv-tuning-both-directions.md) / [★Gate rehab findings](gate-rehab-findings-0725.md) — ER filters FAKE, ATR floors REAL.
- [★RULE Friday = gate REHABILITATION](friday-gate-rehabilitation-section.md) / [★Tournament changes = Saturdays only](tournament-changes-saturday-only.md)
- [Exit = scar tissue for bad entries](exit-architecture-scar-tissue.md) — on GOOD entries a simple exit wins; real work = ENTRIES.
- [Ratchet give-back 25% static LIVE](ratchet-giveback-leak-and-robustness.md) / [Ratchet studies all NEGATIVE](ratchet-giveback-width-study.md) / [Give-back exit finding](giveback-exit-finding.md)
- [Reversion book autopsy](reversion-edge-quiet-tape-gate-tuner.md) — reversion bleeds fading GRINDS; |slope|<0.15 veto.
- [Multi-gate priority + badge](multi-gate-priority-order.md) / [Promotion ladder sizing](promotion-ladder-sizing.md) / [Saturday promotion shortlist](saturday-promotion-shortlist.md)
- [Momentum amp floor A/B](momentum-amp-floor-ab.md) / [Filter-effectiveness monitor](filter-effectiveness-monitor.md) / [Chop-scalp study](chop-scalp-study.md)
- [Friday deep-dive rg_long_fast_v](friday-rev-fast-vol-deep-dive.md) / [grind_fast](friday-grind-fast-deep-dive.md) / [Monday shadow build queue](monday-shadow-build-queue.md)
- [Continuation entry status](continuation-entry-status.md) — RETIRED shadow; revive=VWAP-anchor+RVOL/ATR floors.
- [ORB rising-bounce bug](orb-gate-rising-bounce-bug.md) — DISARMED. [Shorts re-enable cluster](shorts-reenable-cluster.md).

## NULL results — do not re-derive
- [★★MGC momentum greenfield = NULL](mgc-momentum-greenfield-null.md) — gold's runs are SIZE-predictable (ATR d=+0.80, ER30 d=+0.43) but DIRECTION-unpredictable: slope and 15/30/60-min breaks all ~+2pp over the best CONSTANT. 5/72 cells positive, best strips to $16. Needs a new information source, not retuning.
- [★Run-catcher NULL — microstructure](run-catcher-null-all-microstructure.md) — ROBUST NULL on 22.6M ticks: run START unpredictable.
- [★OFI delay-VETO on grind = the one surviving book cell](ofi-veto-grind-lead.md) — grind_long d=15s −$172→+$772. Book VETOES, does not SELECT. In-sample lead — do NOT arm.
- [MCL different-beast gate sweep](mcl-different-beast-gate-sweep.md) — MCL 2× vol, event-driven; reversion bleeds it.
- [Crypto momentum study](crypto-momentum-study.md) — signal +EV, crypto retired.

## Incidents & infrastructure
- [★★★MD_STREAM is MULTI-SYMBOL — consumers MUST filter](md-stream-multi-symbol-filter.md) — MGC bars folded into the MNQ deque: ATR 1848 vs true 15. A CONFIG change armed a latent bug in 3 files. `protection.held` says a stop EXISTS, not that it is SANE.
- [★★Trade data_quality flag + killswitches are OFF](trade-data-quality-flag.md) — honest P&L must filter `WHERE data_quality IS NULL` (rows 538/539 = the MD_STREAM −$255.50). ⚠ `max_daily_loss_usd`/`loss_streak_halt` are BOTH 0, so sweep's "headroom OK" is vacuous.
- [Sweep the mechanism not outcomes](pipeline-health-monitor-the-mechanism.md) — safety nets masked a DEAD fill path 8h; every safety-net activation = ALARM.
- [Execution integrity = standing check](execution-integrity-standing-check.md) — through-rate counted SUBMITS not fills→desk dead 4h.
- [★Orphan-stop→phantom→halt](orphan-stop-phantom-incident.md) / [Orphan stop / optimistic cancel](orphan-stop-optimistic-cancel.md) / [Position-orphan entry_atr cascade](position-orphan-entry-atr-cascade.md)
- [Naked position from silent auditor skip](naked-position-silent-auditor-skip.md) / [Naked-stop event poke](naked-stop-event-poke.md) — BUILT DARK.
- [★STOP_UNFILLED = ContFuture stops don't trigger](stop-unfilled-contfuture-root-cause.md) — fix NOT deployed, needs live verify.
- [Broker watchdog + cron-liveness](broker-watchdog-and-cron-liveness.md) / [Futures order-status sync gap](futures-order-status-sync-gap.md) / [/positions stale-empty ≠ phantom](positions-stale-empty-not-phantom.md)
- [Futures session-flat routing bug](futures-session-flat-exchange-routing.md) — FIXED. [Projector con_id dedup](projector-conid-dedup-scope.md) — MERGED.
- [Stop-coverage false-naked fix](stop-coverage-false-naked-fix.md) / [EOD-flatten no-open-window fix](eod-flatten-no-open-window-fix.md) / [Locked-profit + reattach-entry](locked-profit-and-reattach-entry-fix.md) — all on branch, NOT deployed.
- [Ratchet restart peak-loss fix](ratchet-restart-peak-loss-fix.md) / [Phantom-trade audit J17](phantom-trade-audit-j17.md) / [V-LEDGER Phase 4](vledger-phase4-completion.md) — half-cut-over.
- [GAZBOT V7 three-service architecture](gazbot-v7-three-service-architecture.md) — core+md+strategy, VENUE-TRUTH-FIRST.
- [DAYTRADE_FLAT_CLOCK=20min](daytrade-flat-clock-20min.md) / [Weekend = no flatten, no fuss](weekend-no-flatten-no-fuss.md) / [Backup timeout DB>4GB](backup-timeout-db-4gb.md)
- [Force-kill dormant + wobble](force-kill-dormant-and-resweep.md) / [Force-kill recal + MGC pullback](mgc-pullback-clock-regression.md) / [Per-contract entry+exit tuning](mes-entry-pullback-vol-ceiling.md)
- [Shadow-sim + desk resource throttle](shadow-sim-and-desk-resource-throttle.md) / [Brain-retire J-rules→janitor](brain-retire-janitor-migration.md)

## Data, capture & reporting
- [Analytics capture roadmap](analytics-capture-roadmap.md) — capture the EPHEMERAL; L2 depth capture filled the microstructure gap.
- [Desk reading LIVE L2 book — SCOPED](desk-l2-book-consumption-scope.md) — book exists but desk doesn't read it; MVP=book-aware absorption cut.
- [Observe-only tick capture](observe-only-tick-capture-and-promotion.md) — bar-backtests ARTIFACTS; dense tick fixes.
- [MGC gold feed RESOLVED](mgc-gold-frozen-feed.md) — real-time COMEX ticks live; do NOT auto-exclude.
- [MNQ-specialist capture experiment](mnq-specialist-capture-experiment.md) — REBOOT: docker restart alphabot-gateway→MD bounce.
- [Edge-spectrum pipeline](edge-spectrum-pipeline.md) / [Rapid walk-forward tool](rapid-walkforward-tool.md) / [Courtroom vs live signal mismatch](courtroom-vs-live-signal-mismatch.md)
- [★Friday report max-depth workflow](friday-report-runs-tonight-maxdepth.md) / [= SHADOW DESK pipeline](friday-report-full-pipeline-guarantee.md) / [= Scientific Journal](three-pass-adversarial-friday.md)
- [★Friday report: stats=TABLES, but RUN CHARTS loved](friday-report-tables-not-charts.md) — chart the runs w/ entry+exit marked. MNQ-only ~80pg, don't pad.
- [★Nightly router+selector review](nightly-router-selector-review.md) / [Nightly self-analysis + TELL ME HOW](nightly-self-analysis-and-tell-me-how.md)
- [★V7 dashboard routing + reports](v7-dashboard-routing-and-restore.md) — STABLE URL dashboard.gazbot.dev/v7 (never mint new).
- [Warn before dashboard restart](warn-before-dashboard-restart.md) — drops the operator's tab. [CUBE tab deployed](cube-tab-deployed.md).
- [/api/futures/performance header gotcha](futures-performance-header-parse.md) — P&L strip=json['header']['today'].
- [Trading desk brochure](trading-desk-brochure.md) — "update brochure"→re-SCAN code.

## Direction of travel
- [★North-star desk GREEN by end Aug](desk-green-by-end-august-goal.md) — green by end Aug 2026, forward-validated.
- [Favourable-condition gating (north star)](favourable-condition-gating-vision.md) — per (contract×gate) learn winning conditions, only trade when met.
- [Strategy-layer reframe](strategy-layer-reframe.md) — REGIME-first, mechanism-over-threshold, stop adding gates, measure FORCE.
- [Go-live drop MNQ+MGC (historical)](golive-drop-mnq-mgc.md) — margin ~$30k; re-add as balance grows.
- [Regime badge vs ATR gate](regime-badge-vs-atr-gate.md) — badge=prior gap, gate=intraday ATR.
