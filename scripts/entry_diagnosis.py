#!/usr/bin/env python3
"""ENTRY DIAGNOSIS — is the day-rider's ENTRY the weak point? (2026-08-19)

★★★ THE ANSWER IS NO, AND THAT IS THE FINDING. The entry is not fragile — it is EMPTY. Four
measurements, all on the 239-session lake replay of the REAL drift.compute():

  1. THE PRICE IS NOT THE PROBLEM. Freeze the direction and move the entry 2/4/8 minutes later:
     paired Δ = +$6 / -$4 / -$32 per session (|t| <= 1.06). Entry-price wobble is UNBIASED noise.
     Re-read the DIRECTION 2/4/8 minutes later instead and it is -$95 / -$285 / -$118 (t=-2.39 at
     4 min), because sign(net) flips on 12-20% of days. The fragile input is the DIRECTION, not the
     price, and it is fragile because it is a coin flip.
  2. THE DIRECTION HAS NO EDGE AT ANY MINUTE. sign(net since 13:30) calls the move to 20:40 at
     46-53% from 13:32 through 14:30 — chance, everywhere, with mean pt/session inside +-1 SE.
  3. THE CONFIRMATION IS A CHASE. Same day, same direction, same exit: entering at the 13:30 open
     instead of the confirmation price is worth +56.7pt +-2.4 per session (t=+23.2). The detector
     waits for a 57pt move and then buys it; the mean give-back exceeds it (-21.1pt to 20:40).
  4. THE WHOLE COMPARISON HAS BEEN RUN BELOW THE NOISE FLOOR. On the ladder exit, 200 RANDOM entry
     systems (minute uniform 9..30, direction a coin flip) total -$17,065..+$15,878, sd $5,400.
     Every designed entry, at every delay, lands inside that band. A +$7,194 -> -$12,090 flip on
     two minutes is one standard deviation of a coin, not a broken component.

Run:  cd /home/alphabot/gazbot7 && PYTHONPATH=src .venv/bin/python scripts/entry_diagnosis.py
Needs reports/entry_lab/signal_series.json — build it with scripts/entry_chatter.py first.
"""
import copy, math, random, statistics as st, sys
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from entry_lab import RL, SER, sess_from, rule_persist, rule_clock, series   # noqa: E402

HOLD = RL.Cfg(breakeven_after_lot=0, rungs=[], adverse_cut_pt=0, trail_atr_arm=1e9)
LAD = RL.Cfg()


def rows(con, S, cfg, dly=0):
    c = copy.copy(cfg); c.entry_delay_min = dly
    return {r["day"]: r for r in RL.run_all(con, c, S)}


def paired(A, B):
    ks = [k for k in A if k in B]
    d = [A[k]["total"] - B[k]["total"] for k in ks]
    if st.pstdev(d) == 0:
        return 0.0, 0.0, 0.0, len(ks)
    m = st.mean(d); se = st.stdev(d) / math.sqrt(len(d))
    return m, se, m / se, len(ks)


def main():
    from gazbot7.lake import connect
    con = connect(symbol="MNQ")
    S10 = sess_from(lambda d: rule_clock(d, 10))
    base = rows(con, S10, HOLD)

    print("1. PRICE vs DIRECTION — which half of the entry actually moves the P&L?")
    for k in (2, 4, 8):
        Sp = [{"day": s["day"], "minute": 10 + k, "dir": s["dir"]} for s in S10]
        m, se, t, n = paired(rows(con, Sp, HOLD), base)
        print(f"   price  +{k}m, direction frozen : {m:+7.0f} +-{se:4.0f}/sess  t={t:+5.2f}")
    for k in (2, 4, 8):
        Sd, fl = [], 0
        for s in S10:
            ss = series(s["day"])
            if 10 + k not in ss:
                continue
            dd = ss[10 + k][2] or ("UP" if ss[10 + k][6] > 0 else "DOWN")
            fl += dd != s["dir"]
            Sd.append({"day": s["day"], "minute": 10, "dir": dd})
        m, se, t, n = paired(rows(con, Sd, HOLD), base)
        print(f"   direction re-read +{k}m       : {m:+7.0f} +-{se:4.0f}/sess  t={t:+5.2f}  flips {100*fl/n:.1f}%")

    print("\n2. DIRECTION EDGE BY MINUTE — sign(net) vs the move to 20:40")
    for k in (2, 5, 10, 15, 20, 30, 60):
        pts = []
        for d in sorted(SER):
            s = series(d)
            if k + 1 not in s or s[k][6] == 0:
                continue
            sg = 1 if s[k][6] > 0 else -1
            pts.append(sg * (SER[d]["close2040"] - s[k + 1][5]))
        m = st.mean(pts); se = st.stdev(pts) / math.sqrt(len(pts))
        cm = 13*60+30+k
        print(f"   {cm//60:02d}:{cm%60:02d}: hit {100*sum(1 for x in pts if x>0)/len(pts):5.1f}%  "
              f"{m:+7.1f}pt +-{se:4.1f}  t={m/se:+5.2f}  n={len(pts)}")

    print("\n3. THE NULL BAND — 200 random entries on the ladder exit")
    days = [d for d in sorted(SER) if 30 in series(d)]
    tots = []
    for it in range(200):
        random.seed(1000 + it)
        S = [{"day": d, "minute": random.randint(9, 30),
              "dir": random.choice(("UP", "DOWN"))} for d in days]
        tots.append(sum(r["total"] for r in rows(con, S, LAD).values()))
    tots.sort()
    print(f"   min {tots[0]:+.0f} · p5 {tots[10]:+.0f} · median {tots[100]:+.0f} · "
          f"p95 {tots[190]:+.0f} · max {tots[-1]:+.0f} · sd {st.stdev(tots):,.0f}")
    for nm, S in (("drift confirmation", sess_from(lambda d: rule_persist(d, 1))),
                  ("clock 13:40 dir=net", S10)):
        for dly in (0, 2, 4, 8):
            tt = sum(r["total"] for r in rows(con, S, LAD, dly).values())
            pct = 100 * sum(1 for x in tots if x < tt) / len(tots)
            print(f"   {nm:<20} delay {dly}: {tt:+8.0f} = {pct:5.1f}th pct of the random null")


if __name__ == "__main__":
    main()
