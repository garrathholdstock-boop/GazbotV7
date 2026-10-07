"""S2 — the MIL line. Two entry-only rules, shown to the model ONLY when it is flat.

Operator, 2026-10-07: *"Do don't enter against the MIL direction and also do R4 re entry spacing in
s2. … we're not changing exits this time?"*  So the tests prove three things through the REAL entry
points ([[a-source-text-test-is-a-lint-not-a-test]]):

  1. the in-harness tracker IS the pre-registered one (`mil_entry_spacing.tracker`) and is causal;
  2. the page a HOLDING model sees is byte-identical with and without the MIL line (exits unchanged);
  3. the rule state it prints is the rule: no entry against the MIL, one per MIL+side until age >= 176.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

import pytest

GB = pathlib.Path("/home/alphabot/gazbot7")
sys.path.insert(0, str(GB / "src"))
sys.path.insert(0, str(GB / "scripts"))

import sim_week_recursive as SW          # noqa: E402
import forward_days as FD                # noqa: E402
import test_strategy_headline as H       # noqa: E402  (its synthetic tape + harness fixture)

harness = H.harness
DAY = H.DAY


def _tracker():
    src = (GB / "scripts" / "mil_entry_spacing.py").read_text().replace("\nmain()\n", "\n")
    g: dict = {}
    exec(compile(src, "mil_entry_spacing", "exec"), g)
    return g


def _trade(side, bars, minute):
    t = dt.datetime.fromtimestamp(bars[minute][0], dt.UTC)
    return {"side": side, "opened": t.isoformat(), "closed": t.isoformat(), "held_min": 5.0,
            "points": 1.0, "pnl_usd": 1.0, "peak_pt": 1.0, "entry": 1.0, "exit": 1.0}


def _first_in_leg(bars, n, leg):
    """first bar index the causal tracker LABELS as `leg` (a leg's start is the old extreme, found
    only when the flip is confirmed, so a trade is in the leg from the confirming bar on)."""
    _, la = _tracker()["tracker"](bars[:n], 7)
    return la.index(leg)


def _end(bars):
    d0 = int(dt.datetime.fromisoformat(DAY + "T00:00:00+00:00").timestamp())
    return [b for b in bars if b[0] <= d0 + 9 * 3600]


# ── 1. it is the pre-registered tracker, and causal ──────────────────────────────────────
def test_constants_are_the_frozen_ones():
    assert SW.MIL_K == 7 and SW.MIL_T == 176


def test_matches_the_preregistered_tracker_at_every_prefix():
    g = _tracker()
    bars = _end(H._bars(DAY))
    legs, la = g["tracker"](bars, 7)
    flips = 0
    for n in range(60, len(bars) + 1, 7):
        m = SW.mil_state(bars[:n])
        pl, pa = g["tracker"](bars[:n], 7)               # causal: the prefix alone gives the same legs
        assert m["leg"] == pa[n - 1] == la[n - 1]
        assert (m["dir"], m["start"]) == (pl[m["leg"]][0], pl[m["leg"]][1]) == (legs[la[n - 1]][0], legs[la[n - 1]][1])
        flips += m["leg"] > 0
    assert flips, "the synthetic tape must contain a MIL flip or this test proves nothing"


def test_matches_the_tracker_on_a_real_day():
    g = _tracker()
    try:
        bars, _ = SW.load_day("2026-02-05")
    except Exception as e:                                # no tape on this box
        pytest.skip(f"no tape: {e}")
    if len(bars) < 600:
        pytest.skip("short tape")
    legs, la = g["tracker"](bars, 7)
    for n in range(60, len(bars) + 1, 37):
        m = SW.mil_state(bars[:n])
        assert (m["dir"], m["start"], m["leg"]) == (legs[la[n - 1]][0], legs[la[n - 1]][1], la[n - 1])


# ── 2. the rule state ────────────────────────────────────────────────────────────────────
def _late_state(bars):
    for n in range(len(bars), 60, -1):
        m = SW.mil_state(bars[:n])
        if m["age"] > 5:
            return n, m
    raise AssertionError("no state")


def test_against_the_mil_is_never_allowed_and_first_with_entry_is():
    bars = _end(H._bars(DAY))
    n, m = _late_state(bars)
    assert m["allowed"][m["against"]] is False
    assert m["allowed"][m["with"]] is True


def test_second_entry_same_mil_side_blocked_until_age_176():
    bars = _end(H._bars(DAY))
    # find a prefix where the MIL is genuinely young (< 176) and one where it is old (>= 176)
    young = old = None
    for n in range(60, len(bars) + 1):
        m = SW.mil_state(bars[:n])
        if 5 < m["age"] < SW.MIL_T and young is None:
            young = (n, m)
        if m["age"] >= SW.MIL_T and old is None:
            old = (n, m)
    assert young, "need a young MIL"
    n, m = young
    k = _first_in_leg(bars, n, m["leg"])
    done = [_trade(m["with"], bars, k)]
    m2 = SW.mil_state(bars[:n], done)
    assert m2["taken"][m["with"]] == 1 and m2["allowed"][m["with"]] is False
    assert m2["allowed"][m["against"]] is False
    if old:                                               # same side, MIL now >= 176 min old: R4 exception
        n3, m3 = old
        k3 = _first_in_leg(bars, n3, m3["leg"])
        d3 = [_trade(m3["with"], bars, k3)]
        assert SW.mil_state(bars[:n3], d3)["allowed"][m3["with"]] is True
        assert SW.mil_state(bars[:n3], d3)["allowed"][m3["against"]] is False


def test_an_entry_in_an_earlier_mil_does_not_count():
    bars = _end(H._bars(DAY))
    m = SW.mil_state(bars)
    assert m["leg"] > 0
    first = _trade(m["with"], bars, 30)                    # minute 30 sits in an earlier MIL
    _, la = _tracker()["tracker"](bars, 7)
    assert la[30] != m["leg"]
    assert SW.mil_state(bars, [first])["taken"] == {"LONG": 0, "SHORT": 0}


# ── 3. the page: shown only when flat; holding page byte-identical ───────────────────────
def _page(bars, pos, mil, done=None):
    return SW.context(bars, bars[-1][0], pos, "", done or [], True, band=False, leg_list=False, mil=mil)


def test_flat_page_carries_the_line_and_the_default_does_not():
    bars = _end(H._bars(DAY))
    on, off = _page(bars, None, True), _page(bars, None, False)
    assert "MAJOR INTRADAY LEG (MIL)" in on and "ENTER_LONG:" in on and "ENTER_SHORT:" in on
    assert "NOT ALLOWED — it is against the MIL" in on
    assert "MAJOR INTRADAY LEG" not in off
    assert SW.context(bars, bars[-1][0], None, "", [], True, band=False, leg_list=False) == off


def test_holding_page_is_byte_identical_so_exits_are_unchanged():
    bars = _end(H._bars(DAY))
    px = bars[-1][3]
    pos = {"dir": 1, "entry": px - 5, "peak": 5.0, "peak_1m": 5.0, "last_ts": bars[-1][0],
           "opened": dt.datetime.fromtimestamp(bars[-20][0], dt.UTC)}
    assert _page(bars, pos, True) == _page(bars, pos, False)
    assert "MAJOR INTRADAY LEG" not in _page(bars, pos, True)


def test_the_printed_permission_is_the_computed_one():
    bars = _end(H._bars(DAY))
    m = SW.mil_state(bars)
    page = _page(bars, None, True)
    assert f"ENTER_{m['with']}: ALLOWED" in page
    assert f"ENTER_{m['against']}: NOT ALLOWED — it is against the MIL" in page
    done = [_trade(m["with"], bars, _first_in_leg(bars, len(bars), m["leg"]))]
    p2 = _page(bars, None, True, done)
    if m["age"] < SW.MIL_T:
        assert f"ENTER_{m['with']}: NOT ALLOWED — you already entered this MIL" in p2


# ── 4. the real run_day and forward_days ─────────────────────────────────────────────────
def test_run_day_records_the_stamp_and_sends_the_line_only_when_flat(harness):
    rec = SW.run_day(DAY, "", "s_mil", resume=False, self_aware=True, line="v2", mil=True)
    assert rec["mil_ctx"] is True and rec["line"] == "v2"
    flat = [p for p in harness if "YOU ARE FLAT." in p]
    held = [p for p in harness if "YOUR POSITION:" in p]
    assert flat and held
    assert all("MAJOR INTRADAY LEG (MIL)" in p for p in flat)
    assert not any("MAJOR INTRADAY LEG" in p for p in held)


def test_v1_cannot_take_the_mil_line(harness):
    with pytest.raises(ValueError):
        SW.run_day(DAY, "", "s_v1mil", resume=False, line="v1", mil=True)


def test_default_record_is_unstamped_true_and_resume_respects_it(harness):
    SW.run_day(DAY, "", "same_mil", resume=True, self_aware=True, line="v2", mil=False)
    n = len(harness)
    SW.run_day(DAY, "", "same_mil", resume=True, self_aware=True, line="v2", mil=False)
    assert len(harness) == n, "an unchanged record must be inherited, not re-run"
    SW.run_day(DAY, "", "same_mil", resume=True, self_aware=True, line="v2", mil=True)
    assert len(harness) > n, "a record made without the MIL page is not an S2 day"
    assert json.load(open(f"{SW.OUT}/same_mil_{DAY}.json"))["mil_ctx"] is True


def test_is_clean_distinguishes_the_pages(harness):
    SW.run_day(DAY, "", "clean_mil", resume=False, self_aware=True, line="v2", mil=False)
    assert FD.is_clean("clean_mil", DAY, "v2", False) and not FD.is_clean("clean_mil", DAY, "v2", True)


def test_flat_calls_stamp_the_mil_block_they_were_shown(harness):
    rec = SW.run_day(DAY, "", "stamp_mil", resume=False, self_aware=True, line="v2", mil=True)
    flat = [c for c in rec["calls"] if not c["holding"]]
    held = [c for c in rec["calls"] if c["holding"]]
    assert flat and all(set(c["mil"]) == {"dir", "age", "taken", "allowed"} for c in flat)
    assert held and not any("mil" in c for c in held)
    off = SW.run_day(DAY, "", "stamp_off", resume=False, self_aware=True, line="v2", mil=False)
    assert not any("mil" in c for c in off["calls"])
