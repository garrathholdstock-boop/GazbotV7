---
name: go-find-the-price-yourself
description: "★★★STANDING ORDER (operator, 2026-08-06): 'you look at it like me. dont rely on machines feeding you. you go and find it.' Query raw bars/ticks and build the structure read yourself — do NOT form a view from desk_view, router_watch, open_hour_watch verdicts or the shadow board."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 20d20fe8-b00d-478a-9a38-35782c5c05e3
  modified: 2026-08-06T15:25:36.577Z
---

**Operator, 2026-08-06:** *"from now on. you look at it like me. dont rely on machines feeding you. you
go and find it."*

**Why:** on 08-06 every wrong call came from consuming a pre-digested verdict instead of reading price.
The desk hands out summaries cheaply — `desk_view`'s day aggregate, `router_watch`'s REGIME→TREND flag,
`open_hour_watch`'s [ACT] lines, the shadow P&L table — and every one of them is either backward-looking
or already collapsed into a conclusion. Acting on them meant being short at the low and flat through a
+297pt rally the operator saw at a glance. Reasoning harder on pre-chewed inputs just produces confident
wrong answers faster.

**How to apply — build the read from PRIMARY data, every time:**

```sql
-- 5-min OHLC structure from raw 5s bars (this is "the chart")
select (bar_ts - bar_ts%300) m5, arg_min(open,bar_ts) o, max(high) h,
       min(low) l, arg_max(close,bar_ts) c, sum(volume) v
from c.bars where symbol='MNQ' and timeframe='5s' and bar_ts >= <session_start>
group by 1 order by 1
```
Then label each bar HH+HL / LH+LL / inside, and read the swing sequence. Compute VWAP
(`sum(close*volume)/sum(volume)`) and ATR yourself (mean 1-min high−low over the last ~20 min from
`c.ticks`) — then price-minus-VWAP in ATRs, and % position in the session range.

That gives, from first principles: **structure** (higher highs/lows or lower), **where price sits in
the range**, **how stretched it is from the mean**, and **whether the swing just failed**. That is what
the operator sees in two seconds and it is the whole basis of the call.

**Order of operations, non-negotiable:** structure → range position → VWAP extension → segment ER/ATR
→ *then* the shadow board, only to confirm ([[read-the-tape-first-shadow-is-confirmation]]).
⚠ Extension figures EXPIRE FAST — on 08-06 price went +6.6 ATR above VWAP at 14:19 (grind structurally
could not fire) to +1.6 ATR by 15:20 (the pullback had arrived). Any claim built on an extension number
must be recomputed before it is repeated. See also [[verify-desk-facts-never-guess]].
