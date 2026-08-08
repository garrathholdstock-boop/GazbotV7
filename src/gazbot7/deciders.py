"""GAZBOT V7 — the decider library (D6): pure entry/exit functions.

Every gate and exit is a pure function of features (+ a position for exits). The
LIVE desk and the SHADOW desk call these *identically* — there is no parallel
copy to drift (V5's equity-vs-crypto map-drift class is impossible). The
reversal_grab research (turnback momentum) lands here as the SHORT variant slate;
thrust is the live momentum edge. Exits: the fixed native 1-ATR STP is the
protective floor (armed by safety.py), and these add the scalp R-target + the
adverse / absorption cuts. Clean-room: re-derived from the sweeps, not copied.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

# ── features ──────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class Bar:
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class Features:
    price: float
    atr: float
    atr_pct: float
    vwap: float
    vwap_slope_atr: float
    ext_atr: float  # (price - vwap) / atr, signed (+ above VWAP)
    net_atr_5: float  # (close - close[-6]) / atr, signed
    vol_surge: bool
    n_bars: int
    net_atr_2: float = 0.0  # (close - close[-3]) / atr — the FAST 2-bar impulse
    vwap_slope_fast: float = 0.0  # VWAP slope over a SHORT (12-bar) window — flips at reversals
    net30_pt: float = 0.0  # trailing 30-bar (≈30-min) net move in POINTS — regime-DEPTH gate for rgv_long
                           # (2026-07-25: deep down-legs, net30<−125pt ≈ −5·ATR, are falling knives → skip the long fade)


_ATR_CONTIGUOUS_S = 90   # Bar.ts is SECONDS; 1-min bars are 60s apart, >90s = a session break between


def _atr(bars: list[Bar], n: int = 14) -> float:
    """ATR-14, HALT-AWARE (★2026-08-03 fix).

    The two gap terms (|high - prev_close|, |low - prev_close|) only mean anything when the two bars
    are genuinely adjacent in time. MinuteBars is a deque by COUNT and a session halt does not flush
    it, so the first bar after a reopen sits next to the last bar before the halt and the entire
    weekend gap enters true range as one enormous bar.

    Live cost, 2026-08-02 22:00 reopen: gap 283.5pt (Fri close 28,284 -> Sun open 28,567.5). ATR read
    48.1pt where the halt-aware value is 29.1pt — 1.65x. The stop is 1.0xATR and every target is an
    R-multiple, so that ONE number mis-sized everything at once: two abs_veto_long lots took 43-46pt
    stops instead of ~29, and their 1.0R target was pushed to ~$96 so a +$68 move could never reach it.
    Both went green and handed it all back, -$180.5. Halt-aware, Lot A's target sits at 29.1pt — inside
    the 34pt it actually reached — so it banks instead of stopping.

    Rare but sharp: scripts/atr_gap_audit.py finds 3 of 489 closed trades affected, ALL in the first
    minutes after a SUNDAY reopen. The nightly 21:00-22:00 halt barely moves price so it inflates
    nothing; the weekend one does. The window self-heals within ~14 bars as real minutes push the gap
    out of the ATR window — which is why it stayed invisible for so long.

    Fix: when two bars are not contiguous, keep the bar's OWN high-low range and drop the two
    cross-halt terms. Byte-identical output whenever bars are contiguous — i.e. every other moment of
    the week. Revert: always take the 3-way max."""
    trs = []
    for i in range(1, len(bars)):
        hl = bars[i].high - bars[i].low
        if (bars[i].ts - bars[i - 1].ts) <= _ATR_CONTIGUOUS_S:
            trs.append(max(hl, abs(bars[i].high - bars[i - 1].close),
                           abs(bars[i].low - bars[i - 1].close)))
        else:
            trs.append(hl)
    if not trs:
        return 0.0
    m = trs[-n:]
    return sum(m) / len(m)


def _vwap(bars: list[Bar]) -> float:
    num = sum(((b.high + b.low + b.close) / 3) * b.volume for b in bars)
    den = sum(b.volume for b in bars)
    return num / den if den > 0 else bars[-1].close


def compute_features(bars: list[Bar]) -> Features:
    price = bars[-1].close
    atr = _atr(bars)
    vwap = _vwap(bars)
    half = len(bars) // 2
    vwap_first = _vwap(bars[:half]) if half >= 1 else vwap
    slope = (vwap - vwap_first) / atr if atr > 0 else 0.0
    ext = (price - vwap) / atr if atr > 0 else 0.0
    net5 = (price - bars[-6].close) / atr if (len(bars) >= 6 and atr > 0) else 0.0
    net2 = (price - bars[-3].close) / atr if (len(bars) >= 3 and atr > 0) else 0.0
    net30 = (price - bars[-31].close) if len(bars) >= 31 else 0.0  # 30-min net move in POINTS (regime depth)
    # fast VWAP slope: a short (12-bar) window flips within minutes of a reversal,
    # where the 60-bar slope lags 30-40min and wrong-foots grind/rg (2026-07-16).
    _rec = bars[-12:] if len(bars) >= 12 else bars
    _h = len(_rec) // 2
    slope_fast = (_vwap(_rec) - _vwap(_rec[:_h])) / atr if (atr > 0 and _h >= 1) else 0.0
    if len(bars) >= 6:
        prior = [b.volume for b in bars[-6:-1]]
        surge = bool(prior) and bars[-1].volume >= 1.5 * (sum(prior) / len(prior))
    else:
        surge = False
    return Features(price, atr, atr / price if price else 0.0, vwap, slope, ext, net5, surge, len(bars), net2, slope_fast, net30)


# ── favourable-condition (efficiency) gate — TICK-HONEST re-derivation 2026-07-21 ──
# ER = Kaufman net-progress / total-path over the trailing 30 one-min closes (~0 chop, ~1 trend).
# A gate only OPENs when the tape condition suits its style. Thresholds come from the TICK-HONEST
# backtest (scripts/gate_backtest_tickhonest.py — entry on the 1-min signal, exit repriced on the
# real ticks) + its per-ER-band sweep — NOT the optimistic BAR-CLOSE gate_backtest (that gave
# illusory numbers: grind_long "+$1,664" was −$1,228 on honest fills). Set from where each gate's
# money ACTUALLY sits by ER band (grind is momentum→floor; rgv needs a specific window→band):
#   grind_long   FLOOR 0.20    — loses in EVERY band; floor only cuts the low-ER bulk-bleed. ⚠ still a
#                                net loser tick-honest → RELEGATION candidate; the floor is damage control.
#   thrust_short FLOOR 0.20    — WITH the ATR>=16 floor (below), ER>=0.20 sharpens it further: the
#                                ER>=0.20+ATR>=16 population is +$726/38tr (vs +$381 ER-only). Operator
#                                chose to ER-gate it too (2026-07-22) to realise that sweep number.
#   rgv_long     BAND 0.10–0.40 — money is the mid-band (peak 0.3–0.4 +$488); bleeds only at the
#                                extremes. Keeps +$864 (the old 0.25 ceiling strangled its best band).
#   rgv_short    BAND 0.30–0.40 — its ONLY edge is that one sliver (+$507); everything else bleeds ~−$2k.
#                                Fragile (37tr, single band) — currently DISABLED via switch; band applies
#                                IF re-enabled. RELEGATION candidate.
#   capitulation_long CEIL 0.10 — tick+L2 duck edge is 0.0–0.10 (+$257). ⚠ fixed-exit-derived.
#   exhaustion_short  CEIL 0.05 — tick+L2 duck edge is 0.0–0.05 (+$295). ⚠ fixed-exit-derived.
# ⚠ tick coverage ~9 days (one summer regime) + 60-min hold cap — a LEAD; re-validate a 2nd regime.
# Momentum → FLOOR (need trend); reversion → CEILING (need chop) or BAND (a specific ER window).
ER_FLOOR: dict[str, float] = {}  # ★2026-08-01 (operator, Saturday window): ALL ER floors DELETED. They were never in force — the dual-slot scale-out slate broke the lookup on 07-29 16:20 (see tournament.py:139), so no ER floor has blocked a single trade in production; both were committed ~18h AFTER that cutover. Re-derived on the blocked book (8d, tick-honest, one-position-per-slot): grind_long ER>=0.35 blocked +$2,923/173sig (strip-3 +$1,132, LODO +$10.03) and abs_veto_long ER>=0.25 blocked +$640/52sig (strip-3 +$111, LODO +$4.88) — i.e. both floors were blocking PROFITABLE populations. Confirms the standing "ER filters are FAKE" prior and REFUTES the 07-30 grind 0.35 rationale below, which was an n=1 rotation-day finding. [prev: {"abs_veto_long": 0.25, "grind_long": 0.35}]
#   Superseded rationale, kept for the audit trail: ★2026-07-30 (operator): momentum-long ER floors — grind_long 0.35, abs_veto_long 0.25. Grounded in the 07-30 rotation day: momentum longs bucketed by 30-min entry-ER were −$431 @18%W in the MID band 0.20-0.35 (rotation legs that look trendy but reverse) vs +$279 @40%W at ER≥0.35 → the floor excludes the mid-zone bleed. abs_veto gets a LOWER floor (0.25) because its 55s absorption-veto already filters fakes, so it can fire earlier on a REAL thrust — LIVE PROOF: abs_veto's +$251 break-win (A +77.5 TARGET / B +174 CHANDELIER) fired at sub-0.35 ER; a blanket 0.35 floor would have blocked it. ⚠ REVERSES the 07-25 grind rehab (dropped grind's floor: "runners & false-starts share ER 0.14, ATR is the lever") — that was a trend-week finding, this is a rotation-day one. N=1, NEEDS a multi-regime backtest before trusting. [prev: abs_veto_long 0.20, grind_long none].
# ★2026-07-28: an exhaustion_short ER floor 0.08 was tried+REVERTED same day — the 225-trade shadow reprice under the live exit showed the real bleed is DIRECTIONAL (counter-trend short-into-uptrend −$190/56tr), NOT low-ER (chop ≈breakeven). Fixed via a counter-regime ENTRY veto in slot_strategy instead (see veto_counter_regime).
ER_CEIL: dict = {}  # ★2026-07-25: BOTH footprint-gate ER ceilings DROPPED — capitulation_long (0.10) AND exhaustion_short (0.05) traced to the SAME footprint_backtest_duck.py DuckDB float-division bug (ts/5000*5000 never buckets → garbage ER); both revived on the exit fix instead. No gate uses an ER ceiling now.
# ★ 2026-07-24 (operator): ER band REMOVED for rgv_long/rgv_short — the 35s ABSORPTION-CONFIRM
# (below) subsumes it (a Friday-lab grid found them near-identical at 35/40s: the confirm reads
# "genuine reversion vs falling-knife" from the microstructure, sharper than the ER band read it
# from the bar tape). rgv now runs ER-ungated + absorption-confirmed. Revert = restore the two bands.
ER_BAND: dict = {}   # (lo, hi): OPEN only when lo <= er <= hi  (empty now — no gate uses a band)
ER_WINDOW = 30  # bars (1-min bars → the 30-min ER used across the desk)

# ── 35s ABSORPTION-CONFIRM on the rgv faders — mechanism KEPT, gate set EMPTIED (revert pattern) ──
# The mirror of the abs_veto momentum filter: a fader WANTS the move it fades to be exhausting, so
# it delays entry CONFIRM_SECS and only fires if that move ABSORBS in the window (heavy aggressor
# flow the WRONG way for the fade that FAILS to move price).
# ★ REMOVED FROM LIVE 2026-07-24 (operator). It went live at 12:27 UTC on a same-week sweep, but a
# 2-WEEK tick-honest re-test (rgv_confirm_layer.py, 07-15..17 + 07-20..24) showed the confirm is a
# blunt exposure cut, not a stabiliser: it DESTROYS the short side's robust tight-ext edge (2-wk net
# +$670 raw → −$180 confirmed at ext3.0/turn0.15) and only marginally trims the weak long bleed. The
# real cross-week edge is the tight-ext SHORT base with NO confirm/flow; the long side is a
# direction-router problem, not a filter one. rgv now reverts to its raw base (ext 2.0, no ER band —
# band was removed earlier the same day, also operator). RE-ENABLE: add the gates back + restart.
CONFIRM_GATES: frozenset = frozenset()   # was {"rgv_long", "rgv_short"} — see note above
CONFIRM_SECS = 35
CONFIRM_MAX_SECS = 55     # give up on a signal older than this (the turn's gone)
CONFIRM_FLOOR = 30.0      # min net-aggressor size to count as absorption

# ── 55s momentum ABSORPTION-VETO on the abs_veto thrust gates (LIVE 2026-07-25, operator) ──
# abs_veto_long/short: a thrust fires, WAIT VETO_SECS, take it ONLY if the thrust STILL fires AND the
# burst was NOT absorbed in the window (heavy aggressor flow OUR way that FAILED to extend price = a
# fakeout to skip). The faithful promotion of the shadow variant abs_veto_55s (+$1,340 both sides,
# engine-truth 07-16..24). OPPOSITE polarity to the fader CONFIRM_GATES above (a fader enters ON
# absorption; a momentum gate SKIPS on it) — the veto TEST is exit_absorption(), not confirm_absorption().
VETO_GATES: frozenset = frozenset({"abs_veto_long", "abs_veto_short"})
VETO_SECS = 55            # wait this long after the thrust before entering
VETO_MAX_SECS = 75        # abandon a thrust signal older than this (a tape gap ate the window)
VETO_FLOW_MIN = 50.0      # net-aggressor size for the exit_absorption fakeout test (shadow default)

# ── 5s CONFIRM-VETO on exhaustion_short (LIVE 2026-07-29, operator) ──────────────────────────
# The fade's own "did the absorption hold?" check: after the exhaustion SHORT signal, WAIT
# EXH_CONFIRM_SECS and take it ONLY if the short has NOT gone adverse by > EXH_ADVERSE_PT (i.e.
# buyers didn't keep pushing = they really were exhausted). A short delay is the whole trick — long
# enough to catch the immediate failure, short enough to keep the winners' head-start.
# Backtest (89 faithful exhaustion_rev SHORT shadow fires, native 8/12/120s reprice): 5s/5pt cut 27
# fast-failing shorts, 0 winners cut, book +$9 → +$236, better on 4/5 days. ⚠ 1wk/one-regime fit;
# net-flow log running in parallel for the net_min tune. Revert: empty EXH_CONFIRM_GATES.
EXH_CONFIRM_GATES: frozenset = frozenset({"exhaustion_short"})
EXH_CONFIRM_SECS = 5           # wait this long after the signal before entering
EXH_CONFIRM_MAX_SECS = 20      # abandon a signal older than this (the turn's gone)
EXH_ADVERSE_PT = 5.0           # skip if price moved this many pt AGAINST the fade during the wait


def confirm_absorption(side: str, net_flow: float, price_change: float) -> bool:
    """True if the faded move is being ABSORBED → take the fade. LONG fade (rgv_long): heavy net
    SELLING that did NOT drop price. SHORT fade: heavy net BUYING that did NOT lift price."""
    if side in ("LONG", "BUY"):
        return net_flow <= -CONFIRM_FLOOR and price_change >= 0
    return net_flow >= CONFIRM_FLOOR and price_change <= 0

# ATR floor (entry ATR in POINTS) — a magnitude gate on TOP of the ER gate: don't ride a trend too
# small to run. Tick-honest ER>=0.20 + ATR sweep 2026-07-22 (~9 days, scripts/momentum_atr_sweep.py):
#   thrust_short 16 — the bleed is all at ATR<16; cutting it NEARLY DOUBLES the gate
#                     (+$381 nat → +$726 / 38tr, +$345). A real sharpening of an already-+EV gate.
#   grind_long   20 — grind is a tick-honest LOSER (nat −$1,228 at ER>=0.20); the floor only reduces
#                     the bleed, first crossing to breakeven at ≥20 (+$16 / 42tr). HARM-REDUCTION on a
#                     RELEGATION candidate — it doesn't make grind +EV, it bleeds less.
# ⚠ 9-day one-regime lead; bump/drop per Saturday.
ATR_FLOOR: dict[str, float] = {"grind_long": 22.0, "capitulation_long": 10.0}  # ★2026-08-08 (operator, SATURDAY #2 / grind-long-revert-atr22-ext30-0808): grind_long 10 -> 22, a straight REVERT of the 08-01 change below, on 21 sessions and two independent populations (REV2 · Q1 §10). Plateau 18-27; 22 is its peak but 24 is within $1,373 on a $6,000 number and beats it out-of-sample, so THE LITERAL IS NOT LOAD-BEARING. Deletes normal-chop and dead-chop entirely (575 of 744 legs). Corroborated on the 128 live router-gated lots: ATR>=24 turns -$182.50 into +$605.00. ⚠ HONEST SHAPE: +$4,151 is a DELTA over 11 tick-honest sessions / 165 legs of which 21 RUNNER EVENTS ARE THE ENTIRE RESULT — strip them and it is +$380.70 over 144 legs. 77% of the gain was already available pre-08-01, i.e. this is a revert to a previously-shipped cell, not a discovery. ⚠ The week's 6 live grind legs ALL fired at ATR>=22 (23.98/23.98/33.50) so the live book is SILENT on this revert; do not quote -$172 as support. Review on 20 admitted legs and on whether 4R events appear near the expected 12.7% rate — NOT on P&L. Revert: set back to 10.0. capitulation_long 10 unchanged. [prev: {"grind_long": 10.0, "capitulation_long": 10.0}]
#   Superseded rationale, kept for the audit trail: ★2026-08-01 (operator, Saturday window): grind_long 24 -> 10; abs_veto_short 16 DELETED. Re-derived on the blocked book (8d, tick-honest): grind ATR>=24 blocked +$982/151sig (strip-3 -$82) so 24 was blocking money — 9/10/11 is a genuine plateau and at 12 the blocked book flips positive, so 12 is one notch the WRONG side of a cliff and costs $941 vs 10. abs_veto_short ATR>=16 blocked +$137/28sig (strip-3 -$197, LODO -$11.02) = NOT PROVEN, deleted rather than tuned. capitulation_long 10 KEPT — the one floor that earns: blocked book -$459/22sig (strip-3 -$601, LODO -$26.62). "ATR floors are REAL" holds, but dollars peak at roughly HALF the old values. [prev: {"grind_long": 24.0, "capitulation_long": 10.0, "abs_veto_short": 16.0}]
#   Superseded rationale, kept for the audit trail: ★2026-07-25 rehab: grind_long 20→24 (the real lever — isolates volatile/trending days, +$1,118); capitulation_long 10 (winner-keeper, rescues the bad week); abs_veto_short 16. thrust_short retired.


def efficiency_ratio(bars: list[Bar], window: int = ER_WINDOW) -> float:
    """ER over the last `window` bar closes (see above). <6 closes → 1.0 (no data → don't gate)."""
    cl = [b.close for b in bars[-window:]]
    if len(cl) < 6:
        return 1.0
    path = sum(abs(cl[i] - cl[i - 1]) for i in range(1, len(cl))) or 1.0
    return abs(cl[-1] - cl[0]) / path


# ── SHADOW: momentum ER-hold spike-filter (2026-07-23, observe-only) ──────────────────────────
# Spike blind spot: a momentum gate fires when the LIVE/forming ER crosses its floor, but the move
# is a violent-chop whipsaw the closed bars don't sustain. Require the gate's ER condition to hold
# for ER_HOLD[gate] CONSECUTIVE completed bars, not just the latest one. Backtest (scripts/
# er_hold_sweep.py, 7d): momentum-only, recovers the momentum spike bucket (~$190) for ~$23 of
# sacrificed winners; N=1 already captures it, N=2 is a free safety margin (blocks nothing extra
# in-sample). MOMENTUM ONLY — the reversion gates fire AHEAD of the trailing ER by design, and a
# blanket application gutted the green capitulation/exhaustion gates (+$252/+$224 of winners cut).
# SHADOW: tournament.step evaluates + logs this but does NOT gate on it until forward-validated.
# ⚠ the live er_blocks already enforces the CURRENT completed-bar ER; this shadow's real job is to
# measure whether the PRIOR-bar hold adds incremental blocks on live decision-time ER (it may not).
ER_HOLD = {"abs_veto_long": 2}  # ★2026-07-25: moved to the current ER-floored momentum gate (grind's ER floor dropped in rehab; thrust_short retired). Observe-only shadow.


def er_hold_blocks(gate: str, bars: list[Bar], window: int = ER_WINDOW) -> bool:
    """True when the gate's ER condition is NOT met across all of the last ER_HOLD[gate] completed
    bars — a single-bar ER spike the tape walked back. Momentum gates only (no ER_HOLD entry →
    never blocked). Pure; same basis as er_blocks/efficiency_ratio (ER ending at each of the last
    n bars: efficiency_ratio(bars), efficiency_ratio(bars[:-1]), …)."""
    n = ER_HOLD.get(gate)
    if not n or len(bars) < 6:
        return False
    for k in range(n):
        window_bars = bars[: len(bars) - k] if k else bars
        if er_blocks(gate, efficiency_ratio(window_bars, window)):
            return True
    return False


def er_blocks(gate: str, er: float) -> bool:
    """True when the gate's efficiency condition is NOT met, so this OPEN should be suppressed:
    a momentum gate below its FLOOR (chop), a reversion gate above its CEILING (trend), or any
    gate outside its BAND (lo <= er <= hi). An ungated gate (in none of the three) is never blocked."""
    if gate in ER_FLOOR and er < ER_FLOOR[gate]:
        return True
    if gate in ER_CEIL and er > ER_CEIL[gate]:
        return True
    if gate in ER_BAND:
        lo, hi = ER_BAND[gate]
        if er < lo or er > hi:
            return True
    return False


def atr_blocks(gate: str, atr: float) -> bool:
    """True when the gate's entry ATR is below its floor (a trend too small to run) → suppress this
    OPEN. Magnitude gate on top of er_blocks; a gate with no ATR_FLOOR is never blocked here."""
    return gate in ATR_FLOOR and atr < ATR_FLOOR[gate]


# ── entry gates ───────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class Entry:
    side: str  # LONG / SHORT
    gate: str
    target_r: float = 2.0
    stop_atr_mult: float = 1.0


def gate_thrust(f: Features, *, thr: float = 1.5, require_vol: bool = True,
                amp_floor: float = 0.0, slope_align: bool = False, fast: bool = False) -> Entry | None:
    """Momentum: a signed 5-bar thrust of >= thr ATR, volume-confirmed. Two-sided.
    This is V5's ``tw_mnq_thrust_loose`` (op 2026-07-12): thr 1.5, keep the volume
    surge + amplitude floor, drop the still-extending veto — **decided on 1-minute
    bars** (a 5-bar thrust = a 5-MINUTE move; on 5s bars it was a 25s blip and fired
    constantly). ``amp_floor`` is V5's MOMENTUM_AMP_FLOOR (atr_pct >= 0.04% — the
    edge lives at 0.04–0.08, noise below 0.03); here in fraction units (0.0004)."""
    # fast=True triggers off the 2-bar impulse (net_atr_2) instead of the 5-bar move
    # — fires ~2 min into a move to catch its START, not 5 min in at the exhaustion.
    net = f.net_atr_2 if fast else f.net_atr_5
    if abs(net) < thr:
        return None
    if amp_floor and f.atr_pct < amp_floor:  # thin tape → stand down
        return None
    if require_vol and not f.vol_surge:
        return None
    # 2026-07-16 measurement: counter-trend thrust (a burst AGAINST the VWAP slope)
    # is the entire bleed (−$29/trade vs +$1.8 with-trend, n=50). slope_align requires
    # the thrust WITH the slope — same sign as the trigger; a flat slope (0) is vetoed too.
    if slope_align and net * f.vwap_slope_atr <= 0:
        return None
    return Entry(side="LONG" if net > 0 else "SHORT", gate="thrust")


def gate_reversal_grab(
    f: Features,
    *,
    side: str = "SHORT",
    turn_atr: float = 0.5,
    flow_min: float | None = None,
    tape_net: float = 0.0,
    require_rth: bool = False,
    in_rth: bool = True,
    ext_min: float = 2.5,
    fast_slope: bool = False,
    fast_turn: bool = False,
    atr_min: float = 0.0,
    net30_floor: float | None = None,
) -> Entry | None:
    """Turnback momentum: over-extended past VWAP, then a fresh turn back, optionally
    confirmed by aggressor flow. SHORT fades a stretch ABOVE VWAP rolling over; LONG
    (the mirror) fades a stretch BELOW VWAP turning up. The research's edge.

    ``fast_slope`` runs the regime guard off the SHORT-window slope (which flattens at
    a reversal, so the guard stops vetoing the exact turn it should catch); ``fast_turn``
    detects the turn on net_atr_2 (2-bar) not net_atr_5 — together they catch a fast
    reversal in its bottom 20% instead of being blocked (proven on the 15:17 run)."""
    slope = f.vwap_slope_fast if fast_slope else f.vwap_slope_atr
    if f.atr_pct > 0.09 or abs(slope) > 1.0:  # regime stand-down
        return None
    if atr_min and f.atr < atr_min:  # VOLATILITY-regime floor — a reversal only RUNS
        return None                  # when the tape has range; low-ATR fades fizzle (noise)
    if require_rth and not in_rth:
        return None
    turn = f.net_atr_2 if fast_turn else f.net_atr_5
    if side == "SHORT":
        if f.ext_atr < ext_min:  # stretched >= ext_min ATR ABOVE vwap
            return None
        if turn > -turn_atr:  # a fresh down-turn of >= turn_atr
            return None
        if flow_min is not None and tape_net > -flow_min:  # net-SELL confirm
            return None
        return Entry(side="SHORT", gate="reversal_grab")
    # LONG mirror — stretched BELOW vwap, turning up, optional net-BUY confirm
    if f.ext_atr > -ext_min:
        return None
    if turn < turn_atr:
        return None
    if flow_min is not None and tape_net < flow_min:
        return None
    # ★2026-07-25 regime-DEPTH floor (rgv_long): a fade of a stretch below VWAP that sits inside a DEEP
    # established down-leg (30-min net move < net30_floor pt) is a falling knife, not a bounce — skip it.
    # The one thing that separates rgv_long's knives from its flush-bounces (net30-depth AUC 0.64-0.69);
    # per-entry IN the gate, which dominates the day-level direction-router bench. LONG-only.
    if net30_floor is not None and f.net30_pt < net30_floor:
        return None
    return Entry(side="LONG", gate="reversal_grab")


# The forward-shadow slate (from the reversal_grab research). LIVE is MNQ-only;
# these run in shadow, scored on honest real_pnl, promoted only if they hold.
REVERSAL_SHORT_VARIANTS: dict[str, dict] = {
    "rg_short_050": dict(turn_atr=0.5, flow_min=None),  # moderate sweet spot (n35 / +14/tr)
    "rg_short_025_raw": dict(turn_atr=0.25, flow_min=None),  # early control — does filtering earn it?
    "rg_short_025_flow25": dict(turn_atr=0.25, flow_min=25),  # early + light flow
    "rg_short_025_flow50": dict(turn_atr=0.25, flow_min=50),  # early + strong flow (Phase-3 winner)
    "rg_short_025_flow50_rth": dict(turn_atr=0.25, flow_min=50, require_rth=True),  # + US session
}


# ── exits ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class Position:
    side: str  # LONG / SHORT
    entry_price: float
    entry_atr: float
    peak_favorable: float = 0.0  # best favourable excursion so far, in price


def gate_capitulation(f: Features, *, cap_sell: float = 0.0, cap_buy: float = 0.0,
                      cap_base: float = 0.0, cap_dpx: float = 0.0, cap_flip: bool = False,
                      climax_min: float = 3.0, dom_min: float = 0.7,
                      require_flip: bool = False) -> Entry | None:
    """FLUSH-AND-FLIP — a microstructure fade of a capitulation (2026-07-16, from the
    L1/tape footprint of today's down-legs). The signal is a ONE-SIDED aggressor
    CLIMAX in the short tape window — that side's volume >= ``climax_min`` × its
    baseline rate AND >= ``dom_min`` of flow — while price moved that way (``cap_dpx``).
    A sell-climax that drove price down → fade LONG; a buy-climax blow-off up → fade
    SHORT. ``require_flip`` demands the aggressor delta has already turned (buyers
    taking over at the low / sellers at the high) — the tight, higher-conviction
    version; loose fades the climax itself. Bar-based ``net_atr_2`` is too slow for
    these sub-minute flushes — the tape climax IS the trigger."""
    tot = cap_sell + cap_buy
    if cap_base <= 0 or tot <= 0:
        return None
    if cap_dpx < 0 and cap_sell / cap_base >= climax_min and cap_sell / tot >= dom_min:
        if not require_flip or cap_flip:  # sell flush + buyers stepping in at the low
            return Entry(side="LONG", gate="capitulation")
    if cap_dpx > 0 and cap_buy / cap_base >= climax_min and cap_buy / tot >= dom_min:
        if not require_flip or not cap_flip:  # buy blow-off + sellers stepping in at the high
            return Entry(side="SHORT", gate="capitulation")
    return None


def gate_grind(f: Features, *, tape_net: float = 0.0, slope_min: float = 0.5,
               ext_lo: float = 0.3, ext_hi: float = 4.0, flow_min: float = 0.0,
               fast_slope: bool = False) -> Entry | None:
    """Trend CONTINUATION — ride an established VWAP trend while price is riding WITH
    it (above VWAP in an up-trend) but not yet exhausted (``ext_lo..ext_hi``). For the
    sustained grinds that thrust (a 5-bar burst gate) misses entirely. Chandelier-
    exited (uncapped ride). NB: ``vwap_slope_atr`` is a 60-bar measure, so it LAGS a
    fresh reversal — this owns an *established* trend, not the first reclaim off a
    flush (the capitulation gate owns that) — UNLESS fast_slope, the short-window slope
    that flips within minutes of a reversal. Down-grind is the mirror."""
    slope = f.vwap_slope_fast if fast_slope else f.vwap_slope_atr
    if slope >= slope_min and ext_lo <= f.ext_atr <= ext_hi and tape_net >= flow_min:
        return Entry(side="LONG", gate="grind")
    if slope <= -slope_min and -ext_hi <= f.ext_atr <= -ext_lo and tape_net <= -flow_min:
        return Entry(side="SHORT", gate="grind")
    return None


# ── NIPC — news-impulse pullback continuation (2026-08-01, greenfield-lab survivor) ──────────
# The one brand-new entry that came through the Friday M3 robustness battery alive (reports/
# friday_v7/sections/movement3_greenfield.html, "Step 5 — THE SURVIVOR"). It is NOT a filtered
# breakout: strip the pullback requirement and the same impulse detector / regime gate / exit /
# tape collapses to −$2,143 @27.9% over 290 trades. The pullback-and-resume IS the edge — the
# opposite trade at the opposite price.
#
# Seven rules, verbatim from the report's spec table (do not "improve" them without a re-run):
#   1 IMPULSE  over the trailing 2 min (24 × 5s bars) leg = close[i] − close[i−24]; require
#              |leg| >= 1.0 × ATR1m measured BEFORE the impulse (no self-reference — the ATR
#              history is carried per-bar so the value read is the one as of the impulse origin).
#              side = sign(leg); ext = impulse extreme, org = its origin, span >= 5 pt.
#   2 PULLBACK walk forward <= 3 min tracking r = |ext − pullback| / span. r > 0.75 → ABANDON
#              (structure broken — that was not a pullback). ARM at the first bar r >= 0.35.
#   3 TRIGGER  entry = pullback extreme + 0.50 × the retrace distance (half-back), still inside
#              the impulse. Live for 1 minute; fill on the first tick trading through. No fill →
#              the setup expires, no trade.
#   4 STOP     pullback extreme ∓ 4 pt. R = |entry − stop| (median 17.2 pt in the lab); R < 2 pt
#              → reject. ★ R is carried to the desk AS ``entry_atr`` on the OPEN intent, so the
#              native 1-ATR STP + exit_scalp reproduce the lab's stop/target with no new exit
#              machinery (same trick footprint.py uses for the fixed 8/12 exhaustion exit).
#   5 EXIT     Lot A 2.0R / Lot B 2.5R (PROVEN pair — fixed 2.5R on Lot B beats the trail by
#              $1,285 in this window; do NOT swap Lot B to the chandelier). 20-min hard cap,
#              flat by 15:30 UTC.
#   6 RISK     one position at a time (both sides share the tracker), 2-min cooldown after exit.
#   7 REGIME   OFF in dead-chop (ATR1m < 18 pt AND ER15 < 0.35) — the one perfectly stable regime
#              finding (negative in all 25 scale-out configs and every top exit config).
# Armed ONLY 13:00 <= t < 15:00 UTC; decisions on 5s bar closes, fills on ticks; no flow/book input.
# ⚠ 12 days / one regime-fortnight. Promotion-ladder first live week = 1 lot.
#
# ★★ ACCEPTANCE FAILURE — READ BEFORE ARMING (2026-08-01). scripts/nipc_replay.py drives THIS
# tracker over the lab's own 12 days of capture.db tape and does NOT reproduce the lab's P&L:
#     lab  n=171  +$2,676  43.3% win  $15.6/tr  9/12 days green  median R 17.2pt
#     here n=159    +$264  34.6% win   $1.7/tr  7/12 days green  median R 13.6pt
# The ENTRY engine reproduces: the report's six published ablation trade-counts all land within
# ~7% (FULL/RMIN=0.15/RMAX=1.5/RES=0/RMIN=0+RES=0 at 0.93x lab), the dead-chop share matches
# (16% vs 17%), the tick-honest half matches n=83 vs 85. The divergence is entirely the
# target-hit rate: 2.5R-before-1R-adverse happens 34.6% of the time here, not 43.3%. That was
# verified twice — the sequential sim and an independent DuckDB tick race agree exactly (30/83).
# It is NOT costs: zeroing the fee AND the slippage only reaches +$1,320 gross, against the
# ~+$3,700 gross the lab's net implies. It is not the tie rule, the intrabar path, the geometry
# (4 alternative readings of ext/org/extension all land in -$427..+$264) or the stop buffer.
# So: this gate SHIPS BENCHED (data/gate_switches.env nipc_*=off). It is still comfortably above
# the report's own null (a random entry in this window is a -$846 loser), but it is a ~$1.7/trade
# construct on our replay, not a $15.6/trade one — nowhere near enough to arm on.
NIPC_WIN_START_S = 13 * 3600      # 13:00 UTC — the news window opens
NIPC_WIN_END_S = 15 * 3600        # 15:00 UTC — last impulse detection
NIPC_FLAT_BY_S = 15 * 3600 + 1800  # 15:30 UTC — flat, unconditionally
NIPC_BAR_S = 5                    # decision bar (5 seconds)
NIPC_IMPULSE_BARS = 24            # 2 minutes
NIPC_ATR_MULT = 1.0               # |leg| >= this × ATR1m (pre-impulse)
NIPC_SPAN_MIN_PT = 5.0
NIPC_PULLBACK_BARS = 36           # 3 minutes to produce the retrace
NIPC_RMIN = 0.35                  # arm here
NIPC_RMAX = 0.75                  # beyond here the impulse is broken → abandon
NIPC_RES = 0.50                   # half-back resumption trigger
NIPC_TRIGGER_BARS = 12            # the trigger is live for 1 minute
NIPC_STOP_BUF_PT = 4.0
NIPC_R_MIN_PT = 2.0
NIPC_HOLD_CAP_S = 20 * 60
NIPC_COOLDOWN_S = 120
NIPC_DEAD_ATR_PT = 18.0
NIPC_DEAD_ER15 = 0.35
NIPC_ER15_BARS = 15               # ER over the trailing 15 one-minute closes


def nipc_in_window(ts_ms: int) -> bool:
    """True inside the 13:00–15:00 UTC news window (the only time NIPC arms)."""
    sod = (ts_ms // 1000) % 86400
    return NIPC_WIN_START_S <= sod < NIPC_WIN_END_S


def nipc_past_flat_clock(ts_ms: int) -> bool:
    """True at/after 15:30 UTC — any open NIPC position must be flat."""
    return ((ts_ms // 1000) % 86400) >= NIPC_FLAT_BY_S


def nipc_dead_chop(atr1m: float, er15: float) -> bool:
    """Rule 7 — the ONE regime the published spec turns off in (both conditions, not either)."""
    return atr1m < NIPC_DEAD_ATR_PT and er15 < NIPC_DEAD_ER15


# ── ★★2026-08-05 REGIME FILTER — the fix the n>=40 review actually found ───────────────────────────
# The n>=40 review came due at n=43 live: -$370.50, 26% win, -$8.62/trade. I first read the SHORT side's
# 0-for-10 as a broken implementation. It was not — replaying the SAME tape went 0-for-8 on shorts too.
# When the model and the desk agree, the EDGE is absent, not the code. Bucketing the lab window by
# regime shows exactly where nipc's money is and is not:
#
#     in-between-building   n=27   +$303   +$11.2/tr   44% win   <- the money
#     clean-trend           n=19   +$181    +$9.5/tr   42%       <- the money
#     dead-chop             n=21     +$2    +$0.1/tr   38%       <- NEUTRAL, and the only one rule 7 cut
#     violent-whipsaw       n=50    -$55    -$1.1/tr   28%       <- the drag, and the BIGGEST bucket
#     normal-chop           n=11    -$34    -$3.1/tr   27%       <- the drag
#
# So the shipped filter removes the one bucket that costs nothing and leaves both losing ones in. On
# 2026-08-05 that let nipc take 11 violent-whipsaw fires and 0 clean-trend, and rule 7 blocked 2 of 19.
# Keeping only the two paying buckets is +$484 on n=46 against -$89 on n=61 — ~+$10.5/trade versus
# +$3.1 blanket.
#
# ★ WHY THIS BELONGS HERE AND NOT IN THE ROUTER (operator asked): the router ticks every 5 MINUTES and
# nipc's mean hold is 1.4 MINUTES — it cannot react inside a trade. And a router bench is session-level,
# while these regimes INTERLEAVE (08-05 was 11 whipsaw + 6 in-between mixed through the afternoon), so
# only a per-entry check can separate them. Both inputs are already handed to the detector.
#
# ⚠ IN-SAMPLE. This is regime attribution on the same window that produced the gate, n=46 in the good
# buckets. It is a MECHANISM rather than a swept threshold, which is why it is trusted more than most —
# but tomorrow is its first out-of-sample day. Revert: NIPC_REGIME_FILTER = False.
NIPC_REGIME_FILTER = True
NIPC_TREND_ER15 = 0.55            # >= this is clean-trend
NIPC_BUILDING_ER15 = 0.35         # >= this is in-between-building
NIPC_VIOLENT_ATR = 25.0           # >= this, below the ER floors, is violent-whipsaw


def nipc_regime(atr1m: float, er15: float) -> str:
    """The bucket, identical to scripts/nipc_replay.py's — one definition, two callers, no drift."""
    if nipc_dead_chop(atr1m, er15):
        return "dead-chop"
    if er15 >= NIPC_TREND_ER15:
        return "clean-trend"
    if er15 >= NIPC_BUILDING_ER15:
        return "in-between-building"
    if atr1m >= NIPC_VIOLENT_ATR:
        return "violent-whipsaw"
    return "normal-chop"


def nipc_bad_regime(atr1m: float, er15: float) -> bool:
    """True when NIPC should NOT take a setup. Supersedes the dead-chop-only rule 7."""
    if not NIPC_REGIME_FILTER:
        return nipc_dead_chop(atr1m, er15)
    return nipc_regime(atr1m, er15) in ("dead-chop", "violent-whipsaw", "normal-chop")


@dataclass(slots=True)
class NipcSetup:
    """One impulse→pullback→trigger setup as it walks through the state machine."""
    side: str            # LONG / SHORT — always WITH the impulse
    ext: float           # impulse extreme
    org: float           # impulse origin (close 2 min back)
    span: float          # |ext − org|
    detect_ms: int
    atr1m: float         # the pre-impulse ATR1m the magnitude test used
    er15: float
    dead_chop: bool      # regime label at detection (rule 7)
    pb_ext: float = 0.0  # deepest pullback so far
    retrace: float = 0.0  # r at arm time
    entry_level: float = 0.0
    stop: float = 0.0
    r_pt: float = 0.0    # |entry_level − stop| → carried as entry_atr
    armed_ms: int = 0    # 0 = still walking the pullback; else the trigger is live
    expires_ms: int = 0
    bars_seen: int = 0


class NipcTracker:
    """The NIPC state machine (rules 1–3 + 6/7). Fed 5s bars (or a raw price stream it folds
    into 5s bars itself) plus the 1-minute ATR/ER15 context; emits a NipcSetup the instant a
    tick trades through a live half-back trigger. Stateful by necessity — the setup spans
    minutes — but self-contained and pure of I/O, so the live desk and the replay harness
    drive the SAME object (the anti-drift guarantee the rest of this module gives by purity).

    ``apply_regime=False`` runs the blanket book (every regime) for measurement; LIVE keeps it
    True so dead-chop never arms.
    """

    def __init__(self, *, apply_regime: bool = True) -> None:
        self._bars: deque = deque(maxlen=NIPC_IMPULSE_BARS + 4)
        self._atrs: deque = deque(maxlen=NIPC_IMPULSE_BARS + 4)
        self._cur: dict | None = None
        self._apply_regime = apply_regime
        self.setup: NipcSetup | None = None
        self.blocked_until_ms: int = 0     # rule 6 cooldown

    # ── ingest ───────────────────────────────────────────────────────────────
    def on_price(self, ts_ms: int, price: float, *, atr1m: float, er15: float,
                 busy: bool = False) -> None:
        """Fold a live tape print into the forming 5s bar; a completed bar advances the machine."""
        b = ((ts_ms // 1000) // NIPC_BAR_S) * NIPC_BAR_S
        cur = self._cur
        if cur is None or b > cur["t"]:
            if cur is not None:
                self.on_bar(Bar(cur["t"], cur["o"], cur["h"], cur["l"], cur["c"], 0.0),
                            atr1m=atr1m, er15=er15, busy=busy)
            self._cur = {"t": b, "o": price, "h": price, "l": price, "c": price}
        elif b == cur["t"]:
            cur["h"] = max(cur["h"], price)
            cur["l"] = min(cur["l"], price)
            cur["c"] = price
        # b < cur["t"]: out-of-order print — ignore (same discipline as MinuteBars.fold)

    def on_bar(self, bar: Bar, *, atr1m: float, er15: float, busy: bool = False) -> None:
        """One COMPLETED 5s bar. ``atr1m``/``er15`` are the 1-minute context as of this bar;
        the ATR history is kept per-bar so rule 1 can read the pre-impulse value."""
        self._bars.append(bar)
        self._atrs.append(atr1m)
        s = self.setup
        if s is not None:
            if s.armed_ms:                              # trigger live → only the 1-min expiry
                if (bar.ts + NIPC_BAR_S) * 1000 >= s.expires_ms:
                    self.setup = None
                return
            self._advance_pullback(bar)
            return
        if busy or bar.ts * 1000 < self.blocked_until_ms:   # rule 6: one at a time + cooldown
            return
        self._detect_impulse(bar, er15)

    # ── rule 1 ───────────────────────────────────────────────────────────────
    def _detect_impulse(self, bar: Bar, er15: float) -> None:
        if len(self._bars) < NIPC_IMPULSE_BARS + 1 or not nipc_in_window(bar.ts * 1000):
            return
        org_bar = self._bars[-(NIPC_IMPULSE_BARS + 1)]
        atr_pre = self._atrs[-(NIPC_IMPULSE_BARS + 1)]   # BEFORE the impulse — no self-reference
        if atr_pre <= 0:
            return
        dead = nipc_bad_regime(atr_pre, er15)            # rule 7, widened to the losing buckets
        if dead and self._apply_regime:
            return
        leg = bar.close - org_bar.close
        if abs(leg) < NIPC_ATR_MULT * atr_pre:
            return
        side = "LONG" if leg > 0 else "SHORT"
        window = list(self._bars)[-NIPC_IMPULSE_BARS:]
        ext = max(b.high for b in window) if side == "LONG" else min(b.low for b in window)
        span = abs(ext - org_bar.close)
        if span < NIPC_SPAN_MIN_PT:
            return
        self.setup = NipcSetup(side=side, ext=ext, org=org_bar.close, span=span,
                               detect_ms=bar.ts * 1000, atr1m=atr_pre, er15=er15,
                               dead_chop=dead, pb_ext=ext)

    # ── rule 2 ───────────────────────────────────────────────────────────────
    def _advance_pullback(self, bar: Bar) -> None:
        s = self.setup
        assert s is not None
        s.bars_seen += 1
        if s.side == "LONG":
            s.pb_ext = min(s.pb_ext, bar.low)
            r = (s.ext - s.pb_ext) / s.span
        else:
            s.pb_ext = max(s.pb_ext, bar.high)
            r = (s.pb_ext - s.ext) / s.span
        if r > NIPC_RMAX:            # impulse broken — that was not a pullback
            self.setup = None
            return
        if r >= NIPC_RMIN:
            self._arm(bar, r)
            return
        if s.bars_seen >= NIPC_PULLBACK_BARS:   # no retrace inside 3 min → drop it
            self.setup = None

    # ── rules 3 + 4 ──────────────────────────────────────────────────────────
    def _arm(self, bar: Bar, r: float) -> None:
        s = self.setup
        assert s is not None
        s.retrace = r
        dist = r * s.span
        if s.side == "LONG":
            s.entry_level = s.pb_ext + NIPC_RES * dist
            s.stop = s.pb_ext - NIPC_STOP_BUF_PT
            inside = s.entry_level <= s.ext
        else:
            s.entry_level = s.pb_ext - NIPC_RES * dist
            s.stop = s.pb_ext + NIPC_STOP_BUF_PT
            inside = s.entry_level >= s.ext
        s.r_pt = abs(s.entry_level - s.stop)
        if not inside or s.r_pt < NIPC_R_MIN_PT:
            self.setup = None
            return
        # armed at the bar's CLOSE (bar.ts is the bucket START) — the trigger cannot be
        # tested against prints that happened before the decision existed.
        s.armed_ms = (bar.ts + NIPC_BAR_S) * 1000
        s.expires_ms = s.armed_ms + NIPC_TRIGGER_BARS * NIPC_BAR_S * 1000

    def trigger(self, ts_ms: int, price: float) -> NipcSetup | None:
        """Rule 3's fill test — the first tick trading THROUGH the live half-back level.
        Returns the setup (and consumes it) or None. Expiry is enforced here too, so a
        quiet minute with no prints still retires the trigger."""
        s = self.setup
        if s is None or not s.armed_ms:
            return None
        if ts_ms >= s.expires_ms:
            self.setup = None
            return None
        through = price >= s.entry_level if s.side == "LONG" else price <= s.entry_level
        if not through:
            return None
        self.setup = None
        return s

    def note_exit(self, ts_ms: int) -> None:
        """Rule 6 — start the 2-minute cooldown when the position closes."""
        self.blocked_until_ms = ts_ms + NIPC_COOLDOWN_S * 1000


def exit_fixed(pos: Position, price: float, *, stop_pt: float, target_pt: float) -> str | None:
    """Fixed POINT stop + fixed POINT target — the snap-back-fade exit (exhaustion_short's
    original FootprintShadow design, 2026-07-25 rehab). ATR-INDEPENDENT, unlike exit_scalp: a
    tight fixed target banks the fade before it reverses (an ATR-scaled 2R target is too wide on
    a snap-back and rarely fills). The managed layer takes BOTH sides here; the native 1-ATR STP
    (armed at entry_atr·stop_atr_mult, wider than stop_pt) stays the outer server-side backstop.
    Returns 'STOP' / 'TARGET' / None."""
    if pos.side == "LONG":
        if price <= pos.entry_price - stop_pt:
            return "STOP"
        if price >= pos.entry_price + target_pt:
            return "TARGET"
    else:
        if price >= pos.entry_price + stop_pt:
            return "STOP"
        if price <= pos.entry_price - target_pt:
            return "TARGET"
    return None


def exit_scalp(pos: Position, price: float, *, target_r: float = 2.0, stop_atr_mult: float = 1.0) -> str | None:
    """1-ATR stop + fixed R-multiple target — the scalp exit for reversal_grab."""
    r = stop_atr_mult * pos.entry_atr
    if pos.side == "LONG":
        if price <= pos.entry_price - r:
            return "STOP"
        if price >= pos.entry_price + target_r * r:
            return "TARGET"
    else:
        if price >= pos.entry_price + r:
            return "STOP"
        if price <= pos.entry_price - target_r * r:
            return "TARGET"
    return None


def exit_chandelier(pos: Position, price: float, *, start_k: float = 3.5,
                    min_k: float = 0.5, tighten: float = 0.75) -> str | None:
    """The tightening ATR chandelier — the momentum PROFIT exit (reimplemented from
    V5's 2026-07-11 go-live logic, clean-room). Trails the peak by ``k * entry_atr``,
    where k tightens from ``start_k`` toward ``min_k`` as the peak grows:
    ``k = max(min_k, start_k - tighten * peak_r)``, ``peak_r = peak_favorable/atr``.
    Lets a winner run wide early, locks tighter as it extends — and NEVER caps the
    upside (unlike a fixed R-target). It ONLY ever exits in profit; the native
    1-ATR stop owns the downside (loss-floor), so a bad peak seed can't fire a red
    exit. Returns 'CHANDELIER' or None."""
    atr = pos.entry_atr
    if atr <= 0 or pos.peak_favorable <= 0:  # not armed / never went green
        return None
    peak_r = pos.peak_favorable / atr
    giveback = max(min_k, start_k - tighten * peak_r) * atr
    fav = (price - pos.entry_price) if pos.side == "LONG" else (pos.entry_price - price)
    # bank only a real gain that has retraced >= the (tightening) give-back from peak
    if fav > 0 and fav <= pos.peak_favorable - giveback:
        return "CHANDELIER"
    return None


def exit_chandelier_lock(pos: Position, price: float, *, start_k: float = 3.5,
                         lock_r: float = 6.0, lock_k: float = 0.5) -> str | None:
    """THRESHOLD (loose-then-lock) chandelier — grind_long's trend-capture profit exit
    (2026-07-26 deploy, DECISIONS §356). Unlike ``exit_chandelier`` (which tightens
    CONTINUOUSLY as the peak grows), this holds a WIDE trail (``start_k * entry_atr``)
    until the run reaches ``lock_r`` R, then STEP-LOCKS to a firm tight trail
    (``lock_k * entry_atr``) for the rest of the ride: ``peak_r = peak_favorable/atr``,
    ``k = start_k if peak_r < lock_r else lock_k``. Loose early lets a trend run breathe
    through its retraces; the firm lock past lock_r banks the tail once it's a proven big
    move. Uncapped; ONLY ever exits in profit (the native 1-ATR STP owns the downside, so
    a bad peak seed can't fire a red exit). Returns 'CHANDELIER' or None."""
    atr = pos.entry_atr
    if atr <= 0 or pos.peak_favorable <= 0:  # not armed / never went green
        return None
    peak_r = pos.peak_favorable / atr
    k = start_k if peak_r < lock_r else lock_k
    giveback = k * atr
    fav = (price - pos.entry_price) if pos.side == "LONG" else (pos.entry_price - price)
    if fav > 0 and fav <= pos.peak_favorable - giveback:
        return "CHANDELIER"
    return None


def chandelier_start_k(entry_atr: float, *, atr_hi: float = 35.0, atr_mid: float = 20.0,
                       k_hi: float = 2.0, k_mid: float = 3.0, k_lo: float = 3.5) -> float:
    """VOL-ADAPTIVE chandelier — pick the trail width from the entry ATR.

    A flat trail bleeds give-back on the high-ATR (volatile-day) entries: the run is
    huge, and so is the retrace a wide 3.5 trail waits through. Tightening the trail
    only on those high-ATR entries locks more of the big swing, while the bulk of
    entries (median ATR ~13) keep the wide default so a normal run still breathes.

    25-day MNQ grind_fast (V5 1m basis): flat-3.5 −$7,975 → graded −$6,323 (+$1,653).
    Feed the result to exit_chandelier(..., start_k=chandelier_start_k(pos.entry_atr)).
    Still a net loser standalone — a give-back saver, NOT a fix; grind needs the router.
    """
    if entry_atr > atr_hi:
        return k_hi
    if entry_atr >= atr_mid:
        return k_mid
    return k_lo


def exit_adverse_cut(pos: Position, price: float, *, cut_atr: float = 1.5, arm_atr: float = 0.5) -> str | None:
    """A position >= cut_atr offside that NEVER went meaningfully green — cut it."""
    if pos.entry_atr <= 0:
        return None
    adverse = (pos.entry_price - price) if pos.side == "LONG" else (price - pos.entry_price)
    peak_r = pos.peak_favorable / pos.entry_atr
    if adverse >= cut_atr * pos.entry_atr and peak_r < arm_atr:
        return "ADVERSE_CUT"
    return None


def exit_giveback(pos: Position, price: float, *, value_per_point: float, qty: float = 1.0,
                  arm_usd: float = 50.0, giveback_usd: float = 40.0) -> str | None:
    """The tight dollar profit give-back — the 'ratchet 2' (2026-07-20). Once the
    position has been >= ``arm_usd`` favorable (in POSITION dollars, incl. qty), cut
    if it retraces ``giveback_usd`` from its peak. Dollar-denominated — the risk the
    operator feels — so it arms sooner in point-terms on bigger size and caps the
    green-then-reverse losses (the deep losers peak green, then reverse hard) that the
    wide ATR chandelier and the trail-less 2R scalp let round-trip to −$120–150.

    Only ever acts on a trade that went GREEN first (peak reached ``arm_usd``); a trade
    that goes straight offside never arms, so this NEVER cuts a mere dip — those
    never-green losses are the native 1-ATR stop's job. Returns 'GIVEBACK' or None."""
    if pos.peak_favorable <= 0:
        return None
    peak_usd = pos.peak_favorable * value_per_point * qty
    if peak_usd < arm_usd:                                    # never armed → never fires
        return None
    fav = (price - pos.entry_price) if pos.side == "LONG" else (pos.entry_price - price)
    fav_usd = fav * value_per_point * qty
    if peak_usd - fav_usd >= giveback_usd:
        return "GIVEBACK"
    return None


def exit_absorption(pos: Position, *, tape_net: float, window_price_delta: float, flow_min: float = 50) -> str | None:
    """Heavy aggressor flow OUR way that FAILED to move price — exhaustion, cut."""
    if pos.side == "SHORT" and tape_net <= -flow_min and window_price_delta >= 0:
        return "ABSORPTION_CUT"
    if pos.side == "LONG" and tape_net >= flow_min and window_price_delta <= 0:
        return "ABSORPTION_CUT"
    return None
