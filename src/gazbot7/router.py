"""Per-contract regime router — SHADOW-FIRST, observe-only.

The desk's biggest single leak (week to 17 Jul 2026) is not missing runs — it is
firing the WRONG engine for the regime: momentum gates fading a live move, reversion
gates fired into a trend. Tag every trade by the regime it fired into and the book
splits perfectly in two — every winning bucket trades WITH the move, every losing
bucket AGAINST it. The router stands the wrong-regime engine down.

This module is the SHADOW-FIRST Phase 1 (REGIME_ROUTER_SCOPE.md §4): the counterfactual
monitor. It provides:

  - classify_regime(features)        the reactive regime read (TREND_UP/DOWN/CHOP/DEAD)
  - engine_class_of(gate)            momentum vs reversion
  - engine_aligned(gate, side, reg)  the engine map — is this trade the right engine?
  - route_counterfactual(...)        the auditable readout: routed P&L vs actual P&L

NOTHING here submits an order. It reads the shadow board and the captured bars and
reports what a regime gate WOULD have banked. Arming the live router is Phase 2 and is
operator-gated (FUT_REGIME_ROUTER_ENABLED, default off) — it does not live here yet.

The read is REACTIVE, never predictive: it classifies the regime we are already in
(from the trailing bar window), it does not forecast the next one.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .deciders import Bar, Features, compute_features

# ── regimes ──────────────────────────────────────────────────────────────────
TREND_UP = "TREND_UP"
TREND_DOWN = "TREND_DOWN"
CHOP = "CHOP"
DEAD = "DEAD"

# ── engine classes ───────────────────────────────────────────────────────────
MOMENTUM = "momentum"   # rides a live move — wants a trend, dies in chop
REVERSION = "reversion"  # fades an extension — wants a range, dies in a trend

# gate (ShadowVariant.gate / live entry name) → engine class.
_MOMENTUM_GATES = frozenset({"thrust", "grind", "continuation"})
_REVERSION_GATES = frozenset({"reversal_grab", "capitulation", "vwap_pullback", "fade"})


# ── tunables (first cut; observe-only, tune on the counterfactual) ────────────
@dataclass(frozen=True, slots=True)
class RouterCfg:
    # bars of the regime window. 180 × 5s = 15 min — slower than the 60-bar (5-min)
    # entry window on purpose: regime is a slower thing than the trigger, and a short
    # window boundary-flickers (REGIME_ROUTER_SCOPE.md §5).
    regime_bars: int = 180
    # |VWAP slope / ATR| over the window at/above which we call it a trend. Below → chop.
    slope_trend: float = 0.45
    # ATR% below this = DEAD (too quiet for either engine to pay its costs). 0 disables.
    atr_pct_dead: float = 0.0


DEFAULT = RouterCfg()


def classify_regime(f: Features, cfg: RouterCfg = DEFAULT) -> str:
    """Reactive regime read from the trailing-window features. No look-ahead."""
    if cfg.atr_pct_dead and f.atr_pct < cfg.atr_pct_dead:
        return DEAD
    slope = f.vwap_slope_atr
    if slope >= cfg.slope_trend:
        return TREND_UP
    if slope <= -cfg.slope_trend:
        return TREND_DOWN
    return CHOP


def engine_class_of(gate: str) -> str | None:
    """momentum / reversion / None(unknown) from the gate name."""
    if gate in _MOMENTUM_GATES:
        return MOMENTUM
    if gate in _REVERSION_GATES:
        return REVERSION
    return None


def engine_aligned(gate: str, side: str, regime: str) -> bool:
    """The engine map: would the router let THIS engine, THIS side, submit in THIS regime?

    - momentum: eligible only in a trend, and only WITH it (LONG in TREND_UP,
      SHORT in TREND_DOWN). Stood down in chop / dead.
    - reversion: eligible only in chop — a range to fade. Stood down in a trend / dead.
    """
    ec = engine_class_of(gate)
    if ec == MOMENTUM:
        return (regime == TREND_UP and side == "LONG") or (regime == TREND_DOWN and side == "SHORT")
    if ec == REVERSION:
        return regime == CHOP
    return False  # unknown engine → not routed (counted as stood-down, never a false credit)


# ── counterfactual monitor ───────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class RoutedTrade:
    trade_id: int
    strategy: str
    gate: str
    side: str
    entry_ts: int
    regime: str
    aligned: bool
    real_pnl: float


def _load_bars(cap: sqlite3.Connection, symbol: str) -> list[Bar]:
    cap.row_factory = sqlite3.Row
    rows = cap.execute(
        "SELECT bar_ts, open, high, low, close, volume FROM bars "
        "WHERE symbol=? AND timeframe='5s' ORDER BY bar_ts",
        (symbol,),
    ).fetchall()
    return [Bar(r["bar_ts"], r["open"], r["high"], r["low"], r["close"], r["volume"]) for r in rows]


def regime_at(bars: list[Bar], entry_ts: int, cfg: RouterCfg = DEFAULT) -> str | None:
    """Classify the regime as of entry_ts from the trailing window. None if too few bars."""
    # bars are ascending by ts; take the window ENDING at-or-before entry_ts.
    win: list[Bar] = []
    for b in bars:
        if b.ts > entry_ts:
            break
        win.append(b)
    win = win[-cfg.regime_bars:]
    if len(win) < 6:  # compute_features needs a handful; too few → unknown
        return None
    return classify_regime(compute_features(win), cfg)


def route_counterfactual(
    shadow_db: str,
    capture_db: str,
    symbol: str = "MNQ",
    gate_of: dict[str, str] | None = None,
    cfg: RouterCfg = DEFAULT,
) -> dict:
    """Replay the shadow board through the router and report routed-vs-actual P&L.

    gate_of maps strategy → gate (thrust/reversal_grab/…). If None, it is inferred from
    the ShadowVariant slate in shadow.py.
    """
    if gate_of is None:
        gate_of = _gate_map()

    sc = sqlite3.connect(shadow_db)
    sc.row_factory = sqlite3.Row
    trades = sc.execute(
        "SELECT t.id, t.strategy, t.side, t.entry_ts, r.real_pnl "
        "FROM shadow_trades t JOIN shadow_real r ON r.trade_id=t.id "
        "WHERE t.symbol=? ORDER BY t.entry_ts",
        (symbol,),
    ).fetchall()
    sc.close()

    cap = sqlite3.connect(capture_db)
    bars = _load_bars(cap, symbol)
    cap.close()

    routed: list[RoutedTrade] = []
    for t in trades:
        gate = gate_of.get(t["strategy"], "")
        reg = regime_at(bars, int(t["entry_ts"]), cfg) or CHOP  # unknown-regime → conservative CHOP
        al = engine_aligned(gate, t["side"], reg)
        routed.append(RoutedTrade(
            t["id"], t["strategy"], gate, t["side"], int(t["entry_ts"]),
            reg, al, float(t["real_pnl"] or 0.0),
        ))

    actual = sum(x.real_pnl for x in routed)
    aligned_pnl = sum(x.real_pnl for x in routed if x.aligned)
    counter_pnl = sum(x.real_pnl for x in routed if not x.aligned)

    # engine split — the finding underneath the routing: which ENGINE carries the book,
    # regardless of the regime read. On the 16–17 Jul board this is the whole story.
    by_engine: dict[str, list] = {MOMENTUM: [0, 0.0], REVERSION: [0, 0.0], "?": [0, 0.0]}
    for x in routed:
        ec = engine_class_of(x.gate) or "?"
        by_engine[ec][0] += 1
        by_engine[ec][1] += x.real_pnl

    return {
        "symbol": symbol,
        "n": len(routed),
        "actual_pnl": round(actual, 2),
        "routed_pnl": round(aligned_pnl, 2),          # keep aligned, stand the rest down
        "stood_down_pnl": round(counter_pnl, 2),       # what the benched trades would have done
        "n_aligned": sum(1 for x in routed if x.aligned),
        "n_stood_down": sum(1 for x in routed if not x.aligned),
        "by_engine": {k: [v[0], round(v[1], 2)] for k, v in by_engine.items() if v[0]},
        "trades": routed,
    }


def _readout(shadow_db: str = "data/shadow.db", capture_db: str = "data/capture.db",
             symbol: str = "MNQ") -> None:
    """Print the shadow counterfactual — routed vs actual, engine split, regime mix.

    Run:  PYTHONPATH=src python -m gazbot7.router
    Observe-only. Nothing here arms anything.
    """
    from collections import Counter

    r = route_counterfactual(shadow_db, capture_db, symbol)
    print(f"── REGIME ROUTER · {symbol} · shadow counterfactual (observe-only) ──")
    print(f"trades              {r['n']}")
    print(f"actual book         {r['actual_pnl']:+.0f}")
    print(f"ROUTED (engine-map) {r['routed_pnl']:+.0f}   "
          f"[keep {r['n_aligned']} regime-aligned, stand {r['n_stood_down']} down]")
    print(f"stood-down would-be {r['stood_down_pnl']:+.0f}   (what the benched trades did)")
    print()
    print("the split underneath — which engine carries the book:")
    for eng, (n, pnl) in r["by_engine"].items():
        print(f"  {eng:10} n={n:3}  {pnl:+.0f}")
    print()
    print("regime mix at entry:", dict(Counter(x.regime for x in r["trades"])))
    print("\nNB: reactive read on a 15-min window; shadow-first — the live router is "
          "Phase 2 and operator-gated (FUT_REGIME_ROUTER_ENABLED, off).")


def _gate_map() -> dict[str, str]:
    """strategy → gate, read straight off the live ShadowVariant slate."""
    from .shadow import default_slate  # local import: avoid a cycle at module load
    try:
        return {v.name: v.gate for v in default_slate()}
    except Exception:
        return {}


if __name__ == "__main__":  # pragma: no cover
    _readout()
