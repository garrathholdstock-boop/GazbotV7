"""The MGC level-break gate and its depth feed.

Two survivors from the 2026-08-15 gold hunt, shadow-only. The gate asks the book nothing about
DIRECTION — the break has already chosen the side — only whether that side will HOLD.

Most of what follows guards fail-closed behaviour, because every failure mode here is silent: a
gate that trades without a book is just the plain extension trigger, which loses -$3.60 to -$5.49 a
trade in every cell and both directions at gold's true cost.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7.depthfeed import DepthFeed  # noqa: E402
from gazbot7.levelbreak import (  # noqa: E402
    MGC_FEE_RT,
    MGC_VPP,
    band_size,
    detect_break,
    gate_level_break,
    read_book,
)


def bars(n=70, base=3000.0, last=None):
    h = [base + 1] * n
    lo = [base - 1] * n
    c = [base] * n
    if last is not None:
        c[-1] = last
        h[-1] = max(h[-1], last)
        lo[-1] = min(lo[-1], last)
    return h, lo, c


EMPTY = {f"{s}{k}{f}": (0.0 if f == "s" else 0.0) for s in ("bid", "ask")
         for k in range(1, 11) for f in ("p", "s")}


def book(**rungs):
    b = dict(EMPTY)
    b.update(rungs)
    return b


# ── the break itself ─────────────────────────────────────────────────────────
def test_a_break_needs_to_clear_the_prior_extreme_by_the_margin():
    h, lo, c = bars(last=3001.0)          # prior high 3001, so a close AT it is not a break
    assert detect_break(h, lo, c, atr=10.0, look_min=60, margin_atr=0.10) is None
    h, lo, c = bars(last=3002.5)          # 3001 + 0.10*10 = 3002 -> cleared
    assert detect_break(h, lo, c, atr=10.0, look_min=60, margin_atr=0.10) == (1, 3001.0)
    h, lo, c = bars(last=2996.5)          # 2999 - 2 = 2997 -> cleared downward
    assert detect_break(h, lo, c, atr=10.0, look_min=60, margin_atr=0.10) == (-1, 2999.0)


def test_the_level_excludes_the_signal_bar_itself():
    """★ CIRCULARITY GUARD. If the signal bar's own high were in its own level, a bar could break a
    level it had just set. The level must come from bars STRICTLY BEFORE it."""
    h, lo, c = bars(last=3050.0)
    brk, level = detect_break(h, lo, c, atr=10.0, look_min=60, margin_atr=0.10)
    assert level == 3001.0, "the level must not include the breaking bar's own high"


def test_not_enough_history_is_no_signal():
    h, lo, c = bars(n=20, last=3050.0)
    assert detect_break(h, lo, c, atr=10.0, look_min=60, margin_atr=0.10) is None


# ── the book split ───────────────────────────────────────────────────────────
def test_obstacle_and_support_follow_the_BREAK_direction():
    """★ Getting this pair the wrong way round INVERTS the gate silently — it still fires, just on
    the mirror condition. An UP break runs into ASKS and is caught by BIDS."""
    b = book(ask1p=3001.5, ask1s=7.0, bid1p=3000.5, bid1s=4.0)
    up = read_book(b, brk=+1, level=3001.0, band=1.0)
    assert (up.obstacle, up.support) == (7.0, 4.0)
    dn = read_book(b, brk=-1, level=3001.0, band=1.0)
    assert (dn.obstacle, dn.support) == (4.0, 7.0)


def test_size_outside_the_band_does_not_count():
    b = book(ask1p=3005.0, ask1s=50.0)     # 4pt beyond a 1pt band
    assert band_size(b, "ask", 3001.0, 1.0) == 0.0


def test_a_missing_rung_is_UNKNOWN_not_empty():
    """An absent rung must be skipped, never counted as zero size — calling it empty would
    manufacture the VACUUM this gate trades on."""
    b = book(ask1p=None, ask1s=None, ask2p=3001.5, ask2s=3.0)
    assert band_size(b, "ask", 3001.0, 1.0) == 3.0


def test_a_zero_price_rung_is_ignored():
    b = book(ask1p=0.0, ask1s=99.0)
    assert band_size(b, "ask", 3001.0, 1.0) == 0.0


# ── the gate ─────────────────────────────────────────────────────────────────
def test_VACUUM_fades_the_break():
    """obstacle == 0 -> the break has nothing to clear and reverts. 49% of breaks, +$12.47/trade."""
    h, lo, c = bars(last=3002.5)                       # UP break
    b = book(bid1p=3000.5, bid1s=4.0)                  # asks empty near the level
    assert gate_level_break(h, lo, c, 10.0, b, fade=True, obstacle_max=0) == "SHORT"


def test_WALL_follows_the_break():
    """obstacle > support -> it pushes through. 14% of breaks, +$11.84/trade."""
    h, lo, c = bars(last=3002.5)
    b = book(ask1p=3001.5, ask1s=20.0, bid1p=3000.5, bid1s=2.0)
    assert gate_level_break(h, lo, c, 10.0, b, fade=False,
                            require_obstacle_gt_support=True) == "LONG"


def test_the_neither_bucket_trades_NOTHING():
    """37% of breaks: the book has no opinion and BOTH directions lose there. Not a gap — a finding."""
    h, lo, c = bars(last=3002.5)
    b = book(ask1p=3001.5, ask1s=5.0, bid1p=3000.5, bid1s=20.0)
    assert gate_level_break(h, lo, c, 10.0, b, fade=True, obstacle_max=0) is None
    assert gate_level_break(h, lo, c, 10.0, b, fade=False, require_obstacle_gt_support=True) is None


def test_NO_BOOK_MEANS_NO_TRADE():
    """★★ THE FAIL-CLOSED TEST. Without the book this is the plain extension trigger, which loses
    -$3.60 to -$5.49 a trade in EVERY cell and BOTH directions at gold's true cost. Failing open
    would silently convert a tested edge into a known loser."""
    h, lo, c = bars(last=3002.5)
    assert gate_level_break(h, lo, c, 10.0, None, fade=True, obstacle_max=0) is None


def test_gold_costs_are_not_MNQs():
    """$7.50/RT, not $1.50 — gold crosses the spread on BOTH legs. Applying the true cost killed the
    coil bouncer outright (+$470 -> -$454)."""
    assert (MGC_VPP, MGC_FEE_RT) == (10.0, 7.50)


# ── the depth feed ───────────────────────────────────────────────────────────
_MK_N = [0]


def _mk(tmp_path, rows):
    _MK_N[0] += 1
    p = str(tmp_path / f"d{_MK_N[0]}.db")   # a fresh file per call — the torn-quote test loops
    c = sqlite3.connect(p)
    cols = ", ".join(f"bid{k}p REAL, bid{k}s REAL, ask{k}p REAL, ask{k}s REAL" for k in range(1, 11))
    c.execute(f"CREATE TABLE depth_snap (symbol TEXT, ts_ms INTEGER, {cols})")
    names = ", ".join(f"bid{k}p, bid{k}s, ask{k}p, ask{k}s" for k in range(1, 11))
    q = ", ".join(["?"] * 40)   # 10 levels x 4 fields
    for ts, b1, a1 in rows:
        vals = [b1, 5.0, a1, 5.0] + [0.0] * 36
        c.execute(f"INSERT INTO depth_snap (symbol, ts_ms, {names}) VALUES (?,?,{q})",
                  ["MGC", ts] + vals)
    c.commit(); c.close()
    return p


def test_the_feed_NEVER_reaches_forward(tmp_path):
    """★★★ THE LOOK-AHEAD GUARD. The snapshot must be the last one AT OR BEFORE the stamp. Reaching
    forward by even one 250ms sample lets the gate see the book AFTER price arrived at the level —
    which is exactly what it is trying to predict."""
    p = _mk(tmp_path, [(1000, 2999.0, 3001.0), (2000, 2000.0, 2002.0)])
    f = DepthFeed("MGC", path=p, max_stale_ms=10_000)
    assert f.book_at(1500)["bid1p"] == 2999.0, "took the FUTURE snapshot"
    assert f.book_at(2000)["bid1p"] == 2000.0
    assert f.book_at(999) is None, "invented a book before any existed"


def test_a_stale_book_is_no_book(tmp_path):
    p = _mk(tmp_path, [(1000, 2999.0, 3001.0)])
    f = DepthFeed("MGC", path=p, max_stale_ms=5_000)
    assert f.book_at(3000) is not None
    assert f.book_at(90_000) is None, "a book from 89s ago is not the book now"


def test_a_torn_quote_is_rejected(tmp_path):
    for b1, a1 in ((3001.0, 2999.0), (0.0, 3001.0), (2990.0, 3001.0)):
        p = _mk(tmp_path, [(1000, b1, a1)])
        assert DepthFeed("MGC", path=p).book_at(1200) is None


def test_a_missing_file_returns_None_not_an_exception(tmp_path):
    assert DepthFeed("MGC", path=str(tmp_path / "nope.db")).book_at(1000) is None


def test_the_wrong_symbol_returns_nothing(tmp_path):
    """capture.db has NO MGC depth at all — a reader pointed at the wrong source returns nothing
    forever, with no error. Same shape: never serve another symbol's book."""
    p = _mk(tmp_path, [(1000, 2999.0, 3001.0)])
    assert DepthFeed("MNQ", path=p).book_at(1200) is None


