"""D4 — position safety: 1-ATR stop, naked guard, reconcile scars."""

from __future__ import annotations

from gazbot7.safety import (
    SafetyManager,
    audit_naked,
    compute_stop_price,
    reconcile,
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


def test_reconcile_detects_drift():
    # tracker thinks flat, venue says we're short 2 → the 2026-06-11 blind-book class
    assert reconcile({"MNQ": 0.0}, {"MNQ": -2.0}) == ["MNQ"]
    assert reconcile({"MNQ": 2.0}, {"MNQ": 2.0}) == []
