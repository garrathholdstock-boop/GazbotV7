# S1b BASELINE — per-day tables and per-trade post-mortems

Source: `reports/sim_week_recursive/sline_s1b_*.json` (arm s1b, line v2, claude-sonnet-5). 4 lots, $2/pt, cost $6/trade (4 x $1.50). Tags are rule-derived, not opinion:
- `NG` never green (peak_1m<5) · `FADE` peak 5-15 then red · `GB` peak>=15 then red · `WIN` banked, with share of peak kept
- `vs-MIL` entered against the causal 7xATR MIL direction · `#n` entry ordinal inside MIL+side · `gap` minutes since previous exit
- Hindsight tags are post-mortem only; none is knowable at entry except vs-MIL, #n and gap.

## 2026-02-05  net $+752  (20 trades, 11 wins)

| # | side | open-close UTC | held | pnl $ | peak pt | tag | notes | model entry reason |
|--|--|--|--|--|--|--|--|--|
| 1 | S | 02:05-02:20 | 15m | +448 | 131 | WIN 43% | vs-MIL | Leg 6 down (72pt/49min from the 25169 high) is still driving — the last 15-min bar broke to a fresh low on str |
| 2 | L | 02:25-02:40 | 15m | +206 | 42 | WIN 64% | vs-MIL gap 5m | the 204pt down leg exhausted at 24959 and price has reversed 76pt in 9min with a strong close-off-the-low bar, |
| 3 | S | 02:50-03:00 | 10m | +364 | 61 | WIN 75% | vs-MIL gap 10m | Leg 6 is a confirmed fresh down leg (59pt/15min, last bar closing near its low), already recognized as its own |
| 4 | L | 03:25-03:35 | 10m | -372 | 0 | NG |  | Leg 7 is a proven up-leg (64pt/26min) with the last two 15-min bars both closing higher and making a fresh hig |
| 5 | S | 03:50-04:00 | 10m | -98 | 16 | GB |  | Leg 8 down 71pt/28min is still making fresh lows with bearish closes, no stall yet, so joining the proven down |
| 6 | S | 04:25-04:30 | 5m | -154 | 10 | FADE | #2 | The down leg is still driving with a fresh 63-min extreme (new low 24922.75, close near the low), so it has pr |
| 7 | L | 04:40-05:00 | 20m | +204 | 35 | WIN 74% | vs-MIL gap 10m | The down leg into 24915.50 reversed decisively and the new leg is already up 65pt in 14 minutes, a proven move |
| 8 | S | 05:20-05:25 | 5m | -128 | 2 | NG | vs-MIL | Price has fallen steadily from the 25027 high at 04:36 through 24997 at 04:51 to 24971 now, a confirmed ~56pt  |
| 9 | L | 05:40-05:55 | 15m | -256 | 12 | FADE |  | Leg 7 is still driving up, just printed a fresh extreme off a shallow pullback, so joining the confirmed grind |
| 10 | L | 06:35-07:15 | 40m | +208 | 48 | WIN 56% | #2 | After trade 9's stop-out, price pushed to a fresh extreme (25053) beyond the prior swing high and the latest 1 |
| 11 | L | 07:20-07:50 | 30m | -104 | 10 | FADE | #3 gap 5m | Leg 7 is still driving up (152pt/174min) with a fresh extreme to 25082 beyond the 25060 level I exited at, and |
| 12 | L | 08:05-08:30 | 25m | +182 | 38 | WIN 61% | #4 | Leg 7 is still the running up-leg (156pt/219min) and the 07:51 bar shows a strong reclaim back to 25079 after  |
| 13 | S | 08:50-09:00 | 10m | +214 | 48 | WIN 57% | vs-MIL #2 | The up leg into 08:06 rolled over and the last 15-min bar closed right at its low on an outsized down range, c |
| 14 | S | 09:05-09:20 | 15m | -304 | 0 | NG | vs-MIL #3 gap 5m | Down leg 8 just made a fresh extreme below the last short's exit, with the 08:51 bar closing right at its low  |
| 15 | L | 09:25-09:35 | 10m | +116 | 40 | WIN 38% | #5 gap 5m | The down leg into 09:05 is clearly reversed - a strong 69pt reversal bar off the 24978 low has already run 71p |
| 16 | L | 10:20-10:35 | 15m | -240 | 11 | FADE | vs-MIL | the down leg bottomed near 25011 and has ground up to a new local high near 25087, with the pullback to 25077  |
| 17 | S | 10:55-11:15 | 20m | +24 | 25 | WIN 15% |  | Up leg 11 stalled at the 25092 high and the last two 15-min bars closed lower into 25037.75, a confirmed rever |
| 18 | S | 11:35-11:50 | 15m | -146 | 0 | NG | #2 | Leg 12 is a proven 68min/85pt downleg that just broke to a fresh low (24991) on a strong impulsive bar, so joi |
| 19 | S | 12:20-12:25 | 5m | +462 | 83 | WIN 70% | #3 | The running down leg (113min, 111pt) just printed a strong fresh-extreme bar to 24957 with a close near the lo |
| 20 | S | 12:35-13:00 | 25m | +126 | 100 | WIN 17% | #4 gap 10m | the down leg just drove to a fresh session low (24817) on a wide-range bar, well beyond my last short's exit,  |

