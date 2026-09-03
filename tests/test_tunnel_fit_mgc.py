"""The gold tunnel fit — the properties that, if broken, would produce a plausible wrong answer.

★2026-09-03. Every test EXECUTES the thing it is about. A source-grep test passed green on this
desk while the code under it crashed, three times in seven days, so nothing here reads source.
"""

from __future__ import annotations

import math
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import tunnel_fit_mgc as tf  # noqa: E402

np = pytest.importorskip("numpy")


# ── the finding that shaped the fit ──────────────────────────────────────────
def test_zero_range_minutes_are_masked_not_floored():
    """A minute where nothing printed has an UNOBSERVED range, not a zero one. Floored to 1e-6 it
    lands at logTR −13.8 against a real distribution living in [−2.5, +4.5], and a 2-state HMM
    spends a whole state on the spike — the first gold fit returned quiet = 0.03pt covering 2.5%
    of minutes, which is a dead-tape detector, not a compression detector."""
    obs = tf.observations([1.0, 0.0, 2.0, None, 0.04, 3.0])
    assert math.isnan(obs[1]), "a zero true range must be missing, not tiny"
    assert math.isnan(obs[3]), "a roll seam must be missing"
    assert math.isnan(obs[4]), "sub-half-tick is below what the instrument can express"
    assert not math.isnan(obs[0]) and not math.isnan(obs[5])
    assert obs[0] == pytest.approx(math.log(1.0))


def test_masked_minutes_do_not_move_the_fitted_means():
    """The mask must inform transitions and NOTHING else. If a masked minute leaked into the M
    step it would drag a mean toward whatever placeholder it carried."""
    random.seed(3)
    clean = [math.log(random.lognormvariate(0.0, 0.3)) for _ in range(4000)]
    mu_a, _, _, _ = tf.fit_hmm(np.array(clean))
    holed = list(clean)
    for i in range(0, 4000, 25):
        holed[i] = float("nan")
    mu_b, _, _, _ = tf.fit_hmm(np.array(holed))
    assert abs(mu_a[0] - mu_b[0]) < 0.25 and abs(mu_a[1] - mu_b[1]) < 0.25


# ── does the model actually work? ────────────────────────────────────────────
def _synthetic(n=6000, mu=(0.0, 1.2), sd=(0.35, 0.35), stay=(0.99, 0.985), seed=11):
    rnd = random.Random(seed)
    s, out, states = 0, [], []
    for _ in range(n):
        out.append(rnd.gauss(mu[s], sd[s]))
        states.append(s)
        if rnd.random() > stay[s]:
            s = 1 - s
    return np.array(out), states


def test_fit_recovers_parameters_it_was_given():
    x, _ = _synthetic()
    mu, sd, A, _ = tf.fit_hmm(x)
    assert mu[0] == pytest.approx(0.0, abs=0.15)
    assert mu[1] == pytest.approx(1.2, abs=0.15)
    assert A[0][0] == pytest.approx(0.99, abs=0.02)
    assert A[1][1] == pytest.approx(0.985, abs=0.03)


def test_quiet_is_always_state_zero():
    """Baum-Welch has no idea which state is which. Two refits coming back label-swapped make a
    stability check read as a total model failure when nothing actually moved."""
    x, _ = _synthetic()
    mu, _, _, _ = tf.fit_hmm(x)
    assert mu[0] < mu[1]
    mu2, _, _, _ = tf.fit_hmm(-x)          # mirrored data — the labels must still come back sorted
    assert mu2[0] < mu2[1]


def test_filter_finds_the_states_it_was_generated_from():
    x, states = _synthetic()
    mu, sd, A, _ = tf.fit_hmm(x)
    post = tf.filter_quiet(x, mu, sd, A)
    hit = sum(1 for p, s in zip(post, states) if (p >= 0.5) == (s == 0))
    assert hit / len(states) > 0.85


# ── causality: the three places a look-ahead would hide ──────────────────────
def test_filter_is_causal():
    """P(quiet at t) must not change when later data arrives. Viterbi/smoothing would fail this,
    which is exactly why production forward-filters."""
    x, _ = _synthetic(n=1200)
    mu, sd, A, _ = tf.fit_hmm(x)
    short = tf.filter_quiet(x[:600], mu, sd, A)
    long_ = tf.filter_quiet(x, mu, sd, A)
    assert short == pytest.approx(long_[:600], abs=1e-12)


