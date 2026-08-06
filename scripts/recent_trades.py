#!/usr/bin/env python3
"""Recent-trades read for the router scan — the LIVE bleeding check.

The aggregate per-gate P&L (desk_view) hides bleeding: a big banked morning tail
can mask a scalp lot that's getting stopped out over and over in chop. This shows
the actual recent fills + exit_reason (a wall of STOP = a gate getting chopped up)
and a per-gate last-N-min tally, so "is this gate bleeding RIGHT NOW" is obvious.

Read-only. Usage: PYTHONPATH=src .venv/bin/python scripts/recent_trades.py [n_recent] [window_min]
"""
import sqlite3
import sys
from datetime import datetime, timezone

n_recent = int(sys.argv[1]) if len(sys.argv) > 1 else 15
window_min = int(sys.argv[2]) if len(sys.argv) > 2 else 60

c = sqlite3.connect("data/gazbot7.db")
c.row_factory = sqlite3.Row

# ★2026-08-06 `data_quality IS NULL` on BOTH queries — this file is the router's wall-of-STOP check,
# so an EXCLUDED row here corrupts a live bench/arm decision, not just a report. See desk_view.py for
# the 08-06 day-rider cross-desk flatten that booked two fictitious TARGET wins.
rows = c.execute(
    "SELECT gate, side, pnl_usd, exit_reason, closed_at FROM trades "
    "WHERE closed_at IS NOT NULL AND data_quality IS NULL "
    "ORDER BY closed_at DESC LIMIT ?", (n_recent,)
).fetchall()

print(f"RECENT {n_recent} CLOSED TRADES (newest first) — exit_reason wall of STOP = bleeding:")
print(f"  {'gate':18} {'side':5} {'pnl':>8} {'exit':12} closed(UTC)")
for r in rows:
    t = (r["closed_at"] or "")[11:19]
    flag = " <" if (r["pnl_usd"] or 0) < 0 else ""
    print(f"  {r['gate']:18} {r['side']:5} {r['pnl_usd']:>8.1f} {str(r['exit_reason'])[:12]:12} {t}{flag}")

cut = datetime.now(timezone.utc).timestamp() - window_min * 60
tally = {}
for r in c.execute(
    "SELECT gate, pnl_usd, exit_reason, closed_at FROM trades "
    "WHERE closed_at IS NOT NULL AND data_quality IS NULL "
    "ORDER BY closed_at DESC LIMIT 120"
).fetchall():
    try:
        ts = datetime.fromisoformat(r["closed_at"]).timestamp()
    except (ValueError, TypeError):
        continue
    if ts < cut:
        continue
    g = r["gate"]
    d = tally.setdefault(g, {"n": 0, "pnl": 0.0, "stops": 0})
    d["n"] += 1
    d["pnl"] += r["pnl_usd"] or 0.0
    if r["exit_reason"] == "STOP":
        d["stops"] += 1

print(f"\nLAST {window_min}min PER GATE (live behaviour — bleeders at top):")
if not tally:
    print("  (no closed trades in window — gates idle/benched)")
for g, d in sorted(tally.items(), key=lambda x: x[1]["pnl"]):
    print(f"  {g:18} {d['n']:2}tr  {d['pnl']:>8.1f}  ({d['stops']}/{d['n']} stopped)")
