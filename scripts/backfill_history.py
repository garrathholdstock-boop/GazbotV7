#!/usr/bin/env python3
"""BACKFILL — pull every bar of history IBKR will serve for our instruments, into the lake.

Operator, 2026-08-18: "why arent we pulling all this history. we dont need to wait a year"— correct,
for BARS. Ticks, quotes and L2 depth cannot be bought retroactively at any price and remain
accumulate-only; bars can be bootstrapped and were not being.

★ MEASURED CEILING ON THIS ACCOUNT (2026-08-18, not from documentation):
    CONTFUT daily   asking 15Y and asking 5Y both return the SAME 482 bars from 2024-09-23.
                    The request size is not the limit — the entitlement is. ~23 months.
    expired MNQ     reqContractDetails lists 8 contracts, earliest expiry 2025-12-19.
    expired MGC     17 contracts, earliest 2025-10-29.
    older           will not resolve, by month OR by exact expiry date.
IBKR documents 2 years past expiry for futures; we see well under that, most likely because
DUQ191770 is a PAPER account. That is an entitlements question, not an engineering one, and no
amount of runtime changes it — which is why this job is BOUNDED and does not need a whole night.

★ TWO SOURCES, because they reach different depths:
    CONTFUT   long continuous series, no endDateTime (it is REJECTED — Error 10339). Deepest daily.
    per-contract  every listed expiry with includeExpired=True. Deepest INTRADAY.

⚠ includeExpired=True IS MANDATORY or expired contracts silently fail to resolve, and
  qualifyContractsAsync can return [None] — `if not q` is False for that, so the None reaches the
  next call as an AttributeError that reads like "IBKR has no data". Both handled here.
⚠ ONE REQUEST PER DAY for minute bars. A too-large durationStr returns a SHORT result rather than an
  error — silent truncation that would read as thin days rather than as a broken pull.
⚠ Shares the LIVE gateway. Preflight refuses unless nothing is open. The intended window is the
  00:00-07:00 UTC Asia block, where the desk is already config-blocked from new entries, so the pull
  costs no trading opportunity at all.
"""
from __future__ import annotations
import argparse
import asyncio
import datetime as dt
import json
import os
import sys
import time

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/src")
OUT = f"{GB}/data/backfill"
CLIENT_ID = 81
PACE_S = 10.5                       # 60 historical requests / 10 min is the hard limit

SYMBOLS = {"MNQ": "CME", "MGC": "COMEX"}
# (barSize, durationStr, one-request-per-day?) — coarse first, so a truncated run still leaves the
# long series on disk. Minute bars are pulled a day at a time; they cannot be trusted in bulk.
LADDER = [("1 day", "15 Y", False), ("1 hour", "1 Y", False),
          ("5 mins", "1 M", False), ("1 min", "1 D", True)]


def log(m: str) -> None:
    print(f"{dt.datetime.now(dt.UTC):%H:%M:%S} {m}", flush=True)


def preflight(force: bool = False) -> tuple[bool, str]:
    """Nothing may be open. The Asia block is the intended window; the halt is also fine."""
    try:
        h = json.load(open(f"{GB}/data/core_health.json"))
        flat = bool(h.get("flat", False))
    except Exception as e:
        log(f"ABORT: cannot read core_health.json ({e})")
        return (False, "error")
    try:
        r = json.load(open(f"{GB}/data/day_rider_state.json"))
        rider_open = bool(r.get("entered")) and not bool(r.get("closed"))
    except Exception:
        rider_open = False
    log(f"preflight: tournament_flat={flat} rider_open={rider_open}")
    if not force and (rider_open or not flat):
        log("DECLINED: a desk holds a position — not competing for the gateway")
        return (False, "declined")
    return (True, "ok")


def _write(rows, path) -> int:
    """DuckDB COPY + read-back count. No pyarrow on this box, and tape_mirror verifies its writes."""
    import duckdb
    import pandas as pd
    df = pd.DataFrame(sorted(set(rows)), columns=["ts", "open", "high", "low", "close", "volume"])
    c = duckdb.connect()
    c.register("t", df)
    c.execute(f"COPY (SELECT * FROM t ORDER BY ts) TO '{path}' (FORMAT parquet, COMPRESSION zstd)")
    n = c.execute(f"SELECT count(*) FROM read_parquet('{path}')").fetchone()[0]
    c.close()
    return int(n)


