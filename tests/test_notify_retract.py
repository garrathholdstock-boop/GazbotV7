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
