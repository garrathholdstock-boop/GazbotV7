#!/usr/bin/env python3
"""Filter-effectiveness monitor — are the ER/ATR floors doing their job?

For each recent trade, reconstructs the ER (30-min, 1-min closes) and ATR (14-period, 1-min bars)
AT ENTRY — the same numbers the gate saw — and shows them against the gate's floor/ceiling/band.
LEADS with the losers, especially the big ones: were they BORDERLINE (just past the threshold, so a
higher floor would've caught them) or clean-in-regime (the gate itself losing, not a filter miss)?
DuckDB-vectorized (the rule). `review()` is imported by hour_watch.py to fold into the hourly sweep.

Caveat worth knowing: the gate decides on the LIVE/forming price; this reconstructs from CLOSED
1-min bars. In fast/violent tape the two diverge — a reconstructed ER *below* a floor means the
gate fired on an intra-minute spike the closed bar didn't confirm (a chop whipsaw), not a leak.

  PYTHONPATH=src python scripts/filter_check.py            # today
  PYTHONPATH=src python scripts/filter_check.py --days 3
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import pnl  # noqa: E402
from gazbot7.deciders import ATR_FLOOR, ER_BAND, ER_CEIL, ER_FLOOR  # noqa: E402

DB = "/home/alphabot/gazbot7/data/gazbot7.db"
CAP = "/home/alphabot/gazbot7/data/capture.db"
BIG_LOSS = -40.0        # a "big loss" worth dissecting
BORDER = 0.15           # within 15% of a threshold = borderline
_CLEANUP = ("ADOPT_FLATTEN", "RECONCILED_CLOSE")


def er_rule(gate):
    if gate in ER_FLOOR:
        return f">={ER_FLOOR[gate]:.2f}", ("floor", ER_FLOOR[gate])
    if gate in ER_CEIL:
        return f"<={ER_CEIL[gate]:.2f}", ("ceil", ER_CEIL[gate])
    if gate in ER_BAND:
        lo, hi = ER_BAND[gate]
        return f"{lo:.2f}-{hi:.2f}", ("band", (lo, hi))
    return "—", (None, None)


def er_flags(gate, er):
    """(in_range, borderline) — is ER within the gate's rule, and is it hugging a boundary?"""
    if er is None:
        return None, False
    kind, val = er_rule(gate)[1]
    if kind == "floor":
        return er >= val, abs(er - val) <= BORDER * val
    if kind == "ceil":
        return er <= val, abs(er - val) <= BORDER * val
    if kind == "band":
        lo, hi = val
        return lo <= er <= hi, (abs(er - lo) <= BORDER * lo or abs(er - hi) <= BORDER * hi)
    return True, False


def atr_border(gate, atr):
    """borderline vs the ATR floor (only momentum gates have one)."""
    if gate not in ATR_FLOOR or atr is None:
        return False
    return atr >= ATR_FLOOR[gate] and abs(atr - ATR_FLOOR[gate]) <= BORDER * ATR_FLOOR[gate]


def classify(gate, pnl_usd, er, atr):
    """Per-trade verdict: borderline (a tighter floor catches it) vs clean-in-regime (gate lost)."""
    in_er, bord_er = er_flags(gate, er)
    bord_atr = atr_border(gate, atr)
    why = []
    if bord_er:
        why.append(f"ER {er:.2f} hugs its {er_rule(gate)[0]} boundary")
    if bord_atr:
        why.append(f"ATR {atr:.1f} hugs its {ATR_FLOOR[gate]:.0f} floor")
    below = in_er is False   # fired outside the rule per the closed-bar reconstruction (spike entry)
    return {"in_er": in_er, "borderline": bool(why), "below_rule": below, "why": why}


