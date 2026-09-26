#!/usr/bin/env python3
"""SECTION 3 — CAN THIS BE AUTOMATED? The measurements behind the Friday V7 automation section.

Three questions, none of which needs a decision boundary and therefore none of which is blocked by
the fact that there are ZERO recorded PASSes:

  A. DETECTION vs DELIVERY. leg_watch already writes `leg OPEN <DIR>` for every leg it sees and
     SAYS NOTHING (silent by design — 17 legs/session, most die young). It only pages at 60min.
     So "did the machine see it" and "did the machine tell him" are DIFFERENT questions and the
     whole automatable half lives in the gap between them. Score both against his real entries.
  B. THE JUDGEMENT-FREE RULES. A hold-time cap, the event-day stand-aside, and the $250 daily loss
     limit need no model of him at all. Price each on this week's tape.
  C. THE NEGATIVES THAT DO EXIST. A paged alert he ignored WHILE DEMONSTRABLY LOOKING is a
     rejection — the only negative example this desk has ever captured. Count the rate.

⚠ THE EVENT PAGE OF 2026-09-18T07:04:03Z IS NOT AN ALERT. The timer is OnCalendar=*:0/5:30 and
journald shows the service ran at 07:05:30 and logged "ok — nothing in a band". 07:04:03 is
off-cadence, the only FOMC in the calendar is 2026-09-16, and a T-15 band cannot open two days
late. It is a hand-run test that wrote to the live log. Crediting it would hand the desk a lead it
never gave him, so it is dropped here and score_alerts.py's headline is one LED too generous.

  PYTHONPATH=src .venv/bin/python scripts/fv7_automation_gap.py
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

GB = "/home/alphabot/gazbot7"
SINCE = "2026-09-14"
PT = 2.0                      # MNQ $/point. MGC is $10 and is not in this book.
FAKE_EVENT_PAGE = "2026-09-18T07:04:03Z"


def _t(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


# ══ A. HIS ENTRIES ════════════════════════════════════════════════════════════════════════════
def entries() -> list[dict]:
    """GROUPED BY DECISION. The rows are scale-out exits of one press; 62 rows are 40 entries."""
    c = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
    rows = c.execute(
        "select opened_at,closed_at,side,qty,entry_price,exit_price,pnl_usd,exit_reason,"
        "data_quality,entry_source from trades where opened_at>=? and symbol='MNQ' "
        "order by opened_at, closed_at", (SINCE,)).fetchall()
    c.close()
    g: dict[str, dict] = {}
    for o, cl, side, qty, ep, xp, pnl, xr, dq, src in rows:
        e = g.setdefault(o, dict(opened=_t(o), side=side, lots=0.0, net=0.0, entry_px=ep,
                                 legs=[], reasons=[], bad=False, src=src))
        e["lots"] += qty
        e["net"] += pnl                      # pnl_usd is already NET of fees on this desk
        e["legs"].append((_t(cl), qty, xp))
        e["reasons"].append(xr)
        if dq and dq.startswith("BADFILL:"):
            e["bad"] = True
    out = []
    for e in g.values():
        e["closed"] = max(t for t, _, _ in e["legs"])
        e["hold_min"] = (e["closed"] - e["opened"]).total_seconds() / 60
        e["sign"] = 1 if e["side"] == "LONG" else -1
        e["session"] = (e["opened"] - dt.timedelta(hours=22)).date().isoformat()
        out.append(e)
    return sorted(out, key=lambda x: x["opened"])


# ══ B. WHAT leg_watch SAW, AND WHAT IT SAID ═══════════════════════════════════════════════════
def leg_log() -> tuple[list[dict], list[dict]]:
    """(every leg it DETECTED, every alert it actually PAGED). The first list is silent."""
    seen, paged = [], []
    for ln in open(f"{GB}/data/leg_watch.log"):
        if ln[:10] < SINCE:
            continue
        t = _t(ln[:20])
        m = re.search(r"leg OPEN (UP|DOWN) from ([\d.]+)", ln)
        if m:
            seen.append({"t": t, "dir": m.group(1), "px": float(m.group(2))})
            continue
        m = re.search(r"ALERT (\S+): (UP|DOWN) LEG", ln)
        if m:
            paged.append({"t": t, "dir": m.group(2), "band": m.group(1), "src": "leg_watch"})
        elif " ALERT break: (UP|DOWN)" or " ALERT break:" in ln:
            m2 = re.search(r"ALERT break: (UP|DOWN)", ln)
            if m2:
                paged.append({"t": t, "dir": m2.group(1), "band": "break", "src": "leg_watch"})
    for ln in open(f"{GB}/data/event_alert.log"):
        if ln[:10] < SINCE or "PAGED" not in ln:
            continue
        if ln[:20] == FAKE_EVENT_PAGE:       # see the module docstring — a hand-run test
            continue
        paged.append({"t": _t(ln[:20]), "dir": None, "band": "event", "src": "event_alert"})
    return sorted(seen, key=lambda x: x["t"]), sorted(paged, key=lambda x: x["t"])


def score(E: list[dict], A: list[dict], look: int, side_must_match: bool) -> dict:
    """Did an alert/detection of the RIGHT SIDE land in the `look` minutes before each entry?"""
    hit, lead, rows = 0, [], []
    for e in E:
        want = "UP" if e["side"] == "LONG" else "DOWN"
        cands = [a for a in A
                 if 0 <= (e["opened"] - a["t"]).total_seconds() / 60 <= look
                 and (not side_must_match or a["dir"] is None or a["dir"] == want)]
        if cands:
            hit += 1
            g = (e["opened"] - cands[-1]["t"]).total_seconds() / 60
            lead.append(g)
            rows.append((e, cands[-1], g))
        else:
            rows.append((e, None, None))
    lead.sort()
    return {"hit": hit, "n": len(E), "median_lead": lead[len(lead) // 2] if lead else None,
            "rows": rows}


# ══ C. THE JUDGEMENT-FREE RULES ═══════════════════════════════════════════════════════════════
_BARS = sqlite3.connect(f"file:{GB}/data/capture.db?mode=ro", uri=True)


def px_at(t: dt.datetime) -> float | None:
    """Tape close at or just before t, from the 5s bars. None if the tape was not printing."""
    ts = int(t.timestamp())
    r = _BARS.execute("select close from bars where symbol='MNQ' and timeframe='5s' "
                      "and bar_ts<=? and bar_ts>? order by bar_ts desc limit 1",
                      (ts, ts - 900)).fetchone()
    return float(r[0]) if r else None


def hold_cap(E: list[dict], hours: float) -> dict:
    """Force every still-open lot out at T+hours at the tape price. ⚠ The DELTA depends only on
    exit prices, so the paper engine's fabricated ENTRY fills cancel out of this number."""
    d, touched, detail = 0.0, 0, []
    for e in E:
        if e["bad"]:
            continue
        cap = e["opened"] + dt.timedelta(hours=hours)
        late = [(t, q, xp) for t, q, xp in e["legs"] if t > cap]
        if not late:
            continue
        cp = px_at(cap)
        if cp is None:
            continue
        delta = sum((cp - xp) * e["sign"] * q * PT for _, q, xp in late)
        d += delta
        touched += 1
        detail.append((e, delta, sum(q for _, q, _ in late)))
    return {"hours": hours, "delta": d, "touched": touched, "detail": detail}


