"""The Friday body runs as a dependency-aware ROLLING POOL. 2026-08-30.

Replaces wave batching, which was a barrier: every phase capped at the wave's share, and the next
wave blocked on the slowest member. With 13 phases in 4 waves that capped a 240m-declaring section
at 76m while a 30m section finished and left its worker idle. Observed 08-29: wave 1 ran ~3h with a
free slot most of it.

The budget was never the real problem — 4 workers x 305m = 1,220 agent-minutes against 975m of
declared demand. Waves spent that capacity in equal slices instead of by need.
"""
import importlib.util, threading, time, types, pytest

spec = importlib.util.spec_from_file_location("sr", "/home/alphabot/gazbot7/scripts/friday/serial_runner.py")
sr = importlib.util.module_from_spec(spec); spec.loader.exec_module(sr)


def P(key, deps=(), t=3600):
    return {"key": key, "deps": list(deps), "timeout_s": t, "artifact": f"/tmp/{key}"}


@pytest.fixture(autouse=True)
def _no_mem_wait(monkeypatch):
    monkeypatch.setattr(sr, "_free_mb", lambda: 999999)


def _pool(body, workers=4, budget_s=100000, **kw):
    return sr.run_pool(body, body, time.time() + budget_s, 0, workers, **kw)


def test_every_phase_runs_exactly_once(monkeypatch):
    seen = []
    monkeypatch.setattr(sr, "run_phase", lambda q, cap: seen.append(q["key"]) or True)
    res = _pool([P(f"s{i}") for i in range(13)])
    assert len(seen) == 13 and len(set(seen)) == 13
    assert all(res.values())


def test_a_free_worker_is_reused_immediately(monkeypatch):
    """★ THE POINT OF THE POOL. A fast phase must not idle its worker until a barrier."""
    live = peak = 0
    lock = threading.Lock()

    def rp(q, cap):
        nonlocal live, peak
        with lock:
            live += 1; peak = max(peak, live)
        time.sleep(0.05 if q["key"].startswith("fast") else 0.4)
        with lock:
            live -= 1
        return True

    monkeypatch.setattr(sr, "run_phase", rp)
    body = [P("slow1"), P("slow2")] + [P(f"fast{i}") for i in range(8)]
    t0 = time.time(); _pool(body, workers=2); took = time.time() - t0
    assert peak == 2, f"pool never filled its 2 slots (peak {peak})"
    # 2 slow (0.4) + 8 fast (0.05) over 2 workers ~= 0.6s. A barrier of 5 waves would be ~2.0s.
    assert took < 1.4, f"took {took:.2f}s — workers were idling like a barrier"


def test_a_long_phase_gets_its_full_declared_time(monkeypatch):
    """Under waves this was capped at the wave share and timed out."""
    caps = {}
    monkeypatch.setattr(sr, "run_phase", lambda q, cap: caps.__setitem__(q["key"], cap) or True)
    _pool([P("huge", t=240 * 60), P("small", t=30 * 60)], workers=4, budget_s=305 * 60)
    assert caps["huge"] >= 200 * 60, f"long phase capped at {caps['huge']/60:.0f}m"


def test_dependencies_are_honoured(monkeypatch):
    order = []
    monkeypatch.setattr(sr, "run_phase", lambda q, cap: order.append(q["key"]) or True)
    _pool([P("gf_A"), P("gf_B"), P("movement3", deps=["gf_A", "gf_B"])], workers=4)
    assert order.index("movement3") > order.index("gf_A")
    assert order.index("movement3") > order.index("gf_B")


def test_a_dep_outside_the_body_does_not_deadlock(monkeypatch):
    """A greenfield cluster rotated out this week must not block movement3 forever."""
    monkeypatch.setattr(sr, "run_phase", lambda q, cap: True)
    res = _pool([P("gf_A"), P("movement3", deps=["gf_A", "gf_ROTATED_OUT"])])
    assert set(res) == {"gf_A", "movement3"}


def test_a_starved_phase_is_skipped_not_handed_a_sliver(monkeypatch):
    monkeypatch.setattr(sr, "run_phase", lambda q, cap: True)
    logs = []
    res = sr.run_pool([P("a"), P("b")], [P("a"), P("b")], time.time() + 60, 0, 1, logs.append)
    assert res["b"] is False or res["a"] is False
    assert any("SKIP" in m or "BUDGET" in m for m in logs)


def test_a_failing_phase_does_not_stall_the_pool(monkeypatch):
    monkeypatch.setattr(sr, "run_phase", lambda q, cap: q["key"] != "bad")
    res = _pool([P("bad"), P("ok1"), P("ok2")])
    assert res["bad"] is False and res["ok1"] and res["ok2"]


def test_kill_tree_actually_kills_a_grandchild():
    """★ ORPHAN REAPING, EXECUTED — not grepped. Signalling only the direct child leaves
    grandchildren reparented to PID 1: the 4.4GB orphan of 08-29 that filled swap, drove memory
    pressure to 93% and most plausibly starved three phases into timing out with nothing.
    A source grep would pass on code that never runs; this spawns the real shape (a child that
    forks its own background process) and asserts the whole GROUP dies.
    """
    import os, subprocess, time
    proc = subprocess.Popen(["bash", "-c", "sleep 600 & sleep 600"], start_new_session=True)
    time.sleep(1)
    pgid = os.getpgid(proc.pid)
    assert len(subprocess.run(["pgrep", "-g", str(pgid)], capture_output=True,
                              text=True).stdout.split()) >= 2, "fixture did not spawn a grandchild"
    sr._kill_tree(proc)
    proc.wait()                       # collect the zombie, as run_phase's communicate() does
    time.sleep(0.5)
    left = subprocess.run(["pgrep", "-g", str(pgid)], capture_output=True, text=True).stdout.split()
    assert not left, f"{len(left)} process(es) survived the group kill — orphans"


def test_the_group_plumbing_is_present():
    src = open("/home/alphabot/gazbot7/scripts/friday/serial_runner.py").read()
    assert "start_new_session=True" in src and "os.killpg" in src
    assert "SIGTERM" in src and "SIGKILL" in src, "no TERM->KILL escalation"
