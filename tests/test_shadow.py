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


# absorption is a CATASTROPHE backstop, not a green-scalp cutter (operator 2026-07-16).
# Without the loss-floor the sim guillotined green scalps and insta-re-entered on the
# still-valid signal → churn (the bug that faked sims 10/11/12's +$291/94%).
_ABS_TAPE = dict(tape_net=80.0, window_price_delta=-1.0)  # tape that trips exit_absorption for a LONG


def test_absorption_does_not_cut_a_green_scalp():
    store = open_store(":memory:")
    sim = ShadowSim(store, [ShadowVariant("t1", "thrust", {})], absorption_min_loss_usd=60.0)
    sim.on_bars(THRUST_UP)                       # LONG open ~103.5
    sim.on_bars(_flat_at(104.0), **_ABS_TAPE)    # GREEN + absorption tape → must NOT cut
    assert get_shadow_trades(store, "t1") == []  # still open, rode through the absorption


def test_absorption_floor_is_the_lever_on_a_small_loss():
    # a small offside loss ($1, above the ~1-ATR stop) with absorption tape: the floor
    # decides. At 60 it rides (backstop only); at 0 the same tape guillotines (old churn).
    for floor, expect_cut in [(60.0, False), (0.0, True)]:
        store = open_store(":memory:")
        sim = ShadowSim(store, [ShadowVariant("t1", "thrust", {})], absorption_min_loss_usd=floor)
        sim.on_bars(THRUST_UP)                    # LONG open ~103.5
        sim.on_bars(_flat_at(103.0), **_ABS_TAPE)  # ~$1 loss, above the stop
        trades = get_shadow_trades(store, "t1")
        assert bool(trades) is expect_cut
        if expect_cut:
            assert trades[0]["exit_reason"] == "ABSORPTION_CUT"


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


# ── chandelier give-back A/B (2026-07-17) ─────────────────────────────────────
def test_chandelier_params_cover_every_chandelier_variant():
    # the repricer scores each chandelier variant on ITS OWN trail via this map; if a
    # chandelier variant were missing here it'd be silently scored at the 3.5 default.
    from gazbot7.shadow import chandelier_params, default_slate
    cp = chandelier_params()
    assert cp["chand_k35"] == (3.5, 0.5, 0.75)  # = the live desk exit (control) — PROTECTED, kept
    # ★2026-08-02: chand_k25/k20 RETIRED. The trail A/B is answered (k35 -$1.79 vs k25 -$4.39 vs
    # k20 -$4.39 per trade) and k25/k20 scored identically to the cent (J=0.97, r=0.94), so they were
    # measuring the same thing twice. The control k35 stays; without it the abs_veto comparison dies.
    from gazbot7.shadow import RETIRED
    assert {"chand_k25", "chand_k20"} <= RETIRED
    assert "chand_k25" not in cp and "chand_k20" not in cp
    assert cp["grind_fast"] == (3.5, 0.5, 0.75)  # existing ride variant unchanged
    # the mechanism this test exists for: EVERY chandelier variant still on the slate is in the map,
    # else the repricer would silently score it at the 3.5 default.
    assert set(cp) == {v.name for v in default_slate() if v.chandelier}


def test_full_slate_with_chandelier_ab_instantiates_and_steps():
    # the live slate builds, all names are unique, and it steps on a flat tape without raising.
    # ★2026-08-02: post-retirement the slate is 18 (was 28 — 11 slate names retired, cb_thrust and
    # cb_thrust_dropped are booked by the breaker not the slate, and capit_live_mirror was added).
    from gazbot7.shadow import RETIRED, default_slate
    slate = default_slate()
    names = [v.name for v in slate]
    assert len(names) == len(set(names))  # no duplicate strategy names
    assert "chand_k35" in names                       # the control survives
    assert not (RETIRED & set(names)), RETIRED & set(names)   # nothing retired is still running
    assert "capit_live_mirror" in names               # live capitulation has a twin again
    # a variant whose gate has no ShadowSim._entry branch would silently NEVER FIRE — guard it
    # ★2026-08-08 + "clock_rider": the Open Rider, the first variant here with no signal at all.
    assert {v.gate for v in slate} <= {"thrust", "reversal_grab", "capitulation", "grind",
                                       "clock_rider"}
    # ★2026-08-08 the four Open Rider arms (cadence x stop width, shadow only). Drop one and it has
    # been silently retired, at which point the 2x2 is no longer a comparison.
    # ★2026-08-13 now EIGHT: the same 2x2 run twice, once with the drift-direction gate. The pairing
    # assertion is the real guard — an unpaired gated arm confounds the gate with whichever cadence
    # or stop cell it sits in, and the backtest cannot separate those (per-trade SD ~$160).
    riders = [v for v in slate if v.gate == "clock_rider"]
    assert len(riders) == 8, [v.name for v in riders]
    assert {v.rider_cadence_min for v in riders} == {5, 10}
    assert {v.stop_atr_mult for v in riders} == {2.0, 3.0}
    gated = {v.name for v in riders if v.rider_gate_drift}
    plain = {v.name for v in riders if not v.rider_gate_drift}
    assert len(gated) == len(plain) == 4, (gated, plain)
    assert gated == {n + "_g" for n in plain}, "every gated arm needs its exact ungated twin"
    # Every rider MUST carry a time cap. The sim has no other way out of a trade that neither
    # stops nor targets, so an uncapped rider would sit open until the feed stopped.
    assert all(v.time_cap_s == 45 * 60 for v in riders)
    # And the window must be the 08-08 corrected right edge (14:45Z), not the original 15:00Z:
    # 14:45-15:00 is -$446 across all days and -$453 on the unseen leg alone.
    assert all(v.rider_win_end_s == 14 * 3600 + 45 * 60 for v in riders)
    store = open_store(":memory:")
    ShadowSim(store, slate).on_bars(_flat_at(100.0))  # no raise on a flat bar set
