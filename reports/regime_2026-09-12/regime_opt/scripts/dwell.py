#!/usr/bin/env python3
"""THE DWELL ARM - operator instruction 2026-09-12.

  "i want to see if we can trade in between the tunnels or regimes.
   will it use sustained efficiency as a trigger?"

As the code stood the answer was NO, and worse than no: efficiency was only a FEATURE of the
GMM, and `clean=True` REQUIRED the target state to be absent in the prior two bars - i.e. the
incumbent deliberately selects the NEWEST, LEAST-CONFIRMED instance of a state. This arm tests
the opposite: wait for the state to be ESTABLISHED, then join.

THE GRAMMAR (one mechanism, four arms, so the 2x2 is like-for-like):
  qual[i]  a per-bar condition      side[i]  a per-bar direction
  a RUN is a maximal block of consecutive bars with qual True and side constant.
  DWELL K enters at the OPEN OF BAR K+1 of the run - i.e. the signal bar is the K-th bar of the
  run, and entry is the next bar's open, exactly as everywhere else in this study.
  K=1 is therefore the incumbent trigger: the first bar of a new state.

  ARM             qual                                        side
  STATE           label(state) is BULLISH/BEARISH             that label
  ER              er >= floor                                 sign(d8)
  BOTH            label directional AND er >= floor           that label
  NEITHER         (always true)                               sign(d8)      <- the control

COST OF WAITING is reported for every K: the part of the leg already gone at entry, measured in
ATR units from where a K=1 entry would have filled, on the SAME runs (matched subset), because
the unmatched curve confounds waiting with survivorship - only runs that LAST reach large K.
"""
import sys, os, itertools, time
sys.path.insert(0, os.path.dirname(__file__))
import regimelab as R, numpy as np, pandas as pd

ART = R.ART; FRIC = 1.25


def runs(qual, side, sess):
    """Maximal blocks of consecutive bars with qual True and constant side within a session.

    Returns (start_idx, length, side) arrays.
    """
    n = len(qual)
    ok = qual & (side != 0)
    new = np.ones(n, bool)
    new[1:] = ~(ok[1:] & ok[:-1] & (side[1:] == side[:-1]) & (sess[1:] == sess[:-1]))
    gid = np.cumsum(new)
    d = pd.DataFrame({"g": gid, "ok": ok, "i": np.arange(n), "s": side})
    d = d[d.ok]
    if not len(d):
        return np.array([], int), np.array([], int), np.array([], int)
    a = d.groupby("g").agg(start=("i", "first"), ln=("i", "size"), s=("s", "first"))
    return a.start.values, a.ln.values, a.s.values


def dwell_trades(M, starts, lens, sides, K, hold, friction=FRIC, min_len=None):
    """Entry = open[start+K] (signal bar = start+K-1). Exit = close of signal_bar + hold."""
    g = M.g
    op, cl, sess = g.open.values, g.close.values, g.sess.values
    atr = M.feat["atr"]; n = len(g)
    need = K if min_len is None else max(K, min_len)
    m = lens >= need
    st, sd = starts[m], sides[m]
    sig = st + K - 1                       # the bar whose close completes the K-bar dwell
    ok = (sig + hold < n) & (sig + 1 < n)
    st, sd, sig = st[ok], sd[ok], sig[ok]
    ok = (sess[sig] == sess[sig + hold]) & (sess[sig] == sess[st])
    st, sd, sig = st[ok], sd[ok], sig[ok]
    if not len(sig):
        return pd.DataFrame(columns=["sess", "i", "side", "gross", "bars", "pt", "forfeit"])
    entry = op[sig + 1]
    gross = sd * (cl[sig + hold] - entry)
    forfeit = sd * (entry - op[st + 1]) / np.maximum(atr[st], 1e-6)   # leg given up, in ATR
    T = pd.DataFrame({"sess": sess[sig], "i": sig, "side": sd, "gross": gross,
                      "bars": hold, "forfeit": forfeit})
    T["pt"] = T.gross - friction
    return T


def arms(M, er_feat="er8", floor=0.0):
    d8 = M.feat["d8"]
    sgn = np.sign(np.nan_to_num(d8)).astype(int)
    dirn = M.sign
    er = np.nan_to_num(M.feat[er_feat], nan=-1)
    fin = np.isfinite(d8)
    return {
        "STATE":   (dirn != 0, dirn),
        "ER":      (fin & (er >= floor), sgn),
        "BOTH":    ((dirn != 0) & (er >= floor), dirn),
        "NEITHER": (fin, sgn),
    }


