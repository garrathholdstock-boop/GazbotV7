"""Exact IBKR margin per micro contract, via WHAT-IF orders (operator 2026-10-26: "Get it from ibkr it will be accurate").
A what-if order (Order.whatIf=True) asks IBKR for the margin impact WITHOUT placing or filling anything. Every order built here is asserted to
carry whatIf=True before it is sent; nothing else is ever sent. Separate clientId 82 (the desk uses others). Writes margins_ibkr.json.

    PYTHONPATH=src .venv/bin/python reports/research/markets/ib_margins.py
"""
import asyncio, datetime as dt, json

CLIENT_ID = 82
SPECS = [("MNQ", "CME", "202612"), ("MES", "CME", "202612"), ("M2K", "CME", "202612"), ("MYM", "CBOT", "202612"),
         ("MGC", "COMEX", "202612"), ("MBT", "CME", "202611")]


async def main():
    from ib_async import IB, Future, MarketOrder
    ib = IB()
    await ib.connectAsync("127.0.0.1", 4002, clientId=CLIENT_ID, timeout=20)
    out = {"asof": dt.datetime.now(dt.timezone.utc).isoformat(), "account": None, "method": "whatIfOrder BUY 1, MarketOrder, whatIf=True", "rows": []}
    try:
        for sym, exch, month in SPECS:
            q = [c for c in (await ib.qualifyContractsAsync(Future(symbol=sym, exchange=exch, currency="USD", lastTradeDateOrContractMonth=month)) or []) if c]
            if not q:
                out["rows"].append({"symbol": sym, "error": "contract did not resolve"}); continue
            order = MarketOrder("BUY", 1)
            order.whatIf = True
            assert order.whatIf is True                                       # a what-if order is never placed
            st = await ib.whatIfOrderAsync(q[0], order)
            out["account"] = out["account"] or getattr(order, "account", None)
            out["rows"].append({"symbol": sym, "contract": q[0].localSymbol, "expiry": q[0].lastTradeDateOrContractMonth, "multiplier": q[0].multiplier,
                                "init_margin": st.initMarginChange, "maint_margin": st.maintMarginChange,
                                "commission": st.commission})
            print(out["rows"][-1], flush=True)
            await asyncio.sleep(1.5)
    finally:
        ib.disconnect()
    json.dump(out, open("/home/alphabot/gazbot7/reports/research/markets/margins_ibkr.json", "w"), indent=1)


asyncio.run(main())
