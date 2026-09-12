#!/usr/bin/env python3
"""THE OPERATOR'S CUT-AND-FLIP, tested against the rule it would replace.

His rule, 2026-09-12: "we start automating our entries using when and the 10 minute delay. if it
hits targets great. if it starts grinding the other way we cut it quickly. and then buy in that
direction too. instantly. so at least we are a good chance of hitting target in that direction."

★ WHY IT IS WORTH TESTING RATHER THAN WAVING AWAY. Everything this desk has measured says the tape
  says WHEN and never WHICH WAY (OFI r=0.688 contemporaneous, -0.001 forward; break direction
  0.44-0.53; twelve regime cells at t~1). A cut-and-flip is the one structure that needs only the
  WHEN: it takes both sides, cheaply on the wrong one and in full on the right one.
★ AND WHY IT IS NOT ALREADY REFUTED. A BAND stop-and-reverse was refuted here at -15.64pt/hr, but
  that version reverses at every band touch and pays ~12pt/hr in flip costs. Flip COUNT is the whole
  economics, so a rule that flips once or twice is a different animal and has to be measured.
★ THE POPULATION IT EXISTS TO RESCUE: drift confirms on 97% of sessions and only 42% of entries pay.

⚠ THE ENTRY IS NOT RE-DERIVED. Confirmation minute and direction come from the driftlab replay
  (data/driftlab/_persistence.json), which called the REAL drift.compute() causally. A hand-rolled
  detector once fabricated +$819 on this desk.
⚠ HARNESS INTEGRITY: rule A (hold to 20:40, no stop) must reproduce the recorded pt_2040 or every
  number below is worthless. It is asserted, not eyeballed.
"""
from __future__ import annotations
import argparse, json
import duckdb, numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
FRIC = 1.25          # MNQ all-in per round trip, in points. EVERY flip pays it again.
FLAT_S = 20*3600 + 40*60


def load(sym: str):
    con = duckdb.connect()
    df = con.execute(f"""
      select ts, open, high, low, close from read_parquet('{GB}/data/driftlab/{sym}_*.parquet')
      order by ts""").df().drop_duplicates("ts")
    df["d"] = pd.to_datetime(df.ts, unit="s", utc=True).dt.date.astype(str)
    df["sec"] = df.ts % 86400
    recs = {r["day"]: r for r in json.load(open(f"{GB}/data/driftlab/_persistence.json"))
            ["by_symbol"][sym] if r["confirmed"]}
    return df, recs


def run(df, recs, cut, target, max_flips, flip=True):
    """One session, one entry, cut at `cut` points against, optionally reverse. Flat at 20:40Z."""
    out = []
    for day, g in df.groupby("d", sort=True):
        r = recs.get(day)
        if r is None:
            continue
        entry_sec = 13*3600 + 30*60 + int(r["minute"])*60
        s = g[(g.sec >= entry_sec) & (g.sec <= FLAT_S)]
        if len(s) < 30:
            continue
        o, h, l = s.open.values, s.high.values, s.low.values
        side = 1 if r["dir"] == "UP" else -1
        i, flips, pnl, e = 0, 0, 0.0, s.open.values[0]
        while i < len(s):
            hit_t = hit_c = None
            for j in range(i, len(s)):
                fav = (h[j]-e) if side > 0 else (e-l[j])
                adv = (e-l[j]) if side > 0 else (h[j]-e)
                # ⚠ BOTH TOUCHED IN ONE BAR = assume the CUT first. The optimistic reading is how a
                # backtest invents money it never had; on a 1-min bar we cannot know the order.
                if adv >= cut: hit_c = j; break
                if target and fav >= target: hit_t = j; break
            if hit_t is not None:
                pnl += target - FRIC; flips += 1; break
            if hit_c is None:                       # neither — carry to the 20:40 flat
                pnl += side*(s.close.values[-1]-e) - FRIC; flips += 1; break
            pnl += -cut - FRIC; flips += 1
            if not flip or flips > max_flips or hit_c >= len(s)-2:
                break
            side, e, i = -side, o[hit_c+1], hit_c+1   # ★ INSTANT REVERSE at the next bar's open
        out.append((day, pnl, flips))
    return pd.DataFrame(out, columns=["day", "pt", "flips"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sym", default="NQ")
    a = ap.parse_args()
    df, recs = load(a.sym)
    print(f"{a.sym}: {len(recs)} confirmed sessions on {df.d.nunique()} tape days\n")

    # ── harness integrity: rule A must reproduce the recorded hold-to-20:40 result
    A = run(df, recs, cut=1e9, target=0, max_flips=0, flip=False)
    rec = pd.DataFrame([{"day": d, "rec": r["pt_2040"]} for d, r in recs.items()])
    m = A.merge(rec, on="day")
    err = (m.pt + FRIC - m.rec).abs()
    print(f"HARNESS CHECK vs the recorded drift replay: n={len(m)}, median |err| "
          f"{err.median():.2f}pt, 90th {err.quantile(.9):.2f}pt")
    assert err.median() < 2.0, "the harness does not reproduce the recorded entry — stop here"
    print(f"  INCUMBENT (enter on drift, no stop, hold to 20:40): "
          f"{A.pt.mean():+.1f}pt/session, {100*(A.pt > 0).mean():.0f}% green\n")

    # ── THE DECOMPOSITION. A = the incumbent (no cut). B = CUT ONLY, no reverse. C = cut AND
    #    flip. The claim is not "C makes money" — it is "the FLIP adds something". That is only
    #    answerable against B. If C and B are indistinguishable the flip is decoration and the real
    #    finding is that the rider wants a stop, which is a different and much louder conversation.
    rng = np.random.default_rng(12)

    def boot(x, y):
        """Day-clustered bootstrap of the C-B difference: 10,000 resamples of SESSIONS."""
        d = (x - y).values
        idx = rng.integers(0, len(d), size=(10000, len(d)))
        m = d[idx].mean(axis=1)
        return d.mean(), np.percentile(m, 2.5), np.percentile(m, 97.5)

    print(f"{'cut':>5}{'target':>7}{'flips':>6} | {'A hold':>8}{'B cut':>8}{'C flip':>8} | "
          f"{'C-B':>7}{'95% CI on C-B':>20}{'verdict':>12}")
    for cut in (25, 40, 60):
        for target in (100, 0):
            for mf in (1, 3):
                B = run(df, recs, cut, target, mf, flip=False)
                C = run(df, recs, cut, target, mf, flip=True)
                j = B.merge(C, on="day", suffixes=("_b", "_c"))
                d, lo, hi = boot(j.pt_c, j.pt_b)
                tgt = f"{target}" if target else "hold"
                v = "FLIP ADDS" if lo > 0 else ("flip HURTS" if hi < 0 else "indistinct")
                print(f"{cut:>5}{tgt:>7}{mf:>6} | {A.pt.mean():>8.1f}{B.pt.mean():>8.1f}"
                      f"{C.pt.mean():>8.1f} | {d:>7.1f}   [{lo:>6.1f},{hi:>6.1f}]{v:>12}")
    print(f"\n  costs {FRIC}pt per flip · a bar that touches BOTH cut and target is scored as the CUT")


if __name__ == "__main__":
    raise SystemExit(main())
