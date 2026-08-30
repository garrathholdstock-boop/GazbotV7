"""The Friday body must run in dependency-aware waves. 2026-08-29.

Operator: "i still dont understand why we are hitting limits... it can basically start straight away
and churn away all night. you know the server and ram we have. just design it to churn within those
limits and make sure it works."

He was right: sections ran ONE AT A TIME because the design assumed ~2.3GB per agent. Measured on a
live run: 465MB per agent, 1,435MB peak for the whole job, against a 4,608MB ceiling. Four at once
is ~2.8GB. Serial was costing 13 sections x 23m = 299m against a 166m budget — the direct cause of
four SKIPPED and eight unbuilt on 08-28.
"""
import importlib.util, pytest

spec = importlib.util.spec_from_file_location("sr", "/home/alphabot/gazbot7/scripts/friday/serial_runner.py")
sr = importlib.util.module_from_spec(spec); spec.loader.exec_module(sr)


def P(key, deps=(), t=3600):
    return {"key": key, "deps": list(deps), "timeout_s": t, "artifact": f"/tmp/{key}"}


def test_independent_phases_pack_into_full_waves():
    body = [P(f"s{i}") for i in range(13)]
    waves = sr.plan_waves(body, 4)
    assert [len(w) for w in waves] == [4, 4, 4, 1]
    assert sum(len(w) for w in waves) == 13, "a section was lost by the scheduler"


def test_a_dependent_phase_never_runs_beside_its_inputs():
    """★ movement3 and gf_report consume every greenfield cluster."""
    body = [P("gf_A"), P("gf_B"), P("movement3", deps=["gf_A", "gf_B"])]
    waves = sr.plan_waves(body, 4)
    where = {q["key"]: i for i, w in enumerate(waves) for q in w}
    assert where["movement3"] > where["gf_A"] and where["movement3"] > where["gf_B"]


def test_a_dep_outside_the_body_does_not_stall_the_schedule():
    """A greenfield cluster rotated out this week must not block movement3 forever."""
    body = [P("gf_A"), P("movement3", deps=["gf_A", "gf_ROTATED_OUT"])]
    waves = sr.plan_waves(body, 4)
    assert sum(len(w) for w in waves) == 2, "rotation deadlocked the scheduler"


def test_every_phase_is_scheduled_exactly_once():
    body = [P(f"s{i}") for i in range(7)] + [P("m3", deps=[f"s{i}" for i in range(7)])]
    keys = [q["key"] for w in sr.plan_waves(body, 3) for q in w]
    assert sorted(keys) == sorted(q["key"] for q in body)
    assert len(keys) == len(set(keys)), "a phase was scheduled twice"


def test_the_memory_gauge_reads_the_real_box():
    mb = sr._free_mb()
    assert 200 < mb < 200000, f"implausible free-memory reading: {mb}MB"


def test_the_memory_floor_is_set_below_what_a_wave_needs():
    """4 agents at ~465MB is ~1.9GB; the floor must leave the desk room, not block every launch."""
    assert 500 <= sr.MIN_FREE_MB <= 2500


def test_run_wave_runs_concurrently_and_reports_each_phase(monkeypatch):
    """★ EXECUTED, not inspected — a scheduler that silently runs serially looks identical here."""
    import threading, time
    live, peak, lock = 0, 0, threading.Lock()

    def fake_run_phase(p, cap):
        nonlocal live, peak
        with lock:
            live += 1; peak = max(peak, live)
        time.sleep(0.25)
        with lock:
            live -= 1
        return p["key"] != "bad"

    monkeypatch.setattr(sr, "run_phase", fake_run_phase)
    monkeypatch.setattr(sr, "_free_mb", lambda: 99999)
    res = sr.run_wave([P("a"), P("b"), P("c"), P("bad")], 60, 4)
    assert peak >= 2, f"wave ran serially (peak concurrency {peak})"
    assert res == {"a": True, "b": True, "c": True, "bad": False}


def test_the_wave_waits_when_memory_is_tight(monkeypatch):
    calls = {"n": 0}

    def tight():
        calls["n"] += 1
        return 99999 if calls["n"] > 2 else 10      # first two reads are below the floor

    monkeypatch.setattr(sr, "_free_mb", tight)
    monkeypatch.setattr(sr, "run_phase", lambda p, cap: True)
    monkeypatch.setattr(sr.time, "sleep", lambda s: None)
    assert sr.run_wave([P("a")], 60, 1) == {"a": True}
    assert calls["n"] > 1, "launched without ever re-checking memory"
