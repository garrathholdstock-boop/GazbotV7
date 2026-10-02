"""THE RESEARCH DATA LAYER — entry grouping and fabricated-fill exclusion, as VIEWS.

★★★ PHASE 0 of the autonomous trading loop (docs/SCOPE_RECURSIVE_TRADING_LOOP.md §8). Nothing in
here trades, writes to `trades`, or runs inside the desk. It is read-only and additive.

WHY VIEWS AND NOT COLUMNS. `trades` has 66 consumers and a writer that probes `PRAGMA table_info`.
An ALTER plus a backfill would need every one of them audited (method trap #6 — a right number
beside a wrong one is worse than either alone) and the backfill would go stale the moment a new
trade landed. A view is computed on read, cannot drift from the table, cannot break a consumer that
does not know it exists, and gives ONE definition of "entry" that two surfaces cannot disagree
about.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT PROBLEM THIS SOLVES — both halves are load-bearing and both were found by inspection 2026-10-02
────────────────────────────────────────────────────────────────────────────────────────────────

1. ★★★ `trades` HAS NO ENTRY KEY, so CLAUDE.md's own rule is MECHANICALLY UNOBEYABLE.
   The rule: *"group by ENTRY, not by trade row — the rows are scale-out exits; counting them
   inflates n ~2.5x."* But there is no `entry_id`, no `parent_id`, and `entry_exec_id` is populated
   on only **98 of 1,176 rows**. So every study that has ever grouped these rows has either
   silently counted scale-out legs as independent trades, or hand-rolled its own grouping.
   → `entry_id = symbol|side|opened_at`. Verified: 1,176 rows → 1,071 entries. The >1 groups are
     unambiguous scale-outs (TARGET_100 / TARGET_200 / MANUAL_CLAIM / TRAIL on one entry).
   ⚠ `entry_price` is deliberately NOT in the key. Including it split one real entry
     (2026-07-30T15:52:27 LONG at 28071.50 and 28071.25) whose two prices are ONE TICK apart — a
     split fill of a single entry, not two entries.

2. ★★★ THE PAPER ENGINE FABRICATES FILLS, AND ONLY ONE ROW IN THE BOOK IS FLAGGED FOR IT.
   The IBKR paper engine fills every lot BEYOND THE FIRST at exactly 0.1% of price, adverse,
   rounded to the tick — 21/21 multi-lot rider orders at 0.09897-0.09998%, $2,916.50 over 32
   orders, which is more than the desk's entire booked loss. A `BADFILL:` label was applied to
   **one** row by hand. 367 multi-lot rows exist.
   → `fill_clean` excludes rows whose fill the engine fabricated, BY DATE, because both sides were
     fixed on known days:
       * ENTRIES became marketable limits **2026-09-04** (643d9e2)
       * multi-lot EXITS became marketable limits that escalate to market **2026-09-15** (3734acd)
       * ONE LOT WAS NEVER FABRICATED — deliberately, the fabrication hits only lots beyond the
         first, so a qty=1 fill is clean on any date.

   ⚠⚠ GETTING THIS FILTER WRONG INVERTS THE DESK'S CENTRAL QUESTION. On 2026-10-02 I first filtered
   on `qty == 1` alone, which conflates "clean fill" with "single-lot trade" and discarded ~200
   legitimate rows — a qty=1 exit from a 4-lot entry after 09-04 is perfectly clean. That filter
   said the hold-time gradient did not exist. The date-aware filter keeps 82% of rows and the
   gradient is plainly there. **A filter is a measurement instrument; too aggressive is as wrong as
   too lax.**

   ⚠ Post-fix multi-lot exits still cross the spread — that is REAL slippage and a legitimate cost.
   `fill_clean` excludes FABRICATION, never real execution cost.

   ⚠ THIS IS A PAPER-ACCOUNT FACT. If the desk ever trades a live account the fabrication does not
   apply and `FAB_*` must be revisited. A test asserts these dates are not edited casually.
"""

from __future__ import annotations

import sqlite3

# ── the two dates that define fabrication, from the commits that fixed it ───────────────────────
FAB_ENTRY_FIXED = "2026-09-04"   # 643d9e2 — enter on a marketable limit
FAB_EXIT_FIXED = "2026-09-15"    # 3734acd — multi-lot exits escalate to market

# ── COST ───────────────────────────────────────────────────────────────────────────────────────
# ⚠⚠⚠ RESEARCH PRICES AT $1.50/LOT ROUND-TURN, THE SAME AS PRODUCTION, AND THERE IS NO SECOND
# CONSTANT IN THIS FILE. The first draft declared FEE_RT_RESEARCH = 3.42 "IB-implied" and
# tests/test_fee_constant.py rejected it — correctly.
#
# ★ WHY I WAS WRONG. The $3.42 came from ONE day's book-recon divergence: $153.58 against 80 lots.
# I attributed that gap to commission. But the fee guard records that **every closed trade in the
# ledger carries fees_usd = 1.50, measured over 487 fills** — that is venue truth — and the
# divergence is far better explained by the thing this very module exists to exclude: the paper
# engine's FABRICATED FILL, ~0.1% of price on every lot beyond the first, which is ~$60/lot. Eighty
# lots with lots 2-4 fabricated produces a divergence of exactly that size.
#
# So "FEE_RT understates cost by 128%" was a MISATTRIBUTION of the fabrication, and `fill_clean`
# below already removes it properly. The scope's Phase-0 fee item is withdrawn.
#
# ⚠⚠ AND THE GUARD'S REASONING IS WHY THIS MATTERS MORE THAN IT LOOKS: "an over-charged fee is the
# worst kind of wrong because it NEVER LOOKS WRONG. At 3.3x the true commission a marginal edge
# simply dies, the harness reports a clean NULL, and the finding is recorded as 'no edge there' — a
# false negative nobody re-opens." A research loop built on an inflated cost would spend every night
# manufacturing exactly those. Same family as the $7.50 gold constant that killed a breakeven lead.
#
# ⚠ If a real commission difference is ever established it must come from the MECHANISM (a fee
# schedule, or book-recon across many days with fabrication already excluded), and then it changes
# in ONE place for production and research together — never a research-only fee.
FEE_RT = 1.50

