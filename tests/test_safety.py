"""D4 — position safety: 1-ATR stop, naked guard, reconcile scars."""

from __future__ import annotations

from gazbot7.safety import (
    SafetyManager,
    audit_naked,
    compute_stop_price,
    covered_qty,
    is_naked,
    is_protective_stop,
    reconcile,
    reconcile_verdict,
)


class FakeStopBroker:
    def __init__(self) -> None:
        self.placed: list[dict] = []
        self.cancelled: list[str] = []
        self._n = 0

    def place_stop(self, *, symbol, side, qty, stop_price) -> str:
        self._n += 1
        coid = f"stp-{self._n}"
        self.placed.append(dict(symbol=symbol, side=side, qty=qty, stop_price=stop_price, coid=coid))
        return coid

    def cancel(self, coid) -> None:
        self.cancelled.append(coid)


def test_stop_price_symmetric():
    # long stop below entry, short stop above — 1 ATR each way
    assert compute_stop_price(100.0, 4.0, is_short=False) == 96.0
    assert compute_stop_price(100.0, 4.0, is_short=True) == 104.0


def test_arm_stop_places_opposite_side(tmp_path=None):
    broker = FakeStopBroker()
    sm = SafetyManager(broker)
    st = sm.arm_stop("MNQ", side="LONG", qty=2, entry_price=100.0, atr=4.0)
    assert st.side == "SELL"  # a long is protected by a SELL stop
    assert st.stop_price == 96.0
    assert broker.placed[0]["side"] == "SELL" and broker.placed[0]["stop_price"] == 96.0
    assert sm.has_stop("MNQ")


def test_short_protected_by_buy_stop():
    broker = FakeStopBroker()
    sm = SafetyManager(broker)
    st = sm.arm_stop("MNQ", side="SHORT", qty=2, entry_price=100.0, atr=4.0)
    assert st.side == "BUY" and st.stop_price == 104.0


def test_on_flat_cancels_stop():
    broker = FakeStopBroker()
    sm = SafetyManager(broker)
    sm.arm_stop("MNQ", side="LONG", qty=2, entry_price=100.0, atr=4.0)
    sm.on_flat("MNQ")
    assert broker.cancelled == ["stp-1"]
    assert not sm.has_stop("MNQ")


def test_audit_naked_flags_unprotected_position():
    # MNQ open with a stop → safe; MES open with NO stop → naked
    naked = audit_naked({"MNQ": 2.0, "MES": -1.0}, venue_stops={"MNQ"})
    assert naked == ["MES"]


def test_audit_naked_ignores_flat():
    assert audit_naked({"MNQ": 0.0}, venue_stops=set()) == []


def test_handle_naked_reprotects_and_pages():
    broker = FakeStopBroker()
    paged: list[str] = []
    sm = SafetyManager(broker, notifier=paged.append)
    sm.handle_naked("MNQ", side="SHORT", qty=2, entry_price=100.0, atr=4.0)
    assert broker.placed[0]["side"] == "BUY" and broker.placed[0]["stop_price"] == 104.0  # reprotected
    assert len(paged) == 1 and "NAKED MNQ" in paged[0]  # AND paged


def test_zombie_reentry_rearms_stop():
    # a re-entry onto a just-flattened line gets its OWN fresh stop (V5 zombie scar)
    broker = FakeStopBroker()
    sm = SafetyManager(broker)
    sm.arm_stop("MNQ", side="LONG", qty=2, entry_price=100.0, atr=4.0)
    sm.on_flat("MNQ")  # closed
    sm.arm_stop("MNQ", side="SHORT", qty=2, entry_price=110.0, atr=4.0)  # re-entered, other way
    assert sm.has_stop("MNQ")
    assert broker.placed[-1]["side"] == "BUY" and broker.placed[-1]["stop_price"] == 114.0


def test_arm_stop_rounds_off_grid_price_to_tick():
    # today's incident: entry 29491.5, ATR 13.286 → raw stop 29478.214 (Error 110).
    # arm_stop must floor the SELL stop onto the 0.25 grid before it leaves.
    broker = FakeStopBroker()
    sm = SafetyManager(broker)
    st = sm.arm_stop("MNQ", side="LONG", qty=1, entry_price=29491.5, atr=13.286)
    assert st.stop_price == 29478.0
    assert round(st.stop_price / 0.25) == st.stop_price / 0.25  # on-grid, IBKR-legal
    assert broker.placed[0]["stop_price"] == 29478.0


def test_is_protective_stop_only_live_closing_side():
    assert is_protective_stop("STP", "SELL", "PreSubmitted", "LONG")   # SELL STP protects a long
    assert is_protective_stop("TRAIL", "BUY", "Submitted", "SHORT")    # BUY TRAIL protects a short
    assert not is_protective_stop("STP", "BUY", "PreSubmitted", "LONG")  # wrong side
    assert not is_protective_stop("STP", "SELL", "Inactive", "LONG")     # not live
    assert not is_protective_stop("STP", "SELL", "Cancelled", "LONG")    # cancelled
    assert not is_protective_stop("LMT", "SELL", "Submitted", "LONG")    # a take-profit, not a stop


def test_is_naked_reads_venue_truth_not_a_flag():
    # held long, but the only stop is Inactive → NAKED ("placed but didn't stick")
    assert is_naked("LONG", 1.0, [("STP", "SELL", "Inactive", 1.0)]) is True
    assert is_naked("LONG", 1.0, [("STP", "SELL", "PreSubmitted", 1.0)]) is False
    assert is_naked("LONG", 0.0, []) is False  # flat is never naked


def test_covered_qty_sums_live_only():
    orders = [("STP", "SELL", "PreSubmitted", 1.0), ("STP", "SELL", "Cancelled", 1.0)]
    assert covered_qty("LONG", orders) == 1.0


def test_reconcile_detects_drift():
    # tracker thinks flat, venue says we're short 2 → the 2026-06-11 blind-book class
    assert reconcile({"MNQ": 0.0}, {"MNQ": -2.0}) == ["MNQ"]
    assert reconcile({"MNQ": 2.0}, {"MNQ": 2.0}) == []


def test_reconcile_verdict_cases():
    assert reconcile_verdict(None, 0.0, 0.0) == "match"      # both flat
    assert reconcile_verdict("LONG", 1.0, 1.0) == "match"    # agree
    assert reconcile_verdict(None, 0.0, 2.0) == "adopt"      # flat, venue holds → take over
    assert reconcile_verdict("LONG", 1.0, 0.0) == "vanished" # held, venue flat → closed unseen
    assert reconcile_verdict("LONG", 1.0, -1.0) == "drift"   # sign flip
    assert reconcile_verdict("LONG", 1.0, 2.0) == "drift"    # qty mismatch
