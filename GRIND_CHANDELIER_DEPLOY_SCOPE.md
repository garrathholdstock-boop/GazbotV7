# Grind threshold-chandelier deploy — SCOPE (queued for Sunday 2026-07-26)

**Status:** APPROVED by operator 2026-07-25, deploy DEFERRED to Sunday (no Saturday-night IBKR-maintenance
restarts — see [[weekend-no-flatten-no-fuss]]). This doc is the durable spec in case the scheduling session dies.

## What & why
Switch **grind_long ONLY** from its current `scalp-2R` exit to a **threshold (loose-then-lock) chandelier**.
Validated (scratchpad `recon.py`, one tick-honest engine, full 07-05→24 archive): the operator's profile
`start_k=3.5, lock_r=4.0, lock_k=0.75` nets **+$1,626 vs scalp-2R +$1,118 (+$508)** — tail-capture 61% vs 37%,
whipsaw 23% vs 64%, green every ISO-week. It is the ONLY exit that beats scalp-2R on grind; captures the big
trend runs (07-17 ~44-ATR: +$415/+$395 per trade vs scalp +$172/+$175). **abs_veto: NO change — keep scalp-2R**
(no chandelier beats its +$1,384; it's a fast-2R-pop gate, not a trend gate — the exit must match the edge shape).
⚠ in-sample, one summer RANGE regime, +$508 leans on ~a dozen big-ATR runs (thin trend-day n) — a bet on trends.

### ★ lock_r FINE-SWEEP (2026-07-26, scratchpad `lockr_sweep.py`/`lockr_robust.py`) — DEPLOY lock_r=6.0, NOT 4.0
Operator asked "did you try 4.5/5/5.5/6 to see what's best?" — swept lock_r {3.0–8.0} × lock_k {0.5,0.75} on the
same engine (grind_long n=89 full / n=21 wk30; incumbent 3.5/4.0/0.75 reproduces +$1,626/+$546 exactly).
**Result: a HIGHER lock_r wins and is robust. Best = `start_k=3.5, lock_r=6.0, lock_k=0.5` → +$1,782 full (+$156)
/ +$747 wk30 (+$200)**, tail-cap 63%, whipsaw 16% (vs 23%), win 29%. **Robust 15/15 leave-one-day-out** (beats
incumbent every LODO scenario; dropping the 07-17 44-ATR monster day the edge WIDENS to +$245 — carried by four
ordinary-ATR days 07-08/21/23/24, NOT one monster). ⚠ The operator's hypothesized **4.5–5.0 band is a TROUGH**
(~$460 BELOW both 4.0 and 6.0 — runs peaking ~4.5R ride the wide trail and give it back before hard-locking); the
lock_r surface is jagged so 6.0-vs-5.5-vs-7.0 is noise-sensitive, but lock_r=6.0 robustly clears 4.0. Two picks:
**(recommended, cleanest one-knob) 3.5/6.0/0.75 = +$1,710/+$741, robust 13/15**; **(max) 3.5/6.0/0.5 = +$1,782/
+$747, robust 15/15, lowest whipsaw.** → **PIN `start_k=3.5, lock_r=6.0, lock_k=0.5`** (most robust + max); operator
may override to lock_k=0.75 (one-knob, −$72) before 18:07.

## The exit mechanism (loose early, firm lock past lock_r)
The current `exit_chandelier` tightens CONTINUOUSLY (`k = start_k − tighten·peak_r`) — it CANNOT hold "loose until
4R then step-lock." Add a dedicated function (mirror the `exit_fixed` pattern from 07-25):
```
def exit_chandelier_lock(pos, price, *, start_k, lock_r, lock_k) -> str | None:
    # Loose trail (start_k·ATR) until the run reaches lock_r; then a FIRM lock (lock_k·ATR). Uncapped;
    # only exits in profit (native 1-ATR STP owns losses). peak_r = peak_favorable/atr.
    atr = pos.entry_atr
    if atr <= 0 or pos.peak_favorable <= 0: return None
    peak_r = pos.peak_favorable / atr
    k = start_k if peak_r < lock_r else lock_k
    giveback = k * atr
    fav = (price - pos.entry_price) if pos.side == "LONG" else (pos.entry_price - price)
    if fav > 0 and fav <= pos.peak_favorable - giveback:
        return "CHANDELIER"
    return None
```

## Implementation steps
1. `deciders.py`: add `exit_chandelier_lock` (above).
2. `slot_strategy.py`: add SlotSpec fields `lock_r: float = 0.0`, `lock_k: float = 0.0`; import `exit_chandelier_lock`;
   in `_manage` add a branch `elif spec.exit == "chandelier_lock": reason = exit_chandelier_lock(pos, price,
   start_k=spec.chandelier_start_k, lock_r=spec.lock_r, lock_k=spec.lock_k)`.
3. grind_long SlotSpec → `exit="chandelier_lock", chandelier_start_k=3.5, lock_r=6.0, lock_k=0.5,
   giveback_enabled=False` (lock_r=6.0 per the 07-26 sweep, NOT 4.0; keep sizing=conviction, base_size=2,
   ATR≥24 floor + no ER floor stay in deciders).
   Drop the scalp `target_r`/`stop_atr_mult` (unused for this exit; leave or remove).
4. Tests: add an `exit_chandelier_lock` unit test (loose→lock transition at lock_r); the roster shape tests are
   UNCHANGED (grind_long tag/side/kind unchanged — only its exit config changed).
5. Full suite must be GREEN.

## Deploy (Sunday, gateway healthy, desk flat, BEFORE the ~22:00 UTC reopen)
Confirm flat → `sudo systemctl restart gazbot7-tournament` → verify startup `slots=[...]` + overall OK/preflight/flat.
**If the restart HANGS (Sat/Sun IBKR-maintenance sync-stall):** clean `systemctl stop` → wait ~15s → single `start`
(this recovered it 2026-07-25). Then commit (`src/` + tests, NOT data/) + push. Ping the operator.

## Revert
grind_long back to `exit="scalp", target_r=2.0, stop_atr_mult=1.0, giveback_enabled=False` + restart.
