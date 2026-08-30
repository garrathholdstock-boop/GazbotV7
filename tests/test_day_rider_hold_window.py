"""A hand-opened position must be MANAGED, not hard-flatted. Regression for the 09:11 incident.

2026-08-21: the operator bought 4 lots by hand at 09:11Z. The next tick hard-flatted them at a
40pt slip on the last lot, because the flatten branch triggered on `mod < OPEN_UTC_MIN` — true all
morning. Manual ENTRY had been extended to the full CME session; MANAGEMENT had not. The tick then
died on an unbound `px` AFTER the order reached the venue, so the book still claimed 4 lots against
a venue of 0; the reconciler wrote the kill file and the rider went inert — which is why the claim
buttons stopped responding. One window mismatch, four downstream failures.
"""
import pytest
from gazbot7.day_rider import (hard_flat_window, idle_block_applies,
                               FLAT_UTC_MIN, REOPEN_UTC_MIN, OPEN_UTC_MIN)

H = lambda hh, mm=0: hh * 60 + mm


@pytest.mark.parametrize("mod", [H(9, 11), H(9, 12), H(2), H(23), H(13, 29), H(20, 39)])
def test_a_position_we_hold_is_managed_not_killed(mod):
    assert idle_block_applies(mod, owned_live=True) is False, (
        f"minute {mod//60:02d}:{mod%60:02d} would hard-flat a hand-opened position")


@pytest.mark.parametrize("mod", [H(20, 40), H(21), H(21, 59)])
def test_the_flatten_window_still_closes_everything(mod):
    """NEVER HOLD OVERNIGHT — nothing survives 20:40Z, held or not."""
    assert hard_flat_window(mod) is True
    assert idle_block_applies(mod, owned_live=True) is True


@pytest.mark.parametrize("mod", [H(22), H(23), H(0), H(9), H(13, 29)])
def test_outside_the_flatten_window_nothing_is_forced_closed(mod):
    assert hard_flat_window(mod) is False


def test_the_dead_window_is_exactly_2040_to_2200():
    assert FLAT_UTC_MIN == H(20, 40) and REOPEN_UTC_MIN == H(22)
    assert not hard_flat_window(REOPEN_UTC_MIN), "22:00 is a NEW session, not the halt"
    assert hard_flat_window(FLAT_UTC_MIN), "20:40 is the flat"


@pytest.mark.parametrize("mod", [H(9), H(23), H(2)])
def test_when_flat_the_idle_branch_still_runs_so_manual_buy_is_reachable(mod):
    assert idle_block_applies(mod, owned_live=False) is True


@pytest.mark.parametrize("mod", [H(13, 30), H(15), H(20, 39)])
def test_the_automatic_entry_path_is_untouched(mod):
    """Flat inside 13:30-20:40 must fall THROUGH to the detector, not into the idle branch."""
    assert idle_block_applies(mod, owned_live=False) is False
    assert idle_block_applies(mod, owned_live=True) is False
