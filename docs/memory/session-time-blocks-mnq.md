---
name: session-time-blocks-mnq
description: "ASIA (00-07 UTC) is benched permanently at config level; the desk's expectancy lives in the 75 min after the US open — and \"don't trade before the US open\" was REFUTED"
metadata: 
  node_type: memory
  type: project
  originSessionId: 882eb15b-b9b1-4c08-9348-cd06bd148585
  modified: 2026-08-05T17:56:58.189Z
---

**2026-08-05.** Measured on the SHADOW book (fires regardless of benching = the unconfounded counterfactual), n=6,324 MNQ sims.

```
ASIA   00-07 UTC   n=1840   -$5,838   -$3.17/tr   35%   ← BENCHED PERMANENTLY
LONDON 07-13 UTC   n=1516   +$1,055   +$0.70/tr   37%   ← the ONLY positive block
US     13-21 UTC   n=2394   -$4,613   -$1.93/tr   36%
post   21-24 UTC   n= 574   -$2,078   -$3.62/tr   31%
```

**★ ASIA IS BENCHED IN CONFIG, NOT BY A SWITCH.** `RunConfig.no_open_asia=True` → guard in `multislot_core._open()`, which is the single funnel every tournament entry passes through (one check covers all 8 gates and every sub-slot; a per-gate version gets missed on the next gate added). Window in `session.py::in_asia_block`. **NEW ENTRIES ONLY** — exits, closes and all flatten paths untouched. Revert: `RunConfig(no_open_asia=False)`. Day-rider unaffected (13:38-20:40 only).

**★★ "DON'T DAY-TRADE MNQ UNTIL THE US OPEN" WAS REFUTED — do not re-adopt it.** Pre-open is −$1.75/tr against the US session's −$1.93: indistinguishable, US marginally WORSE. The signal is that **ASIA specifically** is the worst block, and **LONDON is the best thing the desk has**. A "wait for the US open" policy would bench the best window along with the worst.

**★ THE ONE TIME-BASED FINDING THAT SURVIVED THE FULL BATTERY:** the **75 minutes after the US open** (13:30-14:45) is where expectancy lives.
```
0-75 min    n=562  +$5,016  +$8.93/tr  42%   strip-best-3 +$695 · halves +$828/+$4,188 · +3.27sd, beaten 0.0%   PASS×3
75-210 min  n=657  -$3,493  -$5.32/tr  33%   strip-worst-3 FLIPS to +$180 · halves +$507/-$4,000               FAIL
```
So the early window being good is robust; **the late window being bad is NOT** — three days carry $3,673 of a $3,493 loss. **Do not bench the late session**; that would be acting on three days.

⚠ THINGS I CLAIMED AND THE BATTERY KILLED, same day — the pattern to distrust: a "15-30 min after the open is the worst window" finding looked striking (−$17.03/tr) and failed everything — it was only the FOURTH-worst window, one day was 60% of it, 18% of random windows were worse, and the halves were opposite signs (+$31/tr vs −$38/tr). I called it "a far bigger, more consistent hole" *before* testing. Post-hoc time-slicing generates these freely; a simple one-boundary hypothesis on n=562 is a different thing from a hunted 15-minute window.

See [[exits-are-exit-proof]] for the same discipline applied to exits, and [[day-rider-live-paper]].