## 2026-02-19  net $+274  (11 trades, 5 wins)

| # | side | open-close UTC | held | pnl $ | peak pt | tag | notes | model entry reason |
|--|--|--|--|--|--|--|--|--|
| 1 | L | 02:30-03:45 | 75m | -52 | 18 | GB |  | Off the 01:31 swing low at 24937.75 price has grinded up for three straight 15-min bars with higher highs each |
| 2 | L | 04:00-04:25 | 25m | -112 | 1 | NG | #2 | the up leg since 23:00 just reconfirmed itself with a strong bounce off the 24966 pullback low back to 24991,  |
| 3 | S | 04:55-05:15 | 20m | +38 | 19 | WIN 28% |  | the down leg since 03:30 has proven itself with accelerating red 15-min bars making a fresh low at 24953.50, s |
| 4 | L | 05:40-06:10 | 30m | +60 | 19 | WIN 43% |  | fresh up leg confirmed by a new extreme at 24988.75 well beyond the 04:56 low, joining the grind up after two  |
| 5 | L | 06:30-07:40 | 70m | +182 | 38 | WIN 62% | #2 | Leg 3 up is still running and just printed a fresh extreme above the prior 06:10 exit, so this is a new entry  |
| 6 | L | 07:45-08:45 | 60m | -272 | 15 | FADE | #3 gap 5m | The up leg since 05:06 has made a fresh extreme to 25048, well beyond trade 5's exit at 25030, and the one dow |
| 7 | S | 08:50-09:00 | 10m | +174 | 35 | WIN 64% | gap 5m | The up leg topped at 25054 and has been grinding down for 29 minutes with a fresh extreme low and a strong clo |
| 8 | S | 09:05-10:00 | 55m | +506 | 94 | WIN 68% | #2 gap 5m | The down leg is still proving itself with three straight down bars and a fresh extreme low at 24941 beyond the |
| 9 | S | 10:10-10:45 | 35m | -8 | 30 | GB | #3 gap 10m | The down leg is still driving with a fresh extreme low at 24858 beyond the last exit, so it's safe to jump bac |
| 10 | L | 11:15-11:40 | 25m | -42 | 9 | FADE | vs-MIL | Down leg made a higher low at 10:46 (24838 vs 24825 low) then broke above the bounce highs into 11:01 with a s |
| 11 | L | 12:25-12:55 | 30m | -200 | 0 | NG |  | Price reversed off the 24814 low and the leg has proven itself with a fresh extreme at 24896.25 on strong clos |

## 2026-03-05  net $-1,204  (21 trades, 7 wins)

