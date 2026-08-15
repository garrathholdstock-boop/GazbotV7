"""NIPC — the news-impulse pullback state machine + its desk wiring.

★ SEE scripts/nipc_replay.py: the 12-day acceptance replay does NOT reproduce the Friday-M3
lab's +$2,676 (we get +$264 on the same tape with the same rules). The gate therefore ships
BENCHED. These tests pin the RULES as specified, not the lab's P&L claim.
"""
from __future__ import annotations

from gazbot7.deciders import Bar, NipcTracker

DAY = 1785110400          # 2026-07-27 00:00 UTC
T0 = DAY + 13 * 3600 + 600   # 13:10 UTC — inside the window
ATR, ER = 20.0, 0.50         # atr>=18 → never dead-chop


def _feed(tk, prices, t0=T0, **kw):
    for i, p in enumerate(prices):
        hi = p if not isinstance(p, tuple) else p[0]
        lo = p if not isinstance(p, tuple) else p[1]
        c = p if not isinstance(p, tuple) else p[2]
        tk.on_bar(Bar(t0 + 5 * i, c, hi, lo, c, 1.0), atr1m=kw.get("atr", ATR),
                  er15=kw.get("er", ER), busy=kw.get("busy", False))
    return t0 + 5 * len(prices)


def _impulse_then(tk, tail, **kw):
    """24 flat bars, one +60 impulse bar, then `tail`. Returns the next bar timestamp."""
    return _feed(tk, [100.0] * 24 + [160.0] + list(tail), **kw)


def test_impulse_then_pullback_arms_at_half_back():
    tk = NipcTracker()
    _impulse_then(tk, [130.0])                 # retrace 30/60 = 0.50 → arm
    s = tk.setup
    assert s is not None and s.side == "LONG" and s.armed_ms
    assert s.ext == 160.0 and s.org == 100.0 and s.span == 60.0
    assert s.pb_ext == 130.0
    assert s.entry_level == 145.0              # 130 + 0.50 × 30
    assert s.stop == 126.0                     # pullback extreme − 4
    assert s.r_pt == 19.0


def test_trigger_fires_only_on_a_tick_through_the_level():
    tk = NipcTracker()
    t = _impulse_then(tk, [130.0])
    assert tk.trigger(t * 1000, 144.75) is None      # not through yet
    fired = tk.trigger(t * 1000, 145.25)
    assert fired is not None and fired.side == "LONG" and fired.r_pt == 19.0
    assert tk.setup is None                          # consumed


def test_trigger_expires_after_one_minute_with_no_fill():
    tk = NipcTracker()
    t = _impulse_then(tk, [130.0])
    assert tk.trigger((t + 59) * 1000, 100.0) is None and tk.setup is not None
    assert tk.trigger((t + 61) * 1000, 145.25) is None   # expired → no trade
    assert tk.setup is None


def test_broken_impulse_is_not_a_pullback():
    tk = NipcTracker()
    _impulse_then(tk, [110.0])                 # retrace 50/60 = 0.83 > RMAX → abandon
    assert tk.setup is None


def test_shallow_retrace_does_not_arm_and_expires_after_three_minutes():
    tk = NipcTracker()
    _impulse_then(tk, [155.0] * 36)            # retrace 5/60 = 0.08, never reaches 0.35
    assert tk.setup is None


def test_dead_chop_regime_blocks_the_gate():
    tk = NipcTracker()                                        # apply_regime=True (LIVE)
    _impulse_then(tk, [130.0], atr=17.0, er=0.30)             # ATR<18 AND ER<0.35
    assert tk.setup is None
    loose = NipcTracker(apply_regime=False)                   # measurement book keeps it
    _impulse_then(loose, [130.0], atr=17.0, er=0.30)
    assert loose.setup is not None and loose.setup.dead_chop is True


def test_only_atr_or_only_er_low_is_not_dead_chop():
    """DEAD-CHOP still needs BOTH conditions, not either — the original point of this test, now
    asserted against the function directly. It moved off the tracker because the tracker applies a
    WIDER filter as of 2026-08-05 (nipc_bad_regime), so 'not dead-chop' no longer implies 'takes it'."""
    from gazbot7.deciders import nipc_dead_chop
    assert nipc_dead_chop(17.0, 0.40) is False      # ATR low, ER fine
    assert nipc_dead_chop(25.0, 0.20) is False      # ER low, ATR fine
    assert nipc_dead_chop(17.0, 0.20) is True       # both -> dead-chop


def test_tracker_applies_the_widened_regime_filter():
    """★2026-08-05 BEHAVIOUR CHANGE, deliberate and pinned here. The n>=40 review found nipc's losses
    concentrated in violent-whipsaw (-$55/n=50) and normal-chop (-$34/n=11), while rule 7 was only
    cutting dead-chop — the one bucket that costs nothing (+$2/n=21). The tracker now blocks all three.
    (25.0, 0.20) is NOT dead-chop but IS violent-whipsaw, so it is now refused where it previously
    produced a setup. Revert: deciders.NIPC_REGIME_FILTER = False."""
    tk = NipcTracker()
    _impulse_then(tk, [130.0], atr=17.0, er=0.40)   # in-between-building -> still allowed
    assert tk.setup is not None
    tk2 = NipcTracker()
    _impulse_then(tk2, [130.0], atr=25.0, er=0.20)  # violent-whipsaw -> now BLOCKED
    assert tk2.setup is None


def test_outside_the_news_window_never_arms():
    tk = NipcTracker()
    _impulse_then(tk, [130.0], t0=DAY + 15 * 3600 + 600)   # 15:10 UTC — window shut
    assert tk.setup is None


