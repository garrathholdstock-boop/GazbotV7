#!/usr/bin/env python3
"""Quarantine MD_STREAM-corrupted rows out of shadow.db.

★ WHY THIS EXISTS (2026-08-09). The 2026-08-04 MD_STREAM incident — `md` publishes one bar per
captured symbol on ONE stream tagged body["symbol"], and consumers that folded without checking the
tag ingested MGC bars as MNQ — was fixed at the producer, pinned by tests/test_md_symbol_filter.py,
and the two poisoned LIVE trades were flagged in gazbot7.db::trades with
`data_quality = 'EXCLUDE:md_stream_atr_corruption_20260804'`.

**shadow.db was never cleaned.** It had no data_quality column at all, so nine simulated trades with
gold prices and/or 100x ATRs sat in the shadow book, and the ROUTER IS EXPLICITLY TOLD TO ARM WHEN A
GATE'S SHADOW FAMILY IS GREEN (router_tick_durable.py, the shadow-board arming clause). One of them
is 29% of thrust_short_raw's entire net — the series behind abs_veto_short's arm-by-default case.

★ WHY QUARANTINE (move) RATHER THAN FLAG (mark in place). 41 scripts read shadow_trades and exactly
ONE mentions data_quality. A flag that 40 readers ignore is not a fix — it is the same shape as the
`exit_overrides_uncommitted` flag that sweep.py stamped for four days while nothing consumed it.
Moving the rows makes every reader correct WITHOUT touching 41 files, and the audit trail is
preserved in-database rather than deleted. The data_quality column is added to shadow_trades anyway
so the convention matches trades and a future incident can be marked in place if that is preferable.

★ THE DETECTOR IS ATR, NOT PRICE. An entry_price scan finds only 7 of the 9: ids 7104/7105 carry a
correct MNQ price (29915.5) with a corrupted ATR of 25809.5, because the fold poisoned the ATR
feature while the price came from the right symbol. ATR is what MD_STREAM actually corrupted, so ATR
is the right detector. The cut at 200pt is safe by a wide margin: true MNQ entry_atr tops out at
62.4 in this table, so there is a 3x gap between the highest real value and the lowest poisoned one.

Idempotent — re-running finds nothing to do.

  PYTHONPATH=src .venv/bin/python scripts/quarantine_shadow_md_corruption.py [--apply]

Without --apply it reports what it would move and changes nothing.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone

DB = "/home/alphabot/gazbot7/data/shadow.db"
REASON = "EXCLUDE:md_stream_atr_corruption_20260804"
ATR_MAX = 200.0          # true MNQ entry_atr maxes at 62.4 here; poisoned rows start at 1846.5


def _cols(cx: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in cx.execute(f"PRAGMA table_info({table})")]


def main(apply: bool) -> int:
    cx = sqlite3.connect(DB)
    cx.row_factory = sqlite3.Row

    bad = list(cx.execute(
        "SELECT id, strategy, side, entry_ts, entry_price, entry_atr FROM shadow_trades "
        "WHERE entry_atr > ? ORDER BY entry_ts, id", (ATR_MAX,)))
    if not bad:
        print("quarantine_shadow: nothing to do — no rows above the ATR cut")
        return 0

    ids = [r["id"] for r in bad]
    pnl = cx.execute(
        f"SELECT COUNT(*), ROUND(COALESCE(SUM(real_pnl),0),2) FROM shadow_real "
        f"WHERE trade_id IN ({','.join('?'*len(ids))})", ids).fetchone()
    print(f"quarantine_shadow: {len(bad)} corrupted shadow_trades rows "
          f"({pnl[0]} scored, net real_pnl {pnl[1]:+})")
    for r in bad:
        ts = datetime.fromtimestamp(r["entry_ts"], timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        print(f"    id={r['id']:<6} {r['strategy']:<20} {r['side']:<6} {ts} "
              f"px={r['entry_price']:<10} atr={r['entry_atr']:.1f}")

    strategies = sorted({r["strategy"] for r in bad})
    print(f"  strategies affected ({len(strategies)}): {', '.join(strategies)}")

    if not apply:
        print("\n  DRY RUN — pass --apply to move them.")
        return 0

    backup = f"{DB}.pre-mdquarantine.{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    shutil.copy(DB, backup)
    print(f"\n  backup: {backup}")

    try:
        cx.execute("BEGIN IMMEDIATE")
        if "data_quality" not in _cols(cx, "shadow_trades"):
            cx.execute("ALTER TABLE shadow_trades ADD COLUMN data_quality TEXT")
            print("  + shadow_trades.data_quality column added (matches trades convention)")

        tcols = [c for c in _cols(cx, "shadow_trades") if c != "data_quality"]
        rcols = _cols(cx, "shadow_real")
        cx.execute(
            "CREATE TABLE IF NOT EXISTS shadow_trades_quarantine AS "
            "SELECT *, CAST(NULL AS TEXT) AS data_quality, CAST(NULL AS TEXT) AS quarantined_at "
            "FROM shadow_trades WHERE 0")
        cx.execute(
            "CREATE TABLE IF NOT EXISTS shadow_real_quarantine AS "
            "SELECT *, CAST(NULL AS TEXT) AS quarantined_at FROM shadow_real WHERE 0")

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        marks = ",".join("?" * len(ids))
        cx.execute(
            f"INSERT INTO shadow_trades_quarantine ({','.join(tcols)}, data_quality, quarantined_at) "
            f"SELECT {','.join(tcols)}, ?, ? FROM shadow_trades WHERE id IN ({marks})",
            [REASON, now, *ids])
        cx.execute(
            f"INSERT INTO shadow_real_quarantine ({','.join(rcols)}, quarantined_at) "
            f"SELECT {','.join(rcols)}, ? FROM shadow_real WHERE trade_id IN ({marks})",
            [now, *ids])
        moved_t = cx.execute(f"DELETE FROM shadow_trades WHERE id IN ({marks})", ids).rowcount
        moved_r = cx.execute(f"DELETE FROM shadow_real WHERE trade_id IN ({marks})", ids).rowcount
        cx.commit()
    except Exception:
        cx.rollback()
        raise

    left = cx.execute("SELECT COUNT(*) FROM shadow_trades WHERE entry_atr > ?", (ATR_MAX,)).fetchone()[0]
    orphan = cx.execute(
        "SELECT COUNT(*) FROM shadow_real r LEFT JOIN shadow_trades t ON t.id=r.trade_id "
        "WHERE t.id IS NULL").fetchone()[0]
    tot_t = cx.execute("SELECT COUNT(*) FROM shadow_trades").fetchone()[0]
    tot_r = cx.execute("SELECT COUNT(*) FROM shadow_real").fetchone()[0]
    print(f"  moved: {moved_t} shadow_trades, {moved_r} shadow_real")
    print(f"  remaining above cut: {left} (must be 0)")
    print(f"  orphaned shadow_real: {orphan} (must be 0)")
    print(f"  live table now: {tot_t} trades / {tot_r} scored")
    return 0 if (left == 0 and orphan == 0 and tot_t == tot_r) else 1


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
