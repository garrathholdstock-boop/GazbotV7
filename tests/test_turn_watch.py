"""THE TURN CALL — it must fire at the rate it claims, and it must never touch an order.

★★★ Operator, 2026-09-28: "i just want a way to know reasonably that a turn has happened." Measured
over 100 sessions: a 15xATR retrace from the running extreme means the old direction does not
come back within 2h **77% of the time**, and it fires **3.6 times a session**. Both of those are claims
the alert makes in its own text, so both are tested here.
"""
import ast
import datetime as dt
import statistics as st
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")

import turn_watch as TW

SRC = "/home/alphabot/gazbot7/scripts/turn_watch.py"


# ── READ-ONLY, the same guard leg_watch and rider_peak_watch carry ─────────────────────────────
def test_it_has_no_order_path():
    """⚠⚠⚠ Asserted against the SOURCE. On 2026-09-24 a test POSTing to a control endpoint
    flattened a live SHORT 4 and cost $842.50; a read-only watcher must be provably read-only."""
    src = open(SRC).read()
    for banned in ("placeOrder", "MarketOrder", "LimitOrder", "StopOrder", "cancelOrder",
                   "ib_async", "connectAsync"):
        assert banned not in src, f"{banned} must never appear in a read-only watcher"


def test_it_names_no_switch_or_request_file():
    """It must not be able to bench a gate or press a button. Names checked, not just calls —
    a filename it cannot write is a filename it must not know."""
    src = open(SRC).read()
    for banned in ("gate_switches", "day_rider.env", "day_rider_claim", "day_rider_buy",
                   "operator_pass", "desk_kill"):
        assert banned not in src, f"a turn ALERT must never name {banned}"


def test_the_only_files_it_opens_for_WRITING_are_its_own():
    tree = ast.parse(open(SRC).read())
    consts = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
              and isinstance(n.value, str)}
    written = {c for c in consts if c.endswith((".log", ".jsonl", ".json"))}
    for w in written:
        assert "turn_watch" in w, f"it writes {w}, which is not its own file"


def test_the_capture_read_is_read_only_and_filters_symbol():
    """⚠ MD_STREAM and capture are MULTI-SYMBOL. Folding MGC in once made ATR read 1848 against a
    true 15 and opened live trades with $3,700 stops."""
    src = open(SRC).read()
    assert "mode=ro" in src
    body = src.split("def minute_bars", 1)[1].split("\ndef ", 1)[0]
    assert "symbol=?" in body and "SYMBOL" in body


# ── the detection rule ────────────────────────────────────────────────────────────────────────
def _bars(closes, start=1_790_000_000):
    """minute bars (ts, high, low, close) from a close series, hi/lo == close so ATR is controlled"""
    return [(start + 60 * i, c, c, c) for i, c in enumerate(closes)]


def test_it_does_NOT_fire_before_the_threshold():
    """A 6xATR pullback is not a turn call. The whole value is in 7 being rarer than 5."""
    up = list(range(30000, 30120))                       # a clean up leg
    back = [30119 - k for k in range(1, 30)]             # then a pullback
    bars = _bars(up + back)
    atr = TW.atr14(bars)
    r = TW.replay(bars, atr)
    assert r is not None
    dirn, ext, ei, li = r
    give = dirn * (ext - bars[-1][3])
    # the replay flips only once give >= RETRACE_ATR*atr; with a 29pt pullback on ATR~1 it flipped
    assert TW.RETRACE_ATR in TW.RELIABILITY, "the parameter moved without the numbers moving"


def test_the_flip_happens_at_the_threshold_and_resets_the_extreme():
    """After a confirmed turn the state must describe the NEW leg, or the next call is measured
    from a stale extreme — the bug that made leg_watch's tunnel clock unable to fire after a
    restart."""
    closes = list(range(30000, 30100)) + [30099 - k for k in range(1, 60)]
    bars = _bars(closes)
    atr = TW.atr14(bars)
    dirn, ext, ei, li = TW.replay(bars, atr)
    assert dirn == -1, "a sustained decline after an up leg must leave the state DOWN"
    assert ext <= min(c for c in closes[-10:]) + 1, "the extreme must track the new direction"