_ENTRY_ID = "t.symbol || '|' || t.side || '|' || t.opened_at"

# ── per-row view: every trade row, with its entry, its hold, and whether its fill is real ───────
V_ROWS = f"""
CREATE VIEW IF NOT EXISTS research_rows AS
WITH ent AS (
    SELECT symbol || '|' || side || '|' || opened_at AS eid, SUM(qty) AS entry_lots
    FROM trades GROUP BY 1
)
SELECT
    t.*,
    {_ENTRY_ID}                                   AS entry_id,
    e.entry_lots                                  AS entry_lots,
    CASE WHEN t.qty > 1 AND t.closed_at < '{FAB_EXIT_FIXED}'  THEN 1 ELSE 0 END AS exit_fabricated,
    CASE WHEN e.entry_lots > 1 AND t.opened_at < '{FAB_ENTRY_FIXED}' THEN 1 ELSE 0 END
                                                  AS entry_fabricated,
    CASE WHEN (t.qty > 1 AND t.closed_at < '{FAB_EXIT_FIXED}')
            OR (e.entry_lots > 1 AND t.opened_at < '{FAB_ENTRY_FIXED}')
         THEN 0 ELSE 1 END                        AS fill_clean,
    (julianday(t.closed_at) - julianday(t.opened_at)) * 1440.0 AS held_min
FROM trades t
JOIN ent e ON e.eid = {_ENTRY_ID}
"""

# ── per-ENTRY view: THE UNIT OF RESEARCH. One row per entry, never per scale-out leg ────────────
# ⚠ `fill_clean` here is MIN() over the entry's rows: an entry is clean only if EVERY leg of it is.
#   A partly-fabricated entry is not half-usable — the memory records that flagging a partly
#   fabricated trade takes the whole row, and the same logic applies to scoring.
# ⚠ `held_min` is measured to the LAST exit, because that is the entry's life. Per-leg holds are in
#   research_rows for exit research, which is a different question.
V_ENTRIES = """
CREATE VIEW IF NOT EXISTS research_entries AS
SELECT
    entry_id,
    symbol,
    side,
    opened_at,
    MIN(entry_price)                              AS entry_price,
    MAX(closed_at)                                AS closed_at,
    SUM(qty)                                      AS lots,
    COUNT(*)                                      AS exit_legs,
    SUM(pnl_usd)                                  AS pnl_usd,
    SUM(fees_usd)                                 AS fees_usd,
    MIN(fill_clean)                               AS fill_clean,
    MAX(exit_fabricated)                          AS any_exit_fabricated,
    MAX(entry_fabricated)                         AS entry_fabricated,
    (julianday(MAX(closed_at)) - julianday(opened_at)) * 1440.0 AS held_min,
    GROUP_CONCAT(DISTINCT exit_reason)            AS exit_reasons,
    MAX(COALESCE(entry_source, ''))               AS entry_source,
    MAX(COALESCE(data_quality, ''))               AS data_quality
FROM research_rows
GROUP BY entry_id, symbol, side, opened_at
"""

VIEWS = (("research_rows", V_ROWS), ("research_entries", V_ENTRIES))


def ensure_views(conn: sqlite3.Connection) -> list[str]:
    """Create the research views if absent. Idempotent, additive, touches no table.

    ⚠ Called by RESEARCH code only — deliberately NOT wired into store.py's schema, so a mistake
    in here can never break the desk's startup path.
    """
    made = []
    for name, ddl in VIEWS:
        conn.execute(ddl)
        made.append(name)
    conn.commit()
    return made


def drop_views(conn: sqlite3.Connection) -> None:
    """Remove them. Used by tests and by a rebuild after a definition change."""
    for name, _ in VIEWS:
        conn.execute(f"DROP VIEW IF EXISTS {name}")
    conn.commit()


def connect(path: str = "data/gazbot7.db", read_only: bool = True) -> sqlite3.Connection:
    """A connection with the views present and `sqlite3.Row` set.

    ⚠ A read-only connection cannot CREATE VIEW, so when read_only is asked for we open writable
    just long enough to define them, then reopen read-only. The views are the only thing ever
    written, and only when missing.
    """
    if read_only:
        w = sqlite3.connect(path)
        try:
            ensure_views(w)
        finally:
            w.close()
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(path)
        ensure_views(conn)
    conn.row_factory = sqlite3.Row
    return conn


# ── the standard research filter, in ONE place so no study can quietly disagree ─────────────────
# ⚠ Excludes: fabricated fills, EXCLUDE:/BADFILL: labelled rows, and rows with no P&L.
#   Does NOT exclude losers, outliers, or anything chosen by looking at outcomes.
CLEAN = ("fill_clean = 1 "
         "AND pnl_usd IS NOT NULL "
         "AND (data_quality IS NULL OR data_quality = '')")


def clean_entries(conn: sqlite3.Connection, extra: str = "") -> list[sqlite3.Row]:
    """Every scoreable ENTRY. The default unit for any study of this book."""
    where = CLEAN + (f" AND {extra}" if extra else "")
    return conn.execute(f"SELECT * FROM research_entries WHERE {where} ORDER BY opened_at").fetchall()
