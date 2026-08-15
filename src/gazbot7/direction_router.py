"""GAZBOT V7 — live DIRECTION-ROUTER: bench the counter-trend reversion faders on a PROVEN trend.

The per-gate ER condition reads tape CLEANLINESS, not DIRECTION, so a clean DOWN-trend at ER 0.32
sits inside a long-fader's band and it fades the falling knife (07-23: rgv_long −$361 in one hour).
This flips the COUNTER-TREND REVERSION faders off once a trend is PROVEN, and (★2026-07-27) benches the
MOMENTUM gates in CHOP — the symmetric completion:

    TREND DOWN → off {capitulation_long}                    (long-fader fades the drop)
    TREND UP   → off {rgv_short}                            (short-fader fades the rise)
    CHOP       → off {grind_long, abs_veto_long, abs_veto_short}   (momentum whipsaws in chop)

★2026-07-27 (operator): the router already KNOWS when it's chop — so it benches the momentum gates then.
Validated on realised trades 07-20..27: the momentum book is −$757 in CHOP-regime@entry vs +$18 in TREND
(robust — chop bled them 5 of 7 days). Momentum stays ON in a proven trend (it self-selects by direction:
grind_long/abs_veto_long ride up-legs, abs_veto_short down-legs). Faders stay ON in chop (reversion's home).
HYSTERESIS: a raw per-mark signal becomes the effective state only after
HOLD consecutive marks agree — survives the sub-hour whipsaws that make hand-steering churn.

STATELESS: each run replays the Paris day's STEP-min marks from capture → the current effective state,
so a 15-min cron needs no persisted state. Writes gate_switches.env ONLY when the managed set must
change; logs + Telegrams (routine → self-suppresses in quiet hours) every flip. Market-closed /
stale-feed → HOLD (never flips on stale bars). MANAGED = the 2 faders + the 3 momentum gates (CHOP_OFF);
gates outside MANAGED and any operator switch on the unmanaged ones are left untouched.

Backtest = scripts/direction_router_backtest.py (imports THIS module's logic + constants — no drift).
Tuned + validated Mon–Thu 2026-07-20..23: baseline −$2408 → router −$1828 (+$580), no negative day.
Operator standing-approval, LIVE from 2026-07-24 (Fri) — "see how it goes". While live it OWNS the 4
managed gates (a manual /off on one is re-applied by regime). Revert = disable the timer:
`sudo systemctl disable --now gazbot7-direction-router.timer`.
"""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
import sys
from pathlib import Path

from . import pnl
from .telegram_bot import apply_gate_switch, disabled_from

DATA = "/home/alphabot/gazbot7/data"
CAP = f"{DATA}/capture.db"
SWITCH = f"{DATA}/gate_switches.env"

# ── tuned + validated knobs (edit here → both live AND the backtest move together) ──
ER_TREND = 0.15     # ★2026-08-01 (operator, Saturday window) loosened 0.20→0.15.
                    #
                    # ⚠ RATIONALE CORRECTED SAME DAY BY AUDIT — read this before citing the number below.
                    # It was shipped on the fader-bench study (ER0.20/NET30 +$176/+$995 → ER0.15/NET30 +$492/+$1,307,
                    # ER0.15 winning every net column on both universes). That study measures direction_router's
                    # mechanical fader bench — and THAT PATH IS SWITCHED OFF: gazbot7-direction-router.timer is
                    # disabled+inactive, and the Claude router that actually owns gate_switches.env never reads
                    # ER_TREND. So the cited benefit is currently UNREACHABLE.
                    # The ONLY live consumer is slot_strategy._regime_mode (line ~293), and under the scaleout slate
                    # every sub-slot has adaptive_exit=False, so _regime_mode is reached solely via
                    # veto_counter_regime — i.e. exhaustion_short and nothing else. Measured on 16,708 MNQ 1-min
                    # marks (16 days): the counter-veto surface goes 19.20% → 23.68% of minutes, so the real effect
                    # is ~23% MORE exhaustion_short entries vetoed. Nothing else on the desk changes.
                    # KEPT at 0.15 anyway because that is the CHEAP direction (more vetoing = fewer entries; the
                    # desk's standing asymmetry is wrongly-benched cheap / wrongly-armed expensive), and Q1 found
                    # exhaustion bleeds counter-trend. But it is an UNMEASURED side effect, not the advertised win —
                    # measure it before claiming value. Re-enabling the direction-router timer would make the
                    # original study apply again.
                    # NOTE: distinct from grind's ER ARMING floor — this is "is the tape trending", that is "switch the
                    # gate on at all". Revert: ER_TREND = 0.20.
                    # [prev 0.20] ★2026-07-26 loosened 0.25→0.20 (operator, router_study.py): the 0.25 trigger was too STRICT
                    # — mild-but-real trends read as CHOP and the faders bled into them unblocked (leaked −$641 live /
                    # −$1,453 hist of counter-trend near-miss losers vs blocking only −$152/−$736). Both fader sets agreed
                    # looser blocks more net loss; this is the MODERATE step (grid-best pinned every knob to the edge = overfit).
