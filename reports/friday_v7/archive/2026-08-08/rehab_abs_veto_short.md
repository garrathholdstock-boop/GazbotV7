# REHAB — `abs_veto_short`

**Target:** the week's worst bleeder. 11 closes, 11 losers, −$814.50, across four sessions.
**Data:** `data/gazbot7.db` (live trades) · `data/shadow.db` (tick-repriced shadow book) · `data/capture.db` (5s tape, 17 trading days 2026-07-16 → 08-07, 23,625 minutes) · `data/router_trial_log.txt` + `data/gate_switches.env` + `data/open_hour_alerts.log` (the arming ledger).
**Cost basis:** $2.00/point, $1.50/round-turn, 1 lot. Every number below is tick-honest.
**Working:** `scratchpad/rehab_avs/` (feat.py · ledger.py · enrich.py · sweep.py · robust.py · exitsweep2.py · stopcheck.py · lag.py · burst.py · recon.py).

---

## THE SHORT VERSION

The brief I was given said: *"the leak is WHEN it is allowed to trade, not what it trades — the arming policy is selecting the gate's losing minutes. Widen the leash or give it the k10 stop width its best shadow uses."*

Half of that is right and half of it is wrong, and the wrong half matters.

**Wrong half #1 — "give it the k10 stop width."** It already has it. I read the live slate build and the live `abs_veto_short` runs Lot A = fixed 1.5R scalp on a 1.0×ATR stop and Lot B = fixed 2.5R scalp on a 1.0×ATR stop, plus the quiet-tape clip. That is `sw_absS_A_k10` and `sw_absS_B_k10` **exactly** — same entry, same targets, same stop, same clip. The best shadow in the family is not running a different exit from the live gate. It is running the *same* exit at *different moments*. So that rehab angle is a NULL before a single number is computed, and I should say so plainly rather than sweep it up.

**Wrong half #2 — "the arming policy is selecting the losing minutes."** I tested it directly and it is not true. Inside the exact windows where the router had the gate armed, the identically-configured shadow twin made **+$289.50 on 6 fires (+$48.20 a trade)**, against **+$19.70 a trade** in all the minutes the gate was benched. Every single armed window that produced a shadow signal at all was **green**. The router picked good minutes. The money did not leak at the arming decision.

**Right half — the leash.** The gate was armed for **224 minutes out of 6,780** in the week. That is **3.3% of the tape**, in ten windows averaging 22 minutes, the shortest of them three minutes long. In the other 96.7% the same signal, on the same exit, made **+$1,064.50**. That is where the money is.