def review(t0):
    """Reconstruct ER/ATR at entry for every MNQ trade since epoch `t0`. Returns list of dicts.
    Shared by the CLI and hour_watch.py so the analytics live in one DuckDB pass."""
    con = duckdb.connect()
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    # 1-min OHLC → rolling 14-bar ATR + 30-bar ER (the gate's exact bases), one windowed pass
    con.execute("""
        CREATE TABLE feat AS
        WITH m1 AS (
            SELECT (bar_ts-bar_ts%60) m, arg_min(open,bar_ts) o, max(high) h, min(low) l, arg_max(close,bar_ts) c
            FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' GROUP BY 1),
        st AS (
            SELECT m, c, GREATEST(h-l, abs(h-lag(c) OVER w), abs(l-lag(c) OVER w)) tr,
                   abs(c - lag(c) OVER w) step
            FROM m1 WINDOW w AS (ORDER BY m))
        SELECT m,
               AVG(tr) OVER w14 AS atr,
               abs(c - first_value(c) OVER w30) / NULLIF(SUM(step) OVER w30, 0) AS er
        FROM st
        WINDOW w14 AS (ORDER BY m ROWS BETWEEN 13 PRECEDING AND CURRENT ROW),
               w30 AS (ORDER BY m ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)""")
    ph = ",".join(f"'{x}'" for x in _CLEANUP)
    rows = con.execute(f"""
        WITH tr AS (
            SELECT opened_at, gate, pnl_usd, exit_reason, epoch(opened_at::TIMESTAMPTZ) te
            FROM g.trades WHERE symbol='MNQ' AND exit_reason NOT IN ({ph})
              AND epoch(opened_at::TIMESTAMPTZ) >= {t0})
        SELECT tr.opened_at, tr.gate, tr.pnl_usd, tr.exit_reason, f.er, f.atr
        FROM tr ASOF LEFT JOIN feat f ON f.m <= tr.te
        ORDER BY tr.opened_at""").fetchall()
    con.close()
    out = []
    for opened, gate, p, reason, er, atr in rows:
        d = {"time": opened[11:16], "gate": gate, "pnl": p, "exit": reason, "er": er, "atr": atr}
        d.update(classify(gate, p, er, atr))
        out.append(d)
    return out


def hour_summary(t0):
    """One-line filter read for the hourly sweep: how the hour's LOSERS sat vs the floors."""
    trades = review(t0)
    losers = [d for d in trades if d["pnl"] < 0]
    if not losers:
        return f"FILTER(1h): {len(trades)} trades, no losers"
    border = [d for d in losers if d["borderline"]]
    spike = [d for d in losers if d["below_rule"]]
    clean = [d for d in losers if not d["borderline"] and not d["below_rule"]]
    bits = [f"{len(losers)} losers"]
    if border:
        bits.append(f"{len(border)} BORDERLINE ({','.join(sorted({d['gate'] for d in border}))} — tighter floor catches)")
    if spike:
        bits.append(f"{len(spike)} SPIKE-ENTRY ({','.join(sorted({d['gate'] for d in spike}))} — fired below floor on unconfirmed spike)")
    if clean:
        bits.append(f"{len(clean)} clean-in-regime (gate lost, not a filter miss)")
    return "FILTER(1h): " + " · ".join(bits)


def run(days):
    _t0 = pnl.paris_day_start_utc(dt.datetime.now(dt.UTC))
    today0 = dt.datetime.fromisoformat(_t0).timestamp() if isinstance(_t0, str) else _t0.timestamp()
    t0 = today0 - (days - 1) * 86400
    trades = review(t0)
    if not trades:
        print("no trades in that window.")
        return
    span = "today" if days == 1 else f"last {days} days"
    print(f"FILTER CHECK ({span}) — ER + ATR AT ENTRY vs each gate's rule (are the floors working?)\n")
    print(f"{'TIME':>5} {'GATE':16} {'$PNL':>7} {'ER':>5} {'rule':>10} {'ATR':>5} {'floor':>6}  exit")
    losers = []
    for d in trades:
        gate, p = d["gate"], d["pnl"]
        af = f">={ATR_FLOOR[gate]:.0f}" if gate in ATR_FLOOR else "—"
        flag = "  ⚠BORDER" if d["borderline"] and p < 0 else \
               ("  ↯SPIKE" if d["below_rule"] and p < 0 else ("  ✓win" if p > 0 else ""))
        ers = f"{d['er']:.2f}" if d["er"] is not None else "—"
        ats = f"{d['atr']:.1f}" if d["atr"] is not None else "—"
        print(f"{d['time']:>5} {gate:16} ${p:>+6.0f} {ers:>5} {er_rule(gate)[0]:>10} {ats:>5} {af:>6}  {d['exit']}{flag}")
        if p <= BIG_LOSS:
            losers.append(d)

    print(f"\n── BAD ENTRIES (loss <= ${BIG_LOSS:.0f}) — borderline, spike, or clean-in-regime? ──")
    if not losers:
        print("  none — no big losses this window.")
    for d in losers:
        if d["why"]:
            verdict = "BORDERLINE — " + " + ".join(d["why"]) + " → a tighter floor would've blocked it"
        elif d["below_rule"]:
            verdict = (f"SPIKE-ENTRY — reconstructed ER {d['er']:.2f} is BELOW the rule; gate fired on an "
                       "intra-minute spike the closed bar didn't confirm (violent-chop whipsaw)")
        else:
            verdict = "clean-in-regime — well inside the gate's window; the GATE lost, not a filter miss"
        print(f"  {d['time']} {d['gate']} ${d['pnl']:+.0f} ({d['exit']}): {verdict}")
    print("\n(ER 30-min/1-min closes · ATR 14-period/1-min bars — the gate's exact bases. Borderline = within "
          "15% of a threshold. Lifting a floor cuts losses but also participation — watch the trade-off.)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1)
    run(ap.parse_args().days)
