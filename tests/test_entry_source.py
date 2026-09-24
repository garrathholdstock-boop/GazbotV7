"""WHO OPENED THIS POSITION — recorded, never inferred.

★★★ WHY (2026-09-15). The operator asked whether his own trades make money. The desk could not
answer: `trades` had no entry-source field, journald retains ~5 days, and the exit ladders do not
discriminate (a manual entry DEFAULTS to TARGET_PT, so `TARGET_100` means nothing about who
pressed). Two days of P&L were attributable only by parsing 461,738 lines of journal.

⚠ NULL MEANS UNKNOWN AND MUST STAY NULL. 83 of 110 rider rows predate this column. An inferred
value would be indistinguishable from a recorded one, and inference running out is the entire
reason the column exists.
"""
import sqlite3
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7 import store


def _db(tmp_path):
    return store.open_store(tmp_path / "t.db")


def test_the_column_exists_after_open(tmp_path):
    c = _db(tmp_path)
    assert "entry_source" in {r[1] for r in c.execute("PRAGMA table_info(trades)")}


def test_migration_is_idempotent(tmp_path):
    """open_store runs on every single write path — a non-idempotent ALTER would throw forever."""
    p = tmp_path / "t.db"
    for _ in range(3):
        store.open_store(p).close()
    c = sqlite3.connect(p)
    cols = [r[1] for r in c.execute("PRAGMA table_info(trades)")]
    assert cols.count("entry_source") == 1


def test_it_round_trips_both_values(tmp_path):
    c = _db(tmp_path)
    for i, src in enumerate(("manual", "auto")):
        store.record_trade(c, symbol="MNQ", side="LONG", qty=1, entry_price=100.0 + i,
                           exit_price=101.0 + i, opened_at=f"2026-09-15T0{i}:00:00",
                           closed_at=f"2026-09-15T0{i}:10:00", pnl_usd=1.0, fees_usd=0.1,
                           exit_reason="T", gate="day_rider", entry_source=src)
    got = dict(c.execute("select entry_source, count(*) from trades group by 1").fetchall())
    assert got == {"manual": 1, "auto": 1}


def test_omitting_it_stores_NULL_not_a_guess(tmp_path):
    """⚠ The whole point. A caller that does not know must not be defaulted into a claim."""
    c = _db(tmp_path)
    store.record_trade(c, symbol="MNQ", side="LONG", qty=1, entry_price=100.0, exit_price=101.0,
                       opened_at="2026-09-15T00:00:00", closed_at="2026-09-15T00:10:00",
                       pnl_usd=1.0, fees_usd=0.1, exit_reason="T", gate="day_rider")
    assert c.execute("select entry_source from trades").fetchone()[0] is None


def test_a_database_without_the_column_still_records(tmp_path):
    """⚠ Fixtures and pre-migration databases exist. A view that throws is worse than one that
    stores less — the same conditional shape `data_quality` uses."""
    p = tmp_path / "old.db"
    store.open_store(p).close()
    c = sqlite3.connect(p)
    c.execute("ALTER TABLE trades RENAME TO trades_new")
    c.execute("CREATE TABLE trades AS SELECT id, symbol, side, qty, entry_price, exit_price, "
              "entry_exec_id, exit_exec_id, opened_at, closed_at, pnl_usd, fees_usd, exit_reason, "
              "gate FROM trades_new WHERE 0")
    c.commit()
    assert "entry_source" not in {r[1] for r in c.execute("PRAGMA table_info(trades)")}
    store.record_trade(c, symbol="MNQ", side="LONG", qty=1, entry_price=100.0, exit_price=101.0,
                       opened_at="2026-09-15T00:00:00", closed_at="2026-09-15T00:10:00",
                       pnl_usd=1.0, fees_usd=0.1, exit_reason="T", gate="day_rider",
                       entry_source="manual")
    assert c.execute("select count(*) from trades").fetchone()[0] == 1


def test_the_rider_sources_it_from_state_not_from_a_guess():
    """★ SOURCE-LEVEL. `manual_targets_pt` is written by do_manual_entry() and nothing else, so its
    presence IS the record of a press. If book_trade ever stops reading it, attribution silently
    reverts to the archaeology this column replaced."""
    src = open("/home/alphabot/gazbot7/src/gazbot7/day_rider.py").read()
    assert 'entry_source="manual" if out.get("manual_targets_pt") else "auto"' in src, (
        "book_trade no longer records who opened the position")
    assert src.count("manual_targets_pt=") == 1, (
        "manual_targets_pt must be written by exactly ONE place (do_manual_entry) or it stops "
        "being proof of an operator press")


def test_exit_source_exists_and_round_trips(tmp_path):
    """★★2026-09-24 WHO CLOSED IT. The step-away guard flattens by writing the SAME claim file his
    own button writes, so its exits booked as `MANUAL_CLAIM` — indistinguishable from his hand. The
    first live take-profit (+$401.50) would have counted as an operator decision in every future
    study of how he exits. That is exactly the mistake `entry_source` exists to prevent on the
    other side of the trade."""
    c = _db(tmp_path)
    assert "exit_source" in {r[1] for r in c.execute("PRAGMA table_info(trades)")}
    for i, src in enumerate(("operator", "step_away:take_profit")):
        store.record_trade(c, symbol="MNQ", side="SHORT", qty=1, entry_price=100.0 + i,
                           exit_price=99.0, opened_at=f"2026-09-24T0{i}:00:00",
                           closed_at=f"2026-09-24T0{i}:10:00", pnl_usd=1.0, fees_usd=0.1,
                           exit_reason="MANUAL_CLAIM", gate="day_rider", exit_source=src)
    got = dict(c.execute("select exit_source, count(*) from trades group by 1").fetchall())
    assert got == {"operator": 1, "step_away:take_profit": 1}


def test_only_a_CLAIM_can_carry_an_exit_source():
    """⚠ A ladder rung, the trail and the 20:40 flat CLOSE THEMSELVES. Calling any of them
    'operator' would assert a decision nobody made — the same error as inferring a NULL
    entry_source. Today's +$100 rung (TARGET_100) fired in the same second as the guard's claim and
    must stay NULL."""
    src = open("/home/alphabot/gazbot7/src/gazbot7/day_rider.py").read()
    assert 'exit_source=((_LAST_CLAIM_SRC or "operator") if reason == "MANUAL_CLAIM" else None)' in src


def test_the_guard_stamps_its_own_claims():
    """★ And it does so WITHOUT changing the claim parser: an unrecognised spec already falls
    through to 'all', so `src=` rides alongside `lot=` for free."""
    away = open("/home/alphabot/gazbot7/scripts/step_away.py").read()
    assert 'f"{stamp}|src=step_away:{reason.replace(\' \', \'_\')}"' in away
    rider = open("/home/alphabot/gazbot7/src/gazbot7/day_rider.py").read()
    assert '_LAST_CLAIM_SRC' in rider and 'startswith("src=")' in rider
