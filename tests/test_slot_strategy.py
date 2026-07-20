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
