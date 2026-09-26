#!/usr/bin/env python3
"""THE ACCOUNT READER — and the equity loss limit, built but NOT armed.

★★★2026-09-26 AUDIT, FINDINGS 02 AND 03. This desk reconciled LOTS every 30 seconds and had never
once reconciled MONEY. `ib_gateway.account_summary()` existed and was called by nothing; a grep for
NetLiquidation, ExcessLiquidity, reqPnL or realizedPNL returned that one unused wrapper. So there was
no independent check that the dashboard's P&L equalled the money in the account, and no margin
monitoring of any kind — while 4 MNQ lots is roughly $246k of notional against a planned $30k.

And the only risk rule that runs — the $250 daily limit — has three holes: it sums `trades.pnl_usd`
from OUR OWN LEDGER (the thing that has lied twice and once booked $1,551 of profit that never
existed), it counts REALISED P&L only (so an open -$2,000 never trips it), and it can only write
`off` to gate switches, which does not touch the rider — the desk that actually trades.

★ WHAT THIS DOES
  1. Reads the account from IBKR on a READ-ONLY connection: net liquidation, excess liquidity, cash,
     and IB's own realised + unrealised P&L. Appends one line to data/equity_guard.jsonl — the
     series, so the reconciliation question becomes answerable at all.
  2. Compares IB's realised P&L against our own ledger for the session and records the divergence.
     Nothing has ever done this on a cadence.
  3. Pages if excess liquidity falls below a configured floor.
  4. Evaluates a loss limit on OPEN + REALISED equity.

⚠⚠⚠ IT IS NOT ARMED, AND ON PAPER IT NEVER ACTS. Operator, 2026-09-26: "just dont switch on any kill
switches while paper trading. i want to be able to trade and learn." So in PAPER mode this is
REPORT-ONLY: it measures, it logs, it can page, and it will not close anything, ever. The flatten
path is reached only when livemode.mode() is LIVE and `equity_loss_limit_usd` is set — two
deliberate acts, neither of which is done. `tests/test_equity_guard.py` asserts that against the
SOURCE and against behaviour.

★ AND WHEN IT DOES ACT, IT NEVER TOUCHES THE BROKER. Like step_away.py it writes
`day_rider_claim.txt` — the same file his own Claim button writes — and the rider executes it through
its own ownership check. It therefore cannot open, size, reverse or add. The read connection is
`readonly=True` on its own clientId, so it has no order path at all.

⚠ WHY 2 MINUTES AND NOT ON THE 30-SECOND RECONCILER, which is what the audit recommended: the
leading hypothesis for the gateway's CLOSE-WAIT leak is IBKR pacing, and the desk already opens
~5,000 short-lived connections a day. Adding one every 30s to diagnose money would feed the exact
failure that has cost $364 and $2,149. A margin tracker must never be what costs a claim — the same
reasoning macro_watch.py uses for being hourly. Equity moves on a scale of minutes; this is enough.

  PYTHONPATH=src .venv/bin/python scripts/equity_guard.py [--once] [--json] [--no-act]
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import sqlite3
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

GB = "/home/alphabot/gazbot7"
SERIES = f"{GB}/data/equity_guard.jsonl"
LOG = f"{GB}/data/equity_guard.log"
STATE = f"{GB}/data/equity_guard_state.json"
CLAIM = f"{GB}/data/day_rider_claim.txt"
RIDER = f"{GB}/data/day_rider_state.json"
DB = f"{GB}/data/gazbot7.db"
CLIENT_ID = 11          # core=0 md=2 rider=4 wd=5 eod=6 checks=8 macro=9 breadth=16 — 11 is free

# The account fields worth having. Names are IBKR's own accountSummary tags.
TAGS = ("NetLiquidation", "ExcessLiquidity", "TotalCashValue", "AvailableFunds",
        "MaintMarginReq", "InitMarginReq", "UnrealizedPnL", "RealizedPnL")


def log(m: str) -> None:
    line = f"{dt.datetime.now(dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} {m}"
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def session_start(now: dt.datetime) -> dt.datetime:
    """The CME session starts at the 22:00Z reopen — NEVER the calendar day.

    ★ The same boundary daily_loss_limit.py and step_away.py use, and for the same reason: a
    midnight reset would clear the limit in the middle of a losing session, the one moment it must
    not."""
    start = now.replace(hour=22, minute=0, second=0, microsecond=0)
    return start - dt.timedelta(days=1) if now.hour < 22 else start


def our_ledger_pnl(now: dt.datetime) -> tuple[float, int]:
    """What OUR book thinks the session made. Read-only, and it filters data_quality.

    ⚠ `EXCLUDE:`/`BADFILL:` rows are excluded, because a bug-caused fill is not a trading result —
    the operator's standing rule is LABEL, never adjust. The divergence recorded below is therefore
    'clean book vs the broker', which is the comparison that means something.
    """
    try:
        c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        row = c.execute(
            "select coalesce(sum(pnl_usd),0), count(*) from trades "
            "where closed_at is not null and closed_at >= ? and data_quality is null",
            (session_start(now).isoformat(),)).fetchone()
        c.close()
        return float(row[0]), int(row[1])
    except Exception:
        return (float("nan"), 0)


async def read_account() -> tuple[dict, str | None]:
    """(values, account_id). READ-ONLY, own clientId, disconnected in a finally.

    ⚠ Everything here is belt-and-braces about not lingering: the gateway's accept queue filling is
    this desk's signature outage, and a tracker that leaks a connection would be contributing to it.
    """
    try:
        from ib_async import IB
    except Exception as e:
        return ({"error": f"ib_async unavailable: {e}"}, None)
    ib = IB()
    try:
        await ib.connectAsync("127.0.0.1", 4002, clientId=CLIENT_ID, readonly=True, timeout=15)
        accounts = [a for a in (ib.managedAccounts() or []) if a]
        acct = accounts[0] if accounts else None
        rows = await ib.accountSummaryAsync()
        vals: dict[str, float] = {}
        for r in rows:
            if r.tag in TAGS:
                try:
                    vals[r.tag] = float(r.value)
                except Exception:
                    pass
        return (vals, acct)
    except Exception as e:
        return ({"error": f"{type(e).__name__}: {e}"}, None)
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass


def rider_holds() -> float:
    """Lots the rider holds, per its own claim. NaN when it cannot be read — never 0."""
    try:
        with open(RIDER) as fh:
            st = json.load(fh)
        if not st.get("entered") or st.get("closed"):
            return 0.0
        return abs(float(st.get("qty") or 0.0))
    except Exception:
        return float("nan")


def read_state() -> dict:
    try:
        with open(STATE) as fh:
            return json.load(fh)
    except Exception:
        return {}


def write_state(d: dict) -> None:
    try:
        cur = read_state()
        cur.update(d)
        tmp = STATE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(cur, fh, indent=1)
        os.replace(tmp, STATE)
    except Exception as e:
        log(f"state write failed: {type(e).__name__}: {e}")


def notify(msg: str, *, critical: bool = False) -> None:
    try:
        from gazbot7.notify import notify as _n
        _n(msg, critical=critical)
    except Exception as e:
        log(f"notify failed: {type(e).__name__}: {e}")


def request_flatten(reason: str) -> None:
    """Write the claim the operator's own button writes. Nothing else.

    ★ The indirection IS the design (step_away.py's pattern): this places no order, so it cannot
    open, size, reverse or add. The rider consumes the request through its own ownership check.
    ⚠ Reached ONLY in LIVE mode with a configured limit — see main().
    """
    with open(CLAIM, "w") as fh:
        fh.write(json.dumps({"ts": dt.datetime.now(dt.UTC).isoformat(),
                             "source": "equity_guard", "reason": reason}) + "\n")


def assess(vals: dict, ours: float, limit: float | None, floor: float | None) -> dict:
    """Pure: what the numbers say. No I/O, so the decision is testable without a broker."""
    nlv = vals.get("NetLiquidation")
    excess = vals.get("ExcessLiquidity")
    unreal = vals.get("UnrealizedPnL")
    real = vals.get("RealizedPnL")
    total = None
    if unreal is not None and real is not None:
        total = unreal + real
    out = {
        "nlv": nlv, "excess_liquidity": excess, "cash": vals.get("TotalCashValue"),
        "maint_margin": vals.get("MaintMarginReq"),
        "ib_unrealized": unreal, "ib_realized": real, "ib_total_pnl": total,
        "our_realized": (None if ours != ours else ours),
        # ★ THE RECONCILIATION NOBODY HAS EVER DONE ON A CADENCE: IB's realised against our clean
        # book. A persistent non-zero here means the number every decision is made from is wrong.
        "book_divergence": (None if (real is None or ours != ours) else round(real - ours, 2)),
        "breach": False, "margin_breach": False, "reasons": [],
    }
    if limit is not None and total is not None and total <= -abs(limit):
        out["breach"] = True
        out["reasons"].append(f"equity P&L ${total:,.2f} at or beyond the ${abs(limit):,.0f} limit "
                              f"(realised ${real:,.2f} + open ${unreal:,.2f})")
    if floor is not None and excess is not None and excess < abs(floor):
        out["margin_breach"] = True
        out["reasons"].append(f"excess liquidity ${excess:,.2f} below the ${abs(floor):,.0f} floor")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="one read (the timer's normal mode)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-act", action="store_true", help="never write a claim, whatever the mode")
    a = ap.parse_args()

    from gazbot7 import livemode

    now = dt.datetime.now(dt.UTC)
    vals, acct = asyncio.run(read_account())
    if "error" in vals:
        # ⚠ QUIET ON A SINGLE FAILURE, LOUD ON A STREAK — the macro_watch pattern. A venue that is
        # shut, a gateway mid-restart and a real outage all look identical for one sample.
        st = read_state()
        streak = int(st.get("read_fail_streak") or 0) + 1
        write_state({"read_fail_streak": streak, "last_error": vals["error"], "ts": now.isoformat()})
        log(f"read failed ({streak} in a row): {vals['error']}")
        if streak in (30, 180):        # ~1h and ~6h at a 2-minute cadence
            notify(f"⚠ EQUITY GUARD has been unable to read the account for {streak * 2} minutes "
                   f"({vals['error']}). Margin and equity are UNMONITORED until this clears.",
                   critical=False)
        return 0
    write_state({"read_fail_streak": 0})

    mode = livemode.mode(acct)
    conf = livemode._conf()
    limit = conf.get("equity_loss_limit_usd")
    floor = conf.get("margin_floor_usd")
    ours, n = our_ledger_pnl(now)
    verdict = assess(vals, ours, limit, floor)
    rec = {"ts": now.isoformat(), "account": acct, "mode": mode, "lots": rider_holds(),
           "our_trades": n, "limit": limit, "floor": floor, **verdict}

    try:
        with open(SERIES, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception as e:
        log(f"series write failed: {type(e).__name__}: {e}")

    if a.json:
        print(json.dumps(rec, indent=1))
    else:
        log(f"{mode} {acct} · NLV ${verdict['nlv'] or 0:,.0f} · excess "
            f"${verdict['excess_liquidity'] or 0:,.0f} · IB P&L "
            f"{verdict['ib_total_pnl'] if verdict['ib_total_pnl'] is not None else '?'} "
            f"· ours {verdict['our_realized']} · divergence {verdict['book_divergence']}")

    if verdict["margin_breach"]:
        notify(f"⚠⚠ MARGIN FLOOR — {'; '.join(verdict['reasons'])}. NLV "
               f"${verdict['nlv']:,.0f}.", critical=True)

    if verdict["breach"]:
        # ⚠⚠⚠ THE ONE BRANCH THAT CAN CLOSE A POSITION, AND IT IS UNREACHABLE ON PAPER.
        # Three conditions, all of which must hold: a configured limit, LIVE mode, and --act.
        # On the paper account mode is PAPER, so this reports and returns. That is the operator's
        # standing instruction for the paper phase, not an oversight.
        if mode == "LIVE" and not a.no_act:
            request_flatten("; ".join(verdict["reasons"]))
            notify(f"🛡 EQUITY LOSS LIMIT — {'; '.join(verdict['reasons'])}. Flatten requested "
                   f"(the rider executes it through its own ownership check).", critical=True)
        else:
            notify(f"📋 EQUITY LOSS LIMIT WOULD HAVE FIRED ({mode}, report-only) — "
                   f"{'; '.join(verdict['reasons'])}. Nothing was closed.", critical=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
