"""The risk-weighted ALWAYS-ON stack — the evidence-backed desk model (2026-07-18).

Web research (Carver/Davey/Chan/López de Prado) + our own autocorrelation test killed the
shadow-P&L on/off-TIMING idea: the momentum gates' returns are ~random (lag-1 ac ≈ 0) and
the reversion gate is NEGATIVELY autocorrelated (−0.16) — so switching a gate on/off by its
own recent P&L is expected to add no edge (momentum) or actively hurt (reversion). The
supported model instead:

  1. ALWAYS-ON  — run every gate all the time; no equity-curve on/off switch.
  2. CIRCUIT-BREAKER — cap each gate's per-DAY loss (stand it down for the rest of the day
     once it gives back `max_giveback` from the day's peak). Risk control, NOT timing — the
     one use the literature endorses (Chan). It is what beat duty-matched random, because it
     caps the catastrophic tail, not because it "times" a hot hand.
  3. RISK-WEIGHTED — size gates by inverse-vol so each contributes balanced risk, and lean on
     the ANTI-CORRELATION (the "only free lunch"): the diversification multiplier says how far
     the negatively-correlated pair can be scaled at the same risk.

The shadow board's job is now INCUBATION (earn a 100+-trade track record before go-live) +
CORRELATION MONITORING — not routing. Nothing here arms anything.
"""
from __future__ import annotations

import statistics
from math import sqrt

ANN = sqrt(252)  # daily → annualised


def day_circuit_breaker(pnls: list[float], max_giveback: float) -> float:
    """One day's realized P&L with a max-loss circuit breaker: once the day's running P&L
    gives back `max_giveback` from its peak, stand the gate down for the rest of the day.
    A winning day never retraces that far, so it is untouched; a bleed day is capped."""
    kept = peak = 0.0
    for p in pnls:
        kept += p
        peak = max(peak, kept)
        if peak - kept >= max_giveback:
            break
    return kept


def inverse_vol_weights(series: dict[str, list[float]]) -> dict[str, float]:
    """Weight each gate by 1/σ of its daily P&L (equal risk contribution), summing to 1."""
    inv = {g: 1.0 / (statistics.pstdev(s) or 1.0) for g, s in series.items()}
    tot = sum(inv.values()) or 1.0
    return {g: v / tot for g, v in inv.items()}


def combine(series: dict[str, list[float]], weights: dict[str, float]) -> list[float]:
    """The weighted daily P&L series (gates aligned by day index)."""
    n = min(len(s) for s in series.values())
    return [sum(weights[g] * series[g][i] for g in series) for i in range(n)]


def sharpe(daily: list[float]) -> float:
    sd = statistics.pstdev(daily)
    return statistics.mean(daily) / sd * ANN if sd else 0.0


def max_drawdown(daily: list[float]) -> float:
    """Most-negative peak-to-trough of the cumulative equity (≤ 0)."""
    eq = peak = mdd = 0.0
    for p in daily:
        eq += p
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    return mdd


def _corr(a: list[float], b: list[float]) -> float:
    ma, mb = statistics.mean(a), statistics.mean(b)
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(len(a)))
    da = sqrt(sum((x - ma) ** 2 for x in a))
    db = sqrt(sum((x - mb) ** 2 for x in b))
    return num / (da * db) if da and db else 0.0


def diversification_multiplier(series: dict[str, list[float]], weights: dict[str, float]) -> float:
    """Carver's IDM = 1/sqrt(wᵀ·Corr·w): how far the (anti-)correlated set can be scaled at
    the same portfolio risk. >1 always for imperfectly-correlated gates; grows as correlation
    falls (and especially as it goes negative)."""
    gates = list(series.keys())
    var = sum(weights[gi] * weights[gj] * _corr(series[gi], series[gj])
              for gi in gates for gj in gates)
    if var <= 1e-9:      # perfectly/over-hedged → variance →0, diversification →∞; cap it
        return 5.0
    return min(5.0, 1.0 / sqrt(var))   # cap à la Carver (a big IDM is usually estimation error)
