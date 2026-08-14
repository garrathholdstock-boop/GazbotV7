#!/usr/bin/env python3
"""Reconcile the trade ledger against the venue execution record.

    PYTHONPATH=src .venv/bin/python scripts/book_vs_fills.py [--days 14] [--json]

Reads only. Prints one line per (desk, day) with a verdict, and exits non-zero if any UNEXPLAINED
divergence is found — so it can be a systemd/CI gate as well as something you run by hand.

★ Flagged rows (`data_quality IS NOT NULL`) are READ, not skipped. They are flagged, never deleted,
so their executions are still in `fills` — measuring only the reported P&L against ALL fills would
manufacture a divergence exactly equal to the flagged amount. The comparison is our FULL record
(reported + flagged) against the venue; the reported figure is shown separately so the two are never
confused. See [[trade-data-quality-flag]].
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7.bookrecon import reconcile  # noqa: E402

DB = os.environ.get("GAZBOT_DB", "/home/alphabot/gazbot7/data/gazbot7.db")

GLYPH = {"OK": "✓", "KNOWN": "§", "DIVERGENT": "✗", "NO_FILLS": "?", "OPEN_POSITION": "~"}


def load(db: str, days: int):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        trades = c.execute(
            "SELECT date(closed_at), gate, pnl_usd, data_quality FROM trades "
            "WHERE closed_at >= date('now', ?)",
            (f"-{days} day",),
        ).fetchall()
        fills = c.execute(
            "SELECT date(exec_time), order_id, side, qty, price FROM fills "
            "WHERE exec_time >= date('now', ?)",
            (f"-{days} day",),
        ).fetchall()
        return trades, fills
    finally:
        c.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    verdicts = reconcile(*load(a.db, a.days))

    if a.json:
        print(json.dumps([{
            "day": v.day, "desk": v.desk, "status": v.status, "booked": v.booked,
            "venue": v.venue, "divergence": v.divergence, "detail": v.detail, "note": v.note,
        } for v in verdicts], indent=1))
    else:
        print(f"  BOOK vs FILLS — last {a.days}d  ({a.db})")
        print(f"  {'day':<12}{'desk':<12}{'booked':>10}{'venue':>10}{'diff':>9}  verdict")
        for v in verdicts:
            ven = f"{v.venue:>10,.2f}" if v.venue is not None else f"{'—':>10}"
            dif = f"{v.divergence:>+9,.2f}" if v.divergence is not None else f"{'—':>9}"
            print(f"  {GLYPH.get(v.status,'?')} {v.day:<10}{v.desk:<12}{v.booked:>10,.2f}{ven}{dif}"
                  f"  {v.status}")
        faults = [v for v in verdicts if v.is_fault]
        unver = [v for v in verdicts if v.is_unverifiable]
        print()
        for v in faults + unver:
            print(f"  {GLYPH.get(v.status,'?')} {v.day} {v.desk}: {v.detail}")
            if v.note:
                print(f"      {v.note}")
        if not faults:
            print(f"  no unexplained divergence."
                  f"{f' ({len(unver)} desk-day(s) UNVERIFIABLE — not the same as clean)' if unver else ''}")

    return 1 if any(v.is_fault for v in verdicts) else 0


if __name__ == "__main__":
    sys.exit(main())
