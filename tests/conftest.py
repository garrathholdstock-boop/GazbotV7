"""⚠⚠⚠ NO TEST MAY SEND THE OPERATOR A TELEGRAM. EVER.

★★★ 2026-09-26, FOUND BY HIM ON A SATURDAY. He reported three alarms and asked why redundant ones
were back. `data/notify_sent.jsonl` — the send log built two days earlier — showed the truth:

    Sat 05:06:35Z  🔴 STEP AWAY FIRED — open P&L hit -240, your stop was $200
    Sat 05:06:36Z  🔴 STEP AWAY FIRED — open P&L hit +340, your take-profit was $300
    Sat 05:06:46Z  V7 — gates auto-reactivated at Paris midnight ... exhaustion_short
    ... and the identical three again at 05:10:55 and 05:13:39

THREE SUITE RUNS. Those are the exact minutes I ran `pytest tests/`. The numbers are FIXTURE VALUES
— `sa.fire("loss limit", -240.0, ...)` and `sa.fire("take profit", 340.0, ...)` — and -240/+340 never
happened; his real Friday fires were -138, -116, -144, -102. `test_weekend_gates_are_off` called
`rg.run()`, which arms a gate in a tmp fixture, sees the file change, and NOTIFIES.

⚠ THE TESTS HAD SANDBOXES AND THE SANDBOXES WERE INCOMPLETE. `_sandbox()` redirected STATE, CLAIM
and LOG — every file — and left the ALARM pointing at his phone. A sandbox that covers the writes
but not the outbound channel is not a sandbox; it just looks like one.
⚠⚠ AND I ALMOST TOLD HIM THEY WERE HISTORY. `step_away.log` showed no fire today and
`step_away.json` said disarmed, so the service was innocent and the natural conclusion was that he
was scrolling. The send log is what made it undeniable. An instrument built for one purpose caught
something else entirely, which is the argument for recording what you do rather than what you think
you do.

★ WHY THIS IS GLOBAL AND AUTOUSE rather than a fix to the three offenders: a per-test sandbox only
protects the tests somebody remembered. This is the one choke point every alert passes through
(`notify()` -> `_subprocess_send`), so a NEW test that pages him fails immediately, with this note.
⚠ It cannot be a raise. `notify()` is deliberately fail-quiet and most callers wrap it in
`except Exception: pass`, so an exception would be swallowed and the guard would read as working.
It records, and the fixture FAILS THE TEST IN TEARDOWN — which nothing can catch.
"""
import sys

import pytest

sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

_SENT: list = []


class _FakeRun:
    """What subprocess.run returns. The callers read only `.returncode`."""
    returncode = 0
    stdout = ""
    stderr = ""


@pytest.fixture(autouse=True)
def _no_telegram(monkeypatch, request):
    """Block every real send. Fail the test in teardown if one was attempted.

    ⚠⚠ PATCHED AT `subprocess.run`, NOT AT `_subprocess_send`. The first version replaced
    `_subprocess_send` and broke three tests in test_notify_delivery_is_honest.py whose SUBJECT is
    that function's honesty — they stub `subprocess.run` themselves, so they were never sending
    anything, and the guard flagged safe tests while replacing the thing under test. Patching the
    LOWER layer blocks the outbound process while leaving every notify-layer behaviour testable, and
    a test that supplies its own fake `run` simply overrides this one — correctly, because a fake
    run sends nothing either.
    ⚠ It cannot be a raise: notify() is deliberately fail-quiet and most callers wrap it in
    `except Exception: pass`, so an exception would be swallowed and the guard would READ AS WORKING
    while pages kept going out. It records, and the failure happens in TEARDOWN, which nothing can
    catch.
    """
    from gazbot7 import notify as _n

    _real_run = _n.subprocess.run

    def _blocked(cmd, *a, **kw):
        """Intercept ONLY the Telegram sender; let every other subprocess through untouched.

        ⚠⚠⚠ THIRD ITERATION, AND EACH FAILURE TAUGHT SOMETHING. (1) Patching `_subprocess_send`
        broke three tests whose SUBJECT is that function's honesty — they stub subprocess.run
        themselves and were never sending, so the guard flagged SAFE tests while replacing the thing
        under test. (2) Patching `subprocess.run` blindly then broke `grep`, `sweep` and a
        kill-tree test, because `notify.py` does a plain `import subprocess` — so `_n.subprocess` IS
        the global module and setting an attribute on it patches EVERY caller in the process.
        ★ So the guard is scoped by CONTENT, not by module: it looks at the argv for the sender
        script. A guard that blocks more than it was built to block gets switched off by whoever
        hits it next, which is worse than no guard.
        """
        try:
            argv = [str(x) for x in cmd] if isinstance(cmd, (list, tuple)) else [str(cmd)]
        except Exception:
            argv = []
        if any("notify_operator.py" in a for a in argv):
            _SENT.append(argv[-1] if argv else "?")
            return _FakeRun()
        return _real_run(cmd, *a, **kw)

    monkeypatch.setattr(_n.subprocess, "run", _blocked)

    # ★★★2026-09-26 AND NO TEST'S OUTCOME MAY DEPEND ON WHAT DAY IT IS.
    # The weekend-quiet gate fires only when the venue is shut AND the desk is flat. Adding it
    # immediately broke three tests that call notify() without an explicit `now` — they would have
    # passed Monday to Friday and failed every weekend, which is [[tests-must-not-read-the-wall-
    # clock]] for the FIFTH time in one morning (four of them were live-tape reads fixed an hour
    # earlier).
    # ⚠ Neutralised via the FLAT half, not the CALENDAR half: the gate needs both, so reporting
    # "not flat" makes it inert while leaving `venue_shut_for_the_weekend()` real for the tests whose
    # subject it is. "Not flat" is also the FAIL-OPEN direction, so a test that forgets to think
    # about this gets the speaking behaviour rather than the silent one.
    monkeypatch.setattr(_n, "desk_is_flat_and_verified", lambda: False)

    _SENT.clear()
    yield
    if _SENT and "telegram" not in request.fixturenames:
        pytest.fail(
            f"THIS TEST WOULD HAVE SENT THE OPERATOR {len(_SENT)} TELEGRAM(S):\n  "
            + "\n  ".join(m[:120] for m in _SENT)
            + "\n\nInject a sender (`notify(..., send=list.append)`) or request the `telegram` "
              "fixture if exercising the alarm is the point of the test. See tests/conftest.py.")


@pytest.fixture
def telegram():
    """For tests whose SUBJECT is the alert text. Yields the captured messages and, by being
    requested, waives the teardown failure — the waiver is explicit and greppable."""
    _SENT.clear()
    yield _SENT