# ── the service instance: isolation is the design, so it is tested ───────────
def test_the_mgc_slate_is_two_gates_with_the_gold_exit():
    from gazbot7.shadow import mgc_slate
    sl = mgc_slate()
    assert [v.name for v in sl] == ["mgc_holebreak_fade_long", "mgc_holebreak_fade_short"]
    for v in sl:
        assert v.symbol == "MGC" and v.gate == "level_break"
        # the exit IS the finding: wide chandelier, single lot, no profit lock
        assert v.chandelier is True and v.qty == 1.0 and v.stop_atr_mult == 3.0
        assert v.lock_r == 99.0, "the profit lock must never tighten this trail"
        assert v.params["obstacle_max"] == 0, "these are the VACUUM (hole) cells"
        assert v.params["fade"] is True


def test_gold_never_shares_the_mnq_store_or_multiplier():
    """★★★ THE RACE GUARD. reprice_pending() applies ONE value_per_point to every unprocessed trade,
    so two services on one store would price gold at MNQ's $2 instead of $10 — silently,
    intermittently, and 5x in the direction that makes a loser look like a winner."""
    from gazbot7.shadow_mgc import mgc_cfg
    c = mgc_cfg()
    assert c.symbol == "MGC"
    assert c.value_per_point == 10.0, "gold is $10/pt, not MNQ's $2"
    # ★2026-08-15 audit fix #5: the REPRICER gets commission only ($1.50) because it already fills
    # at the far touch on both legs, so the spread is inside `gross`. MGC_FEE_RT ($7.50) is the
    # mid-priced constant and is asserted separately.
    assert c.fee_rt == 1.50, "the repricer must not be charged the spread twice"
    assert c.shadow_store_path == "data/shadow_mgc.db"
    from gazbot7.config import RunConfig
    assert RunConfig().shadow_store_path != c.shadow_store_path, "must not share the MNQ store"


def _sim(tmp_path, lookback=None):
    """A real ShadowSim on the MGC slate, driven through MinuteBars exactly as the service does."""
    from gazbot7.agg import MinuteBars
    from gazbot7.shadow import ShadowSim, mgc_slate
    from gazbot7.shadow_mgc import BAR_LOOKBACK
    from gazbot7.store import open_store
    st = open_store(str(tmp_path / "s.db"))
    return ShadowSim(st, mgc_slate(), value_per_point=10.0, fee_rt=1.5), \
        MinuteBars(lookback if lookback is not None else BAR_LOOKBACK), st


def _grind(mb, n, start=3000.0, step=0.0, t0=1_780_000_000):
    """Feed n flat 1-min bars. Returns the ts to fold the breaking bar at."""
    for i in range(n):
        px = start + i * step
        mb.fold(t0 + i * 60, px, px + 0.5, px - 0.5, px, 10)
    return t0 + n * 60


def _break(mb, t, close=3005.0):
    """Fold the breaking bar, then one more minute to CLOSE it.

    ⚠ MinuteBars keeps the newest bar OPEN and bars() yields only completed ones, so a breaking bar
    is invisible to the gate until the following minute arrives. A test that folds the break and
    stops is testing nothing — which is how the first version of this file passed while the gate
    could not fire at all.
    """
    mb.fold(t, 3000.0, close + 1.0, 2999.5, close, 10)
    mb.fold(t + 60, close, close + 0.5, close - 0.5, close, 10)
    return t + 60


def test_the_gate_ACTUALLY_FIRES_end_to_end(tmp_path):
    """★★★ AUDIT FINDING #1. The previous version of this test string-matched the source and passed
    while the gate was STRUCTURALLY UNABLE TO FIRE: RunConfig.bar_lookback is 60, MinuteBars is a
    deque with maxlen=60, and detect_break(look_min=60) needs 61 — sixty for the level plus the
    signal bar. Off by one, permanently, silently: shadow_mgc.db would have held zero rows forever.
    A guard that cannot observe the failure it was written for is not a guard. This one drives the
    real sim and asserts a POSITION OPENS."""
    sim, mb, _st = _sim(tmp_path)
    t = _break(mb, _grind(mb, 70))                           # closes well above the 60-bar high
    book = {f"{s}{k}{f}": 0.0 for s in ("bid", "ask") for k in range(1, 11) for f in ("p", "s")}
    book.update(bid1p=3004.0, bid1s=6.0)                     # asks EMPTY near the level -> VACUUM
    sim.on_bars(mb.bars(), now_ms=t * 1000, book=book)
    assert "mgc_holebreak_fade_short" in sim._open, "the gate did not fire — finding #1 is back"


def test_the_shipped_lookback_is_big_enough(tmp_path):
    """The regression that would reintroduce #1: a 60-bar deque can never satisfy look_min=60."""
    from gazbot7.shadow_mgc import BAR_LOOKBACK
    assert BAR_LOOKBACK >= 61, "detect_break(look_min=60) needs 61 bars"
    sim, mb, _st = _sim(tmp_path, lookback=60)               # the OLD, broken configuration
    t = _break(mb, _grind(mb, 70))
    book = {f"{s}{k}{f}": 0.0 for s in ("bid", "ask") for k in range(1, 11) for f in ("p", "s")}
    book.update(bid1p=3004.0, bid1s=6.0)
    sim.on_bars(mb.bars(), now_ms=t * 1000, book=book)
    assert not sim._open, "a 60-bar deque must NOT be able to fire — this test proves the bug existed"


def test_one_decision_per_BAR_not_per_tape_message(tmp_path):
    """★★★ AUDIT FINDING #3. on_bars re-runs on every T_TAPE (1/s), re-evaluating the same newest
    bar ~60 times. The break cannot change during the minute — only the BOOK can — so the effective
    rule became 'was the far side empty at ANY second?' rather than 'at the bar's close'. Measured
    on real depth that admitted 85.9% of breaks against the research's 47.1%: 1.82x the population,
    and the book cut IS the gate."""
    sim, mb, _st = _sim(tmp_path)
    t = _break(mb, _grind(mb, 70))
    walled = {f"{s}{k}{f}": 0.0 for s in ("bid", "ask") for k in range(1, 11) for f in ("p", "s")}
    walled.update(ask1p=3001.0, ask1s=50.0, bid1p=3004.0, bid1s=6.0)   # a WALL: no trade
    sim.on_bars(mb.bars(), now_ms=t * 1000, book=walled)
    assert not sim._open
    empty = dict(walled); empty.update(ask1p=0.0, ask1s=0.0)           # book clears 30s later
    sim.on_bars(mb.bars(), now_ms=t * 1000 + 30_000, book=empty)
    assert not sim._open, "re-decided the same bar on a later book — finding #3 is back"