NET_MIN = 30.0      # ★2026-07-26 loosened 40→30 with ER (same study). AND |net| over the window must be >= this (a real leg).
WINDOW = 30         # trailing 1-min bars for ER/net (matches the gate's 30-min ER)
STEP = 15           # minutes between marks
HOLD = 2            # consecutive agreeing marks to flip the effective state (hysteresis, both ways)
STALE_S = 200       # newest 1-min bar older than this → market closed / feed gap → HOLD

DOWN_OFF = frozenset({"capitulation_long"})   # long-faders — bench in a down-trend. ★2026-07-25: rgv_long REMOVED — it carries its OWN per-entry net30-depth floor in gate_reversal_grab, which dominates this coarse day-level bench (the router nuked rgv_long to −$9 by dropping 60% of its winners).
UP_OFF = frozenset({"rgv_short", "exhaustion_short"})   # short-faders — bench in a PROVEN up-trend.
# ★★2026-08-15 exhaustion_short RESTORED. It was dropped on 07-25 "(retired from roster, replaced by
# rgv_long)" — correct when written, wrong the moment it came back. It has been live and UNMANAGED
# for three weeks and is the desk's busiest gate: 71 of the 108 trades in the week to 08-14, of which
# 12 fired straight into a CONFIRMED TREND_UP for -$241.00 (-$20.08/trade). Over 30 days: 26
# counter-trend fires, -$398.50, red on 7 of the 8 days it happened, surviving strip-worst-day and
# leave-one-day-out. The router was "managing an empty room" — its only other UP-side member,
# rgv_short, is in reactivate_gates.HOLD and never fires.
# ⚠ THIS DOES NOT BREACH THE 2026-08-07 CARVE-OUT, and the distinction is the whole point. That
# carve-out removed ONE trigger — day-bias SIGN — because benching a FADER because the day is up
# removes it exactly when its setup forms. It explicitly PRESERVED the tested fader bench: "bench
# exhaustion_short when a TREND/RUN is genuinely running against a fade (+$810 non-overlap, n=25)".
# TREND_UP here is that case, not day-bias sign: it needs ER >= ER_TREND and |net| >= NET_MIN and
# must survive HYSTERESIS. Revert: drop "exhaustion_short" from this frozenset.
CHOP_OFF = frozenset({"grind_long", "abs_veto_long", "abs_veto_short"})   # MOMENTUM gates — bench in CHOP.
# ★2026-07-27 (operator): the symmetric completion — faders off in trends (above), momentum off in chop. Momentum
# gates fire on short bursts that revert in choppy tape; validated on realised trades 07-20..27: the momentum book
# is −$757 in CHOP-regime@entry vs +$18 in TREND (robust — chop bled them on 5 of 7 days). The router already
# KNOWS it's chop; this uses that read. Momentum stays ON in TREND_UP/DOWN (self-selects by direction).
MANAGED = DOWN_OFF | UP_OFF | CHOP_OFF                     # the gates the router controls

