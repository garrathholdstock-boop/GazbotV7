#!/usr/bin/env python3
"""DOES THE BOOK MATCH THE BROKER? Asked every day, deterministically, and it PAGES.

★★★2026-09-26 AUDIT, FINDING 11. `book_vs_fills` — the check that asks whether the trade ledger
matches what IBKR actually executed — existed and was good, and it ran ONLY inside `sweep.py`, which
runs only as a headless Claude job, on a `Mon-Fri` timer, three-hourly, as a WARN that pages nobody.
So the answer to "is the P&L we reason from real?" depended on an LLM job deciding to mention it, and
was never asked at all on a weekend.

That check is [[ibkr-is-truth-never-trust-our-books]] made enforceable, and it is the reason we know
about the 08-13 +$1,551 of profit from orders that sold 8 lots the desk did not own. A check like that
belongs on a timer of its own.

★ WHAT IT ASKS, in the order that matters:
  1. Does every desk-day in the window reconcile our `trades` ledger against venue `fills`?
     (sweep's own `check_book_vs_fills`, reused rather than reimplemented — one implementation of a
     reconciliation, or the two drift.)
  2. Does IB's OWN realised P&L agree with our clean book for the session? (from
     `equity_guard.jsonl`, the series added by the same audit — finding 02.)
  3. Did any fill land outside the visible book? (sweep's `check_fill_vs_book` — the fabricated-fill
     detector, $2,916.50 over 32 orders.)

⚠ IT IS READ-ONLY AND HAS NO AUTHORITY. A recording fault is not an order-path fault: nothing is
naked and no position is at risk, so this pages and never benches, halts or flattens. The operator's
standing rule also applies — a bug-caused number is LABELLED, never adjusted, and that is a human
decision this script does not make.

⚠ UNVERIFIABLE IS NOT CLEAN, and it says so. A desk-day with no execution record, or a position
carried across the boundary, is reported as unverifiable and never scored either way.

  PYTHONPATH=src .venv/bin/python scripts/book_recon_daily.py [--json] [--days N] [--quiet]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/data/book_recon_daily.json"
SERIES = f"{GB}/data/equity_guard.jsonl"
#: How far apart IB's realised P&L and our clean book may sit before it is a finding. Not zero:
#: the two are sampled at different instants and a trade closing between them is a legitimate gap.
#: One MNQ point on one lot is $2, so $25 is well inside noise and well below anything meaningful.
DIVERGENCE_TOL_USD = 25.0


def latest_equity_record() -> dict | None:
    """The newest equity_guard line. None if the series does not exist yet."""
    try:
        last = None
        with open(SERIES) as fh:
            for line in fh:
                if line.strip():
                    last = line
        return json.loads(last) if last else None
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--quiet", action="store_true", help="assess and print; never page")
    a = ap.parse_args()

    from gazbot7.config import RunConfig
    from gazbot7.store import open_store

    import sweep  # reuse sweep's checks — never a second implementation

    cfg = RunConfig()
    now = dt.datetime.now(dt.UTC)
    faults: list[str] = []
    notes: list[str] = []
    out: dict = {"ts": now.isoformat(), "days": a.days}

    # 1 + 3 — the two ledger/venue checks sweep already owns.
    try:
        store = open_store(cfg.store_path)
        bvf = sweep.check_book_vs_fills(store, now, days=a.days)
        fvb = sweep.check_fill_vs_book(store, now)
    except Exception as e:
        # ⚠ A CHECK THAT CANNOT RUN MUST SAY SO, NOT RETURN OK. sweep's own rule.
        bvf = {"status": "WARN", "detail": f"could not run: {type(e).__name__}: {e}"}
        fvb = {"status": "WARN", "detail": "not run"}
    out["book_vs_fills"] = bvf
    out["fill_vs_book"] = fvb

    for v in (bvf.get("faults") or []):
        faults.append(f"{v['day']} {v['desk']} book vs venue {v['divergence']:+,.2f}")
    for u in (bvf.get("unverifiable") or []):
        notes.append(f"{u['day']} {u['desk']} unverifiable ({u['why']})")
    if str(fvb.get("status", "")).upper() == "WARN" and (fvb.get("findings") or []):
        worst = max(fvb["findings"], key=lambda f: f.get("excess_pt", 0))
        notes.append(f"{len(fvb['findings'])} fill(s) outside the visible book, worst "
                     f"{worst.get('order_id')} {worst.get('excess_pt')}pt "
                     f"(~${worst.get('est_cost_usd', 0):,.0f})")

    # 2 — IB's own realised P&L against our clean book (audit finding 02).
    eq = latest_equity_record()
    if eq is None:
        notes.append("no equity_guard record yet — IB-vs-book divergence not checked")
    else:
        age_min = (now - dt.datetime.fromisoformat(eq["ts"])).total_seconds() / 60
        out["equity"] = {"ts": eq["ts"], "age_min": round(age_min, 1),
                         "ib_realized": eq.get("ib_realized"),
                         "our_realized": eq.get("our_realized"),
                         "divergence": eq.get("book_divergence"),
                         "nlv": eq.get("nlv"), "excess_liquidity": eq.get("excess_liquidity")}
        if age_min > 30:
            notes.append(f"equity record is {age_min:.0f}min old — account not being read")
        d = eq.get("book_divergence")
        if d is None:
            notes.append("IB-vs-book divergence unavailable (one side unreadable)")
        elif abs(d) > DIVERGENCE_TOL_USD:
            faults.append(f"IB realised ${eq['ib_realized']:,.2f} vs our clean book "
                          f"${eq['our_realized']:,.2f} — divergence ${d:+,.2f}")

    out["faults"] = faults
    out["notes"] = notes
    out["status"] = "FAULT" if faults else "OK"

    try:
        with open(OUT + ".tmp", "w") as fh:
            json.dump(out, fh, indent=1)
        os.replace(OUT + ".tmp", OUT)
    except Exception:
        pass

    if a.json:
        print(json.dumps(out, indent=1))
    else:
        print(f"{out['status']} · {len(faults)} fault(s) · {len(notes)} note(s)")
        for f in faults:
            print(f"  ! {f}")
        for n in notes:
            print(f"  · {n}")

    if not a.quiet:
        try:
            from gazbot7.notify import notify
            if faults:
                # ⚠ critical=True because this is the number every decision is made from, and the
                # 08-13 case sat wrong for a day. NOT marked: the mark is reserved for things that
                # can cost money in the next minutes, and a recording fault is not one — it is
                # expensive over days, which is a different urgency. See notify.MARK_ALWAYS.
                notify(f"⚠ BOOK vs BROKER — {' | '.join(faults)}"[:900],
                       critical=True, mark=False)
            elif notes:
                notify(f"BOOK vs BROKER reconciles · {'; '.join(notes)}"[:900], critical=False)
            else:
                notify(f"BOOK vs BROKER reconciles exactly over {a.days} day(s)", critical=False)
        except Exception:
            pass
    return 1 if faults else 0


if __name__ == "__main__":
    raise SystemExit(main())