**And the thing nobody put in the brief:** **36% of the −$814.50 is not the strategy at all.** −$255.50 of it is the MD-stream ATR corruption (the desk's own `data_quality` field already says `EXCLUDE`), and −$35.50 is the phantom LONG opened by an orphaned market close on a gate called *short*. Strip both and the true strategy book is **−$523.50 on four signals**. Four. On a gate whose 17-day, four-ISO-week expectancy is **+$14.40 a trade over 159 fires**.

**Verdict: FIXED.** The signal is proven, the exit is proven, the malfunctions are named and already fixed in code, and the one thing left to change is the arming policy — which should stop being a 22-minute discretionary window and start being a standing permission with one proven veto. Exact config in the last section.

---

## 1 · NORMALIZE THE MALFUNCTIONS

Three things happened this week that are not `abs_veto_short` trading.

### 1a — The 08-04 22:02 pair: a phantom signal from corrupted market data (−$255.50)

At 17:30 on 08-04 gold (MGC) was added to the capture stream. `tournament.py` folded **every** symbol on `MD_STREAM` into the MNQ bar deque, so 3,300-handle gold bars interleaved with 29,800-handle MNQ bars. ATR read **1,848.16** against a true **15.11** — 122× — and every ATR-relative threshold in the gate went with it. The five-bar "thrust" the gate saw was a ~26,500-point drop from MNQ to gold. It was not a down-thrust. It was a symbol change.

The desk opened two lots with stops **1,848 points away instead of ~15**, i.e. ~$3,700 of risk per lot instead of ~$30. With no working stop both lots rode two hours to the `MAX_HOLD` clock.

| | |
|---|---|
| As booked | **−$255.50** (2 × MAX_HOLD) |
| Reconstructed on the 5s tape with a working 1.0×ATR stop (ATR 15.11) | both lots stop at 22:05:00, **−$63.44** |
| **Cost of the malfunction** | **−$192.06** |
| Did the signal even exist? | **No.** The whole shadow desk was up that night (310 fires on 08-04) and **not one** abs-veto variant fired at 22:02. The nearest shadow fires were `rg_short` at 22:18 and 22:23 with ATR 10.9 and 8.1 — i.e. a normal, quiet tape. |

So the honest treatment is not "normalize the stop", it is **strike the trade**. There was no thrust. `pnl.py` already excludes it at source (`data_quality IS NULL` clause, added 08-05). Worth noting for the tooling audit: the open-hour watcher reported this gate at −$387.50 when the true figure was −$132.00 and recommended a bench on a number 3× too large — the same alert is quoted in the brief.

### 1b — The 08-07 13:30 phantom LONG on a SHORT gate (−$35.50)

Trade 585: `gate = abs_veto_short_B`, `side = LONG`. A market BUY placed to close the short was *forgotten* rather than cancelled when the slot's own stop won the race, and it filled 1.4 seconds later into a flat slot — opening a brand-new long on a gate named short, which a protective sell-stop was then armed for. The sequence is documented to the millisecond in `multislot_core.py` and the cancel-on-close bugfix plus a phantom-entry backstop are already shipped. Not a strategy trade.

### 1c — What did NOT go wrong

No `STOP_UNFILLED`, no naked rides, no system stops in this week's book. The nine STOPs all filled. The stop-fill defect that plagued the 07-26/27 overnight batch did not recur here.

### The normalized book

| | closes | net |
|---|---:|---:|
| RAW as booked | 11 | **−$814.50** |
| less (a) MD-stream ATR corruption — struck, no valid signal | 2 | +$255.50 |
| less (b) phantom LONG — not a strategy trade | 1 | +$35.50 |
| **TRUE STRATEGY BOOK** | **8** | **−$523.50** |

Eight closes = **four signals × two lots**. Every one a STOP. Zero winners.

---

## 2 · CORRECTED-COST RECONSTRUCT

I re-derived every row from the prices rather than trusting the field.

| # | gate | side | points | ×$2/pt | −$1.50 fee | recorded | delta |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | abs_veto_short_A | SHORT | −61.50 | −123.00 | −124.50 | −124.50 | 0.00 |
| 2 | abs_veto_short_B | SHORT | −64.75 | −129.50 | −131.00 | −131.00 | 0.00 |
| 3 | abs_veto_short_A | SHORT | −32.25 | −64.50 | −66.00 | −66.00 | 0.00 |
| 4 | abs_veto_short_B | SHORT | −32.25 | −64.50 | −66.00 | −66.00 | 0.00 |
| 5 | abs_veto_short_A | SHORT | −34.75 | −69.50 | −71.00 | −71.00 | 0.00 |
| 6 | abs_veto_short_B | SHORT | −34.75 | −69.50 | −71.00 | −71.00 | 0.00 |
| 7 | abs_veto_short_A | SHORT | −22.00 | −44.00 | −45.50 | −45.50 | 0.00 |
| 8 | abs_veto_short_B | SHORT | −41.25 | −82.50 | −84.00 | −84.00 | 0.00 |
| 9 | abs_veto_short_A | SHORT | −29.00 | −58.00 | −59.50 | −59.50 | 0.00 |
| 10 | abs_veto_short_B | SHORT | −29.50 | −59.00 | −60.50 | −60.50 | 0.00 |
| 11 | abs_veto_short_B | **LONG** | −17.00 | −34.00 | −35.50 | −35.50 | 0.00 |

**0 of 11 rows need restating.** The live book is already booked at $2/point net of $1.50/RT; $16.50 of fees over 11 round turns. There is no hidden cost story here — the −$814.50 is real money, it is just not all *strategy* money.

---

## 3 · ROOT CAUSE — BASE, EXIT, or SIGNAL?

### 3a — The SIGNAL is the strongest thing on the desk. It is not the problem.

`abs_veto_55s` short side, tick-repriced, 17 trading days, four ISO weeks:

| | n | net | win% | $/trade |
|---|---:|---:|---:|---:|
| **All 17 days** | 159 | **+$2,290.50** | 48.4% | +$14.40 |

Robustness on that book:

| test | result |
|---|---|
| strip best 1 / 3 / 5 trades | +$2,100.50 / +$1,780.00 / +$1,484.50 |
| leave-one-day-out, worst | drop 07-29 → **+$1,889.00** |
| per ISO week | wk29 **+$325.50** · wk30 **+$497.00** · wk31 **+$659.00** · wk32 **+$809.00** |
| days green | 14 of 17 |
| out-of-sample | fit wk29–31 +$1,481.50 → untouched wk32 **+$809.00** |
| per regime | NORMAL-CHOP +$660 · TREND-NOBREAK +$656 · CLEAN-TREND +$484 · VIOLENT-WHIPSAW +$358 · BUILDING +$132 — **positive in every one** |

Four weeks, every week green. Every regime green. Survives strip-3 and every leave-one-day-out. Rising week on week. This is not a signal in trouble.

### 3b — The EXIT is already the proven one. The brief's suggested fix is a NULL.

I read the live slate build (`slot_strategy.scaleout_slots` + `data/exit_overrides.json`) rather than assuming:

| | live `abs_veto_short` | shadow `sw_absS_*_k10` |
|---|---|---|
| entry | thrust thr 1.5, amp_floor 0.0004, 55s absorption veto | identical |
| Lot A | fixed **1.5R** scalp, stop **1.0×ATR** | `sw_absS_A_k10` — 1.5R, k 1.0 |
| Lot B | fixed **2.5R** scalp, stop **1.0×ATR** | `sw_absS_B_k10` — 2.5R, k 1.0 |
| quiet-tape clip | atr_split 22 / A $40 / B 1.75R floored $60 | same |

They are the same configuration. "Hand it the k10 stop width its best shadow uses" is **already done** — it has been the live config since the scale-out slate went in.

And the k10 width is the right one. The desk's own tick-repriced stop-width A/B, restricted to the 28 entries where all four arms traded:

| arm | net | win% | $/trade |
|---|---:|---:|---:|
| sw_absS_A_k10 | +$528.50 | 64.3% | +$18.90 |
| sw_absS_A_k20 | +$452.50 | 67.9% | +$16.20 |
| sw_absS_B_k10 | **+$882.00** | 57.1% | **+$31.50** |
| sw_absS_B_k20 | +$665.50 | 57.1% | +$23.80 |
| **pair k1.0 (LIVE)** | **+$1,410.50** | | |
| pair k2.0 | +$1,118.00 | | |

The live width wins by **$292.50**. Leave it alone.

### 3c — So where did −$523.50 come from? Three things, in order of size.

**(i) The leash is 3.3% of the tape.** Ten arming windows totalling 224 minutes out of 6,780. Mean window 22 minutes, shortest 3 minutes. Six of the ten windows produced no live trade at all, and eight of the ten produced no *shadow* signal either — the gate was switched on and off around minutes in which its own signal never fired. That is the churn problem, and at $0 per non-firing switch it is invisible on any per-decision scoreboard.

**(ii) The four signals it did take are a four-trade sample.** On a gate with a +$14.40/trade expectancy and a ~48% win rate, four consecutive stopped signals is unremarkable. It is roughly a 1-in-14 run. It reads as catastrophic only because the leash is so narrow that four trades *is* the whole week.

**(iii) The live desk enters one bar behind its own twin — and this week that draw went badly.** This is the finding I got wrong first and had to correct, so I am showing both passes.

*First pass (4 signals, this week):* on all four real signals the live gate entered on a **later bar** than the shadow twin and at a materially worse price — mean **27.28 points worse**, $54.56 a lot. On eight lots that is ~$436, which would be 83% of the loss. Tempting story.

*Second pass (78 matched entries, whole live abs_veto history, both sides):* the lag is real and it is universal — **median 61 seconds, one full bar** — but the *price penalty* is nothing like 27 points:

| | |
|---|---|
| n | 78 matched live entries |
| lag | median **61s**, mean 59s |
| entry penalty | median **+1.88pt**, mean **+3.44pt**, stdev **10.54pt** |
| p10 / p90 | −6.75pt / +16.25pt |
| worst / best | −26.50pt / +36.25pt |
| mean cost of the lag | **$6.87 a lot**, 1-sd band −$14 to +$28 |
| live worse than twin | 45 of 78 (58%) |

This week's four short signals drew +18.50, +36.25, +10.25, +1.75 — mean +16.69pt, which is **2.51 standard errors** above the population mean. **The lag is systematic; its cost this week was a bad draw from a wide distribution.** I am not going to let the four-trade version stand as the explanation.

Netting it out: at a neutral entry draw the four signals would still have lost roughly **−$256**. Four losing signals on a positive-expectancy gate. That is variance, arriving inside a 3.3% leash that gave it nowhere to recover.

**Root cause: not the BASE, not the EXIT, not the SIGNAL. The bleed is (1) two named software malfunctions worth 36% of it, and (2) an arming policy so tight that four trades of ordinary bad luck become the entire week's record — while the same signal, unrouted, made +$1,354.00 across the same five days.**

---

## 4 · THE HEADLINE TEST — armed minutes vs benched minutes

This is the test the brief asked for: run the continuously-firing shadow against the router's armed window.

**Exact-config twin (`sw_absS_A_k10` + `sw_absS_B_k10`), week 08-03 → 08-07:**

| | n | net | win% | $/trade |
|---|---:|---:|---:|---:|
| **ARMED** (gate could trade) | 6 | **+$289.50** | 66.7% | **+$48.20** |
| **BENCHED** (gate stood down) | 54 | **+$1,064.50** | 57.4% | +$19.70 |
| whole week, unrouted | 60 | **+$1,354.00** | 58.3% | +$22.60 |

The same split across five independent members of the family (different exits, same signal), pooled: **ARMED 12 fires +$765.50 (+$63.80/tr)** vs **BENCHED 152 fires +$2,450.50 (+$16.10/tr)**.

**The armed minutes were, if anything, the BEST minutes of the week — four times better per trade than the benched ones.** n is small (6 twin fires), so the honest claim is the negative one: **there is no evidence the arming policy selected losing minutes, and every armed window that produced a signal was green.**

### Every arming decision, and what it bought

Shadow column = the 5-strategy family pool (`sw_absS_A_k10`, `sw_absS_B_k10`, `abs_veto_55s`, `thrust_short_absveto55`, `cx_absSB_live`) — five independent exits on the same entry, so a green window is green on five different exit rules, not one.

| window (UTC) | mins | who armed it | shadow fires | shadow net | live |
|---|---:|---|---:|---:|---|
| 08-04 22:00 → 22:45 | 46 | **auto re-arm** (Paris-midnight `reactivate_gates`; router's 22:00 tick left it on) | 0 | $0 | the corrupted pair, −$255.50 |
| 08-05 13:32 → ~14:45 | 73 | **operator** do-not-bench override | 4 | **+$541.00** | 2 signals, −$274.00 |
| 08-05 20:00 → 20:35 | 35 | router (new day low, ER 0.06→0.31) | 0 | $0 | — |
| 08-06 08:15 → 08:30 | 15 | router (fresh day low 29450) | 0 | $0 | — |
| 08-06 11:05 → 11:20 | 15 | router (bias DOWN −189, ER 0.38) | 0 | $0 | — |
| 08-06 13:20 → 13:34 | 13 | router (shadow evidence, ER 0.19) | 8 | +$224.50 | 1 signal, −$129.50 |
| 08-07 13:20 → 13:31 | 11 | Claude session, after operator challenge (RUN SHORT) | 0 | $0 | 1 signal, −$120.00 + phantom |
| 08-07 14:06 → 14:09 | 3 | Claude session (confirmed break) | 0 | $0 | never fired |
| 08-07 14:15 → 14:20 | 5 | router (RUN-FADING SHORT) | 0 | $0 | never fired |
| 08-07 16:27 → 16:35 | 9 | Claude session (RUN SHORT declared) | 0 | $0 | never fired |
| **TOTAL** | **224** | 10 decisions | **12** | **+$765.50** | **−$814.50** |

Two things jump out of that table.

**The 08-04 pair was not a router decision at all.** The Paris-midnight `reactivate_gates` cron re-arms every off gate at 22:00 UTC on zero tape ("insufficient bars, range 0pt, day P&L flat" — the router's own words at 22:00:22 that night). It re-armed `abs_veto_short`, the corrupt thrust fired **two minutes later**, and the router did not bench it again until 22:45. A blind automatic re-arm into a 45-minute unsupervised window is a real defect independent of everything else in this report.

**The 08-05 pair was not a router decision either.** The router had the gate benched. An operator "DO-NOT-BENCH" carve-out armed it at 13:32 and explicitly removed the router's bench authority; the router's own logs through 14:00–14:35 read *"tape is still chop (day-ER 0.03, last-hr ER 0.04, ATR 39) with no break trio to arm any momentum gate into… the 13:32 override keeps abs_veto_short armed."* It watched the gate bleed and said so, and could not act. So **−$529.50 of the −$814.50 was booked in windows the router did not choose.**

### Per day — what the desk got vs what was on the table

| day | armed mins | live n | live $ | normalized $ | twin n | twin $ | abs_veto_55s $ |
|---|---:|---:|---:|---:|---:|---:|---:|
| 08-03 | 0 | 0 | $0 | $0 | 0 | $0 | −$4.00 |
| 08-04 | 46 | 2 | −$255.50 | **$0** | 0 | $0 | +$106.00 |
| 08-05 | 108 | 4 | −$274.00 | −$274.00 | 16 | **+$514.00** | +$309.00 |
| 08-06 | 43 | 2 | −$129.50 | −$129.50 | 30 | +$258.50 | +$49.50 |
| 08-07 | 27 | 3 | −$155.50 | −$120.00 | 14 | **+$581.50** | +$348.50 |
| **WEEK** | **224** | **11** | **−$814.50** | **−$523.50** | **60** | **+$1,354.00** | **+$809.00** |

---

## 5 · FILTERS — 54 filters tested, all 54 shown

Rule of the house: a filter that "wins" by dropping the target's winners is a fake win. The 15 biggest winners in the 159-fire book carry **+$1,664.00 of the +$2,290.50 (73%)**, so the winner-retention column is the one that decides.

Full sweep table (17 days, `abs_veto_55s` SHORT, tick-repriced). **strip-3** = net after removing the three best kept trades. **wk-green** = how many of the four ISO weeks the kept book is positive in.

| policy | keep n | keep $ | $/tr | win% | cut n | cut $ | cut $/tr | top-15 kept | strip-3 | wk-green |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **00 BASELINE — continuous fire, no arming filter** | 159 | **+2290.5** | +14.4 | 48.4% | 0 | 0.0 | — | **15/15** | +1780.0 | **ALL** |
| R1 router CHOP_OFF (ER30≥0.15 & \|net30\|≥30) | 99 | +1026.5 | +10.4 | 44.4% | 60 | **+1264.0** | +21.1 | 10/15 | +518.5 | ALL |
| R2 CHOP_OFF + direction (aligned short only) | 90 | +880.0 | +9.8 | 43.3% | 69 | **+1410.5** | +20.4 | 10/15 | +372.0 | ALL |
| R3 router "UP≥+40 bench shorts" (day-bias) | 126 | +1307.0 | +10.4 | 44.4% | 33 | +983.5 | +29.8 | 13/15 | +799.0 | ALL |
| R4 router violent-whipsaw bench (ATR≥19 & ER30<0.25) | 140 | +1933.0 | +13.8 | 48.6% | 19 | +357.5 | +18.8 | 8/15 | +1425.0 | ALL |
| R5 router "arm trio" (new extreme + ER rising + vol up) | 31 | +618.0 | +19.9 | 54.8% | 128 | **+1672.5** | +13.1 | 4/15 | +286.0 | ALL |
| **R6 ALL router rules stacked (R2+R3+R4)** | 67 | +881.0 | +13.1 | 44.8% | 92 | **+1409.5** | +15.3 | **8/15** | +373.0 | **3/4** |
| E0.10 ER30 ≥ 0.10 | 125 | +1723.5 | +13.8 | 48.0% | 34 | +567.0 | +16.7 | 13/15 | +1215.5 | ALL |
| E0.15 ER30 ≥ 0.15 | 101 | +1146.0 | +11.3 | 45.5% | 58 | +1144.5 | +19.7 | 10/15 | +638.0 | ALL |
| E0.20 ER30 ≥ 0.20 | 81 | +1081.0 | +13.3 | 46.9% | 78 | +1209.5 | +15.5 | 9/15 | +573.0 | ALL |
| E0.25 ER30 ≥ 0.25 | 66 | +1098.0 | +16.6 | 48.5% | 93 | +1192.5 | +12.8 | 8/15 | +590.0 | ALL |
| **E0.30 ER30 ≥ 0.30** | 51 | +1140.5 | **+22.4** | 52.9% | 108 | **+1150.0** | +10.6 | **7/15** | +632.5 | ALL |
| E0.35 ER30 ≥ 0.35 | 36 | +927.5 | +25.8 | 55.6% | 123 | +1363.0 | +11.1 | 5/15 | +493.0 | ALL |
| E0.40 ER30 ≥ 0.40 | 23 | +552.0 | +24.0 | 52.2% | 136 | +1738.5 | +12.8 | 3/15 | +187.0 | ALL |
| F0.20 ER15 ≥ 0.20 | 111 | +1769.5 | +15.9 | 49.5% | 48 | +521.0 | +10.9 | 12/15 | +1261.5 | ALL |
| F0.30 ER15 ≥ 0.30 | 90 | +1500.5 | +16.7 | 50.0% | 69 | +790.0 | +11.4 | 11/15 | +1015.0 | ALL |
| F0.35 ER15 ≥ 0.35 | 76 | +1237.0 | +16.3 | 50.0% | 83 | +1053.5 | +12.7 | 10/15 | +802.5 | ALL |
| F0.40 ER15 ≥ 0.40 | 64 | +1014.5 | +15.9 | 50.0% | 95 | +1276.0 | +13.4 | 7/15 | +580.0 | ALL |
| F0.50 ER15 ≥ 0.50 | 38 | +437.5 | +11.5 | 47.4% | 121 | +1853.0 | +15.3 | 4/15 | +106.0 | 3/4 |
| A11 ATR14 ≥ 11pt | 159 | +2290.5 | +14.4 | 48.4% | 0 | 0.0 | — | 15/15 | +1780.0 | ALL |
| **A13 ATR14 ≥ 13pt** | 117 | +2031.5 | +17.4 | 49.6% | 42 | +259.0 | **+6.2** | **15/15** | +1521.0 | ALL |
| **A15 ATR14 ≥ 15pt** | 82 | +1829.0 | +22.3 | 52.4% | 77 | +461.5 | **+6.0** | **15/15** | +1318.5 | ALL |
| **A17 ATR14 ≥ 17pt** | 57 | +1530.0 | +26.8 | 54.4% | 102 | +760.5 | +7.5 | **15/15** | +1019.5 | ALL |
| A19 ATR14 ≥ 19pt | 39 | +1036.5 | +26.6 | 51.3% | 120 | +1254.0 | +10.4 | 15/15 | +526.0 | ALL |
| A22 ATR14 ≥ 22pt | 20 | +496.5 | +24.8 | 45.0% | 139 | +1794.0 | +12.9 | 9/15 | **−14.0** | 2/2 |
| A25 ATR14 ≥ 25pt | 11 | +405.0 | +36.8 | 45.5% | 148 | +1885.5 | +12.7 | 5/15 | **−105.5** | 2/2 |
| **C19 ATR14 < 19pt (ceiling)** | 120 | +1254.0 | +10.4 | 47.5% | 39 | +1036.5 | +26.6 | **0/15** | +1037.0 | ALL |
| C22 ATR14 < 22pt | 139 | +1794.0 | +12.9 | 48.9% | 20 | +496.5 | +24.8 | 6/15 | +1535.5 | ALL |
| C25 ATR14 < 25pt | 148 | +1885.5 | +12.7 | 48.6% | 11 | +405.0 | +36.8 | 10/15 | +1616.5 | ALL |
| C30 ATR14 < 30pt | 151 | +1712.5 | +11.3 | 47.7% | 8 | +578.0 | +72.2 | 10/15 | +1443.5 | ALL |
| C35 ATR14 < 35pt | 152 | +1645.5 | +10.8 | 47.4% | 7 | +645.0 | +92.1 | 10/15 | +1376.5 | ALL |
| X2 extension cap: skip if 30m leg > 2 ATR | 56 | +917.5 | +16.4 | 50.0% | 103 | +1373.0 | +13.3 | 5/15 | +529.5 | 3/4 |
| X3 extension cap > 3 ATR | 79 | +1041.5 | +13.2 | 48.1% | 80 | +1249.0 | +15.6 | 6/15 | +653.5 | ALL |
| X4 extension cap > 4 ATR | 100 | +1203.5 | +12.0 | 48.0% | 59 | +1087.0 | +18.4 | 6/15 | +815.5 | ALL |
| X5 extension cap > 5 ATR | 127 | +1498.5 | +11.8 | 47.2% | 32 | +792.0 | +24.8 | 10/15 | +1036.0 | ALL |
| X6 extension cap > 6 ATR | 143 | +1890.5 | +13.2 | 49.0% | 16 | +400.0 | +25.0 | 12/15 | +1428.0 | ALL |
| X8 extension cap > 8 ATR | 158 | +2319.5 | +14.7 | 48.7% | **1** | −29.0 | −29.0 | 15/15 | +1809.0 | ALL |
| V0.8 participation ≥ 0.8× 4h base | 111 | +1964.5 | +17.7 | 50.5% | 48 | +326.0 | +6.8 | 14/15 | +1454.0 | ALL |
| V1.0 participation ≥ 1.0× | 86 | +1381.5 | +16.1 | 47.7% | 73 | +909.0 | +12.5 | 12/15 | +871.0 | 3/4 |
| V1.2 participation ≥ 1.2× | 65 | +1419.0 | +21.8 | 52.3% | 94 | +871.5 | +9.3 | 11/15 | +908.5 | ALL |
| V1.5 participation ≥ 1.5× | 38 | +1119.0 | +29.4 | 55.3% | 121 | +1171.5 | +9.7 | 9/15 | +608.5 | ALL |
| S0.9 ATR ≥ 0.9× session base | 132 | +2033.5 | +15.4 | 48.5% | 27 | +257.0 | +9.5 | 15/15 | +1523.0 | ALL |
| S1.0 ATR ≥ 1.0× session | 111 | +1490.5 | +13.4 | 45.9% | 48 | +800.0 | +16.7 | 15/15 | +980.0 | 3/4 |
| S1.1 ATR ≥ 1.1× session | 79 | +1565.0 | +19.8 | 50.6% | 80 | +725.5 | +9.1 | 15/15 | +1054.5 | ALL |
| S1.3 ATR ≥ 1.3× session | 45 | +1262.0 | +28.0 | 55.6% | 114 | +1028.5 | +9.0 | 12/15 | +751.5 | ALL |
| D2 dwell: ER30≥0.30 in ≥2 of last 5 min | 42 | +973.5 | +23.2 | 54.8% | 117 | +1317.0 | +11.3 | 5/15 | +539.0 | ALL |
| **D3 dwell ≥3 of 5** | 27 | +937.0 | **+34.7** | 63.0% | 132 | **+1353.5** | +10.3 | **4/15** | +502.5 | ALL |
| D4 dwell ≥4 of 5 | 21 | +757.5 | +36.1 | 61.9% | 138 | +1533.0 | +11.1 | 3/15 | +323.0 | ALL |
| G1 drop BUILDING regime entirely | 116 | +2158.5 | +18.6 | 51.7% | 43 | +132.0 | +3.1 | 14/15 | +1648.0 | ALL |
| **★ G2 drop BUILDING × US-SESSION only** | **151** | **+2497.5** | **+16.5** | 50.3% | **8** | **−207.0** | **−25.9** | **15/15** | **+1987.0** | **ALL** |
| G3 drop PRE-OPEN (12:00–13:30Z) | 139 | +2101.5 | +15.1 | 48.9% | 20 | +189.0 | +9.4 | 15/15 | +1591.0 | ALL |
| T1 US-SESSION only | 44 | +951.0 | +21.6 | 47.7% | 115 | +1339.5 | +11.6 | 11/15 | +440.5 | ALL |
| T2 OVERNIGHT only | 84 | +1015.0 | +12.1 | 48.8% | 75 | +1275.5 | +17.0 | 4/15 | +761.5 | ALL |
| T3 drop PRE-OPEN + BUILDING×US | 131 | +2308.5 | +17.6 | 51.1% | 28 | −18.0 | −0.6 | 15/15 | +1798.0 | ALL |
| T4 ER-rising confirm (ER30 up on 5 min ago) | 110 | +1702.5 | +15.5 | 49.1% | 49 | +588.0 | +12.0 | 12/15 | +1194.5 | ALL |

### What that wall of numbers says

**1. The single best policy is NO POLICY.** 54 filters tested; **53 of them lose money against just letting it fire.** The baseline's +$2,290.50 is beaten exactly once.

**2. Every router-style rule is a fake win, and R6 fails out of sample.** The stacked router rules (R6) raise nothing, cut **+$1,409.50** of live money, throw away 8 of the 15 biggest winners, and — the killer — go **in-sample wk29–31 +$903.50 → out-of-sample wk32 −$22.50**. Fitted on the weeks that made it look sensible, negative on the week it was actually run in. That is the definition of a policy that should not be steering money.

**3. ER floors are FAKE — again.** E0.30 looks lovely at $22.40 a trade against the baseline's $14.40. It gets there by binning **7 of the 15 biggest winners** and leaving **$1,150** on the table. Same shape at every rung from 0.15 to 0.40. This is the desk's standing finding ("ER filters FAKE, ATR floors REAL") reproducing itself on a fifth gate; the recurring reason is that ER measures how *clean* the last thirty minutes were, and a thrust worth trading is precisely a thing that has *just* made the last thirty minutes look messy.

**4. Dwell requirements are the same fake, harder.** D3 hits $34.70 a trade — the best per-trade number in the entire sweep — by keeping **4 of 15** winners and dropping **$1,353.50**.

**5. The ATR floor is REAL but it is not free.** A13/A15/A17 keep **15 of 15** winners while lifting $/trade from $14.40 to $17.40/$22.30/$26.80. That is a genuine, plateau-shaped, winner-preserving improvement in *efficiency* — and it still costs $259/$461/$760 of net. It buys fewer trades for the same money, not more money. It breaks at 22 (strip-3 goes negative, 9/15 winners). **Honest verdict: a slot-contention lever, not a P&L lever.** Do not deploy it to fix a bleed it does not fix.

**6. The ATR *ceiling* is the most instructive failure in the table.** C19 — bench the gate above 19pt ATR — keeps **0 of the 15 biggest winners**. Zero. The gate's whole edge lives in high-ATR tape.

**7. The extension cap is REFUTED for the short side.** This was the flagged rehab question carried over from 07-26 ("skip entry when net already > N·ATR"). At every cap that bites (2/3/4/5/6 ATR) it destroys money and drops winners; the only cap that is net-positive (X8) removes exactly **one** trade in 17 days. There is no exhaustion-chase to cut on this side of the gate over this sample.

### The one filter that survived — drop BUILDING × US-SESSION

**BUILDING** = 30-minute ER between 0.15 and 0.30 — the in-between tape that is neither chop nor a run. In the US session (13:30–20:00 UTC) that specific cell is the only genuinely negative pocket the gate has.

| | n | net | $/trade | top-15 winners kept |
|---|---:|---:|---:|---:|
| baseline | 159 | +$2,290.50 | +$14.40 | 15/15 |
| **drop BUILDING × US-SESSION** | **151** | **+$2,497.50** | **+$16.50** | **15/15** |
| what it cuts | 8 | **−$207.00** | −$25.90 | 0 winners |

Robustness on it:

| test | result |
|---|---|
| top-15 winners kept | **15/15** — no winner damage at all |
| per ISO week (kept book) | wk29 +$325.50 · wk30 +$542.50 · wk31 +$716.00 · wk32 **+$913.50** — all four green, all four improved |
| strip best 3 | +$1,987.00 (baseline +$1,780.00) |
| worst leave-one-day-out | drop 07-29 → +$2,096.00 |
| out-of-sample | fit wk29–31 +$1,584.00 → untouched wk32 **+$913.50** |
| is the cut one lucky day? | no — spread over **5 days in 3 ISO weeks**: 07-22 −$5.00, 07-24 −$40.50, 07-28 −$57.00, 08-06 −$71.50, 08-07 −$33.00. Remove the worst day and the cut is still **−$202.00**. 7 of the 8 cut fires are losers. |

Cross-validated on **nine independent exit configurations** running the same entry — if it were an artefact of one exit it would not travel:

| strategy (own exit) | base $ | kept $ | delta | cut n | cut $/tr |
|---|---:|---:|---:|---:|---:|
| abs_veto_55s | +2290.5 | +2497.5 | **+207.0** | 8 | −25.9 |
| abs_veto_50s | +1997.0 | +2204.0 | **+207.0** | 8 | −25.9 |
| thrust_short_absveto55 | +965.0 | +1069.5 | **+104.5** | 3 | −34.8 |
| thrust_short_raw | +283.0 | +322.5 | +39.5 | 8 | −4.9 |
| sw_absS_A_k10 (live Lot A) | +507.5 | +612.0 | **+104.5** | 3 | −34.8 |
| sw_absS_B_k10 (live Lot B) | +846.5 | +951.0 | **+104.5** | 3 | −34.8 |
| cx_absSB_live | +406.0 | +510.5 | +104.5 | 3 | −34.8 |
| cx_absSB_clip | +417.5 | +522.0 | +104.5 | 3 | −34.8 |
| abs_veto_60s | +33.5 | +120.0 | +86.5 | 4 | −21.6 |
| **POOLED** | **+7746.5** | **+8809.0** | **+1062.5** | | |

**Honest caveat, stated up front: n = 8 over 17 days.** That is thin and I am not going to pretend otherwise. What makes me willing to recommend it anyway is that it is the *cheapest possible* change — it removes eight fires in seventeen days, damages not one winner, improves every ISO week including the untouched one, and reproduces on nine independent exits. If it is noise, it costs almost nothing; if it is real it is worth ~$200 a fortnight.

### And the rule that is actively BACKWARDS

The router's standing carve-out (b) benches this gate whenever **ATR ≥ 19 AND ER30 < 0.25** — "the violent-whipsaw cell". It used it on 08-05 20:35, reasoning *"that is the violent-whipsaw cell that is −$20 to −$33 per signal at every exit rung."* Measured over 17 days, split by time of day:

| VIOLENT-WHIPSAW | n | net | $/trade | win% |
|---|---:|---:|---:|---:|
| **US-SESSION** | 12 | **+$443.50** | **+$37.00** | **58%** |
| OVERNIGHT | 6 | −$19.00 | −$3.20 | 33% |
| LATE (20:00–24:00Z) | 1 | −$67.00 | −$67.00 | 0% |

In the US session the "violent whipsaw" cell is the gate's **second-best** pocket at +$37.00 a trade, and it holds **6 of the 15 biggest winners in the book**. The bench rule is right overnight and wrong in the session, and it is applied without reference to the clock. This is exactly the failure mode the backtest discipline exists to prevent: a rule scored across the whole tape, averaging a segment where it belongs ON with one where it belongs OFF.

---

## 6 · THE EXIT SWEEP — and the instrument that failed

The discipline says every R is a guess and must be swept per regime with a proven plateau. I built a 5s-bar exit simulator to do it. **It failed its own validation and I am reporting the failure rather than the numbers.**

**What I built.** Replay each of the 159 entries forward on 5s bars, stop at 1.0×ATR, sweep Lot A and Lot B targets 0.5→4.0 ATR.

**Validation pass 1 — anchoring.** The shadow's `entry_ts` is the *signal bar start*; per `repricer.py` the honest fill is the first quote after the bar **closes** (ts + 60). Anchoring at `ts` gave −$2,023.80 against the tick truth of +$2,290.50 with 72% sign agreement. Anchoring at `ts+60` gave **+$2,027.80 with 97% sign agreement** — validated, and conservative by 11%.

**Validation pass 2 — and this is where it broke.** With the anchor fixed, the sweep's headline said a **2.0×ATR stop beats the live 1.0×ATR by ~$900**. So I tested whether that was the tape or the instrument, by re-running with the stop detected on the bar **close** (a mid proxy, matching what the tick repricer actually does) instead of the bar **extreme**:

| stop detection | A1.5/B2.5 @ k1.0 | A1.5/B2.5 @ k2.0 | winner |
|---|---:|---:|---|
| bar extreme (high/low) | +$4,256.30 | +$5,152.50 | k2.0 |
| bar close (mid proxy) | +$4,905.10 | +$4,020.20 | **k1.0** |

**The conclusion flips with the measurement rule.** The bar-extreme rule over-triggers tight stops, because a 5s bar's high can spike through a 1-ATR stop that the tick *mid* never crossed. Ground truth — the desk's own tick-repriced k10-vs-k20 A/B on 28 shared entries — says **k1.0 wins by $292.50**, which agrees with the mid-proxy run and contradicts the bar-extreme run.

**So: the stop-width half of my exit sweep is REJECTED as an instrument artefact.** It would have recommended doubling the stop on this gate, on a number produced by my own measurement choice.

**And the R-target half is inconclusive too.** Even at a fixed stop, the target grid rises monotonically to the corner of the grid I tested (best cell = A4.0/B4.0, the largest pair in the sweep). A grid whose optimum pins to the edge is the desk's own definition of overfit, and here it has an obvious cause: with a 1-ATR stop and a 4-ATR target, most trades either stop out or ride to my 2-hour `MAX_HOLD` fallback, so the "target" is doing very little work and the fallback is doing most of it.

**The one signal I will carry forward as a lead, not a result.** Only two regimes produced a genuine plateau (≥4 of the top-10 cells adjacent to the winner), and in both, widening **Lot A** from 1.5 to 2.5 helps:

| regime | n | best cell | net | LIVE A1.5/B2.5 | live rank | plateau? |
|---|---:|---|---:|---:|---:|---|
| TREND-NOBREAK | 27 | A2.5/B2.5 | +$1,638 | +$1,332 | 17/66 | **PLATEAU** (6/10 adjacent) |
| VIOLENT-WHIPSAW | 19 | A2.5/B2.5 | +$1,579 | +$1,075 | 19/66 | **PLATEAU** (4/10 adjacent) |
| CLEAN-TREND | 24 | A4.0/B4.0 | +$1,184 | +$1,023 | 14/66 | SPIKE — reject |
| NORMAL-CHOP | 46 | A4.0/B4.0 | +$1,998 | +$1,038 | 33/66 | SPIKE — reject |
| BUILDING | 43 | A4.0/B4.0 | +$838 | +$437 | 27/66 | SPIKE — reject |

Against the operator cheat-sheet: for a momentum gate the guess is Lot A 1.5R / Lot B 2.5R. In the two regimes where the sweep is trustworthy the tape prefers **A 2.5R**, i.e. Lot A is banking too early in trending and violent tape. **That is a SHADOW candidate, not a deploy** — it comes from an instrument that already failed one validation, so it needs to earn its way through the shadow book on tick-repriced fills before it touches the live exit file.

---

## 7 · ROBUSTNESS SUMMARY

| test | baseline (continuous) | recommended (drop BUILDING×US) | live router policy (R6) |
|---|---:|---:|---:|
| n / net | 159 / **+$2,290.50** | 151 / **+$2,497.50** | 67 / +$881.00 |
| $/trade | +$14.40 | +$16.50 | +$13.10 |
| strip best 1 | +$2,100.50 | +$2,307.50 | +$691.00 |
| strip best 3 | +$1,780.00 | +$1,987.00 | +$373.00 |
| strip best 5 | +$1,484.50 | +$1,691.50 | +$195.00 |
| worst leave-one-day-out | +$1,889.00 | +$2,096.00 | +$332.50 |
| wk29 / 30 / 31 / 32 | +326 / +497 / +659 / **+809** | +326 / +543 / +716 / **+914** | +8 / +121 / +775 / **−23** |
| days green | 14/17 | 14/17 | 10/15 |
| OOS (fit wk29-31 → test wk32) | +$1,481.50 → **+$809.00** | +$1,584.00 → **+$913.50** | +$903.50 → **−$22.50** |
| cross-regime | positive in all 5 | positive in all 5 | only 3 regimes survive |
| top-15 winners kept | 15/15 | **15/15** | 8/15 |

The recommended policy dominates the baseline on every single line, and both of them dominate the policy that was actually live — which is the only one of the three that is negative out of sample.

---

## 8 · THE OTHER THINGS I TRIED THAT DID NOT WORK

Showing these because the nulls are the point.

**"The live desk chases — it takes the SECOND thrust of a burst, not the first."** I liked this one and it half-held. Grouping the 159 fires into bursts (consecutive fires ≤10 min apart):

| | n | net | win% | $/trade |
|---|---:|---:|---:|---:|
| FIRST fire of a multi-fire burst | 16 | +$710.50 | **81.2%** | **+$44.40** |
| LATER fires of the same burst | 18 | +$172.00 | 44.4% | +$9.60 |
| single-fire bursts | 125 | +$1,408.00 | 44.8% | +$11.30 |

The first fire of a burst really is worth 4.6× a later one. But as a **filter** it is a NULL: a first-fire-only policy keeps +$2,118.50 of the +$2,290.50 book — it *loses* $172 — because the later fires are still positive, and it drops 3 of the 15 biggest winners. **REFUTED as a filter, KEPT as a diagnosis:** it tells you the 61-second lag has a real cost shape even though the average is small.

**"Widen the stop to 2.0×ATR."** Rejected — instrument artefact, see §6. Ground truth says the live 1.0×ATR is right by $292.50.

**"Put an ATR floor on it."** Real, plateau-shaped, keeps 15/15 winners at 13/15/17 — and costs $259–$760 of net. PARKED as a slot-contention lever.

**"Cap the extension — don't chase an already-spent move."** REFUTED on this side over 17 days. Every cap that bites loses money; the only profitable cap removes one trade.

**"Require a dwell so ER isn't sampled on noise."** The best per-trade number in the whole sweep ($34.70) and the second-worst winner retention (4/15). Textbook fake.

**"Drop the pre-open."** +$189 of live money for a $9.40/trade cut — a wash, and it makes the recommended filter worse when stacked (T3 +$2,308.50 vs G2 alone +$2,497.50). NULL.

**"Trade the US session only" / "trade overnight only."** Both cut more than they keep. The gate earns in both windows (+$951 US / +$1,015 overnight). NULL.

**The one stone I did NOT turn.** The 07-26 rehab also asked whether the `fast=True` start-of-move trigger (2-bar impulse instead of 5-bar) fixes the chase. I could not test it — it changes which bars fire, so it needs a full signal replay from the tape rather than a filter over an existing ledger, and no shadow variant runs it. **That is the outstanding piece of work on this gate.**

---

## 9 · VERDICT — **FIXED**

The signal is proven, the exit is proven, the two malfunctions are named and already patched. What is left to change is the arming policy.

### Exact config

**1 — SIGNAL: no change.** `thrust`, `thr=1.5`, `amp_floor=0.0004`, 55s absorption veto. Proven: +$2,290.50 / 159 fires / 17 days / 4-of-4 ISO weeks green / strip-3 +$1,780 / worst LODO +$1,889 / positive in all five regimes / OOS +$809. Keep the `amp_floor` exactly as is — it is doing silent work: across all 803 abs-short-family fires in the archive, **not one** lands in DEAD-CHOP. The floor already removes that regime entirely.

**2 — EXIT: no change.** Lot A 1.5R, Lot B 2.5R, stop 1.0×ATR, quiet-tape clip at ATR 22. The desk's own tick A/B says the live width beats the 2.0 alternative by $292.50 on shared entries. The "give it the k10 width" recommendation was already the live state.

**3 — ARMING: this is the change.**

| change | why |
|---|---|
| **`abs_veto_short` armed BY DEFAULT.** Stop treating it as benched-until-argued-for. It goes in the switch file as `on` and comes off only on the vetoes below. | 3.3% of tape armed; the 96.7% benched contained +$1,064.50 of realised money on the exact live config. 53 of 54 filters lose to just letting it fire. |
| **ADD one entry veto: skip when ER30 ∈ [0.15, 0.30) AND 13:30 ≤ UTC < 20:00.** Put it in the gate, not the switch file — it is a per-entry condition, not an arming state. | +$207 on the reference book, **15/15** winners kept, all four ISO weeks improved including the untouched one, cross-validates +$1,062.50 across nine independent exits, cut spread over 5 days / 3 weeks. Thin at n=8 — but it is the cheapest change available. |
| **DELETE the violent-whipsaw bench (ATR≥19 AND ER30<0.25) for the US session.** Keep it overnight if you want; it is roughly neutral there (−$3.20/tr on n=6). | In the US session that cell is **+$37.00/trade, 58% win, n=12**, and holds 6 of the 15 biggest winners in the book. The rule is backwards where it is being applied. |
| **DELETE "bench on a stop-out pair" for this gate.** | On 08-07 the 13:31 bench after the first stop-out pair was followed by **+$311.50** to the twin in the next 60 minutes. Across all ten benches the twin was positive in the hour after **2** of them, **negative after none**, and had no signal at all after the other 8; stretched to two hours it is 4 positive / 2 negative. This is the arm-for-periods finding reproducing on a second gate. |
| **FIX the 22:00 auto re-arm.** Add `abs_veto_short` to `reactivate_gates.HOLD`, or gate the whole Paris-midnight re-arm on there being enough bars to form a regime read. | On 08-04 it re-armed the gate on zero tape and the corrupted thrust fired **two minutes later**, unsupervised for 45 minutes. Even with the MD bug fixed, arming anything on "insufficient bars, range 0pt" is not a decision. |

**Expected effect, stated honestly.** On the 17-day reference book this policy runs 151 fires for **+$2,497.50** (+$16.50/trade) against the +$881.00 the live-style router policy produces and the **−$22.50** that policy produced out of sample. I am not forecasting that number forward — one gate, seventeen days, one instrument. What I am claiming is narrower and better supported: **the arming policy currently in force is the only one of the three that is negative out of sample, and there is no measurement in this report that supports keeping it.**

### What I am NOT claiming

- I have **not** proven that widening the leash would have made money this week. The four signals it took would have lost roughly −$256 even at a neutral entry draw. The claim is about the 54 fires it was benched for.
- The BUILDING × US-SESSION veto rests on **n=8**. It cross-validates well and costs nothing, but it is not a heavyweight finding.
- The 61-second entry lag is **measured and real** (median 61s over 78 matched entries) but its root cause in code is **not proven** — I can see that live entries are pinned to a bar boundary one bar behind the twin, and I can see the price distribution it produces, but I did not isolate which of the `pending_veto` re-fire conditions creates the extra bar.

---

## 10 · DISPOSITION TABLE

| lead | verdict | detail / revival condition |
|---|---|---|
| `abs_veto_short` — the SIGNAL | **LIVE** | +$2,290.50 / 159 fires / 17 days / 4-of-4 weeks green / all 5 regimes positive / OOS +$809. Not in trouble. |
| `abs_veto_short` — the EXIT (A1.5R/B2.5R, k1.0, clip) | **LIVE — no change** | Live width beats k2.0 by $292.50 on the desk's own tick A/B. "Give it the k10 width" is already the live state. |
| Arming policy: default-ON + one veto | **LIVE (deploy)** | §9. Dominates both the baseline and the current policy on every robustness line. |
| Veto: drop BUILDING × US-SESSION | **LIVE (deploy, low confidence)** | +$207, 15/15 winners kept, 9-exit cross-validation. **n=8** — re-look at n≥25. |
| Delete the US-session violent-whipsaw bench | **LIVE (deploy)** | That cell is +$37.00/tr in session and holds 6 of the top-15 winners. |
| Delete "bench on a stop-out pair" | **LIVE (deploy)** | 08-07's bench cost +$311.50 in the next hour. Second gate to show arm-for-periods. |
| Paris-midnight auto re-arm on zero tape | **PARKED → ACTION** | Add to `reactivate_gates.HOLD` or gate on bar count. Revives as a finding if any gate again fires within 5 min of a 22:00 re-arm. |
| Lot A 1.5R → 2.5R in TREND-NOBREAK / VIOLENT-WHIPSAW | **SHADOW** | Only two regimes with a real plateau, and the instrument that found it already failed one validation. Run it as a shadow arm on tick-repriced fills; promote at n≥30 per regime. |
| 61-second entry lag | **PARKED** | Real (median 61s, n=78) and worth ~$6.87/lot on average with a ±$21 1-sd band. **Revives with instrumentation:** log the SIGNAL bar alongside `submitted`/`filled` in the `signals` table, then compare live vs replay per fire. |
| Extension cap (skip if leg > N·ATR) | **REFUTED** for the short side | Named test: 6-rung cap sweep, 17 days. Every cap that bites loses money and drops winners; the only positive cap removes 1 trade in 17 days. No reformulation left on this sample. |
| ER30 / ER15 floors as an arming rule | **REFUTED** | Named test: 12-rung sweep + winner-retention. Best per-trade rung keeps 7/15 winners and drops $1,150. Fifth gate to reproduce "ER filters FAKE". |
| Dwell requirement (ER sustained N-of-5) | **REFUTED** | Named test: 3-rung sweep. $34.70/tr on 4/15 winners kept — the cleanest fake win in the sweep. |
| ATR ceiling (bench above 19/22/25pt) | **REFUTED** | Named test: 5-rung sweep. C19 keeps **0 of 15** winners. The edge lives in high ATR. |
| Router "arm trio" (extreme + ER rising + vol up) | **REFUTED as an arming rule** | Cuts +$1,672.50 (73% of the book) and 11 of 15 winners. |
| Stacked router rules (R6) | **REFUTED** | Named test: OOS split. In-sample +$903.50 → out-of-sample **−$22.50**. |
| First-fire-of-burst filter | **REFUTED as a filter, KEPT as a diagnosis** | Loses $172 and 3 winners. But first fires are +$44.40/tr at 81% vs +$9.60/tr for later ones — real information about the lag. |
| ATR floor 13–17pt | **PARKED** | Real and winner-preserving (15/15) but costs $259–$760 of net. **Revive if slot contention becomes binding** — it buys the same money in fewer trades. |
| 5s-bar exit simulator | **REFUTED as an instrument** | Stop-width conclusion flips with the detection rule (bar-extreme vs bar-close) and disagrees with the tick truth. R grid pins to the edge of the sweep. Do not cite its numbers. |
| `fast=True` 2-bar trigger | **UNTURNED STONE** | Needs a full signal replay from the tape, not a filter over an existing ledger. The one outstanding piece of work on this gate. |