# ★2026-07-28 (operator): the US cash open (13:30 UTC = 15:30 Paris summer) produces big directional
# RUNS the momentum gates exist to catch. Even if the pre-open read CHOP, do NOT bench the momentum
# gates across the open — keep them ON to capture the opening move. Window opens 13:15 UTC so the
# 13:15 router mark un-benches momentum ~15 min BEFORE the 13:30 open; runs to 14:00 (first 30 min of
# the cash session). Faders stay regime-managed (a fader fading the opening run SHOULD stay benched).
OPEN_WINDOW_UTC = (13, 15, 14, 0)   # (start_h, start_m, end_h, end_m) UTC


def in_open_window(now: dt.datetime) -> bool:
    h1, m1, h2, m2 = OPEN_WINDOW_UTC
    t = now.hour * 60 + now.minute
    return h1 * 60 + m1 <= t < h2 * 60 + m2


def er_net(closes: list[float]) -> tuple[float, float]:
    """Kaufman ER + signed net over the last WINDOW closes. <6 → (0,0) (no data → read as chop)."""
    c = closes[-WINDOW:]
    if len(c) < 6:
        return 0.0, 0.0
    path = sum(abs(c[i] - c[i - 1]) for i in range(1, len(c))) or 1.0
    return abs(c[-1] - c[0]) / path, c[-1] - c[0]


def replay_marks(minutes: list[int], closes: list[float], t_start: int, t_end: int,
                 fast_exit: bool = False) -> list[tuple]:
    """Replay STEP-min marks over [t_start, t_end], applying the HOLD-mark hysteresis. Returns
    [(mark_epoch, effective_state, er, net)]. Shared by the live router and the backtest.

    ``fast_exit=False`` (SHIPPED behaviour): a trend flips only when HOLD consecutive marks are the
    SAME new state — sticky, but can OVER-HOLD a trend through an alternating chop/reversal patch
    (07-24: held TREND_DOWN through a chop→up patch, benching the longs ~45min too long).
    ``fast_exit=True`` (the sticky-exit fix): still needs HOLD same-trend marks to ENTER a trend from
    chop, but LEAVES a trend the moment the last HOLD marks are all NON-(current trend) — so a
    reversal or chop patch exits promptly (to the opposite trend if all HOLD marks agree on it, else
    to CHOP). Enter-lag (the whipsaw guard) is unchanged; only the exit is quicker."""
    marks: list[tuple] = []
    state = "CHOP"
    recent: list[str] = []
    t = max(minutes[0] - (minutes[0] % (STEP * 60)) + STEP * 60, int(t_start))
    while t <= t_end:
        er, net = er_net([closes[i] for i in range(len(minutes)) if minutes[i] <= t])
        raw = "TREND_UP" if (er >= ER_TREND and net >= NET_MIN) else \
              "TREND_DOWN" if (er >= ER_TREND and net <= -NET_MIN) else "CHOP"
        recent.append(raw)
        if len(recent) > HOLD:
            recent.pop(0)
        if len(recent) == HOLD:
            uniform = recent[0] if len(set(recent)) == 1 else None
            if state == "CHOP" or not fast_exit:              # confirm: HOLD identical marks flip it
                if uniform is not None and uniform != state:
                    state = uniform
            elif all(r != state for r in recent):             # in a trend + fast_exit: leave it now
                state = uniform if uniform in ("TREND_UP", "TREND_DOWN") else "CHOP"
        marks.append((t, state, round(er, 2), round(net, 0)))
        t += STEP * 60
    return marks


def desired_off(state: str) -> set:
    """Managed gates that should be OFF in the given effective state."""
    if state == "TREND_DOWN":
        return set(DOWN_OFF)
    if state == "TREND_UP":
        return set(UP_OFF)
    return set(CHOP_OFF)   # CHOP → bench the momentum gates (they whipsaw in chop); faders stay on