def event_days(E: list[dict]) -> dict:
    cal = json.load(open(f"{GB}/data/event_calendar.json"))["events"]
    days = {e["date"] for e in cal if e["kind"] in ("FOMC", "CPI", "NFP")}
    on = [e for e in E if not e["bad"] and e["opened"].date().isoformat() in days]
    off = [e for e in E if not e["bad"] and e["opened"].date().isoformat() not in days]
    return {"days": sorted(d for d in days if SINCE <= d <= "2026-09-18"),
            "on_n": len(on), "on": sum(e["net"] for e in on),
            "off_n": len(off), "off": sum(e["net"] for e in off)}


def loss_limit(E: list[dict], limit: float = 250.0) -> list[dict]:
    """Walk each 22:00Z-anchored session's REALISED P&L and find the first crossing of -limit.
    The saving is what he opened AFTER that moment — the limit closes nothing, by design."""
    c = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
    rows = c.execute("select closed_at,pnl_usd,data_quality from trades where opened_at>=? "
                     "and symbol='MNQ' order by closed_at", (SINCE,)).fetchall()
    c.close()
    by = defaultdict(list)
    for cl, pnl, dq in rows:
        t = _t(cl)
        by[(t - dt.timedelta(hours=22)).date().isoformat()].append((t, pnl, dq))
    out = []
    for sess in sorted(by):
        run, fired_at = 0.0, None
        for t, pnl, dq in by[sess]:
            if dq and dq.startswith("BADFILL:"):
                continue
            run += pnl
            if run <= -limit and fired_at is None:
                fired_at = t
        after = [e for e in E if not e["bad"] and e["session"] == sess
                 and fired_at and e["opened"] > fired_at]
        out.append({"session": sess, "fired_at": fired_at, "final": run,
                    "after_n": len(after), "after_net": sum(e["net"] for e in after)})
    return out


