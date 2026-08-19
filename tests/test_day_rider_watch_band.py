"""The confirmation notification must tell the operator whether to WATCH — and must not lie about the clock.

★2026-08-19. Two things are pinned here.

1. `watch_verdict` is the only surviving finding from the 231-session study reaching the operator.
   It is REPORTING ONLY. If a future session wires it to a switch, the boundary tests below are the
   place that should have made them stop and read WATCH_RT's comment first.

2. The entry notification said "flat 21:00" from the day it was written. 21:00Z IS the CME halt, so a
   flatten fired then has no market and no retry — the standing operator rule is 20:40, and a
   notification that restates a clock as a LITERAL is exactly how the two drift apart. The clock must
   be rendered FROM the constant, so it can never disagree with the code that acts on it.
"""
import re

from gazbot7.day_rider import ENTRY_CUTOFF_MIN, FLAT_UTC_MIN, WATCH_RT, watch_verdict


def test_the_band_boundary_is_exclusive():
    """rt < 0.50 watches; 0.50 itself does not. Today's live trade was 0.48."""
    assert watch_verdict(0.48).startswith("WATCH")
    assert watch_verdict(0.4999).startswith("WATCH")
    assert not watch_verdict(WATCH_RT).startswith("WATCH")
    assert not watch_verdict(0.69).startswith("WATCH")


def test_the_verdict_always_states_the_threshold_it_used():
    """A bare "off-band" is unauditable after the fact — the number must travel with the verdict."""
    assert f"{WATCH_RT:.2f}" in watch_verdict(0.80)


def test_the_flat_clock_is_never_a_literal_in_the_notification():
    """★ THE REGRESSION THIS FILE EXISTS FOR. Nothing may hardcode the flatten time."""
    import inspect

    import gazbot7.day_rider as dr

    src = inspect.getsource(dr)
    notify_lines = [ln for ln in src.splitlines()
                    if "notify(" in ln or ("f\"" in ln and "flat" in ln.lower())]
    for ln in notify_lines:
        assert not re.search(r"flat\s+21:00", ln), f"hardcoded halt-time clock in: {ln.strip()}"


def test_the_rendered_clocks_match_the_constants():
    assert f"{FLAT_UTC_MIN//60:02d}:{FLAT_UTC_MIN%60:02d}" == "20:40"
    assert f"{ENTRY_CUTOFF_MIN//60:02d}:{ENTRY_CUTOFF_MIN%60:02d}" == "15:00"
    assert FLAT_UTC_MIN < 21 * 60, "21:00Z is the CME halt — a flatten there has no market"


def test_entries_are_capped_to_the_first_90_minutes_after_the_cash_open():
    """The operator watches "only the first 90 minutes after open, then it calms down". The entry
    cutoff already encodes exactly that: 13:30Z cash open -> 15:00Z."""
    assert ENTRY_CUTOFF_MIN - (13 * 60 + 30) == 90