| # | side | open-close UTC | held | pnl $ | peak pt | tag | notes | model entry reason |
|--|--|--|--|--|--|--|--|--|
| 1 | S | 02:00-02:05 | 5m | -74 | 1 | NG |  | The down leg from 00:18 is proven and still driving - 162pt over 102min with consecutive down bars and a fresh |
| 2 | S | 02:20-02:45 | 25m | -130 | 17 | GB | #2 | The 166pt down leg from 00:18 is still running - after a brief 01:51 bounce to 25095 it rolled back down to 25 |
| 3 | L | 02:50-02:55 | 5m | -228 | 1 | NG | vs-MIL gap 5m | The up leg off the 25044 low has run 64pt in 54min and the last 15-min bar closed near its high on a strong 43 |
| 4 | S | 03:25-03:40 | 15m | +30 | 35 | WIN 13% | #3 | Leg 4 down is confirmed by a full-bodied bar closing at 25060.75 near its low after 34min and 54pt, so joining |
| 5 | L | 04:15-05:05 | 50m | +106 | 28 | WIN 50% | vs-MIL #2 | Price has made a clean swing low at 25026.50 (03:16) and then printed three consecutive higher closes includin |
| 6 | S | 05:40-06:25 | 45m | +394 | 75 | WIN 66% | vs-MIL | Three straight 15-min bars of lower highs and lower lows from the 25106.5 peak have already erased the prior 3 |
| 7 | S | 06:35-06:45 | 10m | -74 | 2 | NG | gap 10m | Leg 4 down is still driving and just made a fresh extreme (24993.75) beyond my prior exit at 25010.62, confirm |
| 8 | L | 06:50-07:05 | 15m | +16 | 34 | WIN 8% | vs-MIL gap 5m | the 06:36 bar closed +65pt off the low on a sharp reversal, confirming the UP leg (73pt/35min) that just stopp |
| 9 | L | 07:25-07:50 | 25m | -260 | 0 | NG |  | The up leg off 06:15 is still driving with two straight strong green 15-min bars closing near session highs, a |
| 10 | S | 08:05-08:20 | 15m | -140 | 12 | FADE | vs-MIL | Leg 6 down is confirmed and accelerating - the last 15-min bar swept to a fresh low (25005.50) and closed righ |
| 11 | S | 08:30-08:35 | 5m | -166 | 4 | NG | vs-MIL #2 gap 10m | The 91-minute, 102pt down leg just printed a fresh session low on an accelerating bar, confirming it's still d |
| 12 | S | 08:40-08:45 | 5m | -194 | 0 | NG | vs-MIL #3 gap 5m | the down leg just printed a fresh session low at 24973 and closed near it, confirming the leg is still running |
| 13 | L | 09:05-09:15 | 10m | +258 | 74 | WIN 45% | #2 | Leg 7 has already proven itself with a 139pt breakout in 34min and a strong high-close bar above the prior con |
| 14 | S | 09:30-09:50 | 20m | +80 | 35 | WIN 30% | vs-MIL #4 | Leg 8 is a confirmed 71pt/19min down move off the 25206 spike high, closing near the bar low at 25127, so join |
| 15 | L | 10:15-10:20 | 5m | -50 | 8 | FADE | #3 | the down leg bottomed near 25088 and the last two 15-min bars closed higher in a row (25092→25108→25122), a pr |
| 16 | L | 10:30-10:40 | 10m | -270 | 0 | NG | vs-MIL gap 10m | Three straight 15-min bars have closed higher off the 25082 low and price is now above where the last long got |
| 17 | S | 10:50-11:05 | 15m | -178 | 6 | FADE | gap 10m | Leg 8's down move just reasserted with a fresh lower low (25097.50 breaking the 10:06 low of 25108.75) after t |
| 18 | L | 11:25-11:35 | 10m | -128 | 15 | FADE | vs-MIL #2 | Three straight 15-min up bars with rising highs (25123→25133→25148) off the 10:56 low confirm the down leg has |
| 19 | S | 11:55-12:10 | 15m | +18 | 22 | WIN 14% | #2 | Bounce to 25152 at 11:26 got rejected and the last two 15-min bars closed lower, grinding back down in line wi |
| 20 | S | 12:50-13:00 | 10m | -18 | 21 | GB | #3 | After rejecting at 25156 the tape broke back below the 25078 pullback low on a strong bar closing near its low |
| 21 | S | 13:10-13:29 | 19m | -196 | 2 | NG | #4 gap 10m | The down leg is still driving with a fresh extreme on the last two 15-min bars (25106→25056→25032, closing nea |

