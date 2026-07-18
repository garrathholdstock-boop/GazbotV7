"""Conviction sizing — quantized position size by trend strength (Kaufman Efficiency Ratio).

The discrete-futures form of Carver's "scale, don't gate": keep the early entry, size each
trade by how clean the recent trend is. At a base of 2 lots the ladder is:
  chop (low ER)      → 0 lots  (skip — the 'gate' rung)
  marginal (mid ER)  → 1 lot
  clean trend (hi ER)→ 2 lots  (full)

Efficiency Ratio = |net move| / |path| over the trailing window (0 = pure noise, 1 = a
straight line). It is the least-lagged trend-vs-chop discriminator (preferred over ADX for a
fast entry). Walk-forward OOS on grind_fast: flat 1-lot −$6,323 → conviction 0/1/2 +$1,162,
and the skipped (0-lot) trades lost −$6,670 as a group (they were genuinely bad, not random).

Thresholds are FROZEN from that walk-forward — do NOT re-tune them live.
"""
from __future__ import annotations

from .deciders import Bar

LO = 0.25   # ER below this = chop → 0 lots
HI = 0.45   # ER at/above this = clean trend → full size


def efficiency_ratio(bars: list[Bar], n: int = 30) -> float:
    """Kaufman ER over the last n closes: |close[-1] − close[-n]| / Σ|Δclose|. 0..1."""
    cl = [b.close for b in bars[-n:]]
    if len(cl) < 10:
        return 0.0
    path = sum(abs(cl[i] - cl[i - 1]) for i in range(1, len(cl))) or 1.0
    return abs(cl[-1] - cl[0]) / path


def conviction_lots(er: float, *, base: int = 2, lo: float = LO, hi: float = HI) -> int:
    """Quantized lots from the Efficiency Ratio. 0 = skip (chop), base = full (clean trend),
    the middle rung = half (rounded up). base=2 → 0/1/2; base=1 → 0/1 (gate only, no upsize)."""
    if er < lo:
        return 0
    if er < hi:
        return max(1, round(base / 2))
    return base
