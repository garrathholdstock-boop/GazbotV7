"""RECORDING SENT MESSAGE IDS, SO AN ERRONEOUS ALERT CAN BE RETRACTED.

★★★2026-09-24. Operator: "yes record the message ids so we can delete them." Telegram deletes a
bot's own message ONLY by `message_id`, and notify_operator.py threw the API response away, so
nothing this desk had ever said was addressable.

⚠ The recording is a CONVENIENCE. Delivery is the job. These tests exist mostly to guarantee the
convenience can never damage the job.
"""
import json
import os
import subprocess
import sys

SENDER = "/home/alphabot/gazbot7/scripts/notify_operator.py"
TOOL = "/home/alphabot/gazbot7/scripts/notify_delete.py"


def _src(p):
    return open(p, encoding="utf-8").read()


def test_recording_can_never_fail_a_delivered_alert():
    """⚠⚠ THE ONLY ONE THAT REALLY MATTERS. A bookkeeping fault must not turn a DELIVERED alert
    into a reported failure — the caller would then fall through to the legacy sender and send it
    twice, or log an alarm outage that did not happen."""
    src = _src(SENDER)
    body = src.split("def _record(", 1)[1].split("\ndef ", 1)[0]
    assert "except Exception:\n        pass" in body, "_record must swallow everything"
    assert "return" not in body.split("try:", 1)[1].split("except", 1)[0], \
        "_record must not return a value the caller could branch on"
    main = src.split("def main(", 1)[1]
    # the record call sits AFTER ok is decided, and ok is never reassigned from it
    assert main.index("ok = resp.get") < main.index("_record(")


def test_it_is_only_recorded_when_telegram_confirmed():
    """⚠ An id recorded for a message that never arrived is a retraction offer for nothing."""
    main = _src(SENDER).split("def main(", 1)[1]
    seg = main.split("else:", 1)[1].split("return", 1)[0]
    assert "_record(" in seg, "_record must sit on the ok branch, not run unconditionally"


def test_the_log_is_writable_by_both_users_that_send():
    """⚠⚠ rider_peak_watch runs as ROOT and is the highest-volume sender; day_rider, web,
    step_away and gate_reactivate run as ALPHABOT. A log created 0644 by whichever sent first is
    silently unwritable by the other and we keep exactly half the ids with nothing reporting it —
    the 2026-08-21 `.notify_env` shape, which cost ~12 hours of silent alarm outage."""
    assert "0o666" in _src(SENDER)
    assert "os.chmod(tmp, 0o666)" in _src(SENDER), "os.open is still subject to umask"


def test_the_write_is_atomic():
    """⚠ A torn log loses EVERY id, not one — it is rewritten whole on each append to prune."""
    assert "os.replace(tmp, SENT_LOG)" in _src(SENDER)


def test_the_tool_can_only_delete_never_send_or_edit():
    """⚠⚠⚠ A desk that can silently REWRITE its own alarm history is far worse than one that
    leaves a wrong message standing. Delete, or leave it."""
    src = _src(TOOL)
    for forbidden in ("sendMessage", "editMessageText", "editMessageCaption"):
        assert forbidden not in src, f"the retraction tool references {forbidden}"
    assert "deleteMessage" in src


def test_a_bulk_match_will_not_fire_without_confirmation():
    """⚠ A deletion is irreversible and removes something from HIS chat. --id is already one
    explicit target; --match could hit many, so it prints and stops."""
    src = _src(TOOL)
    assert "if not a.yes:" in src and "WOULD DELETE" in src


def test_the_48h_limit_is_stated_before_it_is_hit():
    """⚠ Telegram refuses to delete a message older than 48h. Discovering that as an opaque API
    error is how a limit becomes a surprise — --list marks every row LIVE or EXPIRED."""
    src = _src(TOOL)
    assert "DELETE_WINDOW_S = 48 * 3600" in src
    assert "EXPIRED" in src and "LIVE" in src


def test_the_tool_runs_and_lists():
    r = subprocess.run([sys.executable, TOOL, "--list"], capture_output=True, text=True,
                       cwd="/home/alphabot/gazbot7")
    assert r.returncode == 0, r.stderr
    assert "message(s)" in r.stdout or "nothing recorded" in r.stdout


