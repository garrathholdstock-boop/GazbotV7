#!/usr/bin/env python3
"""LIVE BREADTH — is the current run broad? US cash hours only.

★ The frozen definition lives in data/prereg_breadth.json and is NOT re-derived here: share of the
ten NDX megacaps whose price moved the same way as MNQ over the last 8 minutes.

⚠⚠ ONE PERSISTENT CONNECTION, NOT A POLL. The gateway leaks a socket in CLOSE-WAIT under some
condition and has wedged on ten of the last seventeen days; the desk already opens ~5,000
short-lived connections a day. This holds ONE (clientId 16) for the session and lets it idle —
adding churn to diagnose churn would be absurd.
⚠ OUTSIDE 13:30-20:00Z IT REPORTS NOTHING AND SAYS WHY. The constituents are shut; a reading built
from a stale close would be manufactured, and a tile that looks live and is not is this desk's
signature failure.
⚠⚠⚠ IT IS A READING. No gate, no switch, no order path. Pre-registered for 120 legs before anyone
is entitled to an opinion about whether it works.
"""
from __future__ import annotations

import asyncio, datetime as dt, json, os, sqlite3, sys, time
sys.path.insert(0, "/home/alphabot/gazbot7/src")

GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/data/breadth.json"
NAMES = ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AVGO", "TSLA", "NFLX", "COST"]
CLIENT_ID = 16
WINDOW_MIN = 8
US_OPEN, US_CLOSE = dt.time(13, 30), dt.time(20, 0)


def in_us_hours(now=None):
    t = (now or dt.datetime.now(dt.UTC)).time()
    return US_OPEN <= t < US_CLOSE


def mnq_move(mins: int) -> float | None:
    try:
        c = sqlite3.connect(f"{GB}/data/capture.db")
        now = int(time.time())
        r = c.execute("select close from bars where symbol='MNQ' and timeframe='5s' "
                      "and bar_ts<=? order by bar_ts desc limit 1", (now,)).fetchone()
        b = c.execute("select close from bars where symbol='MNQ' and timeframe='5s' "
                      "and bar_ts<=? order by bar_ts desc limit 1", (now - mins * 60,)).fetchone()
        c.close()
        return (r[0] - b[0]) if r and b else None
    except Exception:
        return None


def write(d: dict) -> None:
    tmp = OUT + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(d, fh)
    os.replace(tmp, OUT)


async def main() -> int:
    from ib_async import IB, Stock
    ib = None
    hist: dict[str, list] = {n: [] for n in NAMES}
    while True:
        try:
            if not in_us_hours():
                write({"ts": dt.datetime.now(dt.UTC).isoformat(), "available": False,
                       "why": "US cash session closed — the constituents are shut"})
                if ib and ib.isConnected():
                    ib.disconnect(); ib = None
                    hist = {n: [] for n in NAMES}
                await asyncio.sleep(60)
                continue
            if ib is None or not ib.isConnected():
                ib = IB()
                await ib.connectAsync("127.0.0.1", 4002, clientId=CLIENT_ID,
                                      readonly=True, timeout=25)
                ib.reqMarketDataType(3)
                cons = {}
                for n in NAMES:
                    q = await ib.qualifyContractsAsync(Stock(n, "SMART", "USD"))
                    if q:
                        cons[n] = q[0]
                        ib.reqMktData(q[0], "", False, False)
                    await asyncio.sleep(0.4)
                tick = {n: ib.ticker(c) for n, c in cons.items()}
            now = time.time()
            for n, tk in tick.items():
                px = tk.last if tk.last == tk.last else tk.close
                if px == px and px:
                    hist[n].append((now, float(px)))
                    hist[n] = [x for x in hist[n] if now - x[0] <= (WINDOW_MIN + 2) * 60]
            mv = mnq_move(WINDOW_MIN)
            agree = tot = 0
            if mv is not None and abs(mv) > 0:
                sgn = 1 if mv > 0 else -1
                for n, h in hist.items():
                    old = [x for x in h if now - x[0] >= WINDOW_MIN * 60]
                    if not old or not h:
                        continue
                    tot += 1
                    if (h[-1][1] - old[-1][1]) * sgn > 0:
                        agree += 1
            if tot >= 8:
                frac = agree / tot
                write({"ts": dt.datetime.now(dt.UTC).isoformat(), "available": True,
                       "agree": agree, "of": tot, "frac": round(frac, 3),
                       "band": "broad" if frac > 0.7 else ("narrow" if frac <= 0.4 else "mixed"),
                       "mnq_move_pt": round(mv, 2)})
            else:
                write({"ts": dt.datetime.now(dt.UTC).isoformat(), "available": False,
                       "why": f"warming up — {tot}/10 names have {WINDOW_MIN}min of history"})
        except Exception as e:
            write({"ts": dt.datetime.now(dt.UTC).isoformat(), "available": False,
                   "why": f"{type(e).__name__}: {str(e)[:80]}"})
            try:
                if ib: ib.disconnect()
            except Exception: pass
            ib = None
            await asyncio.sleep(30)
        await asyncio.sleep(20)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
