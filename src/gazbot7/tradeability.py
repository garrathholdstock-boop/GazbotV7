"""TRADEABILITY 0-10 — a live read on what kind of tape we are sitting in.

Operator, 2026-08-03: "I want a reading on the dashboard live to show me what we are currently
sitting in. 0 = completely untradeable messy chop, 10 = smooth strong trends we can ride all day."

WHY A SECOND METER. `untradeable.py` already scores 0-100, but 2026-08-03 exposed two blind spots
that make it the wrong basis for a live gauge:
  1. Its roundtrip term is |net| / range, which reads DIRECTION where Kaufman ER reads CHOP. That day
     covered 624pt to net +303pt and it scored 37/100 = "TRADEABLE" — while the shadow book, the
     honest counterfactual, lost $2,586 across 18 of 19 mechanisms. Day Kaufman ER was 0.04.
  2. It is DAY-CUMULATIVE, so it describes a tape that may already be over. At 19:36 that same day it
     still read 37 while ATR had collapsed to 9pt and ER30 to 0.061.

So this is rolling, not cumulative, and it is built on the three things that actually separated good
tape from bad that day. It is a GUIDE, not a gate — nothing arms or benches off it.

★ CALIBRATION IS AGAINST GROUND TRUTH, NOT TASTE. Every day has a shadow-book total: what all the
mechanisms made, unmanaged, on that tape. `validate()` scores this meter against that number, so the
question "is the meter any good" is answerable instead of aesthetic. Run it after any change here.

THE THREE COMPONENTS (each 0-1, then weighted):
  EFFICIENCY (0.50) — Kaufman ER over 30 min. The single discriminator that was right on 08-03 when
      |net|/range was wrong. Chop travels a long way to go nowhere; ER is the only term that sees it.
  ROOM      (0.30) — ATR. Too little and there is nothing to win after spread+fee (a $15 target
      against a 0.75pt spread is ~20% friction); too much WITHOUT efficiency is violent whipsaw, the
      one regime measured as unsurvivable at every exit cell and every R from 0.5 to 6.0.
  PERSISTENCE (0.20) — is the recent move holding, or being handed back? Round-trippers were 20.6% of
      quiet-window trades and that is the give-back the desk actually bleeds on.

Deliberately NOT included: time of day (ATR carries it — see the halt-aware _atr note), and any
term the untradeable meter already owns.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

# component weights — see module docstring for why these three
W_EFFICIENCY, W_ROOM, W_PERSISTENCE = 0.50, 0.30, 0.20

ER_FLOOR, ER_CEIL = 0.10, 0.55      # 0.10 = noise; 0.55 = the desk's clean-trend cut
ATR_MIN, ATR_GOOD = 8.0, 20.0       # <8pt nothing survives friction; ~20pt is workable room
ATR_VIOLENT = 30.0                  # beyond this, room becomes hazard unless ER is high


def _lerp(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


@dataclass
class Read:
    score: float          # 0-10
    label: str
    efficiency: float
    room: float
    persistence: float
    er30: float
    atr: float
    detail: str


def score(er30: float, atr: float, give_back: float) -> Read:
    """er30 = Kaufman ER over the last 30 one-minute bars. atr = ATR-14 on 1-min bars (halt-aware).
    give_back = fraction of the recent favourable move handed back, 0..1 (0 = holding it all)."""
    eff = _lerp(er30, ER_FLOOR, ER_CEIL)

    # ROOM is deliberately non-monotonic. More vol is better only while there is efficiency to use it;
    # high ATR with low ER is the violent-whipsaw regime, which is worse than dead tape because it
    # also takes wide stops. So the top of the ATR range is discounted by how efficient the tape is.
    raw_room = _lerp(atr, ATR_MIN, ATR_GOOD)
    if atr > ATR_VIOLENT:
        raw_room *= 0.35 + 0.65 * eff      # unusable unless efficiency justifies it
    room = raw_room

    persistence = max(0.0, min(1.0, 1.0 - give_back))

    s = 10.0 * (W_EFFICIENCY * eff + W_ROOM * room + W_PERSISTENCE * persistence)
    s = max(0.0, min(10.0, s))

    if s < 2.0:
        label = "UNTRADEABLE — messy chop"
    elif s < 4.0:
        label = "POOR — grind, expect churn"
    elif s < 6.0:
        label = "MIXED — selective, veto-gates only"
    elif s < 8.0:
        label = "GOOD — tradeable trend"
    else:
        label = "STRONG — ride it"

    why = []
    if eff < 0.25:
        why.append(f"ER {er30:.2f} — going nowhere")
    if atr < ATR_MIN:
        why.append(f"ATR {atr:.0f}pt — no room after costs")
    if atr > ATR_VIOLENT and eff < 0.4:
        why.append(f"ATR {atr:.0f}pt with ER {er30:.2f} — VIOLENT WHIPSAW")
    if persistence < 0.5:
        why.append(f"handing back {100*give_back:.0f}% of the move")
    if not why:
        why.append(f"ER {er30:.2f}, ATR {atr:.0f}pt, holding {100*persistence:.0f}% of the move")
    return Read(round(s, 1), label, round(eff, 3), round(room, 3), round(persistence, 3),
                round(er30, 3), round(atr, 1), " · ".join(why))


def live(cap_path: str, *, symbol: str = "MNQ") -> Read:
    """Read the current tape straight from capture. Never raises — a bad read scores 0 with a reason,
    because a silent stale gauge is worse than one that admits it cannot see."""
    from .deciders import Bar, _atr
    from .sizing import efficiency_ratio
    try:
        con = sqlite3.connect(f"file:{cap_path}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT CAST(bar_ts/60 AS INTEGER)*60 m, MAX(high), MIN(low), "
            "  (SELECT close FROM bars b2 WHERE b2.symbol=b.symbol AND b2.timeframe=b.timeframe "
            "   AND CAST(b2.bar_ts/60 AS INTEGER)=CAST(b.bar_ts/60 AS INTEGER) "
            "   ORDER BY b2.bar_ts DESC LIMIT 1) "
            "FROM bars b WHERE symbol=? AND timeframe='5s' GROUP BY 1 ORDER BY 1 DESC LIMIT 60",
            (symbol,)).fetchall()
        con.close()
    except Exception as e:
        return score(0.0, 0.0, 1.0)._replace_detail(f"capture unreadable: {e}")
    if len(rows) < 31:
        return score(0.0, 0.0, 1.0)
    b = [Bar(ts=m, open=c, high=h, low=lo, close=c, volume=1.0) for m, h, lo, c in rows[::-1]]
    er = efficiency_ratio(b, 30)
    atr = _atr(b)
    w = b[-30:]
    closes = [x.close for x in w]
    peak = max(closes) - closes[0]
    trough = closes[0] - min(closes)
    fav = max(peak, trough)                       # the best the last 30 min offered, either way
    now = abs(closes[-1] - closes[0])
    gb = 0.0 if fav <= 0 else max(0.0, min(1.0, 1.0 - now / fav))
    return score(er, atr, gb)


# Read is a dataclass, so give it a small helper rather than reaching for namedtuple semantics
def _replace_detail(self: Read, d: str) -> Read:
    self.detail = d
    return self


Read._replace_detail = _replace_detail  # type: ignore[attr-defined]


def validate(store_path: str, shadow_path: str, cap_path: str, days: list[str]) -> list[dict]:
    """Score each day and put it beside that day's SHADOW-BOOK total — the honest counterfactual for
    what the desk's mechanisms would have made on that tape. This is the only test of whether the
    meter means anything; a meter that does not track it is decoration."""
    import datetime as dt
    out = []
    sh = sqlite3.connect(f"file:{shadow_path}?mode=ro", uri=True)
    for d in days:
        t0 = int(dt.datetime.fromisoformat(d + "T00:00:00+00:00").timestamp())
        t1 = t0 + 86400
        row = sh.execute(
            "SELECT COUNT(*), COALESCE(SUM(r.real_pnl),0) FROM shadow_trades t "
            "JOIN shadow_real r ON r.trade_id=t.id WHERE t.entry_ts>=? AND t.entry_ts<? "
            "AND r.real_pnl IS NOT NULL", (t0, t1)).fetchone()
        out.append({"day": d, "shadow_n": row[0], "shadow_pnl": round(row[1], 1)})
    sh.close()
    return out
