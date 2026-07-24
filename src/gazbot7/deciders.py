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


def _atr(bars: list[Bar], n: int = 14) -> float:
    trs = [
        max(bars[i].high - bars[i].low, abs(bars[i].high - bars[i - 1].close),
            abs(bars[i].low - bars[i - 1].close))
        for i in range(1, len(bars))
    ]
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
    return Features(price, atr, atr / price if price else 0.0, vwap, slope, ext, net5, surge, len(bars), net2, slope_fast)


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
ER_FLOOR = {"grind_long": 0.20, "thrust_short": 0.20}
ER_CEIL = {"capitulation_long": 0.10, "exhaustion_short": 0.05}
# ★ 2026-07-24 (operator): ER band REMOVED for rgv_long/rgv_short — the 35s ABSORPTION-CONFIRM
# (below) subsumes it (a Friday-lab grid found them near-identical at 35/40s: the confirm reads
# "genuine reversion vs falling-knife" from the microstructure, sharper than the ER band read it
# from the bar tape). rgv now runs ER-ungated + absorption-confirmed. Revert = restore the two bands.
ER_BAND: dict = {}   # (lo, hi): OPEN only when lo <= er <= hi  (empty now — no gate uses a band)
ER_WINDOW = 30  # bars (1-min bars → the 30-min ER used across the desk)

# ── ★ 35s ABSORPTION-CONFIRM on the rgv faders (LIVE 2026-07-24, operator) ─────────────────────
# The mirror of the abs_veto momentum filter: a fader WANTS the move it fades to be exhausting, so
# it delays entry CONFIRM_SECS and only fires if that move ABSORBS in the window (heavy aggressor
# flow the WRONG way for the fade that FAILS to move price). Friday-lab sweep (07-20..24, tick-
# honest): flips the rgv book −$556 → +$228 (35s, 13tr, 62%w), robust across 30–45s. The live loop
# (tournament.run) buffers an rgv OPEN, waits CONFIRM_SECS, then calls confirm_absorption().
CONFIRM_GATES = frozenset({"rgv_long", "rgv_short"})
CONFIRM_SECS = 35
CONFIRM_MAX_SECS = 55     # give up on a signal older than this (the turn's gone)
CONFIRM_FLOOR = 30.0      # min net-aggressor size to count as absorption


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
ATR_FLOOR = {"grind_long": 20.0, "thrust_short": 16.0}


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
ER_HOLD = {"grind_long": 2, "thrust_short": 2}


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
