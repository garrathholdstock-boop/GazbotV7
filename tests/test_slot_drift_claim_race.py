"""SLOT DRIFT MUST SURVIVE A DAY-RIDER CLAIM REWRITE BEFORE IT HALTS AND PAGES.

★★★2026-09-26 AUDIT. Measured over three days: 28 SLOT DRIFT halts, every one reading
`logical net 0 != venue ±4` — the day-rider's own lots, never a leak. Timestamps settle the cause:
rider-3894 filled 12:41:07Z and the halt fired 12:41:09Z; rider-3899 filled 12:44:59Z, halt
12:45:00Z. One and two seconds.

The rider is a ONESHOT on a 60-second tick, so after every rider fill there is a window where the
venue already shows the position and the rider has not yet written the claim that explains it.
`_foreign_net` correctly refuses to believe a claim that does not exist yet; `reconcile` then read
that refusal as a leak. `desk_reconcile.require_fresh_claims()` solved exactly this on 2026-09-03
and the fix never reached the tournament. This is the port, and these are its invariants.

⚠⚠ THE TEST THAT MATTERS MOST IS `test_a_REAL_leak_still_halts`. Everything else here is about
suppressing a false page; that one is about not suppressing a true one.
"""
import json
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.multislot_core import MultiSlotCore


class _SB:
    """Minimal slotbook: a logical net we control and the reconcile rule as shipped."""
    def __init__(self, net=0.0):
        self._net = net

    def gates(self):
        return ["grind_long"]

    def net_qty(self):
        return self._net

    def reconcile(self, venue_net):
        return "match" if abs(self._net - venue_net) < 1e-9 else "drift"


def _core(tmp_path, *, logical=0.0, rider=None, pages=None):
    """A core with only what reconcile() touches wired up."""
    core = MultiSlotCore.__new__(MultiSlotCore)
    core._sb = _SB(logical)
    core._halted = False
    core._drift_pending = None
    core._notify = (pages.append if pages is not None else (lambda _m: None))
    p = tmp_path / "day_rider_state.json"
    if rider is not None:
        p.write_text(json.dumps(rider))
    core.DR_STATE = str(p)
    core.DR_MAX_AGE_S = 180.0
    return core


HB1 = "2026-09-26T12:41:00+00:00"
HB2 = "2026-09-26T12:42:00+00:00"     # the rider's NEXT tick, 60s later


# ── the false halt this fixes ──────────────────────────────────────────────────────────────────
def test_the_first_sight_of_drift_does_NOT_page(tmp_path):
    """★ THE 28 PAGES IN 3 DAYS. The rider has filled 4 lots at the venue and has not yet written
    its claim, so its state still says flat. One second later, this used to halt and page."""
    pages = []
    core = _core(tmp_path, logical=0.0,
                 rider={"entered": False, "closed": False, "heartbeat": HB1}, pages=pages)
    assert core.reconcile(4.0) == "drift"
    assert pages == [], "the first sight of an imbalance must not page"
    assert core._halted is False, "and must not latch the desk into a halt"


def test_but_opens_are_STILL_BLOCKED_while_it_is_unconfirmed(tmp_path):
    """⚠⚠ THE FIX IS NOT A RELAXATION. Deferring the page must never defer the protection: nothing
    may be opened against a venue we cannot account for, confirmed or not."""
    core = _core(tmp_path, logical=0.0,
                 rider={"entered": False, "closed": False, "heartbeat": HB1})
    core.reconcile(4.0)
    assert core._open_blocked is True, "an unconfirmed drift must still stop new entries"


def test_the_claim_arriving_clears_it_with_no_page_at_all(tmp_path):
    """The ordinary path: the rider's next tick writes the claim, _foreign_net can now subtract it,
    the imbalance evaporates. He should never have heard about any of it."""
    pages = []
    rider = {"entered": False, "closed": False, "heartbeat": HB1}
    core = _core(tmp_path, logical=0.0, rider=rider, pages=pages)
    assert core.reconcile(4.0) == "drift"
    # the rider ticks: writes entered/qty/direction and a fresh heartbeat
    (tmp_path / "day_rider_state.json").write_text(json.dumps(
        {"entered": True, "closed": False, "qty": 4.0, "direction": 1,
         "heartbeat": _now_iso()}))
    assert core.reconcile(4.0) == "match"
    assert pages == [], "a claim-write race must be silent from end to end"
    assert core._halted is False and core._open_blocked is False


# ── the invariant that must NOT be weakened ────────────────────────────────────────────────────
def test_a_REAL_leak_still_halts(tmp_path):
    """⚠⚠⚠ THE ONE THAT MATTERS. A genuine unaccounted lot survives the rider's next write, so it
    must still latch and page — one claim-rewrite later than before, and no later."""
    pages = []
    core = _core(tmp_path, logical=0.0,
                 rider={"entered": False, "closed": False, "heartbeat": HB1}, pages=pages)
    assert core.reconcile(4.0) == "drift"          # first sight: pending
    assert pages == []
    # the rider rewrites its claim and STILL says flat — so those 4 lots belong to nobody
    (tmp_path / "day_rider_state.json").write_text(json.dumps(
        {"entered": False, "closed": False, "heartbeat": HB2}))
    assert core.reconcile(4.0) == "drift"          # confirmed
    assert core._halted is True, "a real leak must halt"
    assert len(pages) == 1 and "SLOT DRIFT" in pages[0]
    assert "claim rewrite" in pages[0], "the page should say how it was confirmed"


