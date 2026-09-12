#!/usr/bin/env python3
"""REV2 — does the 55-second mirror fire on the SAME signals the live abs_veto_short fires on?

The whole surviving rehab case for abs_veto_short is "fix the ENTRY with the 55s continuation
confirm". The report states twice that the mirror OVER-fires (it does not model the live gate's
thin-tape default veto, and it enters on the 1-minute bar open rather than the tick the live
decider quoted) and calls the arm "an upper bound" — but never puts a number on the bias.

This does for the mirror what Movement 2's REV2 did for the mechanical sim and the MGC dossier did
for the bar source: timestamp-match the mirror's fires against the live gate's own lots, report the
overlap, and then re-score the arm on the OVERLAPPING fires only. If the mirror's record survives
on the subset the live gate would also have taken, the promotion case is real. If the money is in
fires the live veto would have refused, it is not.

Scored on shadow.db `shadow_real.real_pnl` (the tick-repriced honest number), with the two standing
filters: quarantined rows dropped, and the permanent 00:00-07:00Z Asia bench voided — nothing has
filled in that window since 2026-08-05, so a fire booked there is not tradeable money.
"""
from __future__ import annotations
import datetime as dt
import json
import sqlite3

GB = "/home/alphabot/gazbot7"
# A mirror fire and a live lot are "the same signal" within this many seconds, SAME SIDE.
# The window has to be this wide because the mirror leads the live gate SYSTEMATICALLY: it enters
# at the 1-minute bar OPEN, the live decider enters on the tick it fired on, and every pair found
# here sits at 120-122 seconds. A +-120s window misses all of them by a second and a half, which is
# how a first pass reported 0% overlap.
MATCH_S = 240
WEEK = ("2026-08-17", "2026-08-22")
ASIA = range(0, 7)     # UTC hours in which the desk cannot fill


def live_signals():
    """abs_veto_short's live lots this week, collapsed A/B -> one row per SIGNAL."""
    c = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    rows = [dict(r) for r in c.execute(
        "SELECT opened_at, closed_at, entry_price, pnl_usd, exit_reason, gate FROM trades "
        "WHERE gate LIKE 'abs_veto_short%' AND date(closed_at) BETWEEN ? AND ? "
        "AND data_quality IS NULL ORDER BY opened_at", (WEEK[0], "2026-08-21"))]
    sig = {}
    for r in rows:
        t = dt.datetime.fromisoformat(r["opened_at"]).timestamp()
        k = round(t)
        near = [x for x in sig if abs(x - k) <= 5]
        k = near[0] if near else k
        s = sig.setdefault(k, dict(ts=k, entry=r["entry_price"], lots=0, pnl=0.0, reasons=[]))
        s["lots"] += 1
        s["pnl"] += r["pnl_usd"]
        s["reasons"].append(r["exit_reason"])
    return sorted(sig.values(), key=lambda s: s["ts"])


def mirror(strategy):
    c = sqlite3.connect(f"file:{GB}/data/shadow.db?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    q = c.execute("""
        SELECT t.id, t.entry_ts, t.entry_price, t.side, t.exit_reason, r.real_pnl
        FROM shadow_trades t LEFT JOIN shadow_real r ON r.trade_id = t.id
        WHERE t.strategy=? AND t.data_quality IS NULL
          AND t.entry_ts >= ? AND t.entry_ts < ? ORDER BY t.entry_ts""",
        (strategy, dt.datetime.fromisoformat(WEEK[0] + "T00:00:00+00:00").timestamp(),
         dt.datetime.fromisoformat(WEEK[1] + "T00:00:00+00:00").timestamp()))
    out = []
    for r in q:
        h = dt.datetime.fromtimestamp(r["entry_ts"], dt.UTC).hour
        out.append(dict(id=r["id"], ts=r["entry_ts"], entry=r["entry_price"], side=r["side"],
                        pnl=r["real_pnl"], asia=h in ASIA, reason=r["exit_reason"]))
    return out


def main():
    live = live_signals()
    print(f"live abs_veto_short signals this week: {len(live)} "
          f"({sum(s['lots'] for s in live)} lots, booked {sum(s['pnl'] for s in live):+,.2f})")
    report = {"live_signals": len(live), "live_lots": sum(s["lots"] for s in live),
              "live_booked": round(sum(s["pnl"] for s in live), 2), "arms": {}}

    for arm in ("abs_veto_55s", "abs_veto_50s", "thrust_short_absveto55", "thrust_loose"):
        f = mirror(arm)
        # the live gate is SHORT-ONLY, so only the mirror's short side can ever match it
        pool = [x for x in f if str(x["side"]).upper().startswith("S")]
        matched, unmatched = [], []
        used = set()
        for x in pool:
            hit = [s for s in live if abs(s["ts"] - x["ts"]) <= MATCH_S]  # same side by construction
            if hit:
                matched.append(x)
                used.add(hit[0]["ts"])
            else:
                unmatched.append(x)

        def score(rows):
            v = [r["pnl"] for r in rows if r["pnl"] is not None]
            return dict(n=len(rows), priced=len(v), net=round(sum(v), 2),
                        per=round(sum(v) / len(v), 2) if v else None,
                        win=round(100 * sum(1 for x in v if x > 0) / len(v), 1) if v else None)

        tradable = [x for x in pool if not x["asia"]]
        m_tr = [x for x in matched if not x["asia"]]
        u_tr = [x for x in unmatched if not x["asia"]]
        rec = dict(all=score(pool), tradable_hours=score(tradable),
                   matched_all=score(matched), matched_tradable=score(m_tr),
                   unmatched_tradable=score(u_tr),
                   live_signals_covered=len(used), live_signals=len(live),
                   overlap_pct=round(100 * len(used) / len(live), 1) if live else None)
        report["arms"][arm] = rec
        print(f"\n{arm}")
        print(f"  fires this week (short side)          : {rec['all']}")
        print(f"  ... in tradable hours (07:00-24:00Z)  : {rec['tradable_hours']}")
        print(f"  ... that MATCH a live lot (+-{MATCH_S}s)  : {rec['matched_tradable']}")
        print(f"  ... that the live gate NEVER took     : {rec['unmatched_tradable']}")
        print(f"  live signals the mirror reproduces    : {rec['live_signals_covered']}"
              f"/{rec['live_signals']}  ({rec['overlap_pct']}%)")
        for x in matched:
            print(f"      matched  {dt.datetime.fromtimestamp(x['ts'], dt.UTC):%m-%d %H:%M}Z  "
                  f"{x['entry']:>10,.2f}  real_pnl {x['pnl']:+8.2f}  {x['reason']}")

    json.dump(report, open(f"{GB}/reports/friday_v7/sections/rev2_absveto55_overlap.json", "w"),
              indent=1)
    print("\nwrote rev2_absveto55_overlap.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
