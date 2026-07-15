"""GAZBOT V7 — the EOD flatten (S4): flat before the Globex halt, autonomously.

The operator's cardinal rule is FLAT overnight, every day. This runs from its own
systemd timer on its **own IBKR client** — deliberately independent of core, so a
dead/hung core still goes flat. It cancels resting orders, then fires a market
close for exactly the quantity IBKR holds (never more — the safe-flatten
discipline S5 formalises), and verifies flat. Core is the clientId-0 master, so it
still *sees and records* this flatten's fill even though a different client placed
it.

Two passes (16:53 + 16:57 ET) catch a slow fill; each is a no-op on a flat book,
so firing daily (incl. weekends) never misses a trading day and never misbehaves
on a closed one. Clean-room.
"""

from __future__ import annotations

import asyncio

from .config import RunConfig
from .safety import safe_flatten_verdict

EOD_CLIENT_ID = 6  # dedicated (core=0, md=2, checks=8) — never collide
_EPS = 1e-9


async def flatten_once(cfg: RunConfig) -> tuple[float, float]:
    """Cancel resting orders + flatten the venue position. Returns (pre, post) net."""
    from ib_async import IB, ContFuture, MarketOrder

    ib = IB()
    await ib.connectAsync(cfg.host, cfg.port, clientId=EOD_CLIENT_ID, readonly=False, timeout=15)
    try:
        await asyncio.sleep(1.0)
        (contract,) = await ib.qualifyContractsAsync(ContFuture(cfg.symbol, cfg.exchange))
        await ib.reqAllOpenOrdersAsync()
        await asyncio.sleep(0.3)
        for tr in list(ib.openTrades()):
            if getattr(tr.contract, "symbol", None) == cfg.symbol:
                ib.cancelOrder(tr.order)
        net = sum(p.position for p in ib.positions() if p.contract.symbol == cfg.symbol)
        verdict = safe_flatten_verdict(net)  # fire ONLY what IBKR holds, its direction
        if verdict is not None:
            action, qty = verdict
            tr = ib.placeOrder(contract, MarketOrder(action, qty))
            for _ in range(20):
                await asyncio.sleep(0.5)
                if tr.orderStatus.status == "Filled":
                    break
        await asyncio.sleep(1.0)
        post = sum(p.position for p in ib.positions() if p.contract.symbol == cfg.symbol)
        return net, post
    finally:
        ib.disconnect()


def main() -> None:  # `python -m gazbot7.eod_flatten`
    cfg = RunConfig()
    pre, post = asyncio.run(flatten_once(cfg))
    print(f"eod_flatten: {cfg.symbol} pre={pre:g} post={post:g}")
    if abs(post) > _EPS:  # still not flat → page the operator (a real failure)
        from .notify import notify
        notify(f"Garrath — V7 EOD flatten INCOMPLETE: {cfg.symbol} still {post:g} "
               f"(need you on Termius to flatten at IBKR)", critical=True)


if __name__ == "__main__":
    main()
