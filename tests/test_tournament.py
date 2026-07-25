"""Tournament runner — the pure `step` decision helper's freshness gating."""
from __future__ import annotations

from gazbot7.agg import MinuteBars
from gazbot7.config import RunConfig
from gazbot7.slot_strategy import SlotStrategy, grind_long_short_slots, tournament_slots
from gazbot7.slotbook import SlotBook
from gazbot7.tournament import _ensure_live_cfg, step


def _setup():
    mb = MinuteBars(60)
    sb = SlotBook(["grind_long", "grind_short"], value_per_point=2.0, fee_rt=1.5)
    strat = SlotStrategy(grind_long_short_slots(), value_per_point=2.0)
    return strat, mb, sb


def test_step_stale_tape_returns_empty():
    strat, mb, sb = _setup()
    assert step(strat, mb, {"ts_ms": 0, "net_flow": 0.0}, sb, 1_000_000) == []


def test_step_no_fresh_bars_returns_empty():
    strat, mb, sb = _setup()
    now = 1_000_000_000_000
    # fresh tape, but the MinuteBars is empty → not fresh / < 6 bars → no decision
    assert step(strat, mb, {"ts_ms": now, "net_flow": 0.0, "last": 29000.0}, sb, now) == []


def test_grind_long_short_slots_shape():
    specs = grind_long_short_slots()
    assert [s.tag for s in specs] == ["grind_long", "grind_short"]
    assert [s.side for s in specs] == ["LONG", "SHORT"]


def test_tournament_slate_is_four_long_two_short_distinct():
    specs = tournament_slots()
    assert [s.tag for s in specs] == ["grind_long", "capitulation_long", "abs_veto_long",
                                      "rgv_long", "rgv_short", "abs_veto_short"]
    assert sum(s.side == "LONG" for s in specs) == 4
    assert sum(s.side == "SHORT" for s in specs) == 2
    assert {s.kind for s in specs} == {"reversal_grab", "grind", "thrust", "capitulation"}


def test_live_run_coerces_cfg_place_live():
    # the silent no-trade bug: a live run must lift cfg.place_live so the core places orders
    assert _ensure_live_cfg(RunConfig(place_live=False), True).place_live is True
    assert _ensure_live_cfg(RunConfig(place_live=False), False).place_live is False  # dry-run untouched
    assert _ensure_live_cfg(RunConfig(place_live=True), True).place_live is True


# ── intraday per-gate off-switch (live, no restart) ───────────────────────────
def test_parse_switches_reads_off_values():
    from gazbot7.tournament import parse_switches
    txt = "# intraday gate on/off\nthrust_short=off\nrgv_short = disable\ngrind_long=on\n\nbadline\ncapitulation_long=0"
    assert parse_switches(txt) == {"thrust_short", "rgv_short", "capitulation_long"}
    assert parse_switches("") == set()


def test_read_disabled_mtime_cached_and_absent_is_none(tmp_path):
    from gazbot7.tournament import read_disabled
    p = str(tmp_path / "gate_switches.env")
    cache: dict = {}
    assert read_disabled(p, cache) == set()                 # absent → nothing disabled
    (tmp_path / "gate_switches.env").write_text("thrust_short=off\n")
    assert read_disabled(p, cache) == {"thrust_short"}       # created → picked up live
    (tmp_path / "gate_switches.env").write_text("thrust_short=on\n")
    assert read_disabled(p, cache) == set()                  # flipped back on → live


class _FakeStrat:
    """Returns a fixed intent list so we test step()'s ER filter deterministically."""

    def __init__(self, intents):
        self._i = intents

    def decide(self, f, price, bars, slotbook, net_flow, footprint):
        return [dict(i) for i in self._i]


def _feed(mb, closes, start_min=1_000_000):
    for k, c in enumerate(closes):
        mb.fold((start_min + k) * 60, c, c, c, c, 10)
    last = (start_min + len(closes)) * 60
    mb.fold(last, closes[-1], closes[-1], closes[-1], closes[-1], 10)  # roll → finalise last bar
    return last * 1000


def test_step_er_gate_momentum_blocks_chop_allows_trend():
    _, mb, sb = _setup()
    trend = [100 + 25 * i for i in range(30)]            # ER ≈ 1.0 AND ATR ≈ 25pt → clears both floors
    now = _feed(mb, trend)
    strat = _FakeStrat([{"action": "OPEN", "slot": "grind_long", "side": "LONG"}])
    tape = {"ts_ms": now, "net_flow": 0.0, "last": float(trend[-1])}
    assert [i["slot"] for i in step(strat, mb, tape, sb, now)] == ["grind_long"]  # big trend → kept

    mb2 = MinuteBars(60)
    chop = [100 + (i % 2) for i in range(30)]            # ER ≈ 0 → below the ER floor
    now2 = _feed(mb2, chop)
    tape2 = {"ts_ms": now2, "net_flow": 0.0, "last": float(chop[-1])}
    assert step(strat, mb2, tape2, sb, now2) == []       # chop → grind_long OPEN suppressed


def test_step_atr_gate_blocks_a_weak_trend():
    # a clean trend (high ER) but a TINY one (ATR ~1pt) → grind_long clears the ER floor but the ATR
    # floor (20pt) suppresses it: a trend too small to run.
    _, mb, sb = _setup()
    weak = [100 + i for i in range(30)]                  # ER ≈ 1.0, but ~1pt bars → ATR ≈ 1pt
    now = _feed(mb, weak)
    strat = _FakeStrat([{"action": "OPEN", "slot": "grind_long", "side": "LONG"}])
    tape = {"ts_ms": now, "net_flow": 0.0, "last": float(weak[-1])}
    assert step(strat, mb, tape, sb, now) == []          # weak trend → ATR gate suppresses


def test_step_er_gate_reversion_blocks_trend_keeps_close():
    _, mb, sb = _setup()
    trend = [100 + i for i in range(30)]                 # high ER → above exhaustion_short ceiling 0.05
    now = _feed(mb, trend)
    strat = _FakeStrat([
        {"action": "OPEN", "slot": "exhaustion_short", "side": "SHORT"},   # blocked in trend
        {"action": "CLOSE", "slot": "exhaustion_short", "reason": "STOP"},  # managed exit always kept
    ])
    tape = {"ts_ms": now, "net_flow": 0.0, "last": float(trend[-1])}
    out = [(i["action"], i["slot"]) for i in step(strat, mb, tape, sb, now)]
    assert out == [("CLOSE", "exhaustion_short")]


def test_disabled_filter_drops_opens_keeps_closes():
    # the loop's filter: a disabled gate takes NO new entries, but its open position still exits
    disabled = {"thrust_short"}
    intents = [
        {"action": "OPEN", "slot": "thrust_short", "side": "SHORT"},   # dropped
        {"action": "OPEN", "slot": "grind_long", "side": "LONG"},      # kept (not disabled)
        {"action": "CLOSE", "slot": "thrust_short", "reason": "STOP"}, # kept (managed exit)
    ]
    kept = [i for i in intents if not (i.get("action") == "OPEN" and i.get("slot") in disabled)]
    assert [(i["action"], i["slot"]) for i in kept] == [("OPEN", "grind_long"), ("CLOSE", "thrust_short")]
