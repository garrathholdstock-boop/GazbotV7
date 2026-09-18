#!/usr/bin/env python3
"""THE MACRO TRACKER — oil, the dollar, the 10-year and VIX, once an hour.

Operator, 2026-09-18: *"oil, dxy, 10 year and vix."* — the backdrop he wants at a glance, and the
raw material for the Friday report's "week that was / week coming" headline.

★★★ WHY IT DOES NOT OPEN A PERSISTENT IBKR CLIENT, AND WHY THAT MATTERS. On 2026-09-17 the
gateway's accept queue filled (LISTEN 51 against a backlog of 50, sockets stuck in CLOSE-WAIT):
already-open connections kept working while every NEW one hung, the rider went blind for 5.5 hours
holding 4 lots, and the operator's Claim expired unread. So this takes ONE short-lived, READ-ONLY
connection and disconnects in a `finally` — and when it cannot connect it gives up QUIETLY and
pages only on a streak. A context tracker must never be the thing that costs the desk a claim.
⚠ It is one connect per hour against the rider's ~1,440 and the watchdog's ~720 a day, so it is
noise in that budget — but it is not zero, which is why it is hourly and not every minute.

★★ WHAT EACH SERIES ACTUALLY IS, because "oil" is ambiguous and getting it wrong is the kind of
cost-constant error this desk has been bitten by:
    OIL   ContFuture CL @ NYMEX  — the FRONT WTI FUTURE (CLX6 today), not spot. FRED's DCOILWTICO
          spot read 107.02 on 2026-09-15 while CLX6 read 95.24 on the 18th; they are different
          instruments and must never be quoted interchangeably.
    DXY   ContFuture DX @ NYBOT  — the dollar index FUTURE. Index("DXY") has no security
          definition on this account under any exchange tried (ICE, NYBOT).
    TEN   ContFuture ZN @ CBOT   — the 10-year NOTE FUTURE. ⚠ PRICE, SO IT MOVES INVERSE TO YIELD:
          ZN down = yields UP. Anyone reading this as "the 10-year" must hold that in mind.
    VIX   Index VIX @ CBOE       — ⚠ REQUIRES reqMarketDataType(3) = DELAYED on this account.
          It is roughly 15 MINUTES STALE and every record says so. A delayed number presented as
          live is exactly the instrument-reports-healthy failure this desk keeps meeting.

⚠⚠⚠ READ-ONLY. readonly=True on the connection, no order path, and it writes one append-only log.
⚠⚠ IT MEASURES NO EDGE. Whether any of these four predicts anything for MNQ or MGC is UNTESTED —
they are carried because the operator asked for the backdrop, not because they have earned a place
beside the event calendar's measured numbers.

  PYTHONPATH=src .venv/bin/python scripts/macro_watch.py [--show]
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

LOG = "/home/alphabot/gazbot7/data/macro_watch.jsonl"
BLIND = "/home/alphabot/gazbot7/data/macro_watch_blind.json"
CLIENT_ID = 9          # core=0 md=2 day_rider=4 watchdog=5 eod=6 checks=8 — 9 is free

SERIES = (
    ("OIL", "CL", "NYMEX", "front WTI future", False),
    ("DXY", "DX", "NYBOT", "dollar index future", False),
    ("TEN", "ZN", "CBOT", "10y note future (PRICE — inverse to yield)", False),
    ("VIX", "VIX", "CBOE", "volatility index (DELAYED ~15min)", True),
)


def log_line(msg: str) -> None:
    print(f"{dt.datetime.now(dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}")


async def snap() -> dict:
    from ib_async import IB, ContFuture, Index
    ib = IB()
    out: dict = {"ts": dt.datetime.now(dt.UTC).isoformat(), "series": {}}
    try:
        await ib.connectAsync("127.0.0.1", 4002, clientId=CLIENT_ID, readonly=True, timeout=20)
        ib.reqMarketDataType(3)          # delayed where live is not subscribed; VIX needs it
        for key, sym, exch, note, is_index in SERIES:
            try:
                c = Index(sym, exch) if is_index else ContFuture(sym, exch)
                q = await ib.qualifyContractsAsync(c)
                if not q:
                    out["series"][key] = {"error": "not qualified"}
                    continue
                t = ib.reqMktData(q[0], "", False, False)
                for _ in range(8):
                    await asyncio.sleep(1)
                    if any(v == v and v for v in (t.last, t.close, t.bid)):
                        break

                def num(v):
                    return float(v) if v is not None and v == v else None

                last, close = num(t.last), num(t.close)
                px = last if last else close
                out["series"][key] = {
                    "contract": q[0].localSymbol or q[0].symbol, "what": note,
                    "px": px, "prev_close": close,
                    # ⚠ NEVER silently blend a delayed print with live ones.
                    "delayed": bool(is_index),
                    "chg_pct": (round((px - close) / close * 100, 3)
                                if px and close and close else None),
                }
            except Exception as e:
                out["series"][key] = {"error": f"{type(e).__name__}: {str(e)[:70]}"}
    finally:
        try:
            ib.disconnect()      # ★ ALWAYS. A leaked socket here is a CLOSE-WAIT on the gateway.
        except Exception:
            pass
    return out


def note_blind(err: str) -> None:
    """⚠ Quiet on a blip, loud on a streak — the 2026-09-17 shape. A context tracker that pages on
    every transient would train him to swipe past criticals, which is how a naked position is
    missed; one that NEVER pages is how 5.5 hours went by."""
    try:
        st = json.load(open(BLIND))
    except Exception:
        st = {"streak": 0}
    st["streak"] = int(st.get("streak", 0)) + 1
    st["last"] = err[:200]
    json.dump(st, open(BLIND, "w"))
    if st["streak"] in (6, 24):          # ~6h and ~24h at an hourly cadence
        try:
            from gazbot7.notify import dedupe_ok, notify
            m = (f"⚠ MACRO TRACKER blind for {st['streak']} consecutive hours ({err[:90]}). "
                 f"Context only — no position risk — but the Friday backdrop will be short.")
            if dedupe_ok(f"macro_watch.blind.{st['streak']}", m, cooldown_s=3600):
                notify(m, critical=False)
        except Exception:
            pass


def main() -> int:
    if "--show" in sys.argv:
        try:
            rows = [json.loads(x) for x in open(LOG)][-1:]
        except Exception:
            rows = []
        if not rows:
            print("no readings yet")
            return 0
        r = rows[0]
        print(f"as of {r['ts']}")
        for k, v in r["series"].items():
            if "error" in v:
                print(f"  {k:<4} ERROR {v['error']}")
            else:
                print(f"  {k:<4} {v['contract']:<7} {v['px']:>10} "
                      f"{(str(v['chg_pct'])+'%') if v['chg_pct'] is not None else '':>8}"
                      f"   {v['what']}" + ("  ⚠DELAYED" if v.get("delayed") else ""))
        return 0

    try:
        rec = asyncio.run(snap())
    except Exception as e:
        log_line(f"SKIP venue read failed: {type(e).__name__}: {str(e)[:90]}")
        note_blind(f"{type(e).__name__}: {e}")
        return 0
    ok = [k for k, v in rec["series"].items() if "error" not in v]
    if not ok:
        log_line("SKIP — every series errored")
        note_blind("all series errored")
        return 0
    try:
        os.remove(BLIND)             # a good read ends the streak
    except Exception:
        pass
    with open(LOG, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    log_line("ok " + " · ".join(
        f"{k}={rec['series'][k]['px']}"
        + (f" ({rec['series'][k]['chg_pct']:+.2f}%)" if rec['series'][k].get('chg_pct') else "")
        for k in ok))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