def main():
    bar, K_MAX = 15, 6
    g = R.load_bars(bar)
    M = R.Model(bar, 3, "base", g=g)
    sess = g.sess.values
    print(f"DWELL ARM · {bar}-min bars · 3 states · base features · friction {FRIC}pt")
    print(M.describe().to_string(index=False), "\n")

    rows, cost = [], []
    HOLDS = [30, 60, 90, 120]
    FLOORS = {"er8": [0.0, 0.3, 0.45, 0.6], "er4": [0.0, 0.4, 0.55, 0.7]}

    for erf, floors in FLOORS.items():
        for fl in floors:
            A = arms(M, erf, fl)
            for arm, (q, s) in A.items():
                if arm in ("STATE", "NEITHER") and fl != floors[0]:
                    continue                       # these two do not depend on the ER floor
                st, ln, sd = runs(q, s, sess)
                if not len(st):
                    continue
                for K in range(1, K_MAX + 1):
                    for hold_min in HOLDS:
                        hold = hold_min // bar
                        T = dwell_trades(M, st, ln, sd, K, hold)
                        if len(T) < 100:
                            continue
                        ps = R.period_stats(T, M)
                        sdv = T.gross.std(ddof=1)
                        rows.append(dict(erfeat=erf, floor=fl, arm=arm, K=K, hold_min=hold_min,
                                         n=len(T), gross=T.gross.mean(), gross_sd=sdv,
                                         net=T.gross.mean() - FRIC,
                                         t=(T.gross.mean() - FRIC) / (sdv / np.sqrt(len(T))),
                                         forfeit_atr=T.forfeit.mean(),
                                         TR_n=ps["TRAIN"]["n"], TR=ps["TRAIN"]["mean"],
                                         VA_n=ps["VALIDATE"]["n"], VA=ps["VALIDATE"]["mean"],
                                         TE_n=ps["TEST"]["n"], TE=ps["TEST"]["mean"],
                                         matched=False))
                        # ── MATCHED: the same runs at every K (length >= K_MAX) ──
                        Tm = dwell_trades(M, st, ln, sd, K, hold, min_len=K_MAX)
                        if len(Tm) >= 60:
                            psm = R.period_stats(Tm, M); sm = Tm.gross.std(ddof=1)
                            rows.append(dict(erfeat=erf, floor=fl, arm=arm, K=K,
                                             hold_min=hold_min, n=len(Tm),
                                             gross=Tm.gross.mean(), gross_sd=sm,
                                             net=Tm.gross.mean() - FRIC,
                                             t=(Tm.gross.mean() - FRIC) / (sm / np.sqrt(len(Tm))),
                                             forfeit_atr=Tm.forfeit.mean(),
                                             TR_n=psm["TRAIN"]["n"], TR=psm["TRAIN"]["mean"],
                                             VA_n=psm["VALIDATE"]["n"], VA=psm["VALIDATE"]["mean"],
                                             TE_n=psm["TEST"]["n"], TE=psm["TEST"]["mean"],
                                             matched=True))
                # run-length survivorship for this arm
                for K in range(1, K_MAX + 1):
                    cost.append(dict(erfeat=erf, floor=fl, arm=arm, K=K,
                                     runs_total=len(st), runs_reach_K=int((ln >= K).sum()),
                                     frac=float((ln >= K).mean()),
                                     mean_run_len=float(ln.mean())))

    D = pd.DataFrame(rows); D.to_csv(f"{ART}/tables/dwell_all.csv", index=False)
    C = pd.DataFrame(cost).drop_duplicates(); C.to_csv(f"{ART}/tables/dwell_survivorship.csv",
                                                       index=False)
    print(f"dwell cells: {len(D)}  -> tables/dwell_all.csv")

    # ── THE CURVE, in full, exactly as asked: mean net by K, never just the best K ──
    for mt in (False, True):
        print(f"\n{'='*100}\nDWELL CURVE  ({'MATCHED - only runs that reach 6 bars, same runs at every K'if mt else'UNMATCHED - every run that reaches K'})")
        sub = D[(D.matched == mt) & (D.arm == "STATE")]
        if len(sub):
            print("\n  ARM = STATE (no ER gate)")
            p = sub.pivot_table(index="K", columns="hold_min",
                                values=["n", "net", "forfeit_atr"])
            print(p.round(2).to_string())
        for erf in FLOORS:
            for fl in FLOORS[erf][1:]:
                s2 = D[(D.matched == mt) & (D.arm == "BOTH") & (D.erfeat == erf)
                       & (D.floor == fl)]
                if len(s2):
                    print(f"\n  ARM = BOTH · {erf} >= {fl}")
                    print(s2.pivot_table(index="K", columns="hold_min",
                                         values=["n", "net", "forfeit_atr"]).round(2).to_string())

    # ── THE 2x2: does sustained ER add to the state, or is the state carrying ER? ──
    print(f"\n{'='*100}\n2x2 - STATE x SUSTAINED-ER (unmatched, K = dwell length, net pt at 1.25)")
    for erf in FLOORS:
        for fl in FLOORS[erf][1:]:
            print(f"\n  {erf} floor {fl}")
            s = D[(~D.matched) & (D.erfeat.isin([erf, list(FLOORS)[0]]))]
            s = D[(~D.matched) & (((D.arm.isin(["ER", "BOTH"])) & (D.erfeat == erf)
                                   & (D.floor == fl)) | (D.arm.isin(["STATE", "NEITHER"])))]
            pv = s.pivot_table(index=["K", "hold_min"], columns="arm", values="net")
            nv = s.pivot_table(index=["K", "hold_min"], columns="arm", values="n")
            for c in ("NEITHER", "STATE", "ER", "BOTH"):
                if c not in pv:
                    pv[c] = np.nan; nv[c] = np.nan
            out = pd.DataFrame({"NEITHER": pv.NEITHER, "STATE": pv.STATE, "ER": pv.ER,
                                "BOTH": pv.BOTH,
                                "state_adds": pv.BOTH - pv.ER, "er_adds": pv.BOTH - pv.STATE,
                                "n_BOTH": nv.BOTH})
            print(out.round(2).to_string())

    print(f"\n{'='*100}\nSURVIVORSHIP - what fraction of runs is still alive at bar K")
    print(C[C.arm.isin(["STATE"])].pivot_table(index="K", values=["runs_reach_K", "frac"])
          .round(3).to_string())
    print(C[C.arm == "BOTH"].pivot_table(index="K", columns=["erfeat", "floor"],
                                         values="frac").round(3).to_string())

if __name__ == "__main__":
    main()