# ══ MAIN ══════════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    E = entries()
    good = [e for e in E if not e["bad"]]
    seen, paged = leg_log()
    cov = min(s["t"] for s in seen)

    print(f"═══ ENTRIES ═══  {len(E)} entries from "
          f"{sum(len(e['legs']) for e in E)} rows · {len(good)} countable, "
          f"{len(E)-len(good)} BADFILL · net ${sum(e['net'] for e in good):,.2f}")
    print(f"═══ leg_watch ═══  {len(seen)} legs DETECTED (silent) · {len(paged)} alerts PAGED · "
          f"log starts {cov:%Y-%m-%d %H:%M}Z\n")

    print("── A. DETECTION vs DELIVERY (same-side, 30-min lookback) ──")
    covered = [e for e in good if e["opened"] > cov]
    for label, A, match in (("DETECTED a same-side leg", seen, True),
                            ("PAGED a same-side alert ", paged, True),
                            ("PAGED anything at all   ", paged, False)):
        s = score(covered, A, 30, match)
        ml = f"{s['median_lead']:.0f} min" if s["median_lead"] is not None else "—"
        print(f"  {label}  {s['hit']:>2}/{s['n']}  ({100*s['hit']/s['n']:>4.0f}%)  "
              f"median lead {ml}")
    print(f"  ⚠ {len(good)-len(covered)} entry/entries on 2026-09-14 are OUTSIDE the log — "
          f"leg_watch's log begins {cov:%m-%d %H:%M}Z and is not scored above.\n")

    print("  per-entry detail (D = a silent leg OPEN led it, P = a page led it):")
    sd = {id(e): g for e, a, g in score(covered, seen, 30, True)["rows"] if a}
    sp = {id(e): g for e, a, g in score(covered, paged, 30, True)["rows"] if a}
    for e in covered:
        print(f"    {e['opened']:%d %H:%M} {e['side']:<5} ${e['net']:>9,.2f}  "
              f"D {('-%.0fm' % sd[id(e)]) if id(e) in sd else '  —  ':>6}  "
              f"P {('-%.0fm' % sp[id(e)]) if id(e) in sp else '  —  ':>6}")

    print(f"\n  PRECISION OF PAGING EVERY LEG: {len(seen)} legs detected over "
          f"{(max(s['t'] for s in seen)-cov).total_seconds()/86400:.1f} days = "
          f"{len(seen)/((max(s['t'] for s in seen)-cov).total_seconds()/86400):.0f}/day. "
          f"He took {len(covered)} of them.")

    print("\n── B1. HOLD-TIME CAP (delta to the week, tape-priced) ──")
    for h in (1, 2, 3, 4, 6, 8):
        r = hold_cap(good, h)
        print(f"  cap {h}h   {r['touched']:>2} entries touched   "
              f"{r['delta']:>+10,.2f}   {r['delta']/5:>+8,.2f}/day")
    r3 = hold_cap(good, 3)
    print("   3h detail:", ", ".join(f"{e['opened']:%d %H:%M}{e['side'][0]} {d:+,.0f}"
                                     for e, d, _ in r3["detail"]))

    print("\n── B2. EVENT-DAY STAND-ASIDE ──")
    ed = event_days(good)
    print(f"  event days in the week: {ed['days'] or 'none'}")
    print(f"  on  event days: {ed['on_n']:>2} entries  ${ed['on']:>+10,.2f}")
    print(f"  off event days: {ed['off_n']:>2} entries  ${ed['off']:>+10,.2f}")

    print("\n── B3. THE $250 DAILY LOSS LIMIT, as a rule on HIS book ──")
    for r in loss_limit(good):
        f = f"{r['fired_at']:%H:%M}Z" if r["fired_at"] else "never"
        print(f"  {r['session']}  crossed -$250 at {f:<7} session realised "
              f"${r['final']:>+9,.2f}   opened after: {r['after_n']} entries "
              f"${r['after_net']:>+9,.2f}")
    print("  ⚠ AND IT CANNOT FIRE ON THIS BOOK. daily_loss_limit.py benches GATES=(grind_long, "
          "capitulation_long, abs_veto_long, exhaustion_short, abs_veto_short, rgv_short) in "
          "data/gate_switches.env. `day_rider` is not in that tuple and its switch lives in a "
          "different file (data/day_rider.env). All six gates are ALREADY =off, so bench_all() "
          "would change nothing and write no log line.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
