"""THE GATEWAY MUST NEVER LEAVE HIM BLIND AND HOLDING AGAIN (2026-09-24).

★★★ THE INCIDENT. At 18:05:59 he pressed FLATTEN on a SHORT 4. The gateway's accept queue was at
45/50 with 42 CLOSE-WAIT sockets; the rider was timing out, `venue_ok:false`, `blind_holding:true`.
His claim sat UNREAD for 2m08s and executed only after a manual `docker restart`.

MEASURED COST: price was 30638.25 when he pressed (+$516 on 4 lots) and 30628.00 at the best print
(+$598). It booked +$228. THE OUTAGE COST $282 AGAINST HIS PRESS AND $364 AGAINST THE BEST PRINT.

⚠⚠⚠ AND THE WATCHDOG WATCHED IT HAPPEN. `gateway_watch` sampled the climb (34 -> 38 -> 42), decided
correctly that it must not restart while he held a position, and wrote that decision TO A LOG FILE
NOBODY READS. Operator: "us not knowing is unacceptable."

Two changes, and the second is the load-bearing one:
  1. the DECLINE now pages — a guard that declines in silence is a guard nobody knows they lack
  2. a NARROW exception: restart while holding ONLY when the desk is ALREADY BLIND
"""
import importlib.util
import json
import os
import time

SRC = "/home/alphabot/gazbot7/scripts/gateway_watch.py"


def _load(tmp_path, rider=None, claim_age=None, buy_age=None):
    spec = importlib.util.spec_from_file_location("gw", SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    r = tmp_path / "rider.json"
    if rider is not None:
        r.write_text(json.dumps(rider))
    m.RIDER = str(r)
    for attr, age in (("CLAIM", claim_age), ("BUY", buy_age)):
        f = tmp_path / f"{attr}.txt"
        if age is not None:
            f.write_text("x")
            os.utime(f, (time.time() - age, time.time() - age))
        setattr(m, attr, str(f))
    return m


def test_blind_and_holding_is_detected(tmp_path):
    m = _load(tmp_path, rider={"qty": 4.0, "closed": False, "venue_ok": False})
    blind, why = m.blind_and_holding()
    assert blind and "venue_ok=false" in why


def test_a_healthy_desk_holding_is_NEVER_restarted(tmp_path):
    """⚠⚠⚠ THE STANDING RULE SURVIVES. The exception is for a desk that ALREADY cannot trade —
    it is not a relaxation. A restart blinds every consumer for ~15s, and doing that to a working
    position would be the cure causing the disease."""
    m = _load(tmp_path, rider={"qty": 4.0, "closed": False, "venue_ok": True})
    blind, why = m.blind_and_holding()
    assert not blind and "reachable" in why


def test_a_flat_desk_is_not_the_blind_path(tmp_path):
    m = _load(tmp_path, rider={"qty": 0, "closed": True, "venue_ok": False})
    assert m.blind_and_holding() == (False, "flat")


def test_a_STALE_rider_state_means_cannot_tell_means_do_not_act(tmp_path):
    """⚠⚠ NOT KNOWING IS NOT THE SAME AS BLIND, and it is not the same as flat either. If the
    rider has stopped writing, we cannot tell what it holds — and a watchdog that acts on a guess
    about an open position is worse than one that pages and waits."""
    m = _load(tmp_path, rider={"qty": 4.0, "closed": False, "venue_ok": False})
    old = time.time() - 10_000
    os.utime(m.RIDER, (old, old))
    blind, why = m.blind_and_holding()
    assert not blind and "cannot tell" in why


def test_a_missing_rider_state_does_not_act(tmp_path):
    m = _load(tmp_path)                      # no file written
    blind, why = m.blind_and_holding()
    assert not blind and "cannot read" in why


def test_venue_ok_TRUE_never_triggers_even_though_it_can_go_stale(tmp_path):
    """★ `venue_ok` is known to go STALE-TRUE on the rider's early-return path — it read true for
    2h once while the heartbeat advanced. That failure points the SAFE way here: we act only on an
    explicit False, so a stale True makes us decline rather than restart a working desk."""
    m = _load(tmp_path, rider={"qty": 4.0, "closed": False})   # venue_ok absent entirely
    assert m.blind_and_holding()[0] is False


def test_an_unread_press_is_its_own_trigger(tmp_path):
    """★★ THIS IS THE THING HE ACTUALLY CARES ABOUT — not "is the gateway healthy" but "did my
    button do anything". The rider DELETES a request when it acts, so `exists and old` IS unread.
    It fires independently of the socket counters, because on 18:05 CLOSE-WAIT was still CLIMBING
    THROUGH the trip point while his flatten was already dead."""
    m = _load(tmp_path, claim_age=120)
    hit, why = m.unread_request()
    assert hit and "CLAIM" in why


def test_a_fresh_press_is_not_a_trigger(tmp_path):
    m = _load(tmp_path, claim_age=5)
    assert m.unread_request()[0] is False


def test_the_blind_path_is_capped_not_merely_cooled(tmp_path):
    """⚠ IF RESTARTING DID NOT FIX IT, THE FAULT IS NOT THE GATEWAY. The thing that takes a desk
    down is never the first restart, it is the fourth — so it pages and STOPS."""
    src = open(SRC, encoding="utf-8").read()
    assert "BLIND_MAX" in src and "nres >= BLIND_MAX" in src
    assert "MANUAL INTERVENTION NEEDED" in src


def test_restart_merges_state_instead_of_replacing_it(tmp_path):
    """⚠⚠ restart() used to json.dump a FRESH dict over the state file, which would have wiped
    `blind_restarts` on every restart and made the cap unreachable — the guard would have looped
    forever while appearing to count. Found while wiring the cap, not after it bit."""
    src = open(SRC, encoding="utf-8").read()
    body = src.split("def restart(", 1)[1].split("\ndef ", 1)[0]
    assert "write_state({" in body
    assert 'open(STATE, "w")' not in body


def test_the_decline_pages_rather_than_only_logging():
    """★★★ THE WHOLE POINT. This line existed and was written three times during the incident —
    into a log file. He found out by pressing a button and watching nothing happen."""
    src = open(SRC, encoding="utf-8").read()
    seg = src.split("but NOT RESTARTING", 1)[1][:1200]
    assert "_notify(" in seg and "critical=True" in seg


def test_the_cooldown_fails_OPEN():
    """⚠ An unparseable or absent stamp must mean "no recent restart" so the guard can ACT. A
    cooldown that failed closed would silently disarm the watchdog."""
    src = open(SRC, encoding="utf-8").read()
    body = src.split("def _age(", 1)[1].split("\ndef ", 1)[0]
    assert body.count('float("inf")') >= 2


def test_dedupe_failure_never_eats_an_alarm():
    src = open(SRC, encoding="utf-8").read()
    body = src.split("def dedupe_ok(", 1)[1].split("\ndef ", 1)[0]
    assert "return True" in body


def test_it_samples_fast_enough_to_see_the_climb():
    """⚠ The queue went 34 -> 38 -> 42 in two samples at 60s. A ~4/minute climb deserves better."""
    src = open(SRC, encoding="utf-8").read()
    import re
    d = float(re.search(r'GW_POLL_S", "([\d.]+)"', src).group(1))
    assert d <= 20, f"poll interval {d}s is too slow to see the climb"
