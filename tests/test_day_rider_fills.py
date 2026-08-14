"""The day-rider must leave a venue execution record.

★★★2026-08-14 WHY. The `fills` table held 1,437 executions back to 07-16 and NOT ONE was the
rider's — every order_id was `v7-mnq-*` or `stp-*`, the tournament's. Nine rider trades sat in
`trades` with no execution behind them. The one desk that malfunctioned was the one desk with no
venue record, which is why 08-13 took hours to reconstruct by hand and why its naked-8-lot cost
still cannot be derived from anything on this box.

IBKR's reqExecutions only reaches back ~24h, so without this the rider's history becomes books-only
the next day — the exact thing the operator's standing rule forbids relying on.
"""
import asyncio
import datetime as dt

from gazbot7 import day_rider as dr
from gazbot7.store import open_store


class _Ex:
    def __init__(self, exec_id, order_id, side, shares, price, client_id):
        self.execId, self.orderId, self.side = exec_id, order_id, side
        self.shares, self.price, self.clientId = shares, price, client_id


class _Contract:
    def __init__(self, symbol):
        self.symbol = symbol


class _CR:
    def __init__(self, commission):
        self.commission = commission


class _Row:
    def __init__(self, ex, symbol="MNQ", commission=None, when=None):
        self.execution, self.contract = ex, _Contract(symbol)
        self.commissionReport = _CR(commission) if commission is not None else None
        self.time = when or dt.datetime(2026, 8, 14, 13, 38, 21, tzinfo=dt.UTC)


class _IB:
    def __init__(self, rows, boom=False):
        self._rows, self._boom = rows, boom

    async def reqExecutionsAsync(self, _f):
        if self._boom:
            raise RuntimeError("venue read failed")
        return self._rows


def _fills(db):
    c = open_store(db)
    try:
        return [dict(r) for r in c.execute(
            "SELECT exec_id, order_id, side, qty, price, commission FROM fills ORDER BY exec_id")]
    finally:
        c.close()


def test_rider_fills_are_recorded_with_an_attributable_order_id(tmp_path):
    db = str(tmp_path / "g.db")
    ib = _IB([_Row(_Ex("e1", 73, "SLD", 2, 30194.25, dr.CLIENT_ID), commission=1.5)])
    assert asyncio.run(dr.record_own_fills(ib, "MNQ", db_path=db)) == 1
    (f,) = _fills(db)
    assert f["exec_id"] == "e1" and f["side"] == "SELL" and f["qty"] == 2 and f["price"] == 30194.25
    assert f["order_id"] == "rider-73", "must not collide with the tournament's v7-mnq-* / stp-*"
    assert f["commission"] == 1.5


def test_another_desks_fills_are_NOT_claimed(tmp_path):
    """A master API client id is configured, so this connection SEES the tournament's executions.
    Recording them here would attribute another desk's fills to the rider — the same
    shared-resource-without-the-owner-tag mistake as the 08-06 flatten and MD_STREAM."""
    db = str(tmp_path / "g.db")
    ib = _IB([_Row(_Ex("mine", 73, "SLD", 2, 30194.25, dr.CLIENT_ID)),
              _Row(_Ex("tournament", 1018, "BOT", 1, 30172.75, 0)),
              _Row(_Ex("watchdog", 99, "BOT", 1, 30100.0, 5))])
    assert asyncio.run(dr.record_own_fills(ib, "MNQ", db_path=db)) == 1
    assert [f["exec_id"] for f in _fills(db)] == ["mine"]


def test_other_symbols_are_filtered(tmp_path):
    """MD_STREAM's lesson: a shared feed must always be filtered by the tag that names the owner."""
    db = str(tmp_path / "g.db")
    ib = _IB([_Row(_Ex("mnq", 73, "SLD", 2, 30194.25, dr.CLIENT_ID)),
              _Row(_Ex("mgc", 74, "BOT", 1, 3055.0, dr.CLIENT_ID), symbol="MGC")])
    assert asyncio.run(dr.record_own_fills(ib, "MNQ", db_path=db)) == 1
    assert [f["exec_id"] for f in _fills(db)] == ["mnq"]


def test_reobserving_the_same_executions_is_free(tmp_path):
    """The rider is a 60s oneshot and reqExecutions returns ~24h, so it re-reads the same fills all
    day. record_fill conflicts on IBKR's execId, so repeats must be no-ops, not duplicates."""
    db = str(tmp_path / "g.db")
    ib = _IB([_Row(_Ex("e1", 73, "SLD", 2, 30194.25, dr.CLIENT_ID))])
    assert asyncio.run(dr.record_own_fills(ib, "MNQ", db_path=db)) == 1
    for _ in range(5):
        assert asyncio.run(dr.record_own_fills(ib, "MNQ", db_path=db)) == 0
    assert len(_fills(db)) == 1


def test_a_venue_read_failure_never_raises(tmp_path):
    """Bookkeeping must NEVER break the order path — this runs before every decision the rider makes."""
    assert asyncio.run(dr.record_own_fills(_IB([], boom=True), "MNQ",
                                           db_path=str(tmp_path / "g.db"))) == 0


def test_an_unwritable_store_never_raises(tmp_path):
    ib = _IB([_Row(_Ex("e1", 73, "SLD", 2, 30194.25, dr.CLIENT_ID))])
    assert asyncio.run(dr.record_own_fills(ib, "MNQ", db_path="/nonexistent-dir-xyz/g.db")) == 0


def test_a_missing_commission_report_defaults_to_zero(tmp_path):
    db = str(tmp_path / "g.db")
    ib = _IB([_Row(_Ex("e1", 73, "SLD", 2, 30194.25, dr.CLIENT_ID), commission=None)])
    assert asyncio.run(dr.record_own_fills(ib, "MNQ", db_path=db)) == 1
    assert _fills(db)[0]["commission"] == 0.0