def _day_bounds(now: dt.datetime) -> tuple[float, float]:
    t0s = pnl.paris_day_start_utc(now)
    t0 = dt.datetime.fromisoformat(t0s).timestamp() if isinstance(t0s, str) else t0s.timestamp()
    return t0, now.timestamp()


def _load_day(cap_path: str, t0: float, t_end: float) -> tuple[list[int], list[float]]:
    con = sqlite3.connect(f"file:{cap_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT (bar_ts-bar_ts%60) m, close FROM bars WHERE symbol='MNQ' AND timeframe='5s' "
            "AND bar_ts>=? AND bar_ts<=? ORDER BY bar_ts", (t0 - WINDOW * 60, t_end)).fetchall()
    finally:
        con.close()
    d = {}
    for m, c in rows:      # ordered asc → keep the last close per minute
        d[m] = c
    mins = sorted(d)
    return mins, [d[m] for m in mins]


def current_regime(cap_path: str = CAP, now: dt.datetime | None = None):
    """(state, info) — the effective regime NOW. state=None + info['hold'] when we must HOLD
    (stale feed / market closed / too few bars); never acts on stale data."""
    now = now or dt.datetime.now(dt.UTC)
    t0, t_end = _day_bounds(now)
    mins, closes = _load_day(cap_path, t0, t_end)
    if len(mins) < WINDOW:
        return None, {"hold": "insufficient bars", "n": len(mins)}
    bar_age = t_end - mins[-1]
    if bar_age > STALE_S:
        return None, {"hold": "stale/market-closed", "bar_age": round(bar_age)}
    marks = replay_marks(mins, closes, t0, int(t_end))
    _, state, er, net = marks[-1]
    return state, {"er": er, "net": net, "bar_age": round(bar_age)}


def run(now: dt.datetime | None = None) -> int:
    """One router cycle (systemd timer, every STEP min). Read regime → set the managed gates → write
    the switch file ONLY on a change, log + notify. Never raises (a hygiene job must not crash)."""
    now = now or dt.datetime.now(dt.UTC)
    try:
        state, info = current_regime(now=now)
    except Exception as e:
        print(f"direction_router: regime read FAILED ({e}) — HOLD")
        return 0
    if state is None:
        print(f"direction_router: HOLD — {info}")
        return 0
    target = desired_off(state)
    if in_open_window(now):
        target = target - CHOP_OFF   # US cash open — keep momentum ON to catch the opening run
        info["open_window"] = True
    try:
        text = Path(SWITCH).read_text()
    except OSError as e:
        print(f"direction_router: no switch file ({e}) — HOLD")
        return 0
    cur = disabled_from(text) & MANAGED
    tag = " [OPEN-WINDOW: momentum forced on]" if info.get("open_window") else ""
    if target == cur:
        print(f"direction_router: {state} (ER {info['er']}, net {info['net']:+.0f}) — no change, off={sorted(cur)}{tag}")
        return 0
    new = text
    for g in sorted(MANAGED):
        new = apply_gate_switch(new, g, "off" if g in target else "on")
    tmp = SWITCH + ".tmp"
    Path(tmp).write_text(new)
    os.replace(tmp, SWITCH)   # atomic; the tournament re-reads the switch file live (no restart)
    on = sorted(cur - target)
    off = sorted(target - cur)
    parts = (f"OFF {off} " if off else "") + (f"back ON {on}" if on else "")
    msg = f"{state} (ER {info['er']}, net {info['net']:+.0f}pt) → {parts}".strip()
    print(f"direction_router: FLIP — {msg}")
    try:
        from .notify import notify
        notify(f"V7 direction-router — {msg}", critical=False)   # routine: self-suppresses in quiet hours
    except Exception as e:
        print(f"direction_router: notify skipped ({e})")
    return 0


if __name__ == "__main__":
    sys.exit(run())
