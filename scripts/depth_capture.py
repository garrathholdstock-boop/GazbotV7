#!/usr/bin/env python3
"""GAZBOT V7 L2 ORDER-BOOK DEPTH CAPTURE — 10 levels both sides, MNQ/MES/MGC/M2K.

★ WHY THIS MOVED INTO V7 (operator, 2026-08-04: "move the book capture into v7 so we can use it").
This capture ran for three weeks as `alphabot-depth-capture.service` inside the RETIRED alphabot2 V5
tree, on its own IBKR clientId, tagged "observe-only R&D", writing to alphabot2/data/depth.db. That
placement caused two concrete failures:

  1. I told the operator we did not persist the L2 book AT ALL. We had 4.2M MNQ snapshots of it. The
     data was invisible because it lived in a tree this repo's own CLAUDE.md says never to probe.
  2. Nothing swept it. A capture no sweep watches can die silently; the desk would not have noticed,
     and the 20-day history that any book study depends on would have quietly stopped growing.

It is now a first-class V7 service: gazbot7 naming, gazbot7.slice, V7 data directory, and covered by
scripts/sweep.py like every other capture. Same isolation guarantees as before — its OWN clientId,
read-only IBKR connection, its own database. It cannot affect pricing, orders or exits.

★ ONE BEHAVIOUR CHANGE FROM THE V5 VERSION: FLUSH_S 5.0 -> 1.0.
The V5 version batched writes every 5 seconds, so a LIVE read of the DB was up to 5s behind reality by
design. That was harmless when the book was only ever read offline for backtests. It is not harmless
now: cl_sims.book_snapshot() reads this table at signal time to attach the book to a verdict, and a
5-second-old book describes a market that has already moved. 1s costs ~4 extra commits/sec on a table
doing ~15 rows/sec — negligible — and cuts worst-case staleness by 5x. Override with DEPTH_FLUSH_S.

Dedup is unchanged: an unchanged book is not re-written, so a gap in ts_ms can mean either "nothing
arrived yet" or "the book did not change". Readers must treat snapshot age as information, not assume
the newest row is current — book_snapshot() carries age_ms through for exactly this reason.

Run: .venv/bin/python scripts/depth_capture.py   (systemd: gazbot7-depth-capture.service)
"""
from __future__ import annotations

import os
import signal
import sqlite3
import sys
import time

from ib_async import IB, ContFuture

