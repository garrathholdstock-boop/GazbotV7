"""Direction-router — regime detection, hysteresis, and the gate-off mapping."""

from __future__ import annotations

import datetime as dt

from gazbot7 import direction_router as dr


def test_er_net_trend_vs_chop():
    trend = dr.er_net([100 + i for i in range(30)])          # straight ramp
    chop = dr.er_net([100 + (i % 2) for i in range(30)])     # alternating, no progress
    assert trend[0] > 0.9 and trend[1] > 0        # ER~1, net up
    assert chop[0] < 0.1                          # ER~0


def test_desired_off_mapping():
    assert dr.desired_off("TREND_DOWN") == set(dr.DOWN_OFF)   # long-faders benched
    assert dr.desired_off("TREND_UP") == set(dr.UP_OFF)       # short-faders benched
    assert dr.desired_off("CHOP") == set(dr.CHOP_OFF)         # ★momentum gates benched in chop
    assert {"grind_long", "abs_veto_long", "abs_veto_short"} == set(dr.CHOP_OFF)
    assert dr.CHOP_OFF <= dr.MANAGED and dr.DOWN_OFF <= dr.MANAGED and dr.UP_OFF <= dr.MANAGED
    # momentum gates ARE managed now (chop-benched) — but ONLY via CHOP_OFF, never the trend off-sets
    assert "grind_long" in dr.MANAGED and "grind_long" in dr.CHOP_OFF
    assert "grind_long" not in dr.DOWN_OFF and "grind_long" not in dr.UP_OFF
    assert "thrust_short" not in dr.MANAGED   # retired gate, unmanaged


def _raw(minutes, closes, t):
    er, net = dr.er_net([closes[i] for i in range(len(minutes)) if minutes[i] <= t])
    if er >= dr.ER_TREND and net >= dr.NET_MIN:
        return "TREND_UP"
    if er >= dr.ER_TREND and net <= -dr.NET_MIN:
        return "TREND_DOWN"
    return "CHOP"


def test_replay_detects_sustained_trend():
    minutes = [i * 60 for i in range(120)]
    closes = [100.0] * 60 + [100.0 + 2 * (i + 1) for i in range(60)]   # flat, then a strong ramp up
    marks = dr.replay_marks(minutes, closes, 0, minutes[-1])
    assert marks[-1][1] == "TREND_UP"    # the sustained ramp is eventually detected


def test_replay_hysteresis_needs_two_marks():
    # the FIRST mark whose raw signal is a trend must NOT flip the effective state (run=1);
    # only the SECOND consecutive agreeing mark flips it (the whipsaw guard).
    minutes = [i * 60 for i in range(120)]
    closes = [100.0] * 60 + [100.0 + 2 * (i + 1) for i in range(60)]
    marks = dr.replay_marks(minutes, closes, 0, minutes[-1])
    j = next(i for i, m in enumerate(marks) if _raw(minutes, closes, m[0]) == "TREND_UP")
    assert marks[j][1] == "CHOP"          # 1st trend mark: effective still CHOP (held)
    assert marks[j + 1][1] == "TREND_UP"  # 2nd consecutive: now it flips


def test_fast_exit_leaves_a_trend_sooner():
    # V-shape: chop warmup → a down leg (enters TREND_DOWN) → an up reversal. The sticky-exit fix
    # (fast_exit=True) must spend FEWER marks stuck in TREND_DOWN than the shipped sticky logic,
    # while still ENTERING the down-trend in the first place (the enter-lag/whipsaw guard is unchanged).
    minutes = [i * 60 for i in range(240)]   # == len(closes): 40 + 60 + 120 + 20
    # long steady down leg (enters TREND_DOWN over several marks) then a SLOW up recovery: the sticky
    # logic over-holds TREND_DOWN one extra mark through the gentle reversal; fast_exit releases sooner.
    closes = ([300.0] * 40 + [300.0 - 3 * i for i in range(1, 61)]
              + [120.0 + 1.5 * i for i in range(1, 121)] + [300.0] * 20)
    m_now = dr.replay_marks(minutes, closes, 0, minutes[-1], fast_exit=False)
    m_fix = dr.replay_marks(minutes, closes, 0, minutes[-1], fast_exit=True)
    down_now = sum(1 for _, s, _, _ in m_now if s == "TREND_DOWN")
    down_fix = sum(1 for _, s, _, _ in m_fix if s == "TREND_DOWN")
    assert down_now >= 1 and down_fix >= 1   # both still detect the down leg
    assert down_fix < down_now               # the fix exits the down-trend sooner


def test_shipped_default_is_unchanged():
    # the live default (fast_exit=False) must reproduce the shipped sticky behaviour bit-for-bit
    minutes = [i * 60 for i in range(120)]
    closes = [100.0] * 60 + [100.0 + 2 * (i + 1) for i in range(60)]
    default = dr.replay_marks(minutes, closes, 0, minutes[-1])
    explicit = dr.replay_marks(minutes, closes, 0, minutes[-1], fast_exit=False)
    assert [m[1] for m in default] == [m[1] for m in explicit]


# ── US-open window override (2026-07-28): momentum not benched across the cash open ──
def test_in_open_window_bounds():
    def at(h, m):
        return dt.datetime(2026, 7, 28, h, m, tzinfo=dt.UTC)
    assert dr.in_open_window(at(13, 15)) and dr.in_open_window(at(13, 30)) and dr.in_open_window(at(13, 59))
    assert not dr.in_open_window(at(13, 14))   # before the window (13:15 UTC = 15:15 Paris)
    assert not dr.in_open_window(at(14, 0))     # window is [13:15, 14:00)
    assert not dr.in_open_window(at(10, 0))     # mid-morning, no override


def test_open_window_suppresses_the_momentum_chop_bench():
    # normally CHOP benches the momentum gates; the open-window override removes them → momentum ON.
    off_chop = dr.desired_off("CHOP")
    assert dr.CHOP_OFF <= off_chop                    # momentum benched in chop normally
    assert (off_chop - dr.CHOP_OFF) == set()          # open window → none of CHOP_OFF benched
    # a TREND_UP open still benches the counter-fader (rgv_short), momentum was never in that set anyway
    assert (dr.desired_off("TREND_UP") - dr.CHOP_OFF) == set(dr.UP_OFF)
