"""Per-slot decisions — grind-long and grind-short as INDEPENDENT slots: a signal
opens only its own direction's slot, and each slot manages its own exit."""

from __future__ import annotations

from gazbot7.deciders import Features
from gazbot7.slot_strategy import SlotSpec, SlotStrategy
from gazbot7.slotbook import SlotBook
from gazbot7.store import Fill

VPP = 2.0


def _feat(slope_fast, ext_atr, atr=20.0, price=29000.0):
    return Features(price=price, atr=atr, atr_pct=atr / price, vwap=price - ext_atr * atr,
                    vwap_slope_atr=slope_fast, ext_atr=ext_atr, net_atr_5=0.0,
                    vol_surge=False, n_bars=60, net_atr_2=0.0, vwap_slope_fast=slope_fast)


def _specs():
    p = {"slope_min": 0.4, "fast_slope": True}
    return [SlotSpec("grind_long", "grind", "LONG", params=p, sizing="flat", base_size=1),
            SlotSpec("grind_short", "grind", "SHORT", params=p, sizing="flat", base_size=1)]


def _book():
    return SlotBook(["grind_long", "grind_short"], value_per_point=VPP, fee_rt=1.5)


def _hold(book, tag, side, qty, price, atr=20.0):
    book.register("o-" + tag, tag)
    book.apply(Fill("e-" + tag, "o-" + tag, "MNQ", "BUY" if side == "LONG" else "SELL",
                    qty, price, "2026-07-20T14:00:00+00:00"))
    book.slot(tag).entry_atr = atr


def test_long_signal_opens_ONLY_the_long_slot():
    s = SlotStrategy(_specs(), value_per_point=VPP)
    b = _book()
    ints = s.decide(_feat(+0.5, +1.0), 29000.0, [], b, tape_net=100.0)   # grind LONG
    assert len(ints) == 1
    assert ints[0]["slot"] == "grind_long" and ints[0]["action"] == "OPEN" and ints[0]["side"] == "LONG"


def test_short_signal_opens_ONLY_the_short_slot():
    s = SlotStrategy(_specs(), value_per_point=VPP)
    b = _book()
    ints = s.decide(_feat(-0.5, -1.0), 29000.0, [], b, tape_net=-100.0)  # grind SHORT
    assert len(ints) == 1
    assert ints[0]["slot"] == "grind_short" and ints[0]["side"] == "SHORT"


def test_no_signal_opens_nothing():
    s = SlotStrategy(_specs(), value_per_point=VPP)
    ints = s.decide(_feat(+0.1, +1.0), 29000.0, [], _book(), tape_net=0.0)  # slope below threshold
    assert ints == []


def test_a_held_slot_is_managed_the_other_is_untouched():
    s = SlotStrategy(_specs(), value_per_point=VPP)
    b = _book()
    _hold(b, "grind_long", "LONG", 1, 29000.0)      # long slot open @ 29000, ATR 20
    # ride to +100 fav (sets peak), then retrace to +40 → a managed profit exit fires
    s.decide(_feat(+0.5, +1.0), 29100.0, [], b, tape_net=100.0)
    ints = s.decide(_feat(+0.5, +1.0), 29040.0, [], b, tape_net=100.0)
    closes = [i for i in ints if i["action"] == "CLOSE"]
    assert len(closes) == 1 and closes[0]["slot"] == "grind_long"
    assert b.slot("grind_short").is_flat            # the other slot never opened / untouched


def test_both_directions_can_be_open_at_once():
    s = SlotStrategy(_specs(), value_per_point=VPP)
    b = _book()
    _hold(b, "grind_long", "LONG", 1, 29000.0)
    _hold(b, "grind_short", "SHORT", 1, 29050.0)
    assert b.net_qty() == 0.0                        # venue net 0, both logically held
    # neither at an exit yet → no close intents (fresh, small fav)
    ints = s.decide(_feat(+0.5, +1.0), 29010.0, [], b, tape_net=100.0)
    assert all(i["action"] != "OPEN" for i in ints)  # both slots occupied → no re-open


def _feat2(slope_fast, ext_atr, net_atr_2=0.0, atr=20.0, price=29000.0):
    return Features(price=price, atr=atr, atr_pct=atr / price, vwap=price - ext_atr * atr,
                    vwap_slope_atr=slope_fast, ext_atr=ext_atr, net_atr_5=net_atr_2,
                    vol_surge=False, n_bars=60, net_atr_2=net_atr_2, vwap_slope_fast=slope_fast)


