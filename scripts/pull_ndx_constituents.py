#!/usr/bin/env python3
"""Pull the NDX megacap constituents from IBKR so BREADTH can be MEASURED, not assumed.

Operator: "pull all the data from ibkr to be able to tell me if a run is broad or not. and backtest
it well to see if true."

★★ THE QUESTION. NQ *is* the weighted sum of these names, so they cannot "lead" it — that is
arithmetic, not an empirical claim. What is NOT arithmetic is BREADTH: whether a move is carried by
one name or by all of them. "NQ +40 on NVDA alone" and "NQ +40 with everything participating" are
genuinely different tapes, and only the second is visible here.

⚠⚠ PACED DELIBERATELY. IBKR limits historical requests (~60 per 10 min) and a violation resets the
connection — which is the leading hypothesis for the CLOSE-WAIT leak that has wedged this gateway
on ten of the last seventeen days. This job is the LAST thing that should cause one, so it sleeps
between requests and keeps one connection rather than reconnecting per symbol.
⚠ It writes parquet-free CSV into data/ndx/ and NEVER touches capture.db — the desk's tape stays
the desk's tape.
"""
from __future__ import annotations

import asyncio
import csv
import datetime as dt
import os
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

OUT = "/home/alphabot/gazbot7/data/ndx"
CLIENT_ID = 15                      # 0 core · 2 md · 4 rider · 5 wd · 6 eod · 8 checks · 97 depth
PACE_S = 11.0                       # ~5.5 req/min — comfortably inside IBKR's ~60/10min
NAMES = ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AVGO", "TSLA", "NFLX", "COST"]


async def main() -> int:
    from ib_async import IB, Stock
    os.makedirs(OUT, exist_ok=True)
    ib = IB()
    await ib.connectAsync("127.0.0.1", 4002, clientId=CLIENT_ID, readonly=True, timeout=25)
    ib.reqMarketDataType(3)
    try:
        for i, sym in enumerate(NAMES):
            for dur, size, tag in (("30 D", "5 mins", "5min"), ("1 Y", "1 day", "1day")):
                path = f"{OUT}/{sym}_{tag}.csv"
                try:
                    q = await ib.qualifyContractsAsync(Stock(sym, "SMART", "USD"))
                    if not q:
                        print(f"  {sym} {tag}: NOT QUALIFIED", flush=True)
                        continue
                    bars = await ib.reqHistoricalDataAsync(
                        q[0], "", durationStr=dur, barSizeSetting=size,
                        whatToShow="TRADES", useRTH=True, formatDate=2)   # 2 = UTC epoch
                    with open(path, "w", newline="") as fh:
                        w = csv.writer(fh)
                        w.writerow(["ts", "open", "high", "low", "close", "volume"])
                        for b in bars:
                            ts = int(b.date.timestamp()) if hasattr(b.date, "timestamp") else b.date
                            w.writerow([ts, b.open, b.high, b.low, b.close, b.volume])
                    print(f"  {sym:<6} {tag:<5} {len(bars):>5} bars -> {path}", flush=True)
                except Exception as e:
                    print(f"  {sym:<6} {tag:<5} ERR {type(e).__name__}: {str(e)[:60]}", flush=True)
                await asyncio.sleep(PACE_S)     # ⚠ the pacing guard — do not remove
    finally:
        ib.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
