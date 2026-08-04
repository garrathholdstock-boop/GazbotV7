"""MD_STREAM is MULTI-SYMBOL — every consumer must filter (★2026-08-04 incident).

WHAT HAPPENED. md publishes one bar message per captured symbol on a single stream, correctly tagged
`{"symbol": sym, ...}`. Three consumers — tournament, shadow, strategy — folded EVERY bar into a single
MinuteBars deque without checking the tag. That was harmless for the desk's entire life because md only
ever captured MNQ. Adding MGC to capture at 17:30 on 2026-08-04 exposed it instantly: gold bars (~3,300)
interleaved with MNQ bars (~29,800), and true range across that jump is astronomic.

Measured consequence, 22:02 the same evening: entry_atr 1848.16 against a true 15.11 — 122x. The desk
opened two abs_veto_short lots with stops 1,848 points away instead of ~15 (~$3,700 of risk per lot
instead of ~$30) and profit targets at 1.5R/2.5R of a bogus ATR, i.e. unreachable. Every gate threshold
is ATR-relative, so entries and exits were corrupted at the same moment.

WHY IT NEEDS A TEST AND NOT JUST A FIX. The bug is invisible while only one symbol is captured, so it
cannot be caught by running the desk — it is armed by a CONFIG change in a different file. A regression
here fails the moment someone deletes the guard, regardless of what md happens to be capturing.
"""
from __future__ import annotations

import inspect
import re

import pytest

from gazbot7 import shadow, strategy, tournament

CONSUMERS = [("tournament", tournament.run), ("shadow", shadow.run), ("strategy", strategy.run)]


@pytest.mark.parametrize("name,fn", CONSUMERS)
def test_every_md_consumer_filters_by_symbol(name, fn):
    """Each T_BAR handler must reject foreign symbols before folding."""
    src = inspect.getsource(fn)
    assert "T_BAR" in src, f"{name}: no T_BAR branch found — test needs updating"
    assert re.search(r'body\.get\("symbol"\)\s*!=\s*cfg\.symbol', src), (
        f"{name}: folds MD_STREAM bars without checking body['symbol']. MD_STREAM carries every "
        f"captured symbol; folding gold into an MNQ deque made ATR read 1848 against a true 15.")


@pytest.mark.parametrize("name,fn", CONSUMERS)
def test_the_filter_precedes_the_fold(name, fn):
    """Guard must come BEFORE mb.fold / strat.on_bar, or it filters nothing."""
    src = inspect.getsource(fn)
    guard = src.find('body.get("symbol") != cfg.symbol')
    fold = min([p for p in (src.find("mb.fold("), src.find("strat.on_bar(")) if p != -1] or [-1])
    assert guard != -1 and fold != -1, f"{name}: could not locate guard/fold"
    assert guard < fold, f"{name}: symbol guard appears AFTER the fold — it would filter nothing"


def test_md_publishes_the_symbol_tag():
    """The consumers' guard relies on md tagging every bar. If the publisher stops sending `symbol`,
    `body.get("symbol")` becomes None, != cfg.symbol, and the desk would silently receive NO bars —
    failing closed rather than corrupting, but still fatal. Pin the contract at the source."""
    from gazbot7 import capture
    src = inspect.getsource(capture.CaptureManager)
    assert re.search(r'"symbol":\s*sym', src), (
        "md no longer tags published bars with their symbol — every consumer's filter would drop "
        "everything and the desk would starve for bars")
