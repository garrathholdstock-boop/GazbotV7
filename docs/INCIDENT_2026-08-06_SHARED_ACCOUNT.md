# INCIDENT 2026-08-06 — the account is shared; one flatten cascaded all day

> Moved out of CLAUDE.md on 2026-08-13 during the bootstrap prune. The lesson is now encoded in
> code (`safety.own_flatten_verdict`), in the cross-desk reconciler, and in the 08-13 session doc —
> but the narrative is worth keeping intact, because 08-13 was the SAME bug class in a branch this
> fix missed.

**07:08:01** tournament `abs_veto_long` bought 2 lots. **07:08:21** the DAY-RIDER sold them — its
hard-flat branch flattened the ACCOUNT net without checking whose position it was, while its own state
said `entered=false`. Both desks trade MNQ in **DUQ191770** and IBKR nets them into ONE number.

**The cascade, because nothing stayed local:** the tournament does not receive executions from another
clientId, so its book stayed +2 against a venue of 0 → reconcile DRIFT → **11 minutes halted with the
whole safety block skipped** (`multislot_core.py:610` gates max-hold, the naked auditor, re-protect and
stop-breach behind `!= "drift"`). `audit_age_s` stayed GREEN throughout — the loop was cycling, only the
work inside it was skipped. On restart it "exited" phantom longs into a real −1 short and booked two
mis-paired TARGET wins. Then at **13:47** a leftover GTC stop from that mess fired with no position
behind it, **opened a naked short**, and was booked as `nipc_short` — six and a half hours later.

**Fixed (`d0f5bbd`):** every day-rider flatten is ownership-gated (`safety.own_flatten_verdict`), the
watchdog too (it was passive only by luck — a disabled strategy still stamps a fresh heartbeat), and
`desk_view`/`recent_trades` now filter `data_quality IS NULL` so excluded rows cannot reach the ROUTER's
decision inputs (the convention existed only in the reporting layer).

**⚠ THE GAP THAT IS STILL OPEN:** the desk audits *"does every SLOT have a live stop?"* — it never asks
the inverse, *"does every live STOP have a slot?"* An order belonging to no slot is invisible to the
per-slot auditor, and that is exactly what fires unattended. **Check TWS for working stops with no
position behind them.** Same class as [[md-stream-multi-symbol-filter]]: a SHARED resource consumed
without checking the tag that says whose it is — there the stream was multi-symbol, here the account is
multi-desk.

**Also 08-06:** nipc hit the operator's **−$400** kill criterion exactly (n=47, 26% win) and was benched
at 13:09; it is in `reactivate_gates.py::HOLD` so the 22:00 reopen will not bring it back. Re-arming is a
fresh operator decision — the 08-05 regime filter had its first out-of-sample day and did NOT rescue the
short side (SHORT n=14 −$302.50 = 76% of the loss on 30% of the fills).

---

## ⚠ THE GAP THIS DOC USED TO LEAVE OPEN IS NOW CLOSED (2026-08-13)

It said: *"the desk audits 'does every SLOT have a live stop?' — it never asks the inverse, 'does
every live STOP have a slot?'"* That inverse audit now exists in `scripts/desk_reconcile.py`
(`orphan_stops()`), running every 30s, and `day_rider.cancel_own_stops()` removes the cause on all
five close paths. Both were built after a rider stop outlived its position by two hours on 08-13.