def desk_busy() -> bool:
    """Is any desk holding a position RIGHT NOW?

    ⚠ A start-only preflight is not enough. This job runs for hours and spans the 22:00 reopen, so
    the desk can take a position long after the check passed. Historical requests do not place
    orders, but a pacing violation throttles the shared gateway — and the gateway is how the desk
    receives market data. So the pull YIELDS while anything is open and resumes when flat, rather
    than competing. Fail-safe: unreadable state counts as BUSY.
    """
    try:
        if not json.load(open(f"{GB}/data/core_health.json")).get("flat", False):
            return True
        r = json.load(open(f"{GB}/data/day_rider_state.json"))
        return bool(r.get("entered")) and not bool(r.get("closed"))
    except Exception:
        return True


async def yield_while_busy(deadline: float) -> bool:
    """Block until the desk is flat again. Returns False if the deadline passed while waiting."""
    waited = 0
    while desk_busy():
        if time.time() > deadline:
            return False
        if waited % 300 == 0:
            log("  desk holds a position — pausing the pull (it will resume when flat)")
        await asyncio.sleep(30)
        waited += 30
    if waited:
        log(f"  desk flat again after {waited//60}min — resuming")
    return True


async def _hist(ib, con, *, end, dur, size):
    """One historical request, with a hard per-request timeout so a slow ask cannot eat the budget."""
    return await asyncio.wait_for(
        ib.reqHistoricalDataAsync(con, endDateTime=end, durationStr=dur, barSizeSetting=size,
                                  whatToShow="TRADES", useRTH=False, formatDate=2),
        timeout=90)


def _rows(bars):
    return [(int(b.date.timestamp()), float(b.open), float(b.high),
             float(b.low), float(b.close), float(b.volume)) for b in bars]


async def pull_contfut(ib, sym, exch, deadline):
    """The long continuous series. endDateTime must be EMPTY — CONTFUT rejects it (Error 10339)."""
    from ib_async import ContFuture
    q = [c for c in (await ib.qualifyContractsAsync(ContFuture(sym, exch)) or []) if c is not None]
    if not q:
        log(f"  {sym} CONTFUT: will not qualify")
        return
    for size, dur, per_day in LADDER:
        if per_day or time.time() > deadline:
            continue                       # minute bars come from the dated contracts, not here
        path = f"{OUT}/{sym}_CONTFUT_{size.replace(' ', '')}.parquet"
        if os.path.exists(path):
            continue
        if not await yield_while_busy(deadline):
            return
        try:
            bars = await _hist(ib, q[0], end="", dur=dur, size=size)
        except asyncio.TimeoutError:
            log(f"  {sym} CONTFUT {size:<7} timeout >90s — skipped")
            await asyncio.sleep(PACE_S)
            continue
        except Exception as e:
            log(f"  {sym} CONTFUT {size:<7} {str(e)[:70]}")
            await asyncio.sleep(PACE_S)
            continue
        if bars:
            n = _write(_rows(bars), path)
            log(f"  {sym} CONTFUT {size:<7} {n:6d} bars  from {bars[0].date}")
        await asyncio.sleep(PACE_S)


