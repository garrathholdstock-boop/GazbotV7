# RETIRED UNITS — on disk, deliberately NOT installed. Do not re-arm without reading this.

★ A unit file sitting in `ops/systemd/` reads as "install me". These were removed from service for
CAUSE, and leaving them in the live directory with no note is how a future session re-arms a known
dangerous job. `gazbot7-tunnel-watch` got an explicit retirement note in CLAUDE.md when it was
disabled on 2026-09-24; these did not, which the 2026-09-26 safety audit flagged as finding 11.

## `gazbot7-weekend-flatten.{timer,service}` — DELETED 2026-08-26, DO NOT RE-ARM AS WRITTEN

**What it was for.** After 2026-08-21, four naked lots rode through the CME halt into a weekend and
cost **−$2,149**: the gateway wedged ~19:57Z Friday and all four closing paths (the rider's 20:40
hard flat, the flatten-only watchdog, the EOD flatten, desk_reconcile) share one `ib.connectAsync`,
so all four died on the same call. `gazbot7-eod-flatten.timer` is `Mon-Fri` with `Persistent=false`,
so a Friday failure gets no catch-up at all — its next elapse is Monday 20:53Z while the tape reopens
Sunday 22:00Z. This unit was meant to flatten a weekend carry across the Sunday reopen.

**Why it was deleted.** It was still armed for Sun 08-30 22:00Z when the Friday report caught it. It
was described as self-disabling once the venue read flat — **it died BEFORE the flat check, so it
never disabled itself** — and it would have re-armed the rider and written a BARE-STAMP CLAIM, which
the rider reads as "claim EVERYTHING", against whatever was open at the reopen. A weekend-carry
guard that can flatten an unrelated fresh position is worse than the carry.

**The hazard it covered is still open, and is covered better elsewhere now.** The 2026-09-26 audit's
finding 01 is a resting **catastrophe stop at the broker** (`live_mode.json.venue_stop_armed`,
600pt): it needs no timer, no connection, no process on this box, and it works in every timezone and
through every wedge — which is exactly the failure class this unit existed for. `gazbot7-gateway-watch`
also now restarts the gateway when the desk is **blind AND holding**, which did not exist in August.

**If you rebuild it anyway:** check flat FIRST, size from the venue via `safe_flatten_verdict()` and
never from our book, never synthesise a claim, and make the self-disable unconditional.