## 2026-03-19  net $-1,168  (19 trades, 8 wins)

| # | side | open-close UTC | held | pnl $ | peak pt | tag | notes | model entry reason |
|--|--|--|--|--|--|--|--|--|
| 1 | L | 02:15-02:50 | 35m | +164 | 43 | WIN 50% |  | Leg 6 is a confirmed 70pt/14min up-leg that just broke above the prior swing high (24454) to a fresh session e |
| 2 | L | 03:10-03:30 | 20m | -222 | 3 | NG | #2 | Up leg pulled back to 24471 then recovered to a new extreme at 24493.50, confirming the leg is still intact an |
| 3 | S | 03:35-04:35 | 60m | +258 | 37 | WIN 88% | gap 5m | The down leg just made a fresh extreme low (24459, below the 02:51 low) after a bounce, running through my las |
| 4 | S | 04:40-04:55 | 15m | +12 | 17 | WIN 13% | #2 gap 5m | The down leg that paid me last trade just printed a fresh extreme (24411.50) below my prior exit (24427.38) an |
| 5 | S | 05:45-05:55 | 10m | -198 | 5 | FADE | #3 | The down leg just printed a fresh extreme at 24363, well beyond where my last short exited at 24411.88, confir |
| 6 | L | 06:15-06:30 | 15m | -160 | 16 | GB | vs-MIL | Two consecutive up 15-min bars off the 24363 low, with the last bar closing near its high (+16pt), confirm the |
| 7 | S | 06:55-07:05 | 10m | +40 | 20 | WIN 29% | vs-MIL | Leg 9 down is confirmed by two consecutive 15-min down bars off the 06:11 peak near 24424, now closing near fr |
| 8 | S | 07:55-08:00 | 5m | -204 | 5 | NG |  | The current leg is driving down (68pt/37min) with the 07:11 bounce already rejected and the last bar closing a |
| 9 | S | 08:05-08:10 | 5m | -148 | 0 | NG | #2 gap 5m | The down leg running since 07:18 just pushed to a fresh extreme low (24325.75) and closed near it at 24337.25, |
| 10 | S | 08:40-08:45 | 5m | +76 | 23 | WIN 44% | #3 | The down leg just printed a fresh extreme with a strong bearish 15-min bar (24334->24306 low, closing near the |
| 11 | L | 09:05-09:25 | 20m | -612 | 14 | FADE | vs-MIL | Leg 7 has turned and confirmed up 72pt off the 08:36 low with a strong driving 15-min bar, and the pullback fr |
| 12 | L | 09:40-09:45 | 5m | -174 | 1 | NG | vs-MIL #2 | The 90pt plunge into 24287.50 has reversed into a 58pt, 15-min up leg that just closed strong near its bar hig |
| 13 | S | 10:25-10:30 | 5m | -136 | 0 | NG | vs-MIL | The 90pt up leg topped near 24433 and has now printed two straight 15-min down closes to 24381, more than half |
| 14 | S | 10:40-10:45 | 5m | +30 | 16 | WIN 28% | vs-MIL #2 gap 10m | Three straight 15-min bars of lower highs and lower lows since the 24436 top (62pt down, well beyond ATR) conf |
| 15 | S | 11:05-11:30 | 25m | +102 | 31 | WIN 44% |  | The down leg running since 09:57 is 68min/75pt and just printed back-to-back lower 15-min closes to a fresh lo |
| 16 | S | 11:35-11:50 | 15m | -98 | 3 | NG | #2 gap 5m | Leg 8 down is still driving with a fresh extreme at 24300.25 (below the 24338.62 where the last short exited)  |
| 17 | S | 12:25-12:35 | 10m | -54 | 29 | GB | #3 | the bounce off the midday low was only a 3-minute spike that failed, and price has since pushed to a fresh low |
| 18 | S | 12:50-13:00 | 10m | -2 | 18 | GB | #4 | the down leg is still driving with a fresh session low on strong momentum, so joining it now for a quick scalp |
| 19 | S | 13:05-13:15 | 10m | +158 | 23 | WIN 89% | #5 gap 5m | The down leg just printed a fresh session low (24208.25) breaking below the prior 12:21/12:36 lows, confirming |

