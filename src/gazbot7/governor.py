"""Shadow→live gate controller — the shadow board AS the regime router.

The insight (2026-07-18): you cannot predict the regime, and a feature classifier does
not cleanly separate a gate's good days from its bad — but a gate's OWN live shadow P&L
directly measures whether its edge is present RIGHT NOW. So every gate runs in shadow
(free, observe-only), and live capital follows it: live ON when the gate's recent shadow
is working, OFF when it bleeds, re-armed when it recovers. Reactive, per-gate.

The hard part is re-entry DISCIPLINE — a naive trailing-P&L trigger churns (a chop day
strings two quick shadow wins, re-arms live, bleeds, repeats). This module carries four
predictors so we can sweep for the one that kills the churn:

  - "window"  trailing-W-hour shadow P&L, on/off thresholds with hysteresis (the naive one)
  - "sticky"  window + a cool-down after every OFF, so a bad day can't re-arm on a blip
  - "streak"  arm only after win_k consecutive shadow WINS; disarm after loss_m LOSSES
  - "slope"   arm only when the shadow equity is RISING (2nd half of window > 1st) and green

`govern()` never looks ahead: the live/off decision for a trade uses only the shadow
trades that CLOSED before it. It reports realized (live) P&L, the full-shadow P&L it was
tracking, and the FLIP COUNT — churn is a first-class metric, not a footnote.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GovConfig:
    predictor: str = "window"          # window | sticky | streak | slope
    window_h: float = 2.0              # trailing window (hours) for window/sticky/slope
    on_thr: float = 50.0               # arm when trailing shadow P&L >= on_thr
    off_thr: float = -100.0            # disarm when trailing shadow P&L <= off_thr
    cooldown_h: float = 2.0            # sticky: hold OFF this long after every disarm
    win_k: int = 2                     # streak: arm after this many consecutive wins
    loss_m: int = 2                    # streak: disarm after this many consecutive losses


@dataclass(frozen=True, slots=True)
class GovResult:
    live_pnl: float          # realized: sum of trades taken while LIVE
    full_pnl: float          # the full shadow book it was tracking (always-on)
    n_flips: int             # on↔off transitions — the churn metric
    n_live: int              # trades taken live
    n_total: int             # shadow trades seen


def _window_sum(prior: list[tuple[int, float]], ts: int, w_s: float) -> float:
    return sum(p for (tt, p) in prior if tt >= ts - w_s)


def _desired(cfg: GovConfig, prior: list[tuple[int, float]], ts: int,
             live: bool, last_off_ts: int | None) -> bool:
    """The predictor: should live be ON at this trade, given only PRIOR shadow trades."""
    if cfg.predictor == "streak":
        wins = 0
        for _, p in reversed(prior):
            if p > 0:
                wins += 1
            else:
                break
        losses = 0
        for _, p in reversed(prior):
            if p <= 0:
                losses += 1
            else:
                break
        if wins >= cfg.win_k:
            return True
        if losses >= cfg.loss_m:
            return False
        return live

    w_s = cfg.window_h * 3600.0
    s = _window_sum(prior, ts, w_s)
    if cfg.predictor == "slope":
        mid = ts - w_s / 2
        first = sum(p for (tt, p) in prior if ts - w_s <= tt < mid)
        second = sum(p for (tt, p) in prior if mid <= tt < ts)
        want_on = s >= cfg.on_thr and second >= first   # green AND accelerating
    else:
        want_on = s >= cfg.on_thr

    # sticky cool-down: once OFF, refuse to re-arm until cooldown has elapsed
    if cfg.predictor == "sticky" and not live and last_off_ts is not None:
        if ts - last_off_ts < cfg.cooldown_h * 3600.0:
            return False

    if want_on:
        return True
    if s <= cfg.off_thr:
        return False
    return live   # hysteresis: hold between thresholds


def govern(trades: list[tuple[int, float]], session_t0: int, cfg: GovConfig) -> GovResult:
    """Run the shadow→live controller over one session's shadow trades.

    trades: (entry_ts, net_pnl) for every SHADOW trade this session, ascending by ts.
    session_t0: session start ts — a warm-up of one window is required before the first
    arm (except the streak predictor, which arms on wins whenever they come).
    """
    live = False
    last_off_ts: int | None = None
    live_pnl = 0.0
    full = 0.0
    flips = 0
    n_live = 0
    warm = cfg.window_h * 3600.0
    for j, (ts, p) in enumerate(trades):
        prior = trades[:j]                         # strictly before → no look-ahead
        if cfg.predictor == "streak" or (ts - session_t0) >= warm:
            desired = _desired(cfg, prior, ts, live, last_off_ts)
            if desired != live:
                flips += 1
                live = desired
                if not live:
                    last_off_ts = ts
        if live:
            live_pnl += p
            n_live += 1
        full += p
    return GovResult(round(live_pnl, 1), round(full, 1), flips, n_live, len(trades))
