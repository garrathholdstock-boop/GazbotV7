"""Direction-router — regime detection, hysteresis, and the gate-off mapping."""

from __future__ import annotations

from gazbot7 import direction_router as dr


def test_er_net_trend_vs_chop():
    trend = dr.er_net([100 + i for i in range(30)])          # straight ramp
    chop = dr.er_net([100 + (i % 2) for i in range(30)])     # alternating, no progress
    assert trend[0] > 0.9 and trend[1] > 0        # ER~1, net up
    assert chop[0] < 0.1                          # ER~0


def test_desired_off_mapping():
    assert dr.desired_off("TREND_DOWN") == set(dr.DOWN_OFF)   # long-faders benched
    assert dr.desired_off("TREND_UP") == set(dr.UP_OFF)       # short-faders benched
    assert dr.desired_off("CHOP") == set()                    # everything on
    # momentum gates are NEVER in the managed off-sets
    assert "thrust_short" not in dr.MANAGED
    assert "grind_long" not in dr.MANAGED


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