def test_tournament_slate_shape():
    from gazbot7.slot_strategy import tournament_slots
    ss = tournament_slots()
    assert [s.tag for s in ss] == ["grind_long", "capitulation_long", "abs_veto_long",
                                   "rgv_short", "exhaustion_short", "abs_veto_short",
                                   "nipc_long", "nipc_short"]   # ★2026-08-01: + nipc
    assert len([s for s in ss if s.side == "LONG"]) == 4
    assert len([s for s in ss if s.side == "SHORT"]) == 4
    assert len({s.kind for s in ss}) == 6          # grind/reversal_grab/thrust/capitulation/exhaustion/nipc


def _bars_trend(n=35, step=0.5, start=28900.0):
    from gazbot7.deciders import Bar
    out, c = [], start
    for i in range(n):
        c += step
        out.append(Bar(i * 60, c - step, c + 0.05, c - step - 0.05, c, 10.0))
    return out                                       # clean uptrend → ER ~1 → conviction sizes up


def test_grind_long_routes_only_to_grind_long_slot():
    from gazbot7.slot_strategy import tournament_slots
    ss = tournament_slots()
    strat = SlotStrategy(ss, value_per_point=VPP)
    b = SlotBook([s.tag for s in ss], value_per_point=VPP, fee_rt=1.5)
    ints = strat.decide(_feat2(+0.5, +1.0), 29000.0, _bars_trend(), b, tape_net=100.0)
    opens = [i for i in ints if i["action"] == "OPEN"]
    assert len(opens) == 1 and opens[0]["slot"] == "grind_long"


def test_rgv_short_routes_only_to_rgv_short_slot():
    from gazbot7.slot_strategy import tournament_slots
    ss = tournament_slots()
    strat = SlotStrategy(ss, value_per_point=VPP)
    b = SlotBook([s.tag for s in ss], value_per_point=VPP, fee_rt=1.5)
    # stretched +2.5 ATR above VWAP, a fresh down-turn, calm regime, ATR over the floor
    ints = strat.decide(_feat2(+0.2, +2.5, net_atr_2=-0.3, atr=20.0), 29000.0, [], b, tape_net=-100.0)
    opens = [i for i in ints if i["action"] == "OPEN"]
    assert len(opens) == 1 and opens[0]["slot"] == "rgv_short"


# ── footprint gates: capitulation-long + exhaustion-short routing ──────────────
def _fp_specs():
    return [
        SlotSpec("capitulation_long", "capitulation", "LONG",
                 params={"climax_min": 3.0, "dom_min": 0.7, "require_flip": False},
                 sizing="flat", base_size=1, exit="scalp", target_r=2.0, stop_atr_mult=1.0),
        SlotSpec("exhaustion_short", "exhaustion", "SHORT", params={},
                 sizing="flat", base_size=1, exit="scalp", target_r=2.0, stop_atr_mult=1.0),
    ]


def _fp_book():
    return SlotBook(["capitulation_long", "exhaustion_short"], value_per_point=VPP, fee_rt=1.5)


def test_capitulation_long_fires_on_a_sell_climax_only():
    s = SlotStrategy(_fp_specs(), value_per_point=VPP)
    fp = {"cap_sell": 100.0, "cap_buy": 10.0, "cap_base": 20.0, "cap_dpx": -5.0, "cap_flip": False}
    ints = s.decide(_feat(0.0, 0.0), 29000.0, [], _fp_book(), tape_net=0.0, footprint=fp)
    assert [i["slot"] for i in ints] == ["capitulation_long"]     # sell flush + down-move → LONG fade
    assert ints[0]["side"] == "LONG"


def test_exhaustion_short_fires_on_buy_into_ask_wall_only():
    s = SlotStrategy(_fp_specs(), value_per_point=VPP)
    fp = {"net_signed": 500.0, "price_move_pt": 1.0, "bid1_size": 10.0, "ask1_size": 20.0,
          "bid1_price": 28999.0, "ask1_price": 29001.0}
    ints = s.decide(_feat(0.0, 0.0), 29000.0, [], _fp_book(), tape_net=0.0, footprint=fp)
    assert [i["slot"] for i in ints] == ["exhaustion_short"]      # heavy buying, no move, ask wall → SHORT
    assert ints[0]["side"] == "SHORT"


def test_footprint_gates_silent_without_a_footprint():
    s = SlotStrategy(_fp_specs(), value_per_point=VPP)
    assert s.decide(_feat(0.0, 0.0), 29000.0, [], _fp_book(), tape_net=0.0) == []  # no footprint → nothing