## 2026-04-02  net $+988  (12 trades, 7 wins)

| # | side | open-close UTC | held | pnl $ | peak pt | tag | notes | model entry reason |
|--|--|--|--|--|--|--|--|--|
| 1 | S | 02:05-02:45 | 40m | +450 | 78 | WIN 73% |  | The down leg has run 251pt over 55min and is still making fresh lows with closes near the bar low, so joining  |
| 2 | S | 03:05-04:15 | 70m | +276 | 55 | WIN 64% | #2 | the down leg just printed a fresh extreme (23850, below my prior exit at 23880.62) confirming it is still runn |
| 3 | S | 04:30-04:45 | 15m | +24 | 20 | WIN 18% | #3 | The dominant down leg made a fresh extreme to 23812 after the 04:01 bounce failed, confirming the grind is sti |
| 4 | S | 04:55-05:30 | 35m | -206 | 0 | NG | #4 gap 10m | The down leg running since 22:00Z just printed a fresh extreme (23795 low) below the prior exit at 23817, re-p |
| 5 | S | 05:40-06:15 | 35m | +210 | 38 | WIN 71% | #5 gap 10m | the dominant down leg just swept a fresh extreme to 23783 and closed near the low at 23794.25, confirming the  |
| 6 | L | 06:55-07:20 | 25m | +184 | 32 | WIN 74% | vs-MIL | Down leg bottomed at 23752 then four straight 15-min bars of higher highs/higher lows up to 23803, a confirmed |
| 7 | L | 07:40-08:05 | 25m | -16 | 33 | GB |  | Since exiting the last long at 23826.88 price pushed to a fresh extreme (23851.50/23845.50) on consecutive str |
| 8 | S | 08:20-08:35 | 15m | -128 | 8 | FADE | vs-MIL | the bounce off 23767 topped at 23882 and has now printed two straight lower-high, lower-close 15-min bars back |
| 9 | S | 10:10-10:30 | 20m | +176 | 28 | WIN 81% |  | Price just broke decisively below the multi-hour 23818-23822 chop floor, closing at a fresh low (23807.75) tha |
| 10 | S | 11:10-11:55 | 45m | +320 | 59 | WIN 69% | #2 | Fresh session low on a strong-bodied 15-min down bar (23822->23762 close near low) confirms the down leg is st |
| 11 | S | 12:00-12:20 | 20m | -136 | 13 | FADE | #3 gap 5m | Fresh extreme below the prior swing low (23675 vs ~23700) with the last 15-min bar still closing down, so the  |
| 12 | L | 12:50-13:00 | 10m | -166 | 2 | NG | vs-MIL | three straight 15-min bars off the 23666 low with higher highs and higher lows (23700->23740->23751) confirm a |

## 2026-04-16  net $-484  (12 trades, 4 wins)