def test_normalised_baseline_excludes_the_minute_it_scores():
    """The trailing median is shifted by one. A minute inside its own baseline is a look-ahead —
    small, and still a lie."""
    flat = [math.log(1.0)] * 600
    xa = np.array(flat + [math.log(50.0)] + flat)
    xb = np.array(flat + [math.log(0.02)] + flat)
    a, b = tf.normalised(xa, window=300, min_periods=60), tf.normalised(xb, window=300, min_periods=60)
    # everything BEFORE the odd minute is untouched by it
    assert a[:600] == pytest.approx(b[:600], nan_ok=True)
    # and the odd minute's own BASELINE (value - normalised) is identical in both series, which is
    # only true if minute t is excluded from the median it is scored against
    assert (xa[600] - a[600]) == pytest.approx(xb[600] - b[600])
    # and the window is genuinely LIVE, not lagged into irrelevance: a sustained shift moves the
    # baseline for the minutes that follow it (one outlier does not — the baseline is a MEDIAN,
    # which is the point of using one on a tape that prints the occasional 20-ATR minute)
    xc = np.array(flat + [math.log(50.0)] * 200 + flat)
    c = tf.normalised(xc, window=300, min_periods=60)
    assert (xc[850] - c[850]) != pytest.approx(math.log(1.0))


def test_race_starts_after_the_decision_bar():
    """Racing from the break bar's own high/low replays the minute the decision was made, knowing
    how it ended — the documented 'resample labels the left edge' error."""
    bars = [{"m": i * 60, "hi": 100.0, "lo": 100.0, "close": 100.0} for i in range(30)]
    bars[10] = {"m": 600, "hi": 130.0, "lo": 70.0, "close": 100.0}   # a huge bar AT the decision
    r = tf.race(bars, 10, atr=1.0, mults=(2.0,), horizon=10, direction=1)
    assert r["mfe"] == 0.0 and r["mae"] == 0.0, "bar i0 itself must not be raced"
    assert r["passage"][2.0] == 0


def test_race_scores_an_unresolvable_bar_as_a_loss():
    """Both barriers inside one minute cannot be ordered at this resolution. Calling it a win is
    how a backtest flatters itself; it is scored adverse."""
    bars = [{"m": i * 60, "hi": 100.0, "lo": 100.0, "close": 100.0} for i in range(10)]
    bars[3] = {"m": 180, "hi": 110.0, "lo": 90.0, "close": 100.0}
    r = tf.race(bars, 0, atr=1.0, mults=(2.0,), horizon=8, direction=1)
    assert r["passage"][2.0] == -1


# ── one break per tunnel ─────────────────────────────────────────────────────
def _flat(n, price=100.0):
    return [{"m": i * 60, "hi": price, "lo": price, "close": price} for i in range(n)]


def test_one_break_per_tunnel_not_one_per_minute_outside():
    """Counting every minute price spends outside the range multiplies one event by its duration
    and inflates every rate computed from it."""
    bars = _flat(40)
    for i in range(40, 50):                       # ten minutes all well outside, one event
        bars.append({"m": i * 60, "hi": 120.0, "lo": 119.0, "close": 119.5})
    trs = [1.0] * len(bars)
    post = [1.0] * 40 + [0.0] * 10
    tun, brk = tf.tunnels_and_breaks(bars, trs, post, min_tunnel=25)
    assert len(brk) == 1
    assert brk[0]["side"] == "UP" and brk[0]["tunnel_n"] == 40


def test_a_short_tunnel_never_arms():
    bars = _flat(10) + [{"m": i * 60, "hi": 120.0, "lo": 119.0, "close": 119.5} for i in range(10, 20)]
    trs = [1.0] * len(bars)
    post = [1.0] * 10 + [0.0] * 10
    _, brk = tf.tunnels_and_breaks(bars, trs, post, min_tunnel=25)
    assert brk == []