# ★ V7 PATH. The 20 days of V5 history was MOVED (not copied) to this location during the port, so
# this file is continuous with everything captured since 2026-07-15 — no gap, no duplicate 2.4GB.
DEPTH_DB = os.environ.get("DEPTH_DB", "/home/alphabot/gazbot7/data/depth.db")
IBKR_HOST = os.environ.get("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.environ.get("IBKR_PORT", "4002"))
# dedicated clientId — NOT broker(0)/MD/probe(99). Kept at 97: it is proven and already isolated.
# ⚠ THE OLD V5 SERVICE MUST BE STOPPED AND DISABLED BEFORE THIS RUNS. Two processes on clientId 97
# fight for the same IBKR slot and one gets kicked; the port procedure stops+disables the old unit.
CLIENT_ID = int(os.environ.get("DEPTH_CLIENT_ID", "97"))
# 2026-07-10 entitlement probe (carried over): MNQ/MES/MGC/M2K subscribe — CME L2 covers M2K;
# MYM(CBOT)/MCL(NYMEX) return Error 354 "not subscribed". Add those only if CBOT/NYMEX L2 is bought.
SYMBOLS = [(s.strip().split(":")[0], s.strip().split(":")[1])
           for s in os.environ.get("DEPTH_SYMBOLS", "MNQ:CME,MES:CME,MGC:COMEX,M2K:CME").split(",")
           if s.strip()]
LEVELS = 10             # CME standard depth on our entitlement; a depletion BEHIND the top-5 is the
                        # "vacuum" tell a top-of-book feed cannot see. numRows tracks this.
SNAP_S = float(os.environ.get("DEPTH_SNAP_S", "0.25"))    # sampling cadence
FLUSH_S = float(os.environ.get("DEPTH_FLUSH_S", "1.0"))   # see the FLUSH_S note in the docstring
RETENTION_DAYS = int(os.environ.get("DEPTH_RETENTION_DAYS", "20"))
PRUNE_EVERY_S = 3600.0

_COLS = ["symbol", "ts_ms"] + \
        [f"{sd}{i}{f}" for i in range(1, LEVELS + 1) for sd in ("bid", "ask") for f in ("p", "s")] + \
        ["imbalance"]


def log(m: str) -> None:
    print(f"depth_capture: {m}", flush=True)


def ensure_db() -> sqlite3.Connection:
    con = sqlite3.connect(DEPTH_DB, timeout=10.0)
    con.execute("PRAGMA journal_mode=WAL")
    coldefs = ["symbol TEXT NOT NULL", "ts_ms INTEGER NOT NULL"] + \
              [f"{c} REAL" for c in _COLS[2:]]
    con.execute(f"CREATE TABLE IF NOT EXISTS depth_snap ({','.join(coldefs)})")
    con.execute("CREATE INDEX IF NOT EXISTS ix_depth_sym_ts ON depth_snap(symbol, ts_ms)")
    # Additive migration: when LEVELS grows, add the new columns so old rows keep NULL for the deeper
    # levels and new rows fill all of them. Named INSERT makes column order irrelevant.
    existing = {r[1] for r in con.execute("PRAGMA table_info(depth_snap)")}
    for c in _COLS:
        if c not in existing:
            con.execute(f"ALTER TABLE depth_snap ADD COLUMN {c} REAL")
            log(f"migrated: added column {c}")
    con.commit()
    return con


def snapshot(ticker) -> list | None:
    """Top-LEVELS book as a flat row [b1p,b1s,a1p,a1s,...] + imbalance; None if no book yet."""
    bids = ticker.domBids or []
    asks = ticker.domAsks or []
    if not bids and not asks:
        return None
    row = []
    bsz = asz = 0.0
    for i in range(LEVELS):
        b = bids[i] if i < len(bids) else None
        a = asks[i] if i < len(asks) else None
        row += [getattr(b, "price", None), getattr(b, "size", None),
                getattr(a, "price", None), getattr(a, "size", None)]
        bsz += getattr(b, "size", 0.0) or 0.0
        asz += getattr(a, "size", 0.0) or 0.0
    imb = (bsz - asz) / (bsz + asz) if (bsz + asz) > 0 else None
    row.append(imb)
    return row


_running = True


def _stop(*_):
    global _running
    _running = False


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


def main() -> None:
    con = ensure_db()
    log(f"db={DEPTH_DB} levels={LEVELS} snap={SNAP_S}s flush={FLUSH_S}s retain={RETENTION_DAYS}d")
    ib = IB()
    tickers: dict[str, object] = {}

    def connect_and_subscribe():
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=CLIENT_ID, timeout=15, readonly=True)
        log(f"connected {IBKR_HOST}:{IBKR_PORT} clientId={CLIENT_ID}")
        tickers.clear()
        for sym, exch in SYMBOLS:
            det = ib.reqContractDetails(ContFuture(sym, exch))
            if not det:
                log(f"WARN could not resolve {sym} ({exch}) — skipping")
                continue
            c = det[0].contract
            t = ib.reqMktDepth(c, numRows=LEVELS, isSmartDepth=False)
            tickers[sym] = t
            log(f"reqMktDepth {sym} {c.localSymbol} ({exch})")

    try:
        connect_and_subscribe()
    except Exception as e:
        log(f"initial connect FAILED: {e}")
        sys.exit(1)

    buf: list[tuple] = []
    last_row: dict[str, list] = {}
    last_flush = last_prune = time.time()
    ph = ",".join("?" * len(_COLS))

    while _running:
        try:
            ib.sleep(SNAP_S)  # runs the event loop → depth updates arrive
            if not ib.isConnected():
                log("disconnected — reconnecting…")
                try:
                    ib.disconnect()
                except Exception:
                    pass
                time.sleep(3)
                connect_and_subscribe()
                continue
            now_ms = int(time.time() * 1000)
            for sym, t in tickers.items():
                row = snapshot(t)
                if row is None:
                    continue
                if last_row.get(sym) == row:   # dedup static book
                    continue
                last_row[sym] = row
                buf.append((sym, now_ms, *row))
            now = time.time()
            if buf and (now - last_flush) >= FLUSH_S:
                con.executemany(f"INSERT INTO depth_snap ({','.join(_COLS)}) VALUES ({ph})", buf)
                con.commit()
                buf.clear()
                last_flush = now
            if (now - last_prune) >= PRUNE_EVERY_S:
                cutoff = int((now - RETENTION_DAYS * 86400) * 1000)
                con.execute("DELETE FROM depth_snap WHERE ts_ms < ?", (cutoff,))
                con.commit()
                last_prune = now
        except Exception as e:
            log(f"loop error: {e}")
            time.sleep(2)

    # graceful shutdown: final flush
    if buf:
        con.executemany(f"INSERT INTO depth_snap ({','.join(_COLS)}) VALUES ({ph})", buf)
        con.commit()
    log(f"shutting down (flushed {len(buf)} buffered)")
    try:
        ib.disconnect()
    except Exception:
        pass
    con.close()


if __name__ == "__main__":
    main()