| # | side | open-close UTC | held | pnl $ | peak pt | tag | notes | model entry reason |
|--|--|--|--|--|--|--|--|--|
| 1 | L | 02:00-04:25 | 145m | -102 | 12 | FADE |  | The up leg has run 96pt over 4 hours with a fresh extreme at 26466 and this is just a shallow pullback within  |
| 2 | S | 04:40-04:55 | 15m | -50 | 0 | NG |  | the up leg stalled after 02:56 and price has spent 2 hours grinding to fresh lows (26427 just printed), a conf |
| 3 | S | 05:15-05:20 | 5m | -102 | 0 | NG | #2 | the down leg just printed a fresh extreme (26416.50) breaking below the 04:16-04:46 consolidation, confirming  |
| 4 | L | 05:30-06:25 | 55m | +172 | 31 | WIN 72% | gap 10m | The down-leg from 03:07 just got round-tripped by a strong thrust bar (26416 low to 26457 high, closing 26452  |
| 5 | L | 06:30-07:05 | 35m | -150 | 2 | NG | #2 gap 5m | Price has made a fresh extreme (26484.75) beyond my last exit (26474.38) with higher lows still forming, so th |
| 6 | L | 07:45-07:55 | 10m | -180 | 0 | NG | #3 | Leg 3 up pulled back to 26455 then pushed a fresh extreme to 26487.25, confirming the up leg is intact and res |
| 7 | S | 08:05-08:45 | 40m | +16 | 23 | WIN 12% | gap 10m | The down leg is 25min and 50pt old with the last 15-min bar a 33pt range closing at its low, decisively confir |
| 8 | L | 09:00-09:30 | 30m | +12 | 9 | WIN 25% |  | Price has bounced 36pt off the 08:16 low (26410.75→26446.50) on two consecutive green 15-min bars with higher  |
| 9 | L | 10:05-10:25 | 20m | -158 | 0 | NG | #2 | After a brief stall near 26451-26455, the 09:51 bar broke to a fresh extreme at 26466, confirming leg 5's up-g |
| 10 | S | 10:30-10:50 | 20m | +268 | 48 | WIN 71% | gap 5m | The current down leg has already run 48pt in 28min and the last 15-min bar closed right at its low with a wide |
| 11 | L | 11:00-11:25 | 25m | -134 | 10 | FADE | vs-MIL gap 10m | Leg 7 is a confirmed new up-leg off the leg-6 low (26364), proven by a strong 44pt reversal bar in 13min with  |
| 12 | L | 11:50-12:15 | 25m | -76 | 8 | FADE |  | Leg 7 is still up: a fresh high at 26425.50 on the 11:36 bar confirms continuation beyond where the last long  |

## 2026-04-30  net $+544  (11 trades, 7 wins)

| # | side | open-close UTC | held | pnl $ | peak pt | tag | notes | model entry reason |
|--|--|--|--|--|--|--|--|--|
| 1 | S | 02:20-02:35 | 15m | +716 | 130 | WIN 70% |  | The up leg topped near 27623 at 00:36 and has since made a confirmed series of lower lows with two sharp down- |
| 2 | S | 02:50-03:00 | 10m | -188 | 8 | FADE | #2 | The down leg made a fresh extreme (27395.75) well beyond my prior exit at 27451.62 and is still grinding lower |
| 3 | S | 04:05-04:25 | 20m | +432 | 80 | WIN 68% | #3 | Down leg still running and just printed a fresh extreme low at 03:51 after two bounces failed to hold, confirm |
| 4 | S | 04:30-05:05 | 35m | +44 | 41 | WIN 15% | #4 gap 5m | Down leg still driving with a fresh extreme below the last exit (27273 vs 27311), confirmed by back-to-back st |
| 5 | S | 06:00-06:30 | 30m | -242 | 26 | GB | #5 | the down leg from 00:39 is still running and just printed a fresh extreme below the 04:30-05:46 consolidation  |
| 6 | L | 06:40-06:50 | 10m | -182 | 0 | NG | gap 10m | the 332min down leg reversed at 27185 and the new up leg has already run 91pt over 29min with a strong impulsi |
| 7 | L | 07:10-07:50 | 40m | +38 | 37 | WIN 15% | #2 | The 59-min, 144pt up leg off the 27185.50 low has just posted a strong fresh extreme (27338 high, 06:56 bar cl |
| 8 | L | 08:05-09:00 | 55m | +24 | 27 | WIN 14% | #3 | Leg 3 up is still intact - price absorbed the 07:36 pullback to 27339 and is pushing back toward the 27378 hig |
| 9 | L | 09:30-10:55 | 85m | -454 | 0 | NG | #4 | Leg 3 just printed a fresh extreme at 27420 after holding the 27330 pullback, confirming the up leg is still d |
| 10 | L | 11:15-11:40 | 25m | +262 | 67 | WIN 50% | #5 | Price just pushed to a fresh high (27439) above the recent chop ceiling and closed strong near the top of the  |
| 11 | L | 12:15-12:35 | 20m | +94 | 52 | WIN 24% | #6 | the up leg since 06:11 just printed a fresh extreme at 27506.50 beyond the prior 11:16 high, confirming contin |

## 2026-05-14  net $-1,490  (17 trades, 8 wins)

| # | side | open-close UTC | held | pnl $ | peak pt | tag | notes | model entry reason |
|--|--|--|--|--|--|--|--|--|
| 1 | S | 02:00-02:25 | 25m | -182 | 0 | NG |  | The down leg from 00:58 has run 82pt over 62min with fresh lows into the last bar (29606.75), still driving wi |
| 2 | S | 02:50-03:10 | 20m | -214 | 0 | NG | #2 | The down leg running since 00:58 just broke to a fresh extreme (29577 vs prior 29600 lows) with strong momentu |
| 3 | S | 03:30-04:15 | 45m | +178 | 46 | WIN 50% | #3 | the down leg just printed a fresh extreme (29563 low, below the 02:46 low of 29571) after the 03:01 bounce, co |
| 4 | L | 04:25-04:50 | 25m | +90 | 26 | WIN 47% | vs-MIL gap 10m | Price has reversed off the session low into a fresh up-leg, +50pt over 20min with the last 15-min bar closing  |
| 5 | S | 05:15-05:30 | 15m | -194 | 11 | FADE | vs-MIL | Leg 6 down has proven itself with 47pt over 27min and two consecutive lower 15-min closes near their lows, sti |
| 6 | L | 05:45-06:25 | 40m | +90 | 27 | WIN 45% |  | The up leg from 29534 has run 70pt in 27min with a strong confirming bar (29564→29606.50 making a fresh extrem |
| 7 | L | 06:30-07:05 | 35m | -240 | 6 | FADE | #2 gap 5m | Leg 7 is still driving up and just printed a fresh extreme at 29640.25 beyond my last trade's peak, confirming |
| 8 | S | 07:10-07:20 | 10m | -144 | 3 | NG | vs-MIL #2 gap 5m | Leg 8 is a confirmed down move (48pt/29min off the 29636 high) with the last 15-min bar extending to a fresh l |
| 9 | L | 07:45-07:50 | 5m | -156 | 0 | NG | #3 | the down leg has reversed with two strong consecutive 15-min bars (+10pt, +25.75pt) driving price to a fresh l |
| 10 | S | 08:05-08:10 | 5m | -262 | 0 | NG |  | The down leg from 06:41 just made a fresh extreme (29548.25) and closed near the low on a 58pt bar, confirming |
| 11 | L | 08:15-08:45 | 30m | -494 | 12 | FADE | vs-MIL gap 5m | The down leg capitulated with a new low at 29548 then ripped back to close near the bar high, and the up-leg h |
| 12 | S | 09:30-09:40 | 10m | +256 | 56 | WIN 59% | #2 | The down leg running since 08:16 just printed a fresh extreme low at 29538.75 after 74min/84pt, confirming it' |
| 13 | L | 10:00-10:15 | 15m | +82 | 37 | WIN 30% |  | the down leg bottomed at 29481 and the last 15-min bar closed strongly near its high, confirming a fresh up le |
| 14 | S | 10:35-10:45 | 10m | +106 | 21 | WIN 67% | vs-MIL | The up-leg topped near 29594 with a rejection doji and the next bar closed lower, breaking back below 29548, s |
| 15 | L | 11:10-11:25 | 15m | -458 | 1 | NG | vs-MIL | Leg 11 is up 54pt over 27min with two consecutive confirming green 15-min bars (10:41, 10:56), a proven move w |
| 16 | L | 12:10-12:20 | 10m | +14 | 6 | WIN 39% |  | Three straight 15-min bars of higher closes off the 11:11 low at 29517 show a fresh grind up proving itself, s |
| 17 | S | 12:55-13:15 | 20m | +38 | 25 | WIN 22% |  | The current leg is a confirmed 91pt/31min down move still accelerating into a new low with the last 15-min bar |

## 2026-05-28  net $+1,608  (14 trades, 9 wins)

| # | side | open-close UTC | held | pnl $ | peak pt | tag | notes | model entry reason |
|--|--|--|--|--|--|--|--|--|
| 1 | S | 02:15-02:50 | 35m | +182 | 44 | WIN 53% | vs-MIL | The down leg from 00:58 is 77 minutes in, 61pts, and just printed a fresh session low on a wide bar closing at |
| 2 | S | 03:05-03:55 | 50m | +1268 | 173 | WIN 92% |  | the down leg is still driving with a fresh extreme below my prior exit (29976 vs 29999.62) and no stall yet, s |
| 3 | S | 04:00-04:25 | 25m | +150 | 31 | WIN 62% | #2 gap 5m | Down leg still running, price just made a fresh low at 29803.50 after a brief bounce rejected near 29837, so t |
| 4 | S | 04:30-04:40 | 10m | -262 | 0 | NG | #3 gap 5m | Down leg still running with a fresh extreme at 29763 beyond the last exit, and price is bouncing back toward 2 |
| 5 | S | 05:05-05:20 | 15m | -352 | 0 | NG | #4 | The down leg just rejected a bounce and pressed to a fresh low (29775 on a weak close), reconfirming the leg t |
| 6 | L | 05:30-06:30 | 60m | +426 | 76 | WIN 71% | gap 10m | off the 225pt down leg price has made a higher low (29775 vs 29763) and now a higher high (29861 vs 29822), wi |
| 7 | L | 07:10-07:50 | 40m | +8 | 22 | WIN 8% | #2 | Leg 4 up-leg paused on the 06:11-06:26 pullback then resumed with a fresh extreme to 29964.75, proving itself  |
| 8 | L | 07:55-08:30 | 35m | +98 | 36 | WIN 36% | #3 gap 5m | The 07:41 bar pushed a fresh extreme to 29964, beyond the prior trade's peak near 29958, confirming the 04:21  |
| 9 | L | 09:00-09:35 | 35m | -210 | 12 | FADE | #4 | The up leg made a fresh extreme at 29990 beyond the last exit and the latest 15-min bar closed strong near its |
| 10 | S | 10:20-10:55 | 35m | +238 | 39 | WIN 77% |  | The up leg topped near 30008 and price has made a fresh lower low (29929) breaking below the last two pullback |
| 11 | S | 11:00-11:15 | 15m | -170 | 4 | NG | #2 gap 5m | Down leg 5 just drove to a fresh extreme below the prior short's exit (29862 low vs 29905 exit) with strong mo |
| 12 | S | 11:30-11:40 | 10m | -360 | 0 | NG | #3 | The down leg running since 09:03 just had its bounce rejected at 29906.75 and the 11:16 bar closed back near i |
| 13 | L | 12:00-12:25 | 25m | +104 | 26 | WIN 53% |  | the 63pt down leg reversed off the 10:46 low with a strong 47pt impulse bar and price is now basing right at t |
| 14 | L | 12:30-13:10 | 40m | +488 | 100 | WIN 62% | #2 gap 5m | The up leg off 11:08 is still driving with accelerating 15-min bars making a fresh extreme (29978.50) well bey |

TOTAL $-180