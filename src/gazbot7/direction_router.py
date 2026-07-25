"""GAZBOT V7 — live DIRECTION-ROUTER: bench the counter-trend reversion faders on a PROVEN trend.

The per-gate ER condition reads tape CLEANLINESS, not DIRECTION, so a clean DOWN-trend at ER 0.32
sits inside a long-fader's band and it fades the falling knife (07-23: rgv_long −$361 in one hour).
This flips the COUNTER-TREND REVERSION faders off once a trend is PROVEN, back on in chop:

    TREND DOWN → off {rgv_long, capitulation_long}   (long-faders fade the drop)
    TREND UP   → off {rgv_short, exhaustion_short}    (short-faders fade the rise)
    CHOP       → all managed gates ON

Momentum gates (grind_long, thrust_short) are NOT managed — they fire WITH thrusts (a down-thrust in
an up-trend can be the reversal), so direction doesn't bench them (tune: benching thrust_short cost a
winner and nothing else). HYSTERESIS: a raw per-mark signal becomes the effective state only after
HOLD consecutive marks agree — survives the sub-hour whipsaws that make hand-steering churn.

STATELESS: each run replays the Paris day's STEP-min marks from capture → the current effective state,
so a 15-min cron needs no persisted state. Writes gate_switches.env ONLY when the managed set must
change; logs + Telegrams (routine → self-suppresses in quiet hours) every flip. Market-closed /
stale-feed → HOLD (never flips on stale bars). It manages ONLY the 4 reversion faders — thrust_short /
grind_long and any operator switch on them are left untouched.

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
ER_TREND = 0.25     # ER must clear this for a mark to read as a trend (above the 0.18 bucket line)
NET_MIN = 40.0      # AND |net| over the window must be >= this (a real directional leg)
WINDOW = 30         # trailing 1-min bars for ER/net (matches the gate's 30-min ER)
STEP = 15           # minutes between marks
HOLD = 2            # consecutive agreeing marks to flip the effective state (hysteresis, both ways)
STALE_S = 200       # newest 1-min bar older than this → market closed / feed gap → HOLD

DOWN_OFF = frozenset({"capitulation_long"})   # long-faders — bench in a down-trend. ★2026-07-25: rgv_long REMOVED — it carries its OWN per-entry net30-depth floor in gate_reversal_grab, which dominates this coarse day-level bench (the router nuked rgv_long to −$9 by dropping 60% of its winners).
UP_OFF = frozenset({"rgv_short"})      # short-faders — bench in an up-trend. ★2026-07-25: exhaustion_short REMOVED (retired from roster, replaced by rgv_long).
MANAGED = DOWN_OFF | UP_OFF                                # the only gates the router controls


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
    return set()


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
    try:
        state, info = current_regime(now=now)
    except Exception as e:
        print(f"direction_router: regime read FAILED ({e}) — HOLD")
        return 0
    if state is None:
        print(f"direction_router: HOLD — {info}")
        return 0
    target = desired_off(state)
    try:
        text = Path(SWITCH).read_text()
    except OSError as e:
        print(f"direction_router: no switch file ({e}) — HOLD")
        return 0
    cur = disabled_from(text) & MANAGED
    if target == cur:
        print(f"direction_router: {state} (ER {info['er']}, net {info['net']:+.0f}) — no change, off={sorted(cur)}")
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
