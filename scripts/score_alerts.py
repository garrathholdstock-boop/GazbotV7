#!/usr/bin/env python3
"""DID THE MACHINE SEE WHAT HE SAW? — score every alert against every press.

★★★ WHY THIS IS THE MEASURABLE HALF OF AUTOMATION. Learning his ENTRY RULE needs negative
examples and there are none (every captured press is a "yes"). But "did the alert arrive before he
pressed" needs no negatives at all — it is a join on two timestamps, and it is the question that
decides whether the desk can usefully tell him WHEN TO LOOK.

⚠⚠ THE PRESS LOG DOUBLE-COUNTS AND YOU MUST DEDUPE ON THE PRESS STAMP. `gazbot7-capture-read-*.path`
fires on `PathModified`, which triggers TWICE for one write — measured on 2026-09-14..18, 52 of the
consecutive same-kind gaps are UNDER TWO SECONDS and carry an IDENTICAL `request.raw`. 110 captured
records are ~55 real presses. Counting rows would say he presses twice as often as he does; this is
the same shape as counting scale-out exits as separate trades.

★ THE FOUR OUTCOMES, and the last two are the ones worth money:
    LED         an alert fired in the LOOKBACK before the press          — the machine was early
    CONFIRMED   an alert fired shortly AFTER the press                   — he was early
    UNPROMPTED  he pressed with no alert anywhere near                   — he saw something we did not
    IGNORED     an alert fired and he never pressed                      — noise, or a missed trade

⚠ AN IGNORED ALERT IS NOT AUTOMATICALLY NOISE. It is only noise if the move that followed was not
worth having, so each one is priced by what the tape did afterwards. An alert that fires on a 70pt
run he happened to miss is a DIFFERENT problem from one that fires on nothing.

  PYTHONPATH=src .venv/bin/python scripts/score_alerts.py [--since 2026-09-14] [--lookback 30]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

GB = "/home/alphabot/gazbot7"
LEG = f"{GB}/data/leg_watch.log"
EVT = f"{GB}/data/event_alert.log"
READS = f"{GB}/data/operator_reads.jsonl"


def presses(since: str) -> list[dict]:
    """Real presses, deduped on the OPERATOR'S OWN stamp (request.raw), not on our capture time."""
    seen, out = set(), []
    for line in open(READS):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r["ts"][:10] < since:
            continue
        raw = (r.get("request") or {}).get("raw")
        # ⚠ A request file is "<ISO stamp>[|SIDE|qty|targets]" for a buy and "<stamp>[|lot=N]" for a
        # claim — the same partition the rider itself does. Parsing the whole line as a timestamp
        # throws on every BUY, which is exactly half the sample.
        if isinstance(raw, str):
            raw = raw.partition("|")[0].strip() or None
        # ⚠ Fall back to the capture ts only when the press carried no stamp — 2 of 110 rows.
        key = (r.get("kind"), raw or r["ts"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"t": dt.datetime.fromisoformat(raw or r["ts"]), "kind": r.get("kind"),
                    "px": (r.get("facts") or {}).get("price")})
    return sorted(out, key=lambda x: x["t"])


def alerts(since: str) -> list[dict]:
    """Only alerts that actually PAGED HIS PHONE. The quiet 30/45-min log lines are deliberately
    silent by design, so counting them would credit the desk with warnings he never received."""
    out = []
    try:
        for line in open(LEG):
            if line[:10] < since or " ALERT " not in line:
                continue
            t = dt.datetime.fromisoformat(line[:20].replace("Z", "+00:00"))
            m = re.search(r"ALERT (\S+): (UP|DOWN) LEG", line)
            out.append({"t": t, "src": "leg_watch",
                        "what": (m.group(1) + " " + m.group(2) + " leg") if m else line[21:60].strip()})
    except FileNotFoundError:
        pass
    try:
        for line in open(EVT):
            if line[:10] < since or "PAGED" not in line:
                continue
            t = dt.datetime.fromisoformat(line[:20].replace("Z", "+00:00"))
            out.append({"t": t, "src": "event_alert", "what": line.split("PAGED", 1)[1].strip()[:40]})
    except FileNotFoundError:
        pass
    return sorted(out, key=lambda x: x["t"])


