"""★2026-10-22 The 03:35 double-booked exit, replayed against a scripted broker.

Root cause: ladder_fire booked each rung BEFORE the state was committed; await_fill() booked the
market price of an order that had not filled; a blocking notify() let systemd kill the oneshot
between the orders and the commit; the next tick re-sold the same four rungs.

Every test here drives the REAL fire_lot / commit_lot / reconcile_pending / ladder_fire /
book_trade against tests/fake_rung_broker.py, with a tmp state file, a tmp DB and a tmp dedupe store.
Nothing reads the wall clock for a decision (ages are passed in), nothing sleeps, nothing is sent.
"""
import asyncio
import datetime as dt
import json
import sqlite3
import threading

import pytest

from fake_rung_broker import FakeRungBroker
from gazbot7 import day_rider as dr
from gazbot7 import notify as notify_mod
from gazbot7 import store

LADDER = [37.5] * 4
LUSD = [75.0] * 4
ENTERED = "2026-10-22T03:00:00+00:00"


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(dr, "STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(dr, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(notify_mod, "_DEDUPE_PATH", str(tmp_path / "dedupe.json"))

    async def nosleep(_s):
        return None

    monkeypatch.setattr(dr, "_rung_sleep", nosleep)
    store.open_store(tmp_path / "t.db").close()
    return tmp_path


class Notes:
    def __init__(self):
        self.msgs = []

    def __call__(self, msg, **kw):
        self.msgs.append((msg, kw))
        return True

    def critical(self):
        return [m for m, kw in self.msgs if kw.get("critical")]


def fresh_state(**kw):
    s = {"entered": True, "closed": False, "entered_at": ENTERED, "entry": 30384.25, "direction": -1,
         "qty": 4.0, "lots_open": 4, "entry_lots": 4, "targets_done": [], "rung_pending": {},
         "manual_targets_pt": [37.5] * 4, "manual_targets_usd": [75.0] * 4, "venue_ok": True}
    s.update(kw)
    return s


def reload_state():
    """What a brand-new process would find on disk."""
    with open(dr.STATE) as fh:
        return json.load(fh)


def rows():
    c = sqlite3.connect(dr.DB_PATH)
    try:
        return c.execute("SELECT qty, exit_reason, exit_exec_id FROM trades ORDER BY id").fetchall()
    finally:
        c.close()


def fire(ib, out, notify=None, **kw):
    args = dict(ladder=LADDER, lusd=LUSD, done=list(out.get("targets_done") or []),
                lots_open=int(out["lots_open"]), ahead=40.0, d=-1, px=30340.0, notify=notify)
    args.update(kw)
    return asyncio.run(dr.ladder_fire(ib, object(), out, **args))


def reconcile(ib, out, *, net, notify=None, urgent=False, age_s=60):
    """Pretend `age_s` seconds have passed since the rung orders were written."""
    ts = [dt.datetime.fromisoformat(i["t"]) for i in out["rung_pending"].values()]
    t = max(ts) if ts else dt.datetime(2026, 10, 22, 3, 5, tzinfo=dt.UTC)
    return asyncio.run(dr.reconcile_pending(ib, out, net=net, notify=notify, urgent=urgent,
                                            now=t + dt.timedelta(seconds=age_s)))


# ── the happy path books four lots from four real executions ─────────────────────────────────────
def test_four_rungs_book_four_distinct_executions():
    ib, out = FakeRungBroker(), fresh_state()
    done, left = fire(ib, out)
    assert done == [0, 1, 2, 3] and left == 0
    assert len(ib.placed) == 4 and len({p[2] for p in ib.placed}) == 4        # four orderRefs
    r = rows()
    assert len(r) == 4 and len({x[2] for x in r}) == 4 and all(x[2] for x in r)
    assert out["closed"] and out["exit_reason"] == "LADDER_COMPLETE" and out["rung_pending"] == {}
    assert reload_state()["targets_done"] == [0, 1, 2, 3]


def test_booked_price_is_the_execution_price_not_the_market_price():
    ib, out = FakeRungBroker(base_px=30000.0), fresh_state()
    fire(ib, out, px=12345.0)                                                # a market price that never printed
    c = sqlite3.connect(dr.DB_PATH)
    px = [p[0] for p in c.execute("SELECT exit_price FROM trades ORDER BY id")]
    assert px == [30000.25, 30000.5, 30000.75, 30001.0]


# ── L1: an order that has not filled is not booked, not done, and not re-sent ────────────────────
def test_hanging_order_is_not_booked_and_is_never_resent():
    ib, out, n = FakeRungBroker(), fresh_state(), Notes()
    ib.mode = "hang"
    done, left = fire(ib, out, n)
    assert done == [] and left == 4 and rows() == []
    assert set(out["rung_pending"]) == {"TARGET0", "TARGET1", "TARGET2", "TARGET3"}
    assert len(ib.placed) == 4
    done, left = fire(ib, out, n)                                           # the NEXT tick
    assert len(ib.placed) == 4, "a pending rung must never be sold twice"
    assert rows() == []
    assert any("NOT booked" in m for m in n.critical())


def test_rejected_order_books_nothing_and_the_rung_stays_open():
    ib, out = FakeRungBroker(), fresh_state()
    ib.mode_by_call = {1: "reject"}
    done, left = fire(ib, out)
    assert done == [1, 2, 3] and left == 1 and len(rows()) == 3
    assert out["rung_pending"] == {} and not out["closed"]
    done, left = fire(ib, out)                                              # next tick retries rung 0 only
    assert done == [1, 2, 3, 0] or sorted(done) == [0, 1, 2, 3]
    assert len(rows()) == 4 and len(ib.placed) == 5 and ib.lots_filled == 4


def test_filled_status_without_execution_record_is_adopted_not_booked_blind():
    ib, out = FakeRungBroker(), fresh_state(lots_open=1, qty=1.0, targets_done=[1, 2, 3])
    ib.mode = "fill_no_exec"
    done, left = fire(ib, out)
    assert rows() == [] and "TARGET0" in out["rung_pending"]                # not booked from a guess
    assert reconcile(ib, out, net=-1.0, age_s=60)
    assert len(rows()) == 1 and out["rung_pending"] == {} and out["closed"]


# ── THE INCIDENT: the process dies between an order and its commit, at every point ───────────────
@pytest.mark.parametrize("k", [0, 1, 2, 3])
def test_kill_between_fill_and_commit_then_next_tick_sells_exactly_four(k, monkeypatch):
    ib, out = FakeRungBroker(), fresh_state()
    real = dr.commit_lot
    seen = {"n": 0}

    def dying_commit(*a, **kw):
        if seen["n"] == k:
            raise SystemExit("systemd killed the oneshot")                  # after the order, before the book
        seen["n"] += 1
        return real(*a, **kw)

    monkeypatch.setattr(dr, "commit_lot", dying_commit)
    with pytest.raises(SystemExit):
        fire(ib, out)
    monkeypatch.setattr(dr, "commit_lot", real)

    out2 = reload_state()                                                   # a brand-new process
    assert f"TARGET{k}" in out2["rung_pending"], "the write-ahead record must survive the kill"
    sent_before = len(ib.placed)
    done, left = fire(ib, out2)                                             # tick N+1 BEFORE reconcile: must not resell k
    assert f"TARGET{k}" in out2["rung_pending"] and len(ib.placed) == sent_before + (3 - k)
    reconcile(ib, out2, net=-(4 - k))                                       # adopts rung k from the broker's record
    assert ib.lots_sent == 4 and ib.lots_filled == 4, "exactly four lots may ever be sold"
    r = rows()
    assert len(r) == 4 and len({x[2] for x in r}) == 4
    assert sorted(out2["targets_done"]) == [0, 1, 2, 3] and out2["closed"] and out2["rung_pending"] == {}


def test_kill_after_write_ahead_before_the_order_leaves_retries_once():
    ib, out = FakeRungBroker(), fresh_state()
    ib.mode_by_call = {1: "die_before_place"}
    with pytest.raises(SystemExit):
        fire(ib, out)
    out2 = reload_state()
    assert "TARGET0" in out2["rung_pending"] and ib.placed == []
    assert reconcile(ib, out2, net=-4.0, age_s=60)                          # venue still holds all 4 → nothing happened
    assert out2["rung_pending"] == {}
    fire(ib, out2)
    assert ib.lots_sent == 4 and len(rows()) == 4


def test_absent_but_venue_short_of_our_book_is_not_cleared_and_pages():
    """'No record' beside 'fewer lots at the venue' means we cannot SEE an execution — never re-send."""
    ib, out, n = FakeRungBroker(), fresh_state(), Notes()
    ib.mode_by_call = {1: "die_before_place"}
    with pytest.raises(SystemExit):
        fire(ib, out)
    out2 = reload_state()
    assert not reconcile(ib, out2, net=-3.0, notify=n, age_s=60)            # venue holds 3, book says 4
    assert "TARGET0" in out2["rung_pending"] and ib.placed == []
    assert any("NOT re-sending" in m for m in n.critical())


def test_order_that_fills_after_the_process_is_gone_is_adopted_once():
    ib, out = FakeRungBroker(), fresh_state()
    ib.mode = "hang"
    fire(ib, out)
    ref = [p[2] for p in ib.placed][0]
    ib.complete(ref)                                                        # the venue fills it while we are dead
    out2 = reload_state()
    reconcile(ib, out2, net=-3.0)
    reconcile(ib, out2, net=-3.0)                                           # idempotent: a second pass books nothing more
    assert len([r for r in rows() if r[2]]) == 1 and out2["targets_done"] == [0]


def test_stale_working_order_is_cancelled_then_cleared_for_retry():
    ib, out = FakeRungBroker(), fresh_state(lots_open=1, qty=1.0, targets_done=[1, 2, 3])
    ib.mode = "hang"
    fire(ib, out)
    assert reconcile(ib, out, net=-1.0, age_s=10) is False                  # young: leave it working
    assert "TARGET0" in out["rung_pending"] and len(ib._open) == 1
    assert reconcile(ib, out, net=-1.0, age_s=dr.RUNG_CANCEL_AFTER_S + 1)   # old: cancel, re-read
    assert out["rung_pending"] == {} and ib._open == {} and rows() == []


def test_urgent_reconcile_cancels_immediately_before_a_claim_sizes_from_the_book():
    ib, out = FakeRungBroker(), fresh_state(lots_open=1, qty=1.0, targets_done=[1, 2, 3])
    ib.mode = "hang"
    fire(ib, out)
    reconcile(ib, out, net=-1.0, urgent=True, age_s=6)
    assert ib._open == {}


def test_fill_that_beats_the_cancel_is_adopted_not_lost():
    ib, out = FakeRungBroker(), fresh_state(lots_open=1, qty=1.0, targets_done=[1, 2, 3])
    ib.mode, ib.fill_beats_cancel = "hang", True
    fire(ib, out)
    reconcile(ib, out, net=-1.0, urgent=True, age_s=6)
    assert len(rows()) == 1 and out["closed"] and ib.lots_filled == 1


def test_unreadable_broker_changes_nothing_and_pages_when_it_persists():
    ib, out, n = FakeRungBroker(), fresh_state(lots_open=1, qty=1.0, targets_done=[1, 2, 3]), Notes()
    ib.mode = "hang"
    fire(ib, out)
    ib.fail_reads = True
    assert reconcile(ib, out, net=-1.0, notify=n, age_s=30) is False
    assert "TARGET0" in out["rung_pending"] and not any("UNRESOLVED" in m for m in n.critical())
    reconcile(ib, out, net=-1.0, notify=n, age_s=dr.RUNG_PAGE_AFTER_S + 1)
    assert any("UNRESOLVED" in m for m in n.critical())
    assert "TARGET0" in out["rung_pending"] and len(ib.placed) == 1


# ── L3 backstop: the ledger refuses to say more lots left than ever went in ─────────────────────
def test_ledger_cap_refuses_a_fifth_lot_and_pages():
    out, n = fresh_state(), Notes()
    ok = [dr.book_trade(out, exit_px=30340.0 + i, reason="T", notify=n, qty=1, exit_exec_id=f"E{i}")
          for i in range(5)]
    assert ok == [True, True, True, True, False] and len(rows()) == 4
    assert any("REFUSED TO BOOK" in m for m in n.critical())


def test_same_execution_booked_twice_is_one_row():
    out = fresh_state()
    for _ in range(2):
        dr.book_trade(out, exit_px=30340.0, reason="T", qty=1, exit_exec_id="SAME")
    assert len(rows()) == 1


# ── L5a: the independent ledger-vs-fills check ───────────────────────────────────────────────────
def _put_fill(i, side="BUY"):
    c = store.open_store(dr.DB_PATH)
    c.execute("INSERT INTO fills(exec_id,order_id,symbol,side,qty,price,commission,exec_time,kind,ingested_at) "
              "VALUES(?,?,?,?,?,?,?,?,?,?)",
              (f"F{i}", f"rider-{i}", "MNQ", side, 1, 30340.0, 0, "2026-10-22T03:30:00+00:00", "fill", ENTERED))
    c.commit(); c.close()


def test_audit_ok_when_ledger_and_broker_agree():
    out = fresh_state()
    for i in range(4):
        dr.book_trade(out, exit_px=30340.0, reason="T", qty=1, exit_exec_id=f"E{i}")
        _put_fill(i)
    assert dr.audit_exits_vs_fills(out, Notes()) == "ok" and out["xcheck_miss"] == 0


def test_audit_pages_on_the_second_consecutive_phantom_exit():
    """The 10-22 shape: 8 lots booked, 4 executed."""
    out, n = fresh_state(entry_lots=0), Notes()
    for i in range(8):
        dr.book_trade(out, exit_px=30340.0, reason="T", qty=1, exit_exec_id=f"E{i}")
    for i in range(4):
        _put_fill(i)
    assert dr.audit_exits_vs_fills(out, n).startswith("MISMATCH") and n.critical() == []   # one tick may be lag
    assert dr.audit_exits_vs_fills(out, n).startswith("MISMATCH")
    assert any("PHANTOM EXITS" in m for m in n.critical())


def test_audit_unreadable_db_is_no_verdict_not_a_pass(monkeypatch):
    assert dr.audit_exits_vs_fills(fresh_state(), Notes(), db_path="/nonexistent/x.db") is None


# ── L4: a slow channel can never hold the order path ─────────────────────────────────────────────
def test_async_notifier_returns_immediately_and_drains():
    gate, sent = threading.Event(), []

    def slow(msg, **kw):
        gate.wait(5)
        sent.append(msg)

    n = dr.AsyncNotifier(slow)
    assert n("a", critical=True) is True and sent == []                    # the caller was not held
    gate.set()
    assert n.drain(5.0) and sent == ["a"]


def test_badfill_rows_are_not_counted_against_the_cap_or_the_audit():
    """The live `trades` table carries `data_quality` (added out-of-band); mirror it, label 4 rows
    BADFILL as was done for 1347-1350, and the same entry may legitimately book 4 fresh exits."""
    c = store.open_store(dr.DB_PATH)
    c.execute("ALTER TABLE trades ADD COLUMN data_quality TEXT")
    c.commit(); c.close()
    out = fresh_state()
    for i in range(4):
        dr.book_trade(out, exit_px=30340.0, reason="T", qty=1, exit_exec_id=f"B{i}")
    c = sqlite3.connect(dr.DB_PATH)
    c.execute("UPDATE trades SET data_quality='BADFILL: double-booked'"); c.commit(); c.close()
    assert all(dr.book_trade(out, exit_px=30340.0, reason="T", qty=1, exit_exec_id=f"G{i}") for i in range(4))
    assert dr.book_trade(out, exit_px=30340.0, reason="T", qty=1, exit_exec_id="G9") is False
    for i in range(4):
        _put_fill(i)
    assert dr.audit_exits_vs_fills(out, Notes()) == "ok"


def test_a_real_trade_flagged_out_of_the_pnl_does_not_page_unbooked_exits():
    """10-26: the operator's accidental manual trade (1387) was really executed, then flagged BADFILL so P&L ignores it. Its 4 exit
    lots are in `fills`; the audit paged UNBOOKED EXITS every 15 min until the next entry. Flagged rows that match the broker = ruled."""
    c = store.open_store(dr.DB_PATH)
    c.execute("ALTER TABLE trades ADD COLUMN data_quality TEXT")
    c.commit(); c.close()
    out, n = fresh_state(), Notes()
    for i in range(4):
        dr.book_trade(out, exit_px=30340.0, reason="T", qty=1, exit_exec_id=f"R{i}")
        _put_fill(i, side="SELL" if int(out["direction"]) > 0 else "BUY")
    c = sqlite3.connect(dr.DB_PATH)
    c.execute("UPDATE trades SET data_quality='BADFILL:operator_accidental_manual_trade_20261026'"); c.commit(); c.close()
    for _ in range(3):
        assert dr.audit_exits_vs_fills(out, n).startswith("ok")
    assert n.critical() == []
    _put_fill(9, side="SELL" if int(out["direction"]) > 0 else "BUY")          # a genuinely unbooked exit still pages
    dr.audit_exits_vs_fills(out, n); dr.audit_exits_vs_fills(out, n)
    assert any("UNBOOKED EXITS" in m for m in n.critical())


def test_missing_data_quality_column_does_not_disable_the_cap():
    out = fresh_state()
    for i in range(4):
        dr.book_trade(out, exit_px=30340.0, reason="T", qty=1, exit_exec_id=f"M{i}")
    assert dr.book_trade(out, exit_px=30340.0, reason="T", qty=1, exit_exec_id="M9") is False
