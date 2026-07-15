# Operator-run flatten: closes any net MNQ position to flat + cancels working orders.
import asyncio
from ib_async import IB, ContFuture, MarketOrder

async def main():
    ib = IB()
    await ib.connectAsync("127.0.0.1", 4002, clientId=8, readonly=False, timeout=15)
    await asyncio.sleep(1)
    (c,) = await ib.qualifyContractsAsync(ContFuture("MNQ", "CME"))
    net = sum(p.position for p in ib.positions() if p.contract.symbol == "MNQ")
    print(f"pre-flatten NET = {net}")
    await ib.reqAllOpenOrdersAsync(); await asyncio.sleep(0.5)
    for t in ib.openTrades():
        ib.cancelOrder(t.order)
    if abs(net) > 1e-9:
        tr = ib.placeOrder(c, MarketOrder("BUY" if net < 0 else "SELL", abs(net)))
        for _ in range(20):
            await asyncio.sleep(0.5)
            if tr.orderStatus.status == "Filled":
                break
        print(f"  {tr.orderStatus.status} filled={tr.orderStatus.filled} avg={tr.orderStatus.avgFillPrice}")
    await asyncio.sleep(1.5)
    print(f"post-flatten NET = {sum(p.position for p in ib.positions() if p.contract.symbol=='MNQ')}")
    ib.disconnect()

asyncio.run(main())
