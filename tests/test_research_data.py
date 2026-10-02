"""THE RESEARCH DATA LAYER — entry grouping and fabricated-fill exclusion.

★★★ Phase 0 of docs/SCOPE_RECURSIVE_TRADING_LOOP.md. These views are the foundation every later
experiment stands on, so the tests here are about the two ways the foundation can be wrong:
grouping rows that are not one entry, and filtering fills by the wrong rule.

⚠⚠ THE SECOND ONE ALREADY HAPPENED TO ME. On 2026-10-02 I filtered on `qty == 1` alone, concluded
that the hold-time gradient did not exist, and told the operator the patience thesis was probably a
fill artifact. It was my filter that was broken: `qty == 1` conflates "clean fill" with "single-lot
trade" and discards ~200 legitimate rows, because a qty=1 exit from a 4-lot entry after the
2026-09-04 entry fix is perfectly clean. With the date-aware rule the gradient is plainly there and
reproduces the recorded +$86/entry almost exactly. `test_fill_clean_is_DATE_AWARE_not_qty_only` is
that mistake, written down so it cannot be made twice.
"""

from __future__ import annotations

import sqlite3

import pytest

from gazbot7 import research_data as rd

LIVE = "data/gazbot7.db"


# ── fixtures ────────────────────────────────────────────────────────────────────────────────────