def test_an_unlogged_id_is_still_deletable():
    """★ The log starts empty on 2026-09-24. An id he reads off some other source must not be
    refused just because we have no row for it."""
    assert "not in the log" in _src(TOOL)


# ── NO TEST MAY PAGE THE OPERATOR (2026-09-26) ───────────────────────────────────────────────────
# ★★★ He found this on a Saturday: three alarms, and `data/notify_sent.jsonl` proved they went out
# at 05:06:35, 05:10:55 and 05:13:39 — the exact minutes I ran `pytest tests/`. The numbers (-240,
# +340) were FIXTURE VALUES; his real Friday fires were -138/-116/-144/-102.
# ⚠⚠ THE TESTS HAD SANDBOXES AND THE SANDBOXES WERE INCOMPLETE — `_sandbox()` redirected STATE,
# CLAIM and LOG, every file, and left the ALARM pointing at his phone. A sandbox covering the writes
# but not the outbound channel is not a sandbox, it only looks like one.

def test_a_global_autouse_guard_blocks_every_real_send():
    """★ GLOBAL, not per-test: a sandbox only protects the tests somebody remembered. This sits on
    the single choke point every alert passes through, so a NEW test that pages him fails at once."""
    c = open("/home/alphabot/gazbot7/tests/conftest.py", encoding="utf-8").read()
    assert "autouse=True" in c
    assert "_n.subprocess" in c, "it must patch the outbound process call"
    # ⚠ AND NOT `_subprocess_send` ITSELF. The first version did, and broke three tests in
    # test_notify_delivery_is_honest.py whose SUBJECT is that function's honesty — they stub
    # subprocess.run themselves and were never sending, so the guard flagged SAFE tests while
    # replacing the thing under test. Guard the layer BELOW the behaviour you still want to test.
    assert 'setattr(_n, "_subprocess_send"' not in c


def test_the_guard_cannot_be_swallowed_by_a_fail_quiet_caller():
    """⚠⚠ IT MUST NOT RAISE. notify() is deliberately fail-quiet and most callers wrap it in
    `except Exception: pass`, so an exception would be caught and the guard would READ AS WORKING
    while pages kept going out. It records, and fails in TEARDOWN, which nothing can catch."""
    c = open("/home/alphabot/gazbot7/tests/conftest.py", encoding="utf-8").read()
    blocked = c.split("def _blocked(", 1)[1].split("\n    monkeypatch", 1)[0]
    assert "raise" not in blocked.replace("raise a", ""), "the blocker must not raise"
    assert "_FakeRun()" in blocked, "it must return a success-shaped result, not an exception"
    assert "pytest.fail(" in c.split("yield", 1)[1], "the failure must happen after the test body"


def test_the_guard_only_intercepts_the_SENDER_and_nothing_else():
    """⚠⚠ SECOND ITERATION FAILURE, WORTH PINNING. Patching `subprocess.run` blindly broke `grep`,
    `sweep` and a kill-tree test — `notify.py` does a plain `import subprocess`, so `_n.subprocess`
    IS the global module and setting an attribute on it patches EVERY caller in the process.
    ★ A guard that blocks more than it was built to block gets switched off by whoever hits it
    next, which is worse than no guard at all. So it is scoped by argv content, and everything else
    passes through to the real subprocess.run."""
    c = open("/home/alphabot/gazbot7/tests/conftest.py", encoding="utf-8").read()
    blocked = c.split("def _blocked(", 1)[1].split("\n    monkeypatch", 1)[0]
    assert 'notify_operator.py' in blocked, "it must key on the sender script"
    assert "_real_run(cmd" in blocked, "every other subprocess must reach the real run()"


def test_the_waiver_is_explicit_and_greppable():
    """★ A test whose SUBJECT is the alert text asks for the `telegram` fixture. Requesting it is
    the waiver — visible in the signature, findable with grep, never a silent global flag."""
    c = open("/home/alphabot/gazbot7/tests/conftest.py", encoding="utf-8").read()
    assert '"telegram" not in request.fixturenames' in c
    import subprocess
    out = subprocess.run(["grep", "-rln", "telegram)", "/home/alphabot/gazbot7/tests"],
                         capture_output=True, text=True).stdout.split()
    assert out, "no test declares the waiver — either it is unused or the mechanism changed"
