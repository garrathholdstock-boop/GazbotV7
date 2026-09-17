"""BLIND AND HOLDING IS AN ALARM AT ANY HOUR.

★★★ THE HOLE THIS CLOSES (2026-09-17). day_rider.py already paged on an unreachable venue — but
ONLY inside the flatten window (`mod >= FLAT_UTC_MIN`), because its case (08-21) was an overnight
carry. On 2026-09-17 the gateway's accept queue filled at 00:40Z and the error handler ran 244
CONSECUTIVE TIMES holding 4 lots, at hours nowhere near 20:40Z. Every tick:

    venue_ok: false · note: "ERROR (no action): TimeoutError:" · heartbeat: FRESH · exit code: 0

So systemd was green, the heartbeat was green, sweep was green, and the operator's Claim expired
unread. A position the rider cannot see is unmanaged at 01:00 exactly as much as at 20:50.
"""
import json
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

SRC = "/home/alphabot/gazbot7/src/gazbot7/day_rider.py"


def _code(block: str) -> str:
    """Executable lines only. ⚠ The first version of this test matched `mod >= FLAT_UTC_MIN` inside
    the COMMENT that explains why the old alarm was gated that way — a test that fails on its own
    documentation. Assert the CODE; keep the prose free to explain itself."""
    return "\n".join(ln for ln in block.splitlines()
                     if ln.strip() and not ln.strip().startswith("#"))


def _block(src: str) -> str:
    i = src.index("BLIND AND HOLDING IS AN ALARM AT ANY HOUR")
    return src[i:src.index('out["flatten_blocked"]', i)]


def test_the_alarm_is_not_gated_on_the_flatten_window():
    """★ THE FIX. The blind-and-holding page must be reachable at ANY hour."""
    block = _code(_block(open(SRC).read()))
    assert "rider_blind_holding" in block, "the blind-and-holding page is gone"
    assert "mod >= FLAT_UTC_MIN" not in block, (
        "the blind-and-holding alarm was re-gated on the flatten window — that gate IS the bug: "
        "the 2026-09-17 outage ran 00:40-06:09Z and would page nothing")


def test_the_streak_is_DURABLE_because_the_rider_is_a_oneshot():
    """⚠ An in-memory counter resets every tick and would never reach 2 — `day_rider` is oneshot
    and picks up code (and loses state) on every single run."""
    src = open(SRC).read()
    assert "day_rider_blind.json" in src, "the blind streak is not persisted"


def test_a_good_read_RESETS_the_streak():
    """⚠ Without a reset the counter only grows, so the SECOND outage opens at streak 244 and skips
    3/10/30 — every page that lands early enough to save a live claim."""
    src = open(SRC).read()
    assert src.count("day_rider_blind.json") >= 2, "nothing clears the streak on a good read"
    i = src.index("A GOOD READ ENDS THE BLIND STREAK")
    assert "os.remove" in src[i:i + 700]
    # ★★ AND IT MUST SIT WITH THE VENUE READ, NOT WITH A save_state(). step() has TWELVE
    # save_state(out) calls and the ordinary riding branches return long before the last one — the
    # first version of this reset was placed there and was unreachable on every healthy tick.
    assert src.index('out["venue_ok"] = True') < i < src.index('out["venue_ok"] = True') + 800, (
        "the blind-streak reset drifted away from the successful venue read; if it is not on the "
        "line that proves we reached the broker, some return path will skip it")


def test_the_first_page_lands_while_a_claim_is_still_live():
    """★★ THE WHOLE POINT. CLAIM_MAX_AGE_S is 15 min; the rider ticks every 60s. The first
    escalation must fire well inside that or the alarm arrives after the press is already dead."""
    import gazbot7.day_rider as dr
    block = _code(_block(src := open(SRC).read()))
    assert "(3, 10, 30, 120)" in block, "escalation thresholds changed — re-check them against " \
                                        "CLAIM_MAX_AGE_S before accepting this"
    assert 3 * 60 < dr.CLAIM_MAX_AGE_S, (
        f"the first page (3 ticks = ~3 min) must land inside CLAIM_MAX_AGE_S "
        f"({dr.CLAIM_MAX_AGE_S}s), or it arrives after the claim is already dead")


def test_it_still_only_pages_while_HOLDING():
    """⚠ A blind rider with no position is a problem for the watchdog, not a 3am critical. The desk
    pays for noisy alarms in swiped-past criticals."""
    block = _code(_block(open(SRC).read()))
    assert "if _held:" in block, "the blind alarm no longer requires an open position"


def test_the_message_names_the_remedy_and_the_reason_nothing_else_sees_it():
    block = _code(_block(open(SRC).read()))
    assert "docker restart alphabot-gateway" in block, "the page must name the fix"
    assert "exits 0" in block and "heartbeat" in block, (
        "the page must say WHY no other instrument shows this — that is the whole lesson")