def test_capitulation_does_not_fire_short_slot_on_a_sell_flush():
    # direction gate: a sell-flush is a LONG fade; an exhaustion_short slot must NOT open on it
    s = SlotStrategy([_fp_specs()[1]], value_per_point=VPP)   # exhaustion_short only
    b = SlotBook(["exhaustion_short"], value_per_point=VPP, fee_rt=1.5)
    fp = {"cap_sell": 100.0, "cap_buy": 10.0, "cap_base": 20.0, "cap_dpx": -5.0, "cap_flip": False}
    assert s.decide(_feat(0.0, 0.0), 29000.0, [], b, tape_net=0.0, footprint=fp) == []


# ── regime-3-exit selector (adaptive_exit, 2026-07-27) ────────────────────────
def _bars(closes):
    from gazbot7.deciders import Bar
    return [Bar(i * 60, c, c + 0.1, c - 0.1, c, 10.0) for i, c in enumerate(closes)]


def test_regime_mode_aligned_trend_is_wide_counter_is_mid():
    up = _bars([28000 + 5 * i for i in range(35)])           # clean up-trend: net +170, ER ~1
    assert SlotStrategy._regime_mode("LONG", up) == "wide"    # long WITH the up-trend → ride wide
    assert SlotStrategy._regime_mode("SHORT", up) == "mid"    # short AGAINST it → k2.0 damage-control


def test_regime_mode_chop_is_tight():
    chop = _bars([28000 + (5 if i % 2 else -5) for i in range(35)])   # oscillate: net ~0, ER ~0
    assert SlotStrategy._regime_mode("LONG", chop) == "tight"
    assert SlotStrategy._regime_mode("SHORT", chop) == "tight"
    assert SlotStrategy._regime_mode("LONG", _bars([1, 2, 3])) == "tight"   # <6 bars → tight (safe)


def _held_single(mode, atr=4.0):
    spec = SlotSpec("g", "grind", "LONG", adaptive_exit=True)
    ss = SlotStrategy([spec], value_per_point=VPP)
    b = SlotBook(["g"], value_per_point=VPP, fee_rt=1.5)
    b.register("o-g", "g")
    b.apply(Fill("e-g", "o-g", "MNQ", "BUY", 1, 29000.0, "2026-07-20T14:00:00+00:00"))
    b.slot("g").entry_atr = atr
    ss._exit_mode["g"] = mode
    return spec, ss, b.slot("g")


def test_adaptive_tight_banks_where_wide_holds():
    # peak +12 (3R, atr 4): TIGHT k1.5 (→giveback ~2pt) banks at fav<=10; WIDE lock (start_k3.5 until
    # 6R → giveback 14pt) still holds it. Same trade, opposite exit — proves the width dispatch.
    for mode, expect in (("tight", "CHANDELIER"), ("wide", None)):
        spec, ss, slot = _held_single(mode)
        assert ss._manage(spec, slot, 29012.0) is None        # ride to peak +12
        assert ss._manage(spec, slot, 29009.0) == expect      # fav 9: tight banks, wide holds


def test_adaptive_exit_suppresses_giveback_overlay():
    # under adaptive_exit, the give-back overlay must NOT fire (chandelier is the pure profit exit),
    # even with giveback_enabled=True — else it pre-empts the tight/wide chandelier.
    spec = SlotSpec("g", "grind", "LONG", adaptive_exit=True, giveback_enabled=True,
                    giveback_arm_usd=50.0, giveback_usd=40.0)
    ss = SlotStrategy([spec], value_per_point=VPP)
    b = SlotBook(["g"], value_per_point=VPP, fee_rt=1.5)
    b.register("o-g", "g")
    b.apply(Fill("e-g", "o-g", "MNQ", "BUY", 1, 29000.0, "2026-07-20T14:00:00+00:00"))
    b.slot("g").entry_atr = 20.0                      # wide lock trail = 3.5*20 = 70pt (won't fire on small pullbacks)
    ss._exit_mode["g"] = "wide"
    slot = b.slot("g")
    ss._manage(spec, slot, 29025.0)                   # peak +25pt = $50 favourable → ARMS give-back
    # fav back to +5pt ($10): dropped $40 from peak → give-back WOULD fire; wide 70pt trail does NOT.
    assert ss._manage(spec, slot, 29005.0) is None    # → None proves give-back suppressed under adaptive_exit
