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
    if len(bars) >= 6:
        prior = [b.volume for b in bars[-6:-1]]
        surge = bool(prior) and bars[-1].volume >= 1.5 * (sum(prior) / len(prior))
    else:
        surge = False
    return Features(price, atr, atr / price if price else 0.0, vwap, slope, ext, net5, surge, len(bars))


# ── entry gates ───────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class Entry:
    side: str  # LONG / SHORT
    gate: str
    target_r: float = 2.0
    stop_atr_mult: float = 1.0


def gate_thrust(f: Features, *, thr: float = 1.5, require_vol: bool = True,
                amp_floor: float = 0.0) -> Entry | None:
    """Momentum: a signed 5-bar thrust of >= thr ATR, volume-confirmed. Two-sided.
    This is V5's ``tw_mnq_thrust_loose`` (op 2026-07-12): thr 1.5, keep the volume
    surge + amplitude floor, drop the still-extending veto — **decided on 1-minute
    bars** (a 5-bar thrust = a 5-MINUTE move; on 5s bars it was a 25s blip and fired
    constantly). ``amp_floor`` is V5's MOMENTUM_AMP_FLOOR (atr_pct >= 0.04% — the
    edge lives at 0.04–0.08, noise below 0.03); here in fraction units (0.0004)."""
    if abs(f.net_atr_5) < thr:
        return None
    if amp_floor and f.atr_pct < amp_floor:  # thin tape → stand down
        return None
    if require_vol and not f.vol_surge:
        return None
    return Entry(side="LONG" if f.net_atr_5 > 0 else "SHORT", gate="thrust")


def gate_reversal_grab(
    f: Features,
    *,
    turn_atr: float = 0.5,
    flow_min: float | None = None,
    tape_net: float = 0.0,
    require_rth: bool = False,
    in_rth: bool = True,
    ext_min: float = 2.5,
) -> Entry | None:
    """Turnback momentum, SHORT: over-extended ABOVE VWAP, then a fresh DOWN turn,
    optionally confirmed by net-SELL aggressor flow. The research's edge."""
    if f.atr_pct > 0.09 or abs(f.vwap_slope_atr) > 1.0:  # regime stand-down
        return None
    if f.ext_atr < ext_min:  # must be stretched >= ext_min ATR above VWAP
        return None
    if f.net_atr_5 > -turn_atr:  # need a fresh down-move of >= turn_atr (the turn)
        return None
    if flow_min is not None and tape_net > -flow_min:  # need net-SELL flow >= flow_min
        return None
    if require_rth and not in_rth:
        return None
    return Entry(side="SHORT", gate="reversal_grab")


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


def exit_adverse_cut(pos: Position, price: float, *, cut_atr: float = 1.5, arm_atr: float = 0.5) -> str | None:
    """A position >= cut_atr offside that NEVER went meaningfully green — cut it."""
    if pos.entry_atr <= 0:
        return None
    adverse = (pos.entry_price - price) if pos.side == "LONG" else (price - pos.entry_price)
    peak_r = pos.peak_favorable / pos.entry_atr
    if adverse >= cut_atr * pos.entry_atr and peak_r < arm_atr:
        return "ADVERSE_CUT"
    return None


def exit_absorption(pos: Position, *, tape_net: float, window_price_delta: float, flow_min: float = 50) -> str | None:
    """Heavy aggressor flow OUR way that FAILED to move price — exhaustion, cut."""
    if pos.side == "SHORT" and tape_net <= -flow_min and window_price_delta >= 0:
        return "ABSORPTION_CUT"
    if pos.side == "LONG" and tape_net >= flow_min and window_price_delta <= 0:
        return "ABSORPTION_CUT"
    return None
