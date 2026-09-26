# ROUTER CONTEXT ISOLATION — the prompt is the only instruction

**The context dir is `/var/lib/gazbot7/router_ctx` and it MUST STAY EMPTY.**
It lives OUTSIDE this repo deliberately — see the correction below.

`scripts/router_tick_durable.py` runs its headless `claude -p` decision with `cwd` set to that
directory, and for one reason: **the router's prompt must be the ONLY instruction it receives.**

Claude Code auto-loads context keyed to the working directory — a `CLAUDE.md` found in the cwd or
any parent, and the per-project auto-memory index at
`~/.claude/projects/<slugified-cwd>/memory/MEMORY.md`. The router previously ran with
`cwd=/home/alphabot/gazbot7`, which injected **~1,720 words of auto-memory** into every 5-minute
routing decision: 32 bullets of trading opinion (bench cost, ATR floors, the Asia block,
abs_veto_short, exhaustion_rev …) written by past sessions, unreviewed, sitting alongside the
carefully-maintained prompt and silently shaping live bench/arm calls.

**Operator, 2026-08-19:** *"CLAUDE.md should have zero impact on router operation … the router is
its own beast. It should bench and debench based on the day's tape with a view to making profitable
trades."*

`/root/CLAUDE.md` was never actually loaded (it is not in this cwd chain and not `~/.claude/
CLAUDE.md`) — **the auto-memory index was the real leak**, and this directory closes it. Verified
empirically: from here the tick reports no MEMORY.md, no CLAUDE.md, no project documents.

## ⚠ THE CORRECTION THAT MATTERS — IT MUST BE OUTSIDE THE REPO

The first attempt put the context dir at `gazbot7/ops/router_ctx`. **It did not work, and it
reported success.** Claude Code resolves the project by walking UP to the repo root, so a directory
*inside* `gazbot7` still resolves to the gazbot7 project and still loads its auto-memory index.
The verification that "passed" had been run from `/tmp` — a different directory from the one being
shipped — so it proved nothing about the fix.

Re-tested from the real path: `/var/lib/gazbot7/router_ctx` reports no memory index, no CLAUDE.md,
no desk documents. **Any replacement path must be re-verified BY RUNNING FROM THAT EXACT PATH**, not
from a stand-in, and it must not sit inside a git repo that owns a memory project.

## Rules

* **Do not put a `CLAUDE.md` there. Do not put anything there at all.**
* **Do not move it inside the repo** — that is precisely the bug above.
* Do not point the router back at the repo root "for convenience" — that reopens the leak.
* `HOME` stays `/root`. The OAuth credential lives at `~/.claude/.credentials.json` and credential
  expiry is this desk's #1 fragility; changing `HOME` breaks auth, not memory.
* The prompt is the contract. If the router needs to know something, it goes in the prompt, where it
  is reviewed, diffed and testable — not into a memory file.

Guarded by `tests/test_router_prompt_is_isolated.py`.
