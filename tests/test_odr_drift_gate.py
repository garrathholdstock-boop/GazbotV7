"""The Open Rider's drift-direction gate.

★ THE ASYMMETRY IS THE DESIGN, AND IT IS WHAT THESE TESTS PIN.
Measured on the rider's first 4 days (n=68, tick-repriced):
  · ungated book                                   −$476.50
  · entries BEFORE the detector confirms  n=36     +$502.50  (+$14.00/tr)   <- the edge
  · gate ENTRY on confirmation (wait to trade)     −$979.00                 <- worse than nothing
  · gate DIRECTION only, after confirmation        +$603.50                 <- the shipped arm
The permission gate fails because drift confirmed on ALL FOUR days: it suppressed no losses and
deleted the profitable early window. Operator: "the fact it jumps in early is kind of its edge."

So: before confirmation the gate MUST NOT block anything. A well-meaning "fail closed" here would
silently rebuild the variant that tested worst, and no P&L number would show why.
"""
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.deciders import Bar  # noqa: E402
from gazbot7.drift import MIN_BARS, OPEN_UTC_MIN  # noqa: E402
from gazbot7.shadow import ShadowSim, ShadowVariant, _open_rider  # noqa: E402

DAY = 1786600000 // 86400 * 86400          # midnight UTC of an arbitrary day
OPEN = DAY + OPEN_UTC_MIN * 60             # 13:30 UTC


def _bars(n, start_px, step):
    """n one-minute bars from the cash open, moving `step` points each minute."""
    out = []
    for i in range(n):
        px = start_px + i * step
        out.append(Bar(OPEN + i * 60, px, px + 2, px - 2, px, 100.0))
    return out


def _variant(gated):
    return ShadowVariant(name="t", gate="clock_rider", params={}, target_r=2.0,
                         time_cap_s=45 * 60, rider_lookback_min=15, adverse_cut_atr=99.0,
                         absorption_flow_min=1e9, rider_cadence_min=5, stop_atr_mult=2.0,
                         rider_gate_drift=gated)


def _entry(gated, bars, ts):
    return ShadowSim._rider_entry(object.__new__(ShadowSim), _variant(gated), bars, ts)


def test_detector_confirms_on_a_clean_up_session():
    bars = _bars(40, 30000, 6)                      # +6pt/min, a clean drift
    r = ShadowSim._rider_drift(bars, OPEN + 40 * 60)
    assert r is not None and r.confirmed and r.direction == "UP"


def test_gate_blocks_a_counter_trend_entry_once_confirmed():
    """UP confirmed, but the 15-min lookback ticked down -> a SHORT the gate must refuse."""
    bars = _bars(40, 30000, 6)
    # i counts BACKWARDS from the last bar, so `+ i*3` makes the recent bars the LOW ones — that is
    # what flips mom negative. `- i*3` (my first attempt) leaves the tail still rising and the
    # fixture silently proves nothing.
    for i in range(1, 17):                          # a late pullback flips the raw sign
        bars[-i] = Bar(bars[-i].ts, 30200, 30252, 30100, 30200 + i * 3, 100.0)
    ts = OPEN + 40 * 60
    ungated = _entry(False, bars, ts)
    gated = _entry(True, bars, ts)
    assert ungated is not None and ungated.side == "SHORT", "setup must produce a SHORT"
    assert gated is None, "the gate must refuse a SHORT into a confirmed UP session"


def test_gate_allows_an_aligned_entry():
    bars = _bars(40, 30000, 6)
    ts = OPEN + 40 * 60
    g = _entry(True, bars, ts)
    assert g is not None and g.side == "LONG"


def test_before_confirmation_the_gate_blocks_NOTHING():
    """The load-bearing test. Too little tape to confirm (< MIN_BARS) -> gated and ungated must
    behave IDENTICALLY. Failing closed here rebuilds the −$979 permission gate."""
    bars = _bars(MIN_BARS - 1 + 16, 30000, -6)      # DOWN move, but not enough bars since the open
    short = [b for b in bars if b.ts >= OPEN][:MIN_BARS - 1]
    assert len(short) < MIN_BARS
    ts = OPEN + (MIN_BARS - 1) * 60
    # feed the full pre-open history so the lookback exists, but only sub-MIN_BARS since the open
    pre = [Bar(OPEN - (20 - i) * 60, 30100, 30102, 30098, 30100, 100.0) for i in range(20)]
    bars2 = pre + short
    assert ShadowSim._rider_drift(bars2, ts) is None, "must not confirm on too little tape"
    gated, ungated = _entry(True, bars2, ts), _entry(False, bars2, ts)
    assert gated == ungated, ("before confirmation the gate must be a NO-OP; failing closed here "
                             "rebuilds the permission gate that tested at −$979")


def test_ungated_arms_are_completely_unaffected():
    bars = _bars(40, 30000, 6)
    for i in range(1, 17):                          # same counter-trend fixture as the gate test
        bars[-i] = Bar(bars[-i].ts, 30200, 30252, 30100, 30200 + i * 3, 100.0)
    e = _entry(False, bars, OPEN + 40 * 60)
    assert e is not None and e.side == "SHORT", "the ungated twin must still take the counter trade"


def test_slate_ships_four_exact_pairs():
    vs = {v.name: v for v in _open_rider()}
    assert len(vs) == 8
    for base in ("odr_c5_s20", "odr_c5_s30", "odr_c10_s20", "odr_c10_s30"):
        g = vs[base + "_g"]
        b = vs[base]
        assert g.rider_gate_drift is True and b.rider_gate_drift is False
        # every other field must match, or the pair cannot attribute a difference to the gate
        for f in ("rider_cadence_min", "stop_atr_mult", "target_r", "time_cap_s",
                  "rider_lookback_min", "rider_win_start_s", "rider_win_end_s"):
            assert getattr(g, f) == getattr(b, f), f"{base}: {f} differs — pair is confounded"
