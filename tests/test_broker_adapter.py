"""Live glue — the pure fill translation + config defaults."""

from __future__ import annotations

from types import SimpleNamespace

from gazbot7.broker_adapter import execution_to_fill
from gazbot7.config import RunConfig


def _exec(execId="e1", side="BOT", shares=2, price=29950.0):
    return SimpleNamespace(execId=execId, side=side, shares=shares, price=price)


def test_bot_maps_to_buy():
    f = execution_to_fill(_exec(side="BOT"), order_ref="o1", symbol="MNQ", time_iso="2026-07-15T13:00:00+00:00")
    assert f.side == "BUY"
    assert f.exec_id == "e1" and f.order_id == "o1" and f.qty == 2.0 and f.price == 29950.0


def test_sld_maps_to_sell():
    f = execution_to_fill(_exec(side="SLD"), order_ref="o1", symbol="MNQ", time_iso="t")
    assert f.side == "SELL"


def test_missing_order_ref_is_unknown():
    f = execution_to_fill(_exec(), order_ref=None, symbol="MNQ", time_iso="t")
    assert f.order_id == "unknown"


def test_config_default_is_dry_run():
    c = RunConfig()
    assert c.place_live is False  # SAFE default — no live orders until cutover
    assert c.symbol == "MNQ" and c.client_id == 7 and c.port == 4002
