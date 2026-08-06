#!/usr/bin/env python3
"""GLOBAL DESK VIEW — the read for the intelligent-router-tune trial (operator 2026-07-28).
One-shot, READ-ONLY snapshot of everything a benching decision needs: tape, DAY directional bias
(net from the Paris-day open — the lever the ER-router misses), live positions, day P&L total +
per-gate, last-hour per-gate trades, current gate switches, and the SHADOW per-gate today (which
fires ALL gates unbenched → the counterfactual for scoring what a bench saved/cost).

  PYTHONPATH=src .venv/bin/python scripts/desk_view.py
"""
from __future__ import annotations

import datetime as dt
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"
DB = "/home/alphabot/gazbot7/data/gazbot7.db"
SH = "/home/alphabot/gazbot7/data/shadow.db"


def main():
    now = dt.datetime.now(dt.UTC)
    s = dr.pnl.paris_day_start_utc(now)
    ds = int(dt.datetime.fromisoformat(s).timestamp() if isinstance(s, str) else s.timestamp())
    tnow = int(now.timestamp())
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{SH}' AS s (TYPE sqlite, READ_ONLY)")

    # ── DAY DIRECTIONAL BIAS (net pt from the Paris-day open close to latest) + ER over the day ──
    bars = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl
        FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={ds} AND bar_ts<={tnow}
        GROUP BY 1 ORDER BY 1""").fetchall()
    if len(bars) >= 6:
        dopen, dlast = bars[0][1], bars[-1][1]
        daynet = dlast - dopen
        path = sum(abs(bars[i][1]-bars[i-1][1]) for i in range(1, len(bars))) or 1.0
        er_day = abs(dlast - dopen) / path
        hi = max(b[1] for b in bars); lo = min(b[1] for b in bars)
        bias = "DOWN" if daynet < -40 else ("UP" if daynet > 40 else "FLAT")
        print(f"DAY BIAS: {bias}  net {daynet:+.0f}pt  (open {dopen:.0f} → now {dlast:.0f}, H {hi:.0f}/L {lo:.0f})  day-ER {er_day:.2f}")
    else:
        print("DAY BIAS: (insufficient bars)")

    # ── last-hour tape (ER/ATR) ──
    hb = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl, max(high) hi, min(low) lo
        FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={tnow-3600} AND bar_ts<={tnow}
        GROUP BY 1 ORDER BY 1""").fetchall()
    if len(hb) >= 6:
        cl = [b[1] for b in hb]
        path = sum(abs(cl[i]-cl[i-1]) for i in range(1, len(cl))) or 1.0
        er1 = abs(cl[-1]-cl[0]) / path
        atr = sum(b[2]-b[3] for b in hb) / len(hb)
        print(f"LAST HR: ER {er1:.2f} ({'trend' if er1>=0.18 else 'chop' if er1<0.08 else 'mixed'})  ATR {atr:.0f}pt  net {cl[-1]-cl[0]:+.0f}")

    # ── day P&L total + per-gate (Paris day) ──
    # ★2026-08-06 `data_quality IS NULL` — EXCLUDED rows must never reach the router. This view is the
    # router's per-gate evidence and its arming logic reasons directly from it ("its only two fires
    # today were both green"), so a poisoned row here does not just misreport, it ARMS A GATE. On
    # 08-06 the day-rider flattened two tournament longs it did not own; the desk booked the later
    # unrelated sells as TARGET wins (+$56.00) when the real fills were -$27.50, and without this
    # filter the router read a losing gate as 2-for-2 green. Same filter as the honest-P&L rule in
    # [[trade-data-quality-flag]] — it existed in the reporting layer but never in the DECISION layer.
    print("\nDAY P&L per gate (live):")
    rows = con.execute(f"""SELECT gate, count(*) n, round(sum(pnl_usd),1) pnl, sum(pnl_usd>0) w,
            round(sum(CASE WHEN epoch(opened_at::TIMESTAMPTZ) >= {tnow-3600} THEN pnl_usd ELSE 0 END),1) h,
            sum(CASE WHEN epoch(opened_at::TIMESTAMPTZ) >= {tnow-3600} THEN 1 ELSE 0 END) hn,
            max(CASE WHEN epoch(opened_at::TIMESTAMPTZ) >= {tnow-3600} THEN substr(side,1,1) END) side1
        FROM g.trades WHERE symbol='MNQ' AND data_quality IS NULL
          AND epoch(opened_at::TIMESTAMPTZ) >= {ds}
        GROUP BY gate ORDER BY pnl""").fetchall()
    dtot = sum(r[2] for r in rows) if rows else 0.0
    for gate, n, pnl, w, h, hn, s1 in rows:
        hrmark = f"  [last hr {h:+.0f}/{hn}tr]" if hn else ""
        print(f"  {gate:18} {pnl:>+7.1f}  ({n}tr {w}W){hrmark}")
    print(f"  {'— DAY TOTAL':18} {dtot:>+7.1f}")

    # ── SHADOW per-gate today (unbenched counterfactual — did benched gates avoid losses?) ──
    # ★2026-08-04 TWO FIXES, both found because the operator spotted abs_veto_55s running 100% green
    # at $52/trade that the router had never been shown:
    #   1. was `ORDER BY pnl LIMIT 12` — ASCENDING, so the router saw only the twelve WORST rows and
    #      the whole winning thrust family was truncated off the bottom. It could not notice a family
    #      working, because the winners never reached it.
    #   2. was summing `ceiling_pnl`, the optimistic bar-price number this desk's own rule says never
    #      to score on (shadow.py: real_pnl "is the only number we trust"). Now real_pnl, with any
    #      unscored trades flagged so repricer lag cannot masquerade as a result.
    # Grouped by FAMILY because that is where the signal is: one variant is thin (abs_veto_55s was
    # n=5), but 7-of-7 thrust green against 4-of-4 faders red is a regime read with real weight.
    print("\nSHADOW P&L today — real_pnl, tick-honest (all fire unbenched = the bench counterfactual):")
    sh = con.execute(f"""SELECT t.strategy, count(*) n,
               round(sum(COALESCE(r.real_pnl,0)),1) rp,
               sum(CASE WHEN r.real_pnl IS NULL THEN 1 ELSE 0 END) un
        FROM s.shadow_trades t LEFT JOIN s.shadow_real r ON r.trade_id = t.id
        WHERE CAST(t.entry_ts AS BIGINT) >= {ds} AND t.exit_price IS NOT NULL
        GROUP BY t.strategy HAVING count(*)>0""").fetchall()

    def _fam(s):
        if s.startswith("CL-"):
            return "CL (Claude-gated)"
        if s.startswith(("thrust", "abs_veto", "chand")):
            return "MOMENTUM/thrust"
        if s.startswith("grind"):
            return "MOMENTUM/grind"
        return "FADER/reversion"

    groups: dict = {}
    for strat, n, rp, un in sh:
        groups.setdefault(_fam(strat), []).append((strat, n, rp, un))
    for g in sorted(groups, key=lambda k: -sum(x[2] for x in groups[k])):
        rows = sorted(groups[g], key=lambda x: -x[2])
        tot = sum(x[2] for x in rows)
        ntot = sum(x[1] for x in rows)
        green = sum(1 for x in rows if x[2] > 0)
        print(f"  {g:<20} {tot:>+8.1f}  ({ntot}tr · {green}/{len(rows)} variants green)")
        for strat, n, rp, un in rows:
            print(f"     {strat:22} {rp:>+7.1f}  ({n}tr)" + (f"  !{un} unscored" if un else ""))
    con.close()

    # ── positions + current switches ──
    import json
    try:
        d = json.load(open(f"{DB.rsplit('/',1)[0]}/core_health.json"))
        p = d.get("protection") or {}
        held = [(x.get("gate"), x.get("side"), x.get("qty")) for x in p.get("slots", [])]
        print(f"\nPOSITION: {'HOLDING '+str(held) if held else 'flat'}  | healthy={d.get('healthy')} halted={d.get('halted')}")
    except Exception as e:
        print(f"\nPOSITION: (core_health read failed: {e})")
    try:
        sw = [ln.strip() for ln in open(f"{DB.rsplit('/',1)[0]}/gate_switches.env") if ln.strip() and not ln.startswith('#')]
        print("SWITCHES: " + "  ".join(sw))
    except Exception:
        print("SWITCHES: (none)")


if __name__ == "__main__":
    main()