def test_the_45_minute_cooldown_is_enforced(tmp_path):
    """★★★ AUDIT FINDING #2. The research (gf_mgc_cells.cooldown, cool=45) and every ShadowVariant
    line in the spec carry cooldown_min=45; it was silently dropped. Without it the same rule makes
    $2.67 a trade instead of $12.47 — 79% of the edge — and inflates n with correlated re-entries of
    one move, breaking the independence every robustness test assumes."""
    from gazbot7.shadow import mgc_slate
    v = [x for x in mgc_slate() if x.side == "SHORT"][0]
    sim, mb, _st = _sim(tmp_path)
    t = _break(mb, _grind(mb, 70))
    sim._cool_until[v.name] = float(t) + 45 * 60            # as if a trade had just closed
    book = {f"{s}{k}{f}": 0.0 for s in ("bid", "ask") for k in range(1, 11) for f in ("p", "s")}
    book.update(bid1p=3004.0, bid1s=6.0)
    sim.on_bars(mb.bars(), now_ms=t * 1000, book=book)
    assert not sim._open, "entered inside the 45-minute cooldown"
    assert v.params.get("cooldown_min", 45) == 45


def test_the_repricer_replays_the_GOLD_trail(tmp_path):
    """★★ AUDIT FINDING #4. chandelier_params() built from default_slate() (MNQ) only, so MGC names
    missed and the repricer fell back to (3.5, 0.5, 0.75) — a TIGHTENING trail — while the sim runs a
    CONSTANT 2.0xATR. real_pnl is the only number this desk trusts and it was scoring an exit the
    strategy does not use."""
    from gazbot7.shadow import chandelier_params
    p = chandelier_params()
    for n in ("mgc_holebreak_fade_long", "mgc_holebreak_fade_short"):
        assert n in p, "MGC missing -> repricer silently uses the MNQ 3.5 tightening default"
        start_k, min_k, tighten = p[n]
        assert (start_k, min_k, tighten) == (2.0, 2.0, 0.0), "must be a FLAT 2.0xATR trail"


def test_the_repricer_is_not_charged_the_spread_twice():
    """★★ AUDIT FINDING #5. repricer fills entry AND exit at the far touch, so the round-trip spread
    is already inside `gross`. Subtracting MGC_FEE_RT ($6.00 spread + $1.50 commission) charged it
    again: $6/trade, 31% of the LONG cell and 40% of the SHORT. The research's own true_pnl is
    crossed fills MINUS $1.50."""
    from gazbot7.levelbreak import MGC_FEE_RT
    from gazbot7.shadow_mgc import REPRICER_FEE_RT, mgc_cfg
    assert REPRICER_FEE_RT == 1.50 and mgc_cfg().fee_rt == 1.50
    assert MGC_FEE_RT == 7.50, "the mid-priced constant stays 7.50 — they are not interchangeable"


def test_the_gold_store_is_backed_up_and_inventoried():
    """★★ AUDIT FINDING #6. Its own store by design, which is exactly why it was in no backup, no
    inventory and no sweep. 'Backblaze is the record' — an unbacked store is a book that does not
    really exist, and an empty table pages nobody."""
    assert "shadow_mgc.db" in open("scripts/cloud_backup.py").read()
    assert "shadow_mgc.db" in open("scripts/data_inventory.py").read()
