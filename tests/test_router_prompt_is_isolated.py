"""The router's prompt must be the ONLY instruction the headless tick receives.

Operator, 2026-08-19: *"CLAUDE.md should have zero impact on router operation. If it does, that
needs fixing. CLAUDE.md is a start-up document you read for instructions. The router is its own
beast — it should bench and debench based on the day's tape with a view to making profitable
trades."*

Claude Code auto-loads context keyed to the WORKING DIRECTORY: a `CLAUDE.md` in the cwd or any
parent, plus the per-project auto-memory index at `~/.claude/projects/<slug-of-cwd>/memory/`. The
tick used to inherit the unit's `WorkingDirectory=/home/alphabot/gazbot7`, which injected ~1,720
words of auto-memory — 32 bullets of trading opinion written by past sessions, unreviewed — into
every 5-minute bench/arm decision.

`/root/CLAUDE.md` was never the leak (it is in neither the cwd chain nor `~/.claude/`). The memory
index was. These tests fail if the isolation is undone.
"""
from __future__ import annotations

import os
import re

GB = "/home/alphabot/gazbot7"
SRC = f"{GB}/scripts/router_tick_durable.py"
CTX = "/var/lib/gazbot7/router_ctx"


def _source() -> str:
    with open(SRC) as fh:
        return fh.read()


def test_claude_invocation_passes_an_isolated_cwd():
    """The subprocess must set cwd explicitly — inheriting it is what leaked memory."""
    src = _source()
    call = re.search(r"subprocess\.run\(\[[^\]]*claude[^\]]*\][^)]*\)", src, re.DOTALL)
    assert call, "could not find the `claude -p` subprocess call"
    body = call.group(0)
    assert "cwd=" in body, (
        "the headless `claude -p` call does not set cwd, so it inherits the unit's "
        "WorkingDirectory and auto-loads that project's CLAUDE.md and auto-memory index into "
        "every routing decision. Pass cwd=ROUTER_CTX.")
    assert "ROUTER_CTX" in body or "ctx" in body, "cwd must point at the isolated ROUTER_CTX dir"


def test_router_ctx_is_defined_and_not_the_repo_root():
    src = _source()
    m = re.search(r'^ROUTER_CTX\s*=\s*f?"([^"]+)"', src, re.M)
    assert m, "ROUTER_CTX is not defined"
    path = m.group(1).replace("{GB}", GB)
    assert path.rstrip("/") != GB.rstrip("/"), (
        "ROUTER_CTX points at the repo root — that reopens the auto-memory leak")
    # ★ THE REAL TRAP: a dir INSIDE the repo still resolves to the gazbot7 project and still loads
    # its auto-memory index. The first fix shipped ops/router_ctx and silently did nothing.
    assert not path.startswith(GB.rstrip("/") + "/"), (
        f"ROUTER_CTX ({path}) is INSIDE the repo. Claude Code walks UP to the repo root to resolve "
        f"the project, so the gazbot7 auto-memory index is loaded anyway. It must live outside.")


def test_router_ctx_holds_no_instruction_files():
    """The directory must stay empty. A CLAUDE.md here would be loaded on every tick."""
    if not os.path.isdir(CTX):
        return                      # created defensively at runtime; nothing to police yet
    stray = list(os.listdir(CTX))
    assert not stray, (
        f"{CTX} must be EMPTY — found {stray}. Anything here risks reaching every live routing "
        f"decision; the documentation lives in ops/ROUTER_CONTEXT_ISOLATION.md instead.")
    assert not os.path.exists(f"{CTX}/CLAUDE.md"), "a CLAUDE.md here defeats the entire isolation"


def test_home_is_still_root_because_auth_lives_there():
    """It is the CWD that leaks context, never HOME — and HOME carries the OAuth credential.

    Credential expiry is this desk's #1 fragility (125 dead ticks / 10.5h on 08-13). A future edit
    that 'isolates' the tick by moving HOME would break auth, not memory.
    """
    src = _source()
    assert '"HOME": "/root"' in src, (
        "the tick no longer forces HOME=/root — the OAuth credential at ~/.claude/.credentials.json "
        "would not be found and every tick would ABORT")


# ── Every headless DECISION-MAKER, not just the router tick ────────────────────────────────────
# 2026-08-19, operator: "check the same leak isnt in the other claude jobs". It was in three more.
# The line that matters is DECIDES vs ANALYSES: a job that writes gate_switches.env or produces a
# verdict must see only its prompt. The tool-using REVIEW jobs (claude_job.py, friday/serial_runner)
# genuinely need cwd=repo for Bash/Read and are analysis-only by policy (claude_job.py: "None of
# them may move a switch"), so they are deliberately NOT covered here — closing those needs
# --add-dir, which is a behavioural change to the Friday report and is not free.
DECIDERS = {
    "scripts/open_hour_watch.py": "HEADLESS_CTX",   # ARMS gates (may flip =off -> =on)
    "src/gazbot7/cl_sims.py": "CL_CTX",             # courtroom verdicts
    "src/gazbot7/cl_verify.py": "CL_CTX",           # courtroom verification
}


def _claude_calls(src: str):
    return re.findall(r"subprocess\.run\(\[[^\]]*claude[^\]]*\][^)]*\)", src, re.DOTALL)


def test_every_headless_decider_isolates_its_cwd():
    bad = []
    for rel, const in DECIDERS.items():
        with open(f"{GB}/{rel}") as fh:
            src = fh.read()
        for call in _claude_calls(src):
            if "cwd=" not in call:
                bad.append(f"{rel}: a `claude` call sets no cwd — it inherits the unit's "
                           f"WorkingDirectory and auto-loads the repo's memory index")
            elif const not in call:
                bad.append(f"{rel}: cwd is not {const}")
    assert not bad, "\n".join(bad)


def test_all_deciders_agree_on_one_isolated_path():
    """Four files hardcode this path; drift would silently re-leak whichever one fell behind."""
    paths = set()
    for rel in list(DECIDERS) + ["scripts/router_tick_durable.py"]:
        with open(f"{GB}/{rel}") as fh:
            src = fh.read()
        paths.update(m for m in re.findall(
            r'^(?:ROUTER_CTX|HEADLESS_CTX|CL_CTX)\s*=\s*"([^"]+)"', src, re.M))
    assert len(paths) == 1, f"headless context paths have drifted apart: {sorted(paths)}"
    only = paths.pop()
    assert not only.startswith(GB.rstrip("/") + "/"), (
        f"{only} is inside the repo — Claude Code resolves the project at the repo root, so the "
        f"auto-memory index loads anyway")
