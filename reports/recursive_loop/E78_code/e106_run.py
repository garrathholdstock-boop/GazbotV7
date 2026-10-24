"""E106 (from e105_run.py; one DAY per process because S.WIN_START_MIN is a module global): usage e106_run.py gates | e106_run.py DAY START_MIN
E96: the v1.02 hybrid's ENTRY SOURCE (Claude S1b, BRIEF_V2, empty rules, self-aware page) run over the AFTERNOON 13:30Z-19:55Z.
READ-ONLY replay: simulated fills, no order path, no live file touched. Imports sim_week_recursive; patches only its window constants
and applies the SAME text rewrite hybrid_robot.ext_text applies on the live EXT session (13:30Z -> 19:55Z).
NEVER import e6_detector_t3a here: it sets S.WIN_END_MIN=20:40 at import. Scoring is a separate process (e96_score.py)."""
import sys, os, re, json, time, datetime as dt, threading, concurrent.futures as cf
GB = "/home/alphabot/gazbot7"
sys.path.insert(0, GB + "/scripts"); sys.path.insert(0, GB + "/src")
import sim_week_recursive as S

PM_END = 19 * 60 + 55
CUTS = {"2026-10-21": 8 * 60 + 50, "2026-10-22": 5 * 60 + 25, "2026-10-23": 13 * 60 + 30}
S.WIN_END_MIN = PM_END
TAG = "e106_post"
DAYS = "2026-10-21 2026-10-22 2026-10-23".split()
END_TXT = f"{PM_END // 60:02d}:{PM_END % 60:02d}Z"
_orig_ask = S.ask
def _ask(prompt, timeout=180):
    return _orig_ask(prompt.replace("13:30Z", END_TXT), timeout)      # == hybrid_robot.ext_text (minutes-left is computed by context() off the patched constant)
S.ask = _ask

def avail_mb():
    for l in open("/proc/meminfo"):
        if l.startswith("MemAvailable"): return int(l.split()[1]) // 1024
    return 99999

def clean(day):
    p = f"{S.OUT}/{TAG}_{day}.json"
    if not os.path.exists(p): return False
    r = json.load(open(p)); c = r.get("calls") or []
    return bool(c) and r.get("line") == "v2" and sum(1 for x in c if x.get("error")) / len(c) <= S.POISON_RATE

def gates():
    import claude_usage as U, subprocess, datetime
    g = []
    g.append((os.access(S.CLAUDE, os.X_OK), f"claude binary {S.CLAUDE}"))
    p = subprocess.run([S.CLAUDE, "-p", "Reply with the single word OK."], capture_output=True, text=True, timeout=120)
    g.append((p.returncode == 0 and "OK" in (p.stdout or ""), f"live call answers rc={p.returncode} {(p.stdout or '')[:40]!r}"))
    s = U.summary(); need = 6.33e6 / 138 * (133 + 171 + 77) * 1.5; have = s.get("remaining_tokens")
    g.append((have is None or have >= need * 3, f"budget: need ~{need/1e6:.0f}M (x1.5 margin), have {None if have is None else round(have/1e6)}M, "
              f"required 3x cover so the live hybrid (~6M/day) is not starved"))
    thin = []
    for d in DAYS:
        b, _ = S.load_day(d); d0 = int(dt.datetime.fromisoformat(d + "T00:00:00+00:00").timestamp())
        if not [x for x in b if x[0] >= d0 + 19 * 3600 + 50 * 60]: thin.append(d)
    g.append((not thin, f"tape reaches 19:50Z every day {thin}"))
    bad = []
    for d in DAYS:
        p_ = f"{S.OUT}/{TAG}_{d}.json"
        if os.path.exists(p_) and not clean(d): bad.append(d)
    g.append((True, f"poisoned artefacts (will be re-run by resume): {bad}"))
    return g

def one(d):
    if avail_mb() < 1500:
        time.sleep(60)
        if avail_mb() < 1500: print(f"  {d} DEFERRED (memory)", flush=True); return
    r = S.run_day(d, "", TAG, resume=True, self_aware=True, line="v2", mil=False)
    e = sum(1 for c in r["calls"] if c.get("error"))
    print(f"  {d} claude-sim ${r['net_usd']:+,.0f} {len(r['trades'])} sim-trades {e}/{len(r['calls'])} err", flush=True)

if __name__ == "__main__":
    os.environ.setdefault("ANTHROPIC_MODEL", "claude-sonnet-5")
    if sys.argv[1] == "gates":
        g = gates()
        for ok, m in g: print(("PASS " if ok else "FAIL ") + m, flush=True)
        sys.exit(0 if all(ok for ok, _ in g) else 2)
    d, start = sys.argv[1], int(sys.argv[2]); assert CUTS[d] == start
    S.WIN_START_MIN = start
    print("E106", d, "window", S.WIN_START_MIN, S.WIN_END_MIN, "model", os.environ["ANTHROPIC_MODEL"], flush=True)
    for pass_no in (1, 2, 3):
        if clean(d): break
        one(d)
    print("DONE", d, "clean" if clean(d) else "UNCLEAN", flush=True)