def test_busy_and_cooldown_suppress_new_impulses():
    tk = NipcTracker()
    _impulse_then(tk, [130.0], busy=True)          # rule 6: one position at a time
    assert tk.setup is None
    tk2 = NipcTracker()
    tk2.note_exit((T0 + 60) * 1000)   # cooldown to T0+180; the impulse lands at T0+120
    _impulse_then(tk2, [130.0])
    assert tk2.setup is None


def test_short_side_is_the_mirror():
    tk = NipcTracker()
    _feed(tk, [100.0] * 24 + [40.0, 70.0])         # −60 impulse, 30/60 retrace up
    s = tk.setup
    assert s is not None and s.side == "SHORT"
    assert s.entry_level == 55.0 and s.stop == 74.0 and s.r_pt == 19.0


# ── desk wiring ───────────────────────────────────────────────────────────────
def test_nipc_is_retired_from_the_live_roster():
    """★★2026-08-15 NIPC RETIRED. Operator: "delete nipc gates theyve never done anything."

    It hit his -$400 kill criterion (n=47, 26% win), then sat PINNED OFF and held out of the 22:00
    reactivation, so it last traded 2026-08-06. Whole live record: 49 lots, -$434.50, 08-03..08-06.

    Removing the SlotSpecs is what retires it — no spec means no slot, no intents, no switch to
    manage. This test is the guard: nipc must not reappear on the roster by accident (a revert, a
    merge, a helpful edit). Reviving it is a deliberate act that changes this test.

    ⚠ What is NOT deleted, and deliberately: the deciders, the NipcTracker, `_FIXED_PAIR`, and the
    rest of this file. A refuted lead is archived, not erased — and its 49 historical trades stay in
    the ledger untouched, because deleting them to tidy a roster would corrupt the P&L record."""
    from gazbot7.slot_strategy import scaleout_slots, tournament_slots
    assert not [s for s in tournament_slots() if s.kind == "nipc" or s.tag.startswith("nipc")]
    assert not [s for s in scaleout_slots() if s.tag.startswith("nipc")]


def test_the_proven_pair_is_kept_for_a_revival(monkeypatch):
    """nipc is retired, but `_FIXED_PAIR` stays. It is the reason a revival would get the PROVEN
    2.0R/2.5R pair back rather than silently inheriting the fader default (A@1.5R + a TIGHT
    CHANDELIER Lot B) — and the lab explicitly falsified a trailing Lot B for this gate. Deleting the
    constant along with the roster entry is how a revived gate comes back subtly wrong."""
    import gazbot7.slot_strategy as SS
    monkeypatch.setattr(SS, "_EXIT_OVERRIDES_PATH", "/nonexistent/exit_overrides.json")
    assert SS._FIXED_PAIR["nipc_long"] == (2.0, 2.5)
    assert SS._FIXED_PAIR["nipc_short"] == (2.0, 2.5)
    assert not [s for s in SS.scaleout_slots() if s.tag.startswith("nipc")]


def test_time_cap_and_flat_clock_exits():
    from gazbot7.slot_strategy import SlotSpec, SlotStrategy
    from gazbot7.slotbook import Slot
    spec = SlotSpec("nipc_long", "nipc", "LONG", exit="scalp", target_r=2.5,
                    max_hold_s=1200, flat_by_utc_s=15 * 3600 + 1800)
    st = SlotStrategy([spec], value_per_point=2.0)
    slot = Slot("nipc_long", side="LONG", entry_qty=1, entry_notional=100.0,
                opened_at="2026-07-27T13:10:00+00:00", entry_atr=19.0)
    t = (DAY + 13 * 3600 + 600) * 1000
    assert st._manage(spec, slot, 100.0, t + 60_000) is None            # 1 min in → hold
    assert st._manage(spec, slot, 100.0, t + 1_250_000) == "TIME_CAP"   # 20.8 min → cut
    assert st._manage(spec, slot, 100.0, (DAY + 15 * 3600 + 1801) * 1000) == "SESSION_FLAT"
    assert st._manage(spec, slot, 100.0, None) is None                  # no clock → no time exit


def test_open_intent_carries_R_as_entry_atr():
    """The whole exit contract: R (|entry − stop|) rides on entry_atr, so the native STP and
    exit_scalp land on the lab's stop / 2.0R / 2.5R without new exit machinery."""
    from gazbot7.deciders import Features
    from gazbot7.slot_strategy import SlotSpec, SlotStrategy
    from gazbot7.slotbook import SlotBook
    spec = SlotSpec("nipc_long", "nipc", "LONG", exit="scalp", target_r=2.5, risk_budget_usd=0.0)
    st = SlotStrategy([spec], value_per_point=2.0)
    sb = SlotBook(["nipc_long"], value_per_point=2.0, fee_rt=1.5)
    bars = [Bar(T0 + 60 * i, 100.0, 101.0, 99.0, 100.0 + i, 1.0) for i in range(30)]
    f = Features(price=145.0, atr=33.0, atr_pct=0.001, vwap=140.0, vwap_slope_atr=0.1,
                 ext_atr=0.1, net_atr_5=0.1, vol_surge=True, n_bars=30)
    st._nipc.setup = None
    st._nipc._bars.clear(); st._nipc._atrs.clear()
    _impulse_then(st._nipc, [130.0])
    out = st.decide(f, 145.25, bars, sb, 0.0, None, (T0 + 130) * 1000)
    assert [i["slot"] for i in out] == ["nipc_long"]
    assert out[0]["meta"]["entry_atr"] == 19.0        # R, NOT the 33-pt bar ATR
    assert out[0]["side"] == "LONG" and out[0]["qty"] == 1
