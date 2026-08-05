#!/usr/bin/env python3
"""MGC ABSORPTION VETO — abs_veto's shape, applied to the thrust gate, using the L2 book.

Operator, 2026-08-05: "what about absorption after signal shows up? can we do a variation of abs veto?"

★ THIS IS THE TEST I SHOULD HAVE RUN EARLIER AND DID NOT. `mgc_book_direction.py` asked the book to
CHOOSE a side and it could not (all features within ±3pp of the best constant). It then "tested a veto"
against a fixed constant direction — which was meaningless, because a constant is not a signal and
there was nothing real to protect. abs_veto works precisely because the THRUST picks the side and the
window only kills it when the tape contradicts. That is the shape here:

    thrust fires (direction chosen)  ->  watch the book for 55s  ->  stand down if absorbed

★ WHAT ABSORPTION MEANS MECHANICALLY. A move running UP is eating the ASK. If the far side (ask) is
heavy relative to the near side, or GROWS while price runs into it, sellers are absorbing the move and
it should stall. If the far side thins, there is nothing in the way and the run should extend. That is
a real microstructural claim and it is falsifiable on 250ms 10-level data.

★ WHY THIS IS THE LAST LIVE THREAD. The thrust gate CATCHES the runs — it fired during 22 of 22 big
runs, a median of 3 minutes in, with 76% of the move still available. It loses because it also fires
on everything else, and the loss autopsy found winners and losers identical on ATR (d=+0.21), ER
(d=+0.12) and thrust size (d=+0.02). Nothing in PRICE separates them. The book is a different source.

★ AND IT IS PLACEBO-CONTROLLED. A veto that removes 40% of trades looks brilliant whenever the removed
40% lost. Every veto cell is compared against removing the same NUMBER at random.

  PYTHONPATH=src .venv/bin/python scripts/mgc_absorption_veto.py
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import random
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.lake import connect  # noqa: E402

VPP = 10.0
LOOK = 40
VETO_S = 55        # abs_veto's own window, kept rather than re-tuned


def book_buckets(con, sec=15):
    """Book aggregated to `sec`-second buckets: resting size each side, L1-5 and L1-10."""
    b5 = " + ".join(f"COALESCE(bid{i}s,0)" for i in range(1, 6))
    a5 = " + ".join(f"COALESCE(ask{i}s,0)" for i in range(1, 6))
    b10 = " + ".join(f"COALESCE(bid{i}s,0)" for i in range(1, 11))
    a10 = " + ".join(f"COALESCE(ask{i}s,0)" for i in range(1, 11))
    rows = con.execute(f"""
        SELECT CAST(ts_ms/{sec*1000} AS BIGINT)*{sec} AS t,
               avg({b5}) b5, avg({a5}) a5, avg({b10}) b10, avg({a10}) a10, count(*) n
        FROM depth WHERE bid1p IS NOT NULL AND ask1p IS NOT NULL AND ask1p > bid1p
        GROUP BY 1 HAVING count(*) >= 5 ORDER BY 1""").fetchall()
    return ([int(r[0]) for r in rows],
            {int(r[0]): (float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in rows})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fee", type=float, default=1.50)
    z = ap.parse_args()
    con = connect(symbol="MGC")

    ns = {"__name__": "nm"}
    exec(compile(open("/home/alphabot/gazbot7/scripts/mgc_thrust_continuation.py").read(),
                 "thrust", "exec"), ns)
    T = ns["Tape"](ns["frame"](con))
    bt, bk = book_buckets(con)
    days = sorted({dt.datetime.fromtimestamp(x, dt.UTC).date() for x in T.m})
    print(f"MGC {len(T.m):,} minutes, {len(bt):,} 15s book buckets, {len(days)} days\n")

    CFG = [("thr1.5 w5 ER0.5", dict(thr_atr=1.5, win=5, er_min=0.5)),
           ("thr1.0 w10 ER0.5", dict(thr_atr=1.0, win=10, er_min=0.5)),
           ("thr1.5 w10 ER0.5", dict(thr_atr=1.5, win=10, er_min=0.5))]

    def at(t):
        i = bisect.bisect_right(bt, t) - 1
        return bk.get(bt[i]) if i >= 0 else None

    def tag(tr):
        """Attach absorption features measured AFTER the signal, over abs_veto's 55s window."""
        out = []
        for t in tr:
            t0 = t["ts"]
            pre, post = at(t0), at(t0 + VETO_S)
            if not pre or not post:
                continue
            sgn = 1 if t["side"] == "L" else -1
            # far side = the side price is running INTO (ask for a long, bid for a short)
            far0, near0 = (pre[1], pre[0]) if sgn > 0 else (pre[0], pre[1])
            far1, near1 = (post[1], post[0]) if sgn > 0 else (post[0], post[1])
            f0d, n0d = (pre[3], pre[2]) if sgn > 0 else (pre[2], pre[3])
            f1d, n1d = (post[3], post[2]) if sgn > 0 else (post[2], post[3])
            t = dict(t)
            t["absorb5"] = far0 / (far0 + near0) if (far0 + near0) > 0 else 0.5
            t["absorb10"] = f0d / (f0d + n1d) if (f0d + n1d) > 0 else 0.5
            t["d_far5"] = (far1 - far0) / far0 if far0 > 0 else 0.0
            t["d_far10"] = (f1d - f0d) / f0d if f0d > 0 else 0.0
            t["ratio10"] = f1d / (f1d + n1d) if (f1d + n1d) > 0 else 0.5
            out.append(t)
        return out

    def stat(tr):
        if not tr:
            return None
        tot = sum(x["pnl"] for x in tr)
        bd = defaultdict(float)
        for x in tr:
            bd[x["day"]] += x["pnl"]
        return {"n": len(tr), "tot": tot, "wk": tot / (len(days) / 5.0),
                "win": 100 * sum(1 for x in tr if x["pnl"] > 0) / len(tr),
                "green": sum(1 for v in bd.values() if v > 0), "days": len(bd),
                "stripday": tot - max(bd.values())}

    def line(lab, s, extra=""):
        if not s:
            print(f"{lab:<38}   none")
            return
        print(f"{lab:<38}{s['n']:>5}{s['tot']:>9.0f}{s['wk']:>8.0f}{s['win']:>6.0f}%"
              f"{s['green']:>4}/{s['days']:<3}{s['stripday']:>10.0f}{extra}")

    def placebo(full, k, real, draws=3000):
        rnd = random.Random(20260805)
        d = [sum(x["pnl"] for x in rnd.sample(full, k)) for _ in range(draws)]
        mu, sd = statistics.mean(d), statistics.pstdev(d)
        return mu, sd, 100.0 * sum(1 for x in d if x >= real) / draws

    print("DOES ABSORPTION SEPARATE WINNERS FROM LOSERS AT ALL?  (before any veto is built)")
    tr0 = tag(ns["trades"](T, fee=z.fee, **CFG[0][1]))
    W = [t for t in tr0 if t["pnl"] > 0]
    L = [t for t in tr0 if t["pnl"] <= 0]
    print(f"{'feature':<24}{'winners':>10}{'losers':>10}{'effect d':>10}")
    for k in ("absorb5", "absorb10", "d_far5", "d_far10", "ratio10"):
        if not W or not L:
            break
        a, b = statistics.mean(t[k] for t in W), statistics.mean(t[k] for t in L)
        s = statistics.pstdev([t[k] for t in L]) or 1e-9
        d = (a - b) / s
        flag = "  <-- SEPARATES" if abs(d) >= 0.30 else ("  (weak)" if abs(d) >= 0.15 else "")
        print(f"{k:<24}{a:>10.3f}{b:>10.3f}{d:>+10.2f}{flag}")
    print(f"n: {len(W)} winners vs {len(L)} losers")
    print("★ If absorption reads the same on winners and losers, no veto built from it can work —")
    print("  every later table would just be arithmetic on a random subset.\n")

    print("THE VETO — stand down when the book says the move is being absorbed")
    print(f"{'config':<38}{'n':>5}{'total':>9}{'$/wk':>8}{'win':>7}{'green':>8}{'strip-day':>10}")
    for name, kw in CFG:
        tr = tag(ns["trades"](T, fee=z.fee, **kw))
        if not tr:
            continue
        line(f"{name}  NO VETO", stat(tr))
        for k, thr, desc in (("absorb5", 0.52, "far side heavy at signal (L1-5)"),
                             ("absorb10", 0.52, "far side heavy at signal (L1-10)"),
                             ("d_far5", 0.05, "far side GREW in 55s (L1-5)"),
                             ("d_far10", 0.05, "far side GREW in 55s (L1-10)")):
            kept = [t for t in tr if t[k] < thr]
            if len(kept) < 10 or len(kept) == len(tr):
                continue
            s = stat(kept)
            mu, sd, pct = placebo(tr, len(kept), s["tot"])
            line(f"  veto: {desc}", s, f"   placebo {pct:>3.0f}%")
        print()
    print("★ 'placebo %' = share of RANDOM removals of the same size that beat the veto. Near 50% the")
    print("  book is not reading absorption, it is thinning the book of trades at random.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
