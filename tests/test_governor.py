"""Shadow→live gate controller — the state machine that turns a gate's live desk on/off
by watching its own shadow P&L. The invariants that matter: it never uses a trade's own
outcome to decide whether that trade was live (no look-ahead), it re-arms after recovery,
and the stickier predictors actually damp the churn a naive window would produce.
"""
from __future__ import annotations

from gazbot7.governor import GovConfig, govern

H = 3600


def _t(seq):
    """seq of (hour_float, pnl) → (ts, pnl) with a fixed session_t0=0."""
    return [(int(h * H), p) for h, p in seq]


def test_window_arms_after_warmup_and_tracks_live_only():
    # warmup 2h; a strong green window at 2h+ arms it, then a green trade is banked live
    cfg = GovConfig(predictor="window", window_h=2.0, on_thr=50, off_thr=-100)
    trades = _t([(0.5, 40), (1.0, 40), (2.5, 30), (3.0, 25)])
    r = govern(trades, 0, cfg)
    # trades before 2h warmup are never live; the 2.5h trade sees +80 prior → arms;
    # itself is banked because state flips to live BEFORE we add it
    assert r.n_live >= 1
    assert r.full_pnl == 135.0


def test_no_lookahead_a_trades_own_pnl_cannot_arm_it():
    # a single huge win at 3h with nothing before it: window sum of PRIOR trades is 0,
    # below on_thr → that trade is NOT taken live (can't use its own result to arm)
    cfg = GovConfig(predictor="window", window_h=1.0, on_thr=50, off_thr=-100)
    r = govern(_t([(3.0, 500)]), 0, cfg)
    assert r.n_live == 0
    assert r.live_pnl == 0.0


def test_window_disarms_on_bleed_then_re_arms_on_recovery():
    cfg = GovConfig(predictor="window", window_h=1.0, on_thr=50, off_thr=-80)
    # arm (two +50s), then bleed (two -60s → window <= -80 disarms), then recover (+60s)
    trades = _t([(1.1, 50), (1.2, 50), (2.0, -60), (2.1, -60), (3.0, 60), (3.1, 60)])
    r = govern(trades, 0, cfg)
    assert r.n_flips >= 2          # on … off … on
    assert 0 < r.n_live < r.n_total


def test_sticky_cooldown_blocks_a_too_quick_re_arm():
    base = GovConfig(predictor="window", window_h=0.5, on_thr=50, off_thr=-80)
    sticky = GovConfig(predictor="sticky", window_h=0.5, on_thr=50, off_thr=-80, cooldown_h=1.0)
    # arm ~0.7h, disarm ~1.6h, then a green blip at 2.0-2.3h (0.7h after the OFF, inside
    # the 1h cooldown) that clears the base window and would re-arm it
    trades = _t([(0.6, 60), (0.7, 60), (1.5, -90), (1.6, -90), (2.0, 60), (2.3, 60)])
    rb = govern(trades, 0, base)
    rs = govern(trades, 0, sticky)
    # the window governor re-arms on the blip; sticky refuses inside the cooldown → fewer flips
    assert rs.n_flips < rb.n_flips


def test_streak_needs_consecutive_wins_to_arm_and_losses_to_disarm():
    cfg = GovConfig(predictor="streak", win_k=2, loss_m=2)
    # W W (arm) W (live) L L (disarm) W W (re-arm)
    trades = _t([(0.1, 10), (0.2, 10), (0.3, 10), (0.4, -10), (0.5, -10), (0.6, 10), (0.7, 10)])
    r = govern(trades, 0, cfg)
    assert r.n_flips >= 2          # arms, disarms, re-arms
    # a single win never arms
    r1 = govern(_t([(0.1, 10), (0.2, -5)]), 0, cfg)
    assert r1.n_live == 0


def test_full_pnl_is_always_the_ungoverned_book():
    cfg = GovConfig(predictor="sticky")
    trades = _t([(0.5, 30), (1.0, -20), (5.0, 80)])
    r = govern(trades, 0, cfg)
    assert r.full_pnl == 90.0
    assert r.live_pnl <= r.full_pnl
