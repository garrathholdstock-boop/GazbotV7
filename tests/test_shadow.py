"""D8 — shadow desk: records variant round-trips via the shared deciders."""

from __future__ import annotations

from gazbot7.deciders import REVERSAL_SHORT_VARIANTS, Bar
from gazbot7.shadow import ShadowSim, ShadowVariant
from gazbot7.store import get_shadow_trades, open_store


def _flat_then(deltas, last_vol=40, base=100.0, flat=15):
    bars = [Bar(i, base, base + 0.5, base - 0.5, base, 10) for i in range(flat)]
    px = base
    for j, d in enumerate(deltas):
        px += d
        vol = last_vol if j == len(deltas) - 1 else 10
        bars.append(Bar(flat + j, px - d, max(px, px - d) + 0.2, min(px, px - d) - 0.2, px, vol))
    return bars


def _flat_at(price, ts0=100):
    return [Bar(ts0 + i, price, price + 0.5, price - 0.5, price, 10) for i in range(20)]


THRUST_UP = _flat_then([0.7, 0.7, 0.7, 0.7, 0.7])


def test_shadow_records_a_thrust_roundtrip():
    store = open_store(":memory:")
    sim = ShadowSim(store, [ShadowVariant("t1", "thrust", {})])
    sim.on_bars(THRUST_UP)  # entry (LONG)
    sim.on_bars(_flat_at(110.0))  # past 2R target → close
    (tr,) = get_shadow_trades(store, "t1")
    assert tr["side"] == "LONG"
    assert tr["exit_reason"] == "TARGET"
    assert tr["ceiling_pnl"] > 0
    assert tr["entry_atr"] > 0  # carried for the repricer


def test_shadow_open_position_not_yet_recorded():
    store = open_store(":memory:")
    sim = ShadowSim(store, [ShadowVariant("t1", "thrust", {})])
    sim.on_bars(THRUST_UP)  # entered, still open
    assert get_shadow_trades(store, "t1") == []


def test_two_variants_are_independent():
    store = open_store(":memory:")
    sim = ShadowSim(store, [
        ShadowVariant("a", "thrust", {}),
        ShadowVariant("b", "thrust", {"thr": 5.0}),  # much stricter — won't fire on THRUST_UP
    ])
    sim.on_bars(THRUST_UP)
    sim.on_bars(_flat_at(110.0))
    assert len(get_shadow_trades(store, "a")) == 1
    assert get_shadow_trades(store, "b") == []  # stricter variant never entered


def test_reversal_slate_instantiates():
    variants = [
        ShadowVariant(name, "reversal_grab", cfg) for name, cfg in REVERSAL_SHORT_VARIANTS.items()
    ]
    assert len(variants) == 5
    store = open_store(":memory:")
    ShadowSim(store, variants).on_bars(_flat_at(100.0))  # no raise; nothing fires on flat


# ── delayed-entry absorption veto in the sim (2026-07-16) ─────────────────────
def test_shadow_veto_delays_then_enters():
    store = open_store(":memory:")
    sim = ShadowSim(store, [ShadowVariant("v", "thrust", {}, confirm_s=50)])
    t0 = 1_000_000
    sim.on_bars(THRUST_UP, now_ms=t0)                 # signal raised — watching, no entry
    assert sim._open == {} and "v" in sim._pending
    sim.on_bars(THRUST_UP, now_ms=t0 + 51_000)        # 51s on, thrust persists, clean → enter
    assert "v" in sim._open
    sim.on_bars(_flat_at(110.0), now_ms=t0 + 60_000)  # past 2R → close
    (tr,) = get_shadow_trades(store, "v")
    assert tr["side"] == "LONG"


def test_shadow_veto_vetoes_on_absorption():
    store = open_store(":memory:")
    sim = ShadowSim(store, [ShadowVariant("v", "thrust", {}, confirm_s=50)])
    t0 = 1_000_000
    sim.on_bars(THRUST_UP, now_ms=t0)
    assert "v" in sim._pending
    sim.on_bars(THRUST_UP, now_ms=t0 + 10_000, tape_net=80.0, window_price_delta=-1.0)
    assert "v" not in sim._pending and sim._open == {}  # absorbed during the wait → vetoed