def move_after(t: dt.datetime, mins: int) -> float | None:
    """What the tape actually did in the `mins` after an alert — the price of ignoring it."""
    c = sqlite3.connect(f"{GB}/data/capture.db")
    t0 = int(t.timestamp())
    r = c.execute("select min(low), max(high) from bars where symbol='MNQ' and timeframe='5s' "
                  "and bar_ts>=? and bar_ts<?", (t0, t0 + mins * 60)).fetchone()
    c.close()
    return (r[1] - r[0]) if r and r[0] else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-09-14")
    ap.add_argument("--lookback", type=int, default=30, help="minutes before a press an alert counts")
    ap.add_argument("--confirm", type=int, default=15, help="minutes after a press an alert confirms")
    a = ap.parse_args()

    P, A = presses(a.since), alerts(a.since)
    buys = [p for p in P if p["kind"] == "buy"]
    print(f"=== {a.since} → now ===")
    print(f"{len(P)} real presses ({len(buys)} buy/sell, {len(P)-len(buys)} claim) "
          f"· {len(A)} alerts that PAGED\n")

    used = set()
    rows = []
    for p in buys:
        led = [i for i, x in enumerate(A)
               if 0 <= (p["t"] - x["t"]).total_seconds() / 60 <= a.lookback]
        conf = [i for i, x in enumerate(A)
                if 0 < (x["t"] - p["t"]).total_seconds() / 60 <= a.confirm]
        if led:
            i = led[-1]
            used.add(i)
            rows.append(("LED", p, A[i], (p["t"] - A[i]["t"]).total_seconds() / 60))
        elif conf:
            i = conf[0]
            used.add(i)
            rows.append(("CONFIRMED", p, A[i], (A[i]["t"] - p["t"]).total_seconds() / 60))
        else:
            rows.append(("UNPROMPTED", p, None, None))

    print(f"{'outcome':<11} {'press (UTC)':<9} {'alert':<9} {'gap':>8}  what")
    for o, p, x, g in rows:
        print(f"{o:<11} {p['t'].strftime('%d %H:%M'):<9} "
              f"{(x['t'].strftime('%d %H:%M') if x else '—'):<9} "
              f"{(f'{g:+.0f}m' if g is not None else '—'):>8}  {x['what'] if x else ''}")

    ign = [A[i] for i in range(len(A)) if i not in used]
    # ★★2026-09-18 AN IGNORED ALERT SPLITS IN TWO, and only one half means anything. Operator:
    # "im looking at it periodically during the work day when i have time. not all day and reading
    # every telegram." An alert he never saw is not a rejection. scripts/presence.py separates them
    # from the nginx log — and MEASURED, 12 of 17 fired while he was demonstrably looking, so the
    # alert's problem is SELECTION, not his absence.
    try:
        sys.path.insert(0, f"{GB}/scripts")
        import presence as _pr
    except Exception:
        _pr = None
    print(f"\n--- IGNORED: {len(ign)} alert(s) he did not act on ---")
    rejected = 0
    for x in ign:
        mv = move_after(x["t"], 60)
        seen = _pr.looked_around(x["t"], window_min=20, strong_only=False) if _pr else None
        if seen == "LOOKED":
            rejected += 1
        print(f"  {x['t'].strftime('%d %H:%M')}  {x['src']:<12} {x['what'][:22]:<22} "
              f"{(seen or 'NOT PRESENT'):<15} "
              f"{'next 60min ranged ' + format(mv, '.0f') + 'pt' if mv else 'no tape'}")
    if _pr:
        print(f"\n  ★ {rejected} of {len(ign)} fired while he WAS looking — those are TRUE "
              f"REJECTIONS and are the negative examples the leg-selection question needs. "
              f"The other {len(ign)-rejected} are alerts nobody saw.")

    from collections import Counter
    c = Counter(o for o, _, _, _ in rows)
    print(f"\n=== SCORE ===")
    for k in ("LED", "CONFIRMED", "UNPROMPTED"):
        print(f"  {k:<11} {c.get(k,0):>3}")
    print(f"  IGNORED     {len(ign):>3}")
    if buys:
        print(f"\n  the machine was EARLY on {c.get('LED',0)}/{len(buys)} of his entries "
              f"({100*c.get('LED',0)/len(buys):.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