async def pull_contracts(ib, sym, exch, deadline):
    """Every listed expiry, deepest-intraday first. Resumable: an existing parquet is skipped."""
    from ib_async import Future
    probe = Future(symbol=sym, exchange=exch, currency="USD", includeExpired=True)
    try:
        cds = await ib.reqContractDetailsAsync(probe)
    except Exception as e:
        log(f"  {sym}: contract-details failed {str(e)[:70]}")
        return
    expiries = sorted({c.contract.lastTradeDateOrContractMonth for c in cds})
    log(f"  {sym}: IBKR lists {len(expiries)} contracts, {expiries[0]} .. {expiries[-1]}")
    today = dt.date.today()
    # ★2026-08-18 the FRONT month is the nearest unexpired contract. Only it earns the expensive
    # per-day minute walk among the actives: a far-dated contract has barely traded, so walking 95
    # days of it costs ~12 minutes of budget to collect almost nothing — and four of them would burn
    # ~48 minutes before the contracts that matter. They still get the cheap bulk requests.
    future = [e for e in expiries
              if dt.date(int(e[:4]), int(e[4:6]), int(e[6:8]) if len(e) >= 8 else 15) > today]
    front = future[0] if future else None
    for ex in expiries:
        exp = dt.date(int(ex[:4]), int(ex[4:6]), int(ex[6:8]) if len(ex) >= 8 else 15)
        # ★★★2026-08-18 THE ACTIVE CONTRACT IS PULLED TOO, ending NOW. A first cut skipped every
        # unexpired contract on the reasoning that "the live feed already captures it" — but the
        # live feed only started 2026-07-15, while the current front month has traded since ~March.
        # That silently discarded ~4 months of the single most relevant contract. An unexpired
        # contract simply ends at `now` instead of at its expiry; far-dated ones return little and
        # cost one request each, which is the right price for not having to special-case the roll.
        active = exp > today
        end_at = "" if active else dt.datetime(exp.year, exp.month, exp.day, 22, 0,
                                               tzinfo=dt.UTC).strftime("%Y%m%d-%H:%M:%S")
        for size, dur, per_day in LADDER:
            if time.time() > deadline:
                log("  deadline reached — stopping cleanly, resumable")
                return
            path = f"{OUT}/{sym}_{ex}_{size.replace(' ', '')}.parquet"
            if os.path.exists(path):
                continue
            if not await yield_while_busy(deadline):
                log("  deadline reached while yielding — stopping cleanly")
                return
            con = Future(symbol=sym, exchange=exch, currency="USD",
                         lastTradeDateOrContractMonth=ex, includeExpired=True)
            q = [c for c in (await ib.qualifyContractsAsync(con) or []) if c is not None]
            if not q:
                log(f"  {sym} {ex}: will not resolve — beyond this account's entitlement")
                break
            rows = []
            if per_day and active and ex != front:
                continue                        # far-dated: not worth a 95-day minute walk
            if per_day:
                last = min(exp, today)          # an active contract walks only up to TODAY
                d = last - dt.timedelta(days=95)
                while d <= last and time.time() <= deadline:
                    if d.weekday() < 5:
                        try:
                            b = await _hist(ib, q[0], dur="1 D", size=size,
                                            end=dt.datetime(d.year, d.month, d.day, 22, 0,
                                                            tzinfo=dt.UTC).strftime("%Y%m%d-%H:%M:%S"))
                            rows += _rows(b)
                        except Exception:
                            pass
                        await asyncio.sleep(PACE_S)
                    d += dt.timedelta(days=1)
            else:
                try:
                    b = await _hist(ib, q[0], dur=dur, size=size, end=end_at)
                    rows += _rows(b)
                except Exception as e:
                    log(f"  {sym} {ex} {size:<7} {str(e)[:60]}")
                await asyncio.sleep(PACE_S)
            if rows:
                n = _write(rows, path)
                span = (dt.datetime.fromtimestamp(min(r[0] for r in rows), dt.UTC),
                        dt.datetime.fromtimestamp(max(r[0] for r in rows), dt.UTC))
                log(f"  {sym} {ex} {size:<7} {n:6d} bars  {span[0]:%Y-%m-%d}..{span[1]:%Y-%m-%d}")


async def run(symbols, minutes, force):
    from ib_async import IB, util
    util.logToConsole(50)
    deadline = time.time() + minutes * 60
    ib = IB()
    await ib.connectAsync("127.0.0.1", 4002, clientId=CLIENT_ID, timeout=25, readonly=True)
    log(f"connected readonly clientId={CLIENT_ID}, budget {minutes}min")
    try:
        for sym in symbols:
            exch = SYMBOLS.get(sym, "CME")
            log(f"--- {sym} ({exch}) ---")
            await pull_contfut(ib, sym, exch, deadline)
            await pull_contracts(ib, sym, exch, deadline)
    finally:
        ib.disconnect()
    files = [f for f in os.listdir(OUT) if f.endswith(".parquet")]
    log(f"done: {len(files)} parquet files in {OUT}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="MNQ,MGC")
    ap.add_argument("--minutes", type=int, default=360)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    ok, kind = preflight(a.force)
    if not ok:
        sys.exit(0 if kind == "declined" else 1)
    asyncio.run(run([s.strip() for s in a.symbols.split(",")], a.minutes, a.force))


if __name__ == "__main__":
    main()
