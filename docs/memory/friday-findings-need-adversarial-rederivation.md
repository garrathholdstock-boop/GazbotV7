---
name: friday-findings-need-adversarial-rederivation
description: Friday-report headline numbers routinely do not survive independent re-derivation — verify adversarially before any of them reach a recommendation.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 882eb15b-b9b1-4c08-9348-cd06bd148585
  modified: 2026-08-01T10:38:25.181Z
---

On 2026-08-01 I re-derived four headline recommendations from the 07-31 Friday report using fresh agents told to REFUTE, not confirm. **Only one survived.**

- TREND_UP router fix "+$1,615/wk, 9/9 folds" → **withdrawn**. Arithmetic reproduced exactly (+$1,644), but: a *temporal* double-count (same error the section itself caught on another axis) cut it 57%; a 20,000-draw placebo test under two independent regime tags returned z=−0.16 p=0.56 (null) and z=−2.56 (worse than random); 52% of it was two episodes on the week's biggest DOWN day.
- grind exit cell {a_r 0.5, b 1.0} → **withdrawn**, −$1,127 *worse* than leaving the default alone.
- grind entry fix "£700/wk" → **wrong baseline**. Replay applied filters that were dead on the live desk, so the honest before/after was +$1,552→+$2,830, not −$284→+$2,830.
- Dead ER/ATR floors → **confirmed** (independently, three times, by three different routes) — though its magnitude was overstated 44× (raw log lines counted as episodes).

**Why:** the Friday workflow generates findings but never adversarially verifies them, and single-agent numbers carry the author's framing unchallenged. A finding computed once is a hypothesis, not a result.

**How to apply:** before any Friday finding becomes a recommendation, re-derive it with an agent instructed to refute — independent regime tags where the tag is the desk's own, placebo/null controls, strip-best-N, leave-one-day-out, and an honest position-accounting check. Report survivors and casualties both. Never let a number reach the playbook on one pass. See [[exit-lab-paired-method-overstates]] and [[friday-fold-in-fails-silently]].