def test_a_DEAD_rider_cannot_buy_an_indefinite_reprieve(tmp_path):
    """⚠⚠⚠ THIS TEST ASSERTED THE OPPOSITE OF THE DESIGN AND PASSED BY ACCIDENT.

    It looped `reconcile` 50 times and asserted `_halted is False`, calling that "never confirmed,
    correctly". But a dead rider MUST confirm on the DRIFT_CONFIRM_MAX_S bound — that bound exists
    precisely so a rider which never writes again cannot buy permanent silence while `pending` keeps
    returning "drift" and skipping the caller's whole safety block. The old test passed only because
    50 iterations take microseconds against a 240-second `time.monotonic()` window: it was testing
    the pre-bound window while its name and docstring claimed to test the bound.
    **A regression that deleted the time bound entirely would have left it green.**

    Now it tests both halves for real, by ageing the pending record rather than waiting 240s.
    """
    core = _core(tmp_path, logical=0.0,
                 rider={"entered": False, "closed": False, "heartbeat": HB1})
    # before the bound: correctly unconfirmed, and correctly still blocked
    for _ in range(5):
        core.reconcile(4.0)
    assert core._halted is False, "it must not confirm before the bound on a stamp that never moved"
    assert core._open_blocked is True, "but it must never become openable"

    # ★ age the pending record past the bound. A dead rider's stamp NEVER advances, so this is the
    # only thing that can confirm — and it must.
    import time as _t
    core._drift_pending["mono"] = _t.monotonic() - (core.DRIFT_CONFIRM_MAX_S + 1.0)
    assert core.reconcile(4.0) == "drift"
    assert core._halted is True, (
        "a dead rider must NOT buy indefinite silence — the time bound is what stops an unaccounted "
        "lot being unmanaged AND unreported forever")


def test_the_time_bound_page_says_it_was_the_BOUND_not_a_rewrite(tmp_path):
    """The two confirmation routes mean different things — 'the rider disagrees' vs 'the rider has
    stopped talking' — and the message must not blur them."""
    import time as _t
    pages = []
    core = _core(tmp_path, logical=0.0,
                 rider={"entered": False, "closed": False, "heartbeat": HB1}, pages=pages)
    core.reconcile(4.0)
    core._drift_pending["mono"] = _t.monotonic() - (core.DRIFT_CONFIRM_MAX_S + 1.0)
    core.reconcile(4.0)
    assert len(pages) == 1
    assert "time bound" in pages[0] and "has not rewritten" in pages[0]


def test_the_bound_is_looser_than_the_claim_freshness_bar(tmp_path):
    """⚠ Ordering matters: the bound must be LONGER than DR_MAX_AGE_S so the ordinary
    claim-rewrite path always wins the race and the bound only ever fires on a genuinely dead
    rider. If they inverted, every routine fill would confirm on the clock instead."""
    core = _core(tmp_path, logical=0.0, rider=None)
    assert core.DRIFT_CONFIRM_MAX_S > core.DR_MAX_AGE_S


def test_an_unreadable_claim_never_counts_as_advanced(tmp_path):
    """An empty stamp can never compare equal to a later read, so a garbled claim cannot confirm a
    breach either — it leaves it pending and blocked."""
    core = _core(tmp_path, logical=0.0, rider=None)      # no file at all
    assert core._dr_stamp() == ""
    core.reconcile(4.0)
    assert core._open_blocked is True


def test_a_second_page_is_not_sent_while_already_halted(tmp_path):
    """The latch is the dedupe. 49 pages in two hours is what this service did before it had one."""
    pages = []
    core = _core(tmp_path, logical=0.0,
                 rider={"entered": False, "closed": False, "heartbeat": HB1}, pages=pages)
    core.reconcile(4.0)
    (tmp_path / "day_rider_state.json").write_text(json.dumps(
        {"entered": False, "closed": False, "heartbeat": HB2}))
    core.reconcile(4.0)
    for _ in range(20):
        core.reconcile(4.0)
    assert len(pages) == 1


def test_match_clears_everything(tmp_path):
    core = _core(tmp_path, logical=4.0, rider={"entered": False, "closed": False, "heartbeat": HB1})
    core._halted = True
    core._drift_pending = {"stamp": "x", "net": 9.0}
    assert core.reconcile(4.0) == "match"
    assert core._halted is False and core._drift_pending is None


def _now_iso():
    import datetime as dt
    return dt.datetime.now(dt.UTC).isoformat()
