"""THE GATEWAY WATCH — restart on the climb, and NEVER on an open position.

★★ THE CONDITION (measured 2026-09-18): IB Gateway leaks sockets in CLOSE-WAIT until the 50-slot
accept queue fills. Connections already open keep working while every NEW one hangs — so every
health light stays green while the rider, the watchdog and the reconciler go blind. 25 episodes,
ten of the last seventeen days, ~33 hours. One ate a Claim pressed on a +$262 position.
"""
import json
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")

import gateway_watch as gw

SRC = "/home/alphabot/gazbot7/scripts/gateway_watch.py"


def test_it_refuses_to_restart_while_a_position_is_open(tmp_path, monkeypatch):
    """⚠⚠⚠ THE SAFETY PROPERTY. A restart blinds every consumer for ~15s. Doing that to a naked
    4-lot position to fix something that has not yet bitten is the cure causing the disease."""
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"qty": 4.0, "closed": False}))
    monkeypatch.setattr(gw, "RIDER", str(p))
    flat, why = gw.desk_is_flat()
    assert flat is False and "4" in why


def test_an_unreadable_state_is_NOT_treated_as_flat(tmp_path, monkeypatch):
    """⚠⚠ NOT KNOWING IS NOT THE SAME AS FLAT. A missing or corrupt state file must block the
    restart, not wave it through — that is the instrument-reports-healthy failure in miniature."""
    monkeypatch.setattr(gw, "RIDER", str(tmp_path / "does-not-exist.json"))
    flat, why = gw.desk_is_flat()
    assert flat is False and "blind" in why.lower()


def test_a_closed_position_is_flat(tmp_path, monkeypatch):
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"qty": 4.0, "closed": True}))
    monkeypatch.setattr(gw, "RIDER", str(p))
    assert gw.desk_is_flat()[0] is True


def test_it_trips_on_the_CLIMB_not_the_wedge():
    """★ The queue is 50. Tripping AT 50 means acting after the outage has already started."""
    assert gw.TRIP < gw.BACKLOG, "the trip point is not below the backlog — that is too late"
    assert gw.TRIP >= 20, "too twitchy: a transient handful of CLOSE-WAIT is normal"


def test_there_is_a_cooldown():
    """⚠ A restart that does not clear the condition must not become a restart LOOP. The thing that
    takes a desk down is never the first restart, it is the fourth."""
    assert gw.COOLDOWN_S >= 1800
    assert "cooling down" in open(SRC).read()


def test_declining_is_LOUD():
    """⚠ A guard that declines in silence is a guard nobody knows they lack."""
    src = open(SRC).read()
    assert "NOT RESTARTING" in src


def test_it_records_which_jobs_were_running():
    """★★ THE WHOLE POINT OF THE SERIES. 18 of 25 episodes start 18:00-00:00Z, where driftlab,
    backfill and the overnight research all hammer historical data. That is a HYPOTHESIS; this
    logs the evidence to settle it rather than assuming."""
    src = open(SRC).read()
    for job in ("backfill_history", "driftlab", "overnight"):
        assert job in src, f"the series does not record whether {job} was running"
    s = gw.sample()
    assert "close_wait" in s and "acceptq" in s and "ts" in s


def test_it_samples_both_the_leak_and_the_outage():
    """⚠ CLOSE-WAIT is the leak ACCUMULATING; the accept queue filling is the moment it becomes an
    outage. Logging only one of them loses the lead time that makes this worth running."""
    s = gw.sample()
    assert s["close_wait"] is not None and s["acceptq"] is not None and s["backlog"] == 50


def test_the_ruled_out_causes_are_written_down():
    """★ So nobody re-chases them. Four hypotheses were eliminated with evidence on 2026-09-18."""
    src = open(SRC).read()
    for gone in ("subscriptions", "rogue client", "nightly reset", "per-connection leak"):
        assert gone.split()[0].lower() in src.lower()


# ── THE PER-EPISODE CAP (2026-09-26 audit) ───────────────────────────────────────────────────
# ★★★ BLIND_MAX was a LIFETIME budget. `blind_restarts` was incremented on every blind rescue and
# never reset, so after three episodes EVER — months apart, each one legitimately rescued — the
# guard would stop restarting a blind, holding desk and only page. Live state carried 1 of 3 when
# the audit ran, i.e. two episodes from disarming itself with nothing saying so.

def test_a_cleared_episode_RESTORES_the_restart_budget():
    """★ THE INVARIANT: the cap counts tries WITHIN one episode, never episodes over a lifetime.
    Stated as behaviour, not as the line that implements it — the clear path may move."""
    st = {"blind_since": "2026-09-26T10:00:00+00:00", "blind_restarts": 3,
          "last_blind_restart": "2026-09-26T10:05:00+00:00"}
    out = gw.clear_blind(st)
    assert out["blind_restarts"] == 0, "a cleared episode must hand the budget back"
    assert out["blind_since"] is None


def test_the_cap_cannot_be_exhausted_ACROSS_episodes():
    """Two full episodes, each exhausting the cap. The SECOND must still be able to act — that is
    the whole difference between a per-episode cap and a lifetime one."""
    st = {}
    for episode in (1, 2):
        st["blind_since"] = "2026-09-26T10:00:00+00:00"
        for _ in range(gw.BLIND_MAX):
            st["blind_restarts"] = int(st.get("blind_restarts") or 0) + 1
        assert int(st["blind_restarts"]) >= gw.BLIND_MAX, f"episode {episode} should hit the cap"
        st = gw.clear_blind(st)
        assert int(st["blind_restarts"]) < gw.BLIND_MAX, (
            f"after episode {episode} cleared, the guard must be able to act again")


def test_the_within_episode_loop_is_still_held():
    """⚠ The fix must not weaken the thing the cap was written for: two independent brakes remain,
    a cooldown between tries inside an episode and the cap itself.

    ⚠⚠ 2026-09-26 review: this used to assert only `BLIND_COOLDOWN_S > 0` and `BLIND_MAX >= 1` —
    constants that would pass with the checks that USE them deleted. It now reads the decision block
    with comments stripped, so the guard has to be in the code path and not in the prose about it.
    """
    assert gw.BLIND_COOLDOWN_S > 0, "an intra-episode cooldown must still exist"
    assert gw.BLIND_MAX >= 1, "the per-episode cap must still exist"
    src = open(SRC).read()
    block = src.split("blind, bwhy = blind_and_holding()", 1)[1]
    code = "\n".join(l for l in block.splitlines() if not l.strip().startswith("#"))
    assert "nres >= BLIND_MAX" in code, "the cap must be TESTED in the decision path"
    assert "bage < BLIND_COOLDOWN_S" in code, "the cooldown must be TESTED in the decision path"
    # and the restart must sit behind both
    assert code.index("nres >= BLIND_MAX") < code.index("restart(")
    assert code.index("bage < BLIND_COOLDOWN_S") < code.index("restart(")


def test_clear_blind_is_actually_CALLED_from_the_loop():
    """⚠ The sibling test reimplements the increment inline, so it never proves `clear_blind` is
    wired in. This does: the clear branch must call it."""
    src = open(SRC).read()
    tail = src.split('elif st.get("blind_since"):', 1)[1].split("if once:", 1)[0]
    code = "\n".join(l for l in tail.splitlines() if not l.strip().startswith("#"))
    assert "clear_blind(st)" in code


def test_clearing_says_so_in_the_log():
    """A guard that silently hands itself a fresh budget is the same class of problem as one that
    silently runs out. The transition is logged."""
    src = open(SRC).read()
    assert "budget restored" in src
