"""D2 — order engine: lifecycle + the idempotent-fill correctness gate."""

from __future__ import annotations

from gazbot7.engine import OrderEngine, OrderStatus
from gazbot7.store import Fill, count_fills, get_order, open_store


class FakeBroker:
    def __init__(self) -> None:
        self.placed: list[str] = []
        self.cancelled: list[str] = []

    def place(self, order) -> None:
        self.placed.append(order.client_order_id)

    def cancel(self, client_order_id) -> None:
        self.cancelled.append(client_order_id)


def _eng(tmp_path):
    store = open_store(tmp_path / "t.db")
    broker = FakeBroker()
    return OrderEngine(broker, store), broker, store


def _fill(coid, exec_id, qty=2.0, side="BUY", price=29950.0):
    return Fill(
        exec_id=exec_id,
        order_id=coid,
        symbol="MNQ",
        side=side,
        qty=qty,
        price=price,
        exec_time="2026-07-15T13:00:00+00:00",
    )


def test_submit_places_and_goes_working(tmp_path):
    eng, broker, store = _eng(tmp_path)
    coid = eng.submit(symbol="MNQ", side="BUY", qty=2, order_type="LMT", limit_price=29950.0)
    assert broker.placed == [coid]
    assert eng.get(coid).status is OrderStatus.WORKING
    assert get_order(store, coid)["status"] == "WORKING"


def test_full_fill_completes(tmp_path):
    eng, _b, store = _eng(tmp_path)
    coid = eng.submit(symbol="MNQ", side="BUY", qty=2, order_type="MKT")
    assert eng.on_fill(_fill(coid, "e1", qty=2)) is True
    o = eng.get(coid)
    assert o.status is OrderStatus.FILLED
    assert o.filled_qty == 2
    assert count_fills(store) == 1


def test_duplicate_fill_does_not_double_count(tmp_path):
    # THE D2 gate: the same exec_id delivered twice must not double the fill.
    eng, _b, store = _eng(tmp_path)
    coid = eng.submit(symbol="MNQ", side="BUY", qty=2, order_type="MKT")
    assert eng.on_fill(_fill(coid, "dup", qty=2)) is True
    assert eng.on_fill(_fill(coid, "dup", qty=2)) is False  # re-delivery → no-op
    assert eng.get(coid).filled_qty == 2  # NOT 4
    assert count_fills(store) == 1


def test_partial_then_full(tmp_path):
    eng, _b, _s = _eng(tmp_path)
    coid = eng.submit(symbol="MNQ", side="BUY", qty=2, order_type="MKT")
    eng.on_fill(_fill(coid, "p1", qty=1))
    assert eng.get(coid).status is OrderStatus.PARTIAL
    eng.on_fill(_fill(coid, "p2", qty=1))
    assert eng.get(coid).status is OrderStatus.FILLED
    assert eng.get(coid).filled_qty == 2


def test_reject_is_terminal(tmp_path):
    eng, _b, _s = _eng(tmp_path)
    coid = eng.submit(symbol="MNQ", side="BUY", qty=2, order_type="LMT", limit_price=1.0)
    eng.on_status(coid, OrderStatus.REJECTED)
    assert eng.get(coid).status is OrderStatus.REJECTED
    eng.on_status(coid, OrderStatus.WORKING)  # cannot un-reject
    assert eng.get(coid).status is OrderStatus.REJECTED


def test_cancel_flow(tmp_path):
    eng, broker, _s = _eng(tmp_path)
    coid = eng.submit(symbol="MNQ", side="SELL", qty=1, order_type="LMT", limit_price=30000.0)
    eng.cancel(coid)
    assert broker.cancelled == [coid]
    eng.on_status(coid, OrderStatus.CANCELLED)
    assert eng.get(coid).status is OrderStatus.CANCELLED


def test_status_cannot_override_filled(tmp_path):
    eng, _b, _s = _eng(tmp_path)
    coid = eng.submit(symbol="MNQ", side="BUY", qty=1, order_type="MKT")
    eng.on_fill(_fill(coid, "f", qty=1))
    assert eng.get(coid).status is OrderStatus.FILLED
    eng.on_status(coid, OrderStatus.WORKING)  # a late ack can't un-fill
    assert eng.get(coid).status is OrderStatus.FILLED
