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
    # bars of the SLOW regime window. 180 × 5s = 15 min — this read gates REVERSION
    # (reversion only fires in chop). Slow on purpose: whether the day is a trend or a
    # range is a slow thing, and a short window boundary-flickers (§5).
    regime_bars: int = 180
    # |VWAP slope / ATR| over the slow window at/above which we call it a trend.
    slope_trend: float = 0.45
    # bars of the FAST move window. 60 × 5s = 5 min — the "which way now" read, off
    # vwap_slope_fast (flips at a reversal where the slow slope lags 30-40min).
    fast_bars: int = 60
    # |vwap_slope_fast| at/above which the fast move has a direction. Below → flat.
    fast_thr: float = 0.15
    # Enforce a momentum fade-guard? Default OFF: momentum runs ungated because its own
    # burst trigger + amplitude floor already self-select — on the 16-17 Jul tape it won
    # WITH, AGAINST and FLAT to the move, so gating it on direction only bins winners.
    # The against-move bucket is always MONITORED (readout) so the known chop-week fade
    # bleed stays visible; flip this True to actually bench it once a chop week proves it.
    momentum_needs_move: bool = False
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


def move_direction(f: Features, cfg: RouterCfg = DEFAULT) -> int:
    """Which way is price moving RIGHT NOW: +1 up, -1 down, 0 flat — off the FAST slope."""
    s = f.vwap_slope_fast
    if s >= cfg.fast_thr:
        return 1
    if s <= -cfg.fast_thr:
        return -1
    return 0


def engine_aligned(gate: str, side: str, regime: str, move_dir: int = 0,
                   momentum_needs_move: bool = False) -> bool:
    """The engine map: would the router let THIS engine, THIS side, submit here?

    The tune that keeps the momentum winners:
    - momentum: DEFAULT eligible everywhere — its own burst trigger + amplitude floor are
      the filter, and on the tape it wins with/against/flat to the move, so a direction
      gate only bins winners (incl. the early reversals the slow slope wrongly reads as
      counter-trend). With momentum_needs_move=True the fade-guard is enforced: eligible
      only WITH the fast move (or flat), benched on a genuine fast-fade.
    - reversion: eligible only in chop — a range to fade. Stood down in a trend / dead.
    """
    ec = engine_class_of(gate)
    if ec == MOMENTUM:
        if not momentum_needs_move:
            return True
        want = 1 if side == "LONG" else -1
        return move_dir == 0 or move_dir == want      # with the fast move, or flat
    if ec == REVERSION:
        return regime == CHOP
    return False  # unknown engine → not routed (counted as stood-down, never a false credit)


def counter_move(gate: str, side: str, move_dir: int) -> bool:
    """Is this a momentum trade firing AGAINST the fast move? (the monitored fade bucket)."""
    if engine_class_of(gate) != MOMENTUM or move_dir == 0:
        return False
    return (1 if side == "LONG" else -1) != move_dir


# ── counterfactual monitor ───────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class RoutedTrade:
    trade_id: int
    strategy: str
    gate: str
    side: str
    entry_ts: int
    regime: str
    move_dir: int
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


def _window_ending_at(bars: list[Bar], entry_ts: int, n: int) -> list[Bar]:
    """The last n bars at-or-before entry_ts. bars must be ascending by ts. No look-ahead."""
    win: list[Bar] = []
    for b in bars:
        if b.ts > entry_ts:
            break
        win.append(b)
    return win[-n:]


def regime_at(bars: list[Bar], entry_ts: int, cfg: RouterCfg = DEFAULT) -> str | None:
    """Classify the SLOW regime as of entry_ts. None if too few bars."""
    win = _window_ending_at(bars, entry_ts, cfg.regime_bars)
    if len(win) < 6:  # compute_features needs a handful; too few → unknown
        return None
    return classify_regime(compute_features(win), cfg)


def move_dir_at(bars: list[Bar], entry_ts: int, cfg: RouterCfg = DEFAULT) -> int:
    """The FAST move direction as of entry_ts (+1/-1/0). 0 if too few bars."""
    win = _window_ending_at(bars, entry_ts, cfg.fast_bars)
    if len(win) < 12:  # fast slope needs the short window filled
        return 0
    return move_direction(compute_features(win), cfg)


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
        ts = int(t["entry_ts"])
        reg = regime_at(bars, ts, cfg) or CHOP  # unknown-regime → conservative CHOP
        mdir = move_dir_at(bars, ts, cfg)
        al = engine_aligned(gate, t["side"], reg, mdir, cfg.momentum_needs_move)
        routed.append(RoutedTrade(
            t["id"], t["strategy"], gate, t["side"], ts,
            reg, mdir, al, float(t["real_pnl"] or 0.0),
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

    # the MONITORED fade bucket: momentum firing against the fast move. Kept (not benched)
    # by default, but always measured — this is where a chop-week bleed would show first.
    cm = [x for x in routed if counter_move(x.gate, x.side, x.move_dir)]

    return {
        "symbol": symbol,
        "n": len(routed),
        "actual_pnl": round(actual, 2),
        "routed_pnl": round(aligned_pnl, 2),          # keep aligned, stand the rest down
        "stood_down_pnl": round(counter_pnl, 2),       # what the benched trades would have done
        "n_aligned": sum(1 for x in routed if x.aligned),
        "n_stood_down": sum(1 for x in routed if not x.aligned),
        "by_engine": {k: [v[0], round(v[1], 2)] for k, v in by_engine.items() if v[0]},
        "counter_move_momentum": [len(cm), round(sum(x.real_pnl for x in cm), 2)],
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
    cm_n, cm_pnl = r["counter_move_momentum"]
    print()
    print(f"MONITORED — counter-move momentum (fade guard, NOT benched): n={cm_n}  {cm_pnl:+.0f}")
    print("  (kept because it wins here; flip momentum_needs_move=True once a chop week bleeds it)")
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