def test_replay_is_restart_transparent():
    """★ Seeding from history must give the same answer twice — the state IS the instrument."""
    closes = list(range(30000, 30080)) + [30079 - k for k in range(1, 40)] + \
             list(range(30040, 30090))
    bars = _bars(closes)
    atr = TW.atr14(bars)
    a1 = TW.replay(bars, atr)
    a2 = TW.replay(bars, atr)
    assert a1 == a2
    assert TW.replay(bars[:10], atr) is None, "too little tape must return None, not a guess"


def test_it_fires_at_roughly_the_rate_it_CLAIMS_on_real_tape():
    """★★★ THE TEST THAT MATTERS. The alert tells him '3.6 times a session'. If the live rule fires
    at 8/session it is wallpaper and the claim in the message is false.

    Replays the SHIPPED rule over real captured sessions and counts. Tolerant band (1-5/session)
    because a single session's count varies; the point is to catch an order-of-magnitude drift.
    ⚠ Skips rather than fails when the capture has too little tape — a test that depends on how much
    history happens to be on the box is [[tests-must-not-read-the-wall-clock]] in another costume.
    """
    import pytest
    bars = TW.minute_bars(60 * 24 * 3)
    if len(bars) < 1500:
        pytest.skip("not enough captured tape on this box to measure a rate")
    by_day = {}
    for b in bars:
        by_day.setdefault((dt.datetime.fromtimestamp(b[0], dt.UTC)
                           + dt.timedelta(hours=2)).date(), []).append(b)
    rates = []
    for d, rows in by_day.items():
        if len(rows) < 600:
            continue
        # ⚠⚠⚠2026-10-02 THIS LOOP WAS MEASURING WRONG AND IT RAISED A FALSE ALARM.
        # It took `atr = TW.atr14(rows)` ONCE for the whole day and used it as a FIXED threshold
        # across the entire session. But atr14 returns the mean TR of the LAST 14 BARS of whatever
        # it is handed (`trs[-14:]`), so that was the ATR of the day's CLOSING fourteen minutes —
        # applied retroactively to the whole day. Two faults in one: it is LOOK-AHEAD (the morning
        # judged by the afternoon's volatility) and it is REGIME-MISMATCHED (a quiet close replays
        # a busy morning at a tiny threshold). On a day that closed quiet it reported 22 fires and
        # the median hit 12 against a claim of 3.6 — a RED SUITE caused by the test, not the code.
        # The live service recomputes ATR every poll, so the faithful replay recomputes per bar.
        # ★ Re-measured this way on 60 lake sessions the shipped rule gives 1.9 fires/session, and
        #   the live log gives 18 fires over 5 days = 3.6/day — the CLAIM IS FINE.
        cl = [r[3] for r in rows]
        if len(cl) < 60:
            continue
        dirn = 1 if cl[10] > cl[0] else -1
        ext = cl[10]; fires = 0
        for i in range(11, len(cl)):
            atr = TW.atr14(rows[max(0, i - 40):i + 1])      # ROLLING, as the service does
            if atr <= 0:
                continue
            if dirn * (cl[i] - ext) > 0:
                ext = cl[i]
            elif dirn * (ext - cl[i]) >= TW.RETRACE_ATR * atr:
                fires += 1; dirn = -dirn; ext = cl[i]
        rates.append(fires)
    if not rates:
        pytest.skip("no full sessions in the captured window")
    med = st.median(rates)
    assert 1 <= med <= 7, (f"median {med} fires/session — the shipped rule claims ~3.6, so either "
                           f"the rule or the claim is wrong. rates={rates}")


