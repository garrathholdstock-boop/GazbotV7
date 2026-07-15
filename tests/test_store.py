"""D0 — the store, and its one load-bearing guarantee: idempotent fills."""

from __future__ import annotations

from gazbot7.store import Fill, count_fills, get_fill, open_store, record_fill


def _fill(exec_id: str = "e1", **kw) -> Fill:
    base = dict(
        exec_id=exec_id,
        order_id="o1",
        symbol="MNQ",
        side="BUY",
        qty=2.0,
        price=29950.0,
        commission=1.5,
        exec_time="2026-07-15T13:00:00+00:00",
    )
    base.update(kw)
    return Fill(**base)


def test_schema_creates_and_starts_empty(tmp_path):
    conn = open_store(tmp_path / "t.db")
    assert count_fills(conn) == 0


def test_wal_enabled(tmp_path):
    conn = open_store(tmp_path / "t.db")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_record_fill_round_trips(tmp_path):
    conn = open_store(tmp_path / "t.db")
    assert record_fill(conn, _fill()) is True
    assert count_fills(conn) == 1
    got = get_fill(conn, "e1")
    assert got is not None
    assert got["side"] == "BUY"
    assert got["price"] == 29950.0
    assert got["qty"] == 2.0


def test_duplicate_exec_id_is_a_noop(tmp_path):
    # THE D0 gate: applying the same fill twice cannot double-count. Both the
    # fast per-order path and an account-wide path may observe one execution;
    # the second must be absorbed, not raced (V5's partial-fill class).
    conn = open_store(tmp_path / "t.db")
    assert record_fill(conn, _fill("dup")) is True
    assert record_fill(conn, _fill("dup")) is False  # second observer → no-op
    assert count_fills(conn) == 1


def test_distinct_fills_accumulate(tmp_path):
    conn = open_store(tmp_path / "t.db")
    record_fill(conn, _fill("a"))
    record_fill(conn, _fill("b"))
    record_fill(conn, _fill("a"))  # a re-delivery of 'a'
    assert count_fills(conn) == 2


def test_side_check_rejects_garbage(tmp_path):
    import sqlite3

    conn = open_store(tmp_path / "t.db")
    try:
        record_fill(conn, _fill("bad", side="LONG"))  # not a BUY/SELL — schema CHECK
    except sqlite3.IntegrityError:
        return
    raise AssertionError("expected the side CHECK constraint to reject 'LONG'")


def test_zero_price_rejected(tmp_path):
    # V5 VCORR scar: a synthetic px=0 execution must never enter the ledger.
    import sqlite3

    conn = open_store(tmp_path / "t.db")
    try:
        record_fill(conn, _fill("z", price=0.0))
    except sqlite3.IntegrityError:
        return
    raise AssertionError("expected the price>0 CHECK constraint to reject px=0")
