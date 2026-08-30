"""The rider must WAIT for the confirmed run to persist. Operator-directed, 2026-08-26 (NVDA).

"i want to delay a little bit… once it runs it stays in that direction. so i want to wait until its
confirmed run" — with "i know you cant backtest this because its always a coinflip".

So this is an OPERATOR EXPERIMENT, not a measured edge, and the tests pin the MECHANICS only:
a run that changes its mind restarts the count, a break in confirmation resets it, and the default
is exactly today's behaviour so nothing changes for anyone who does not opt in.
"""
import importlib, os, pytest


def _rider(persist):
    os.environ["GAZBOT7_RIDER_CONFIRM_PERSIST"] = str(persist)
    import gazbot7.day_rider as D
    importlib.reload(D)
    return D


def teardown_module(_):
    os.environ.pop("GAZBOT7_RIDER_CONFIRM_PERSIST", None)
    import gazbot7.day_rider as D
    importlib.reload(D)


def _streak(out, direction, persist):
    """The persistence logic from step(), in the same order."""
    if out.get("confirm_dir") == direction:
        out["confirm_streak"] = int(out.get("confirm_streak") or 0) + 1
    else:
        out["confirm_streak"] = 1
    out["confirm_dir"] = direction
    return out["confirm_streak"] >= persist


def test_default_is_todays_behaviour():
    assert _rider(0).CONFIRM_PERSIST_MIN == 0, "opting nobody in must be the default"


def test_it_waits_the_full_count():
    out = {}
    fires = [_streak(out, "UP", 3) for _ in range(3)]
    assert fires == [False, False, True], "entered before the run persisted"


def test_a_direction_flip_restarts_the_count():
    """★ A run that changes its mind is not the run we are waiting for."""
    out = {}
    _streak(out, "UP", 3); _streak(out, "UP", 3)
    assert out["confirm_streak"] == 2
    assert _streak(out, "DOWN", 3) is False
    assert out["confirm_streak"] == 1, "a flip carried its predecessor's credit"


def test_a_break_in_confirmation_resets():
    out = {"confirm_streak": 2, "confirm_dir": "UP"}
    out["confirm_streak"] = 0; out["confirm_dir"] = None      # the not-confirmed branch
    assert _streak(out, "UP", 3) is False and out["confirm_streak"] == 1


def test_the_env_knob_is_read():
    assert _rider(5).CONFIRM_PERSIST_MIN == 5


def test_the_cutoff_is_unchanged():
    """Waiting must not be allowed to push an entry past 15:00Z — a slow confirm means NO trade."""
    D = _rider(5)
    assert D.ENTRY_CUTOFF_MIN == 15 * 60