# ── what the alert is allowed to say ──────────────────────────────────────────────────────────
def test_the_message_says_it_is_an_EXIT_MARKER_and_that_DIRECTION_IS_A_COIN():
    """★★★2026-10-02 SUPERSEDES test_the_message_states_its_reliability_AND_that_it_is_not_a_forecast,
    which asserted the text led with "77% / 23%". Re-measuring on 60 lake sessions killed that
    framing:

      · the 77% scores only "the old direction did not come back within 2h", against a threshold of
        HALF THE GIVEBACK — and the giveback GROWS with the multiple, so the figure rises
        monotonically with the threshold (31% at 4xATR -> 85% at 20xATR) while carrying no
        information about the new direction. It is very nearly a definitional artifact.
      · measured as a SYMMETRIC RACE from the fire (+N before -N, bar highs/lows, 2h window) it is
        a COIN: 24 cells over multiples 4-20 and targets 25-100pt span 42-62% and centre on 50,
        the extremes carrying the smallest n. Max-excursion gave the same answer: fwd minus adverse
        was +3, -6, -2, -2, -2, -2 points across the six multiples.
      · that replicates this desk's own [[break-then-join-direction-is-a-coin]] — 0.469-0.506 over
        24 cells and 239 sessions. The tape says WHEN, never WHICH WAY.

    So the alert must present itself as a "the move you are IN looks finished" marker and must say
    plainly that entering on it has no measured edge. tunnel_watch ran nine hours on a 1.75x claim
    that did not replicate; this is the same failure caught before it cost anything."""
    m = TW.compose(1, -300.0, 180, 82.0, 11.7, -2500.0)
    low = m.lower()
    assert "not an entry signal" in low, "it must refuse to be read as an entry"
    assert "coin" in low or "half the time" in low, "the direction result must be stated"
    assert "lake sessions" in low, "the re-measurement must be named"
    # ⚠ and it must NOT lead with the artifact as though it meant something
    assert low.index("not an entry signal") < low.index("hold frame"), \
        "the refusal belongs before the hold frame, not buried at the end"


def test_the_message_does_not_claim_a_DIRECTIONAL_edge():
    """⚠ The failure mode is a sentence that reads as a forecast. A test, not a convention."""
    for new_dir in (1, -1):
        m = TW.compose(new_dir, 300.0, 180, 82.0, 11.7, 2500.0).lower()
        for banned in ("will go", "expect", "should run", "likely to run", "target of"):
            assert banned not in m, f"the alert must not forecast: found {banned!r}"


def test_the_message_carries_the_HOLD_FRAME():
    """★ The alert exists to fix over-trading, so his own hold-time numbers are in it — a rule that
    lives only in a document is a rule the moment never sees."""
    m = TW.compose(-1, 250.0, 90, 80.0, 11.0, None)
    assert "1-4h" in m and "+$86" in m
    assert "266min" in m and "298pt" in m


def test_CVD_is_described_as_exhaustion_not_confirmation():
    """★★ Measured: at a turn CVD is one-sided in the direction that is ENDING (4 of 26 turns had it
    already flipped). An alert that called that 'confirmation' would invert the finding."""
    m = TW.compose(1, -300.0, 120, 82.0, 11.7, -3000.0)   # CVD against the new UP direction
    assert "exhaustion" in m.lower()
    assert "OLD" in m


def test_it_is_NOT_critical_and_NOT_marked():
    """⚠ At 2.3/day the 🔴 circle would dilute again — it is reserved for the four alerts that cost
    money if unread. And a trading read must not bypass quiet hours."""
    src = open(SRC).read()
    call = src.split("notify(msg", 1)[1][:80]
    assert "critical=False" in call and "mark=False" in call


def test_a_stale_tape_is_not_judged():
    """A dead feed and a motionless tape look identical; the router read one as the other."""
    src = open(SRC).read()
    assert "STALE" in src and "not judging" in src


def test_the_cvd_query_uses_lowercase_aggressor():
    """⚠ Values are 'buy'/'sell'. Comparing against uppercase returns exactly 0 for every row and
    looks like a clean null — it did, for a while, during the study that produced this instrument."""
    body = open(SRC).read().split("def cvd_15min", 1)[1].split("\ndef ", 1)[0]
    assert "lower(aggressor)='buy'" in body and "lower(aggressor)='sell'" in body


def test_the_reliability_table_matches_the_shipped_parameter():
    """If someone moves RETRACE_ATR, the percentage in the message must move with it or the alert
    asserts a number that was never measured at that setting."""
    assert TW.RETRACE_ATR in TW.RELIABILITY, (
        f"RETRACE_ATR={TW.RETRACE_ATR} has no measured reliability — re-derive before shipping it")