def _db(tmp_path, rows):
    """A trades table with the real column set. `rows` are dicts; missing keys become NULL."""
    p = tmp_path / "t.db"
    c = sqlite3.connect(p)
    c.execute("""CREATE TABLE trades (
        id INTEGER PRIMARY KEY, symbol TEXT, side TEXT, qty REAL, entry_price REAL,
        exit_price REAL, entry_exec_id TEXT, exit_exec_id TEXT, opened_at TEXT, closed_at TEXT,
        pnl_usd REAL, fees_usd REAL, exit_reason TEXT, gate TEXT, data_quality TEXT,
        entry_source TEXT, exit_source TEXT)""")
    cols = ("symbol", "side", "qty", "entry_price", "exit_price", "opened_at", "closed_at",
            "pnl_usd", "fees_usd", "exit_reason", "gate", "data_quality", "entry_source")
    for r in rows:
        c.execute(f"INSERT INTO trades ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                  tuple(r.get(k) for k in cols))
    c.commit()
    rd.ensure_views(c)
    c.row_factory = sqlite3.Row
    return c


def _row(**kw):
    base = dict(symbol="MNQ", side="LONG", qty=1.0, entry_price=30000.0, exit_price=30050.0,
                opened_at="2026-09-20T10:00:00", closed_at="2026-09-20T11:00:00",
                pnl_usd=100.0, fees_usd=1.5, exit_reason="TARGET_100", gate="day_rider",
                data_quality=None, entry_source="manual")
    base.update(kw)
    return base


# ── 1. ENTRY GROUPING ───────────────────────────────────────────────────────────────────────────

def test_scale_out_legs_collapse_to_ONE_entry(tmp_path):
    """★★★ THE WHOLE POINT. CLAUDE.md: "group by ENTRY, not by trade row — the rows are scale-out
    exits; counting them inflates n ~2.5x." Before this view that rule was unobeyable, because
    `trades` has no entry key and `entry_exec_id` is populated on 98 of 1,176 rows."""
    c = _db(tmp_path, [
        _row(qty=1.0, exit_reason="TARGET_100", closed_at="2026-09-20T10:30:00", pnl_usd=100.0),
        _row(qty=1.0, exit_reason="TARGET_200", closed_at="2026-09-20T11:00:00", pnl_usd=200.0),
        _row(qty=2.0, exit_reason="MANUAL_CLAIM", closed_at="2026-09-20T12:00:00", pnl_usd=300.0),
    ])
    assert c.execute("SELECT COUNT(*) FROM research_rows").fetchone()[0] == 3
    ent = c.execute("SELECT * FROM research_entries").fetchall()
    assert len(ent) == 1, "three scale-out legs of one entry must be ONE entry"
    e = ent[0]
    assert e["lots"] == 4.0 and e["exit_legs"] == 3
    assert e["pnl_usd"] == 600.0, "entry P&L is the sum of its legs"


def test_held_min_on_an_entry_runs_to_the_LAST_exit(tmp_path):
    """An entry's life ends when the last lot leaves, not the first. Per-leg holds live in
    research_rows, which is a different question (exit research, not hold-time research)."""
    c = _db(tmp_path, [
        _row(closed_at="2026-09-20T10:15:00"),
        _row(closed_at="2026-09-20T13:00:00"),
    ])
    e = c.execute("SELECT * FROM research_entries").fetchone()
    assert e["held_min"] == pytest.approx(180.0, abs=0.1), "10:00 -> 13:00 is 180 minutes"


def test_entry_price_is_NOT_in_the_key_so_a_SPLIT_FILL_stays_one_entry(tmp_path):
    """⚠ Including entry_price split a real entry in the live book: 2026-07-30T15:52:27 LONG at
    28071.50 and 28071.25 — ONE TICK apart, which is a split fill of a single entry, not two
    entries. A key that fragments on execution detail miscounts n upward."""
    c = _db(tmp_path, [
        _row(entry_price=28071.50),
        _row(entry_price=28071.25),
    ])
    assert c.execute("SELECT COUNT(*) FROM research_entries").fetchone()[0] == 1


def test_different_sides_at_the_same_instant_are_different_entries(tmp_path):
    """The key must not over-merge either. A long and a short are never one entry."""
    c = _db(tmp_path, [_row(side="LONG"), _row(side="SHORT")])
    assert c.execute("SELECT COUNT(*) FROM research_entries").fetchone()[0] == 2


# ── 2. FABRICATED FILLS ─────────────────────────────────────────────────────────────────────────

def test_fill_clean_is_DATE_AWARE_not_qty_only(tmp_path):
    """★★★ THE REGRESSION TEST FOR MY OWN 2026-10-02 ERROR.

    A qty=1 exit from a MULTI-LOT entry opened AFTER the 2026-09-04 entry fix is CLEAN. Filtering on
    `qty == 1` alone would also call it clean — but filtering on "single-lot trade" (entry_lots==1)
    would wrongly discard it, and that is the filter that made me tell the operator the patience
    thesis was a fill artifact. It discarded ~200 legitimate rows and inverted the answer."""
    c = _db(tmp_path, [
        # a 4-lot entry opened after the entry fix, scaled out one lot at a time after the exit fix
        _row(qty=1.0, opened_at="2026-09-20T10:00:00", closed_at="2026-09-20T10:30:00"),
        _row(qty=1.0, opened_at="2026-09-20T10:00:00", closed_at="2026-09-20T10:40:00"),
        _row(qty=1.0, opened_at="2026-09-20T10:00:00", closed_at="2026-09-20T10:50:00"),
        _row(qty=1.0, opened_at="2026-09-20T10:00:00", closed_at="2026-09-20T11:00:00"),
    ])
    e = c.execute("SELECT * FROM research_entries").fetchone()
    assert e["lots"] == 4.0, "this is a multi-lot ENTRY"
    assert e["fill_clean"] == 1, (
        "a 4-lot entry opened after 2026-09-04 and scaled out in single lots is CLEAN. "
        "Rejecting it because entry_lots > 1 is the filter error that inverted Experiment #1")


def test_ONE_LOT_was_never_fabricated_on_any_date(tmp_path):
    """"ONE LOT IS UNCHANGED, DELIBERATELY. The fabrication hits only lots BEYOND THE FIRST."
    So a qty=1 exit is clean even deep in the pre-fix era."""
    c = _db(tmp_path, [_row(qty=1.0, opened_at="2026-08-01T10:00:00",
                            closed_at="2026-08-01T11:00:00")])
    assert c.execute("SELECT fill_clean FROM research_entries").fetchone()[0] == 1


def test_a_multi_lot_EXIT_before_the_exit_fix_is_FABRICATED(tmp_path):
    c = _db(tmp_path, [_row(qty=3.0, opened_at="2026-09-10T10:00:00",
                            closed_at="2026-09-10T11:00:00")])
    e = c.execute("SELECT * FROM research_entries").fetchone()
    assert e["any_exit_fabricated"] == 1 and e["fill_clean"] == 0


def test_a_multi_lot_EXIT_after_the_exit_fix_is_CLEAN(tmp_path):
    """⚠ Post-fix multi-lot exits still CROSS THE SPREAD — that is real slippage and a legitimate
    cost. fill_clean excludes FABRICATION, never real execution cost."""
    c = _db(tmp_path, [_row(qty=3.0, opened_at="2026-09-20T10:00:00",
                            closed_at="2026-09-20T11:00:00")])
    assert c.execute("SELECT fill_clean FROM research_entries").fetchone()[0] == 1


def test_a_multi_lot_ENTRY_before_the_entry_fix_is_FABRICATED(tmp_path):
    c = _db(tmp_path, [
        _row(qty=1.0, opened_at="2026-08-20T10:00:00", closed_at="2026-09-20T10:30:00"),
        _row(qty=1.0, opened_at="2026-08-20T10:00:00", closed_at="2026-09-20T10:40:00"),
    ])
    e = c.execute("SELECT * FROM research_entries").fetchone()
    assert e["entry_fabricated"] == 1 and e["fill_clean"] == 0


def test_an_entry_is_clean_only_if_EVERY_leg_is(tmp_path):
    """MIN() semantics. A partly-fabricated entry is not half-usable: the desk's own rule is that
    flagging a partly-fabricated trade takes the WHOLE row, and scoring follows the same logic."""
    c = _db(tmp_path, [
        _row(qty=1.0, opened_at="2026-09-10T10:00:00", closed_at="2026-09-10T10:30:00"),  # clean
        _row(qty=3.0, opened_at="2026-09-10T10:00:00", closed_at="2026-09-10T11:00:00"),  # fab
    ])
    e = c.execute("SELECT * FROM research_entries").fetchone()
    assert e["fill_clean"] == 0, "one fabricated leg makes the entry unscoreable"


# ── 3. THE STANDARD FILTER MUST NOT SELECT ON OUTCOME ───────────────────────────────────────────

def test_the_CLEAN_filter_excludes_no_trade_for_being_a_LOSER(tmp_path):
    """⚠⚠ A filter that drops losers is not a filter, it is a result. The only exclusions are
    fabricated fills, operator-labelled rows, and rows with no P&L at all."""
    assert "pnl_usd <" not in rd.CLEAN and "pnl_usd >" not in rd.CLEAN
    assert "ORDER BY" not in rd.CLEAN.upper() and "LIMIT" not in rd.CLEAN.upper()
    # ⚠ distinct opened_at — same timestamp is the SAME entry by design, which is the point of
    #   the grouping view and would make this test assert the wrong thing.
    c = _db(tmp_path, [_row(pnl_usd=-900.0, opened_at="2026-09-20T10:00:00"),
                       _row(pnl_usd=900.0, opened_at="2026-09-20T14:00:00")])
    assert len(rd.clean_entries(c)) == 2, "both a big winner and a big loser must survive"


def test_operator_labelled_rows_are_excluded(tmp_path):
    """EXCLUDE: is gone from every view; BADFILL: reaches the blotter but never a P&L ranking."""
    c = _db(tmp_path, [
        _row(data_quality="EXCLUDE:day_rider_phantom_rebook_20260813"),
        _row(data_quality="BADFILL:paper_engine_0.1pct_fabrication", opened_at="2026-09-20T12:00:00"),
        _row(opened_at="2026-09-20T13:00:00"),
    ])
    assert len(rd.clean_entries(c)) == 1


# ── 4. IT MUST NOT TOUCH THE TRADES TABLE ───────────────────────────────────────────────────────

def test_it_is_READ_ONLY_against_trades(tmp_path):
    """The research layer may never write to the book. 66 consumers read that table and the desk
    writes to it live."""
    c = _db(tmp_path, [_row()])
    before = tuple(c.execute("SELECT COUNT(*), SUM(pnl_usd) FROM trades").fetchone())
    rd.ensure_views(c); rd.ensure_views(c)        # idempotent
    rd.clean_entries(c)
    after = tuple(c.execute("SELECT COUNT(*), SUM(pnl_usd) FROM trades").fetchone())
    assert after == before, "the research layer must not alter one row of the book"
    src = open("src/gazbot7/research_data.py", encoding="utf-8").read()
    for forbidden in ("INSERT INTO trades", "UPDATE trades", "DELETE FROM trades",
                      "ALTER TABLE trades", "DROP TABLE"):
        assert forbidden not in src, f"research_data must never {forbidden}"


def test_it_is_NOT_wired_into_the_desk_startup_path(tmp_path):
    """⚠ Deliberately not in store.py's schema. A mistake in a research view must not be able to
    break the desk coming up."""
    store = open("src/gazbot7/store.py", encoding="utf-8").read()
    assert "research_rows" not in store and "research_entries" not in store
    assert "research_data" not in store


# ── 5. THE DATES AND THE FEE ARE NOT CASUAL NUMBERS ────────────────────────────────────────────

def test_the_fabrication_dates_are_the_COMMIT_dates_that_fixed_IT():
    """⚠ These are not estimates. 643d9e2 made entries marketable limits on 2026-09-04; 3734acd did
    the same for multi-lot exits on 2026-09-15. Moving either silently re-labels history."""
    assert rd.FAB_ENTRY_FIXED == "2026-09-04"
    assert rd.FAB_EXIT_FIXED == "2026-09-15"
    src = open("src/gazbot7/research_data.py", encoding="utf-8").read()
    assert "643d9e2" in src and "3734acd" in src, "each date must name the commit that justifies it"


def test_research_prices_at_VENUE_TRUTH_and_declares_no_second_fee():
    """★★2026-10-02 THIS TEST USED TO ASSERT THE OPPOSITE. It pinned a research-only
    FEE_RT_RESEARCH = $3.42 "IB-implied", and tests/test_fee_constant.py rejected the constant —
    correctly. The $3.42 came from ONE day's book-recon divergence ($153.58 over 80 lots) which I
    attributed to commission; the ledger carries fees_usd = 1.50 across 487 fills, and the
    divergence is far better explained by the FABRICATED FILL this module already excludes (~$60
    per extra lot). A research-only inflated fee would manufacture false negatives every night —
    "at 3.3x the true commission a marginal edge simply dies and the harness reports a clean NULL"."""
    assert rd.FEE_RT == 1.50
    src = open("src/gazbot7/research_data.py", encoding="utf-8").read()
    assert "3.42" not in src.split("FEE_RT = 1.50")[1], \
        "no second fee constant may live below the declaration"
    assert not any(n.startswith("FEE") and n != "FEE_RT" for n in dir(rd)), \
        "exactly one fee name, so production and research can never diverge"


# ── 6. AGAINST THE LIVE BOOK — the numbers Phase 0 was built to produce ─────────────────────────

def test_the_live_book_groups_as_measured():
    """A canary on the real database: 1,176 rows collapse to 1,071 entries and 84% are clean. If
    these move a lot without anyone intending it, the grouping or the fill rule has changed."""
    c = rd.connect(LIVE)
    rows = c.execute("SELECT COUNT(*) FROM research_rows").fetchone()[0]
    ents = c.execute("SELECT COUNT(*) FROM research_entries").fetchone()[0]
    assert rows > ents, "scale-out legs must collapse"
    assert 1.0 < rows / ents < 1.6, f"rows/entries = {rows / ents:.2f}, outside the measured range"
    clean = c.execute("SELECT COUNT(*) FROM research_entries WHERE fill_clean=1").fetchone()[0]
    assert 0.70 < clean / ents < 0.95, f"clean share {clean / ents:.2f} — the fill rule moved"


def test_EXPERIMENT_1_the_hold_time_gradient_is_REAL_on_clean_fills():
    """★★★ THE PHASE 0 DELIVERABLE, and the correction of my own wrong answer.

    At ENTRY level on CLEAN fills the gradient is monotone up to 4 hours and then collapses:
        under 15m  n=84  -$47.89     15-60m  n=79  +$33.21
        1-4h       n=30  +$88.28     over 4h n=7   -$705.00
    The 1-4h cell reproduces the independently recorded "+$86/entry over 30" almost exactly, which
    is the strongest corroboration available that the grouping and the filter are both right.
    ⚠ This test pins the SIGN and ORDERING, not the cents — the book grows."""
    c = rd.connect(LIVE)
    e = rd.clean_entries(c, "entry_source='manual'")
    b: dict[str, list] = {}
    for r in e:
        h = r["held_min"]
        if h is None:
            continue
        k = "short" if h < 15 else "mid" if h < 60 else "target" if h < 240 else "over"
        a = b.setdefault(k, [0, 0.0])
        a[0] += 1
        a[1] += r["pnl_usd"]
    per = {k: v[1] / v[0] for k, v in b.items()}
    assert per["short"] < 0, f"under-15min must be negative, got {per['short']:+.2f}"
    assert per["mid"] > 0 and per["target"] > 0, "the 15min-4h window must be positive"
    assert per["target"] > per["mid"], "1-4h must beat 15-60min"
    assert per["over"] < per["short"], "over-4h must be the worst cell of all"
    assert b["target"][0] >= 25, f"n={b['target'][0]} in the target cell — too thin to pin"
