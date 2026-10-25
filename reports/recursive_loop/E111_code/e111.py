"""E111 analysis (spec reports/recursive_loop/E111_change.txt). Six declared pause rules, three controls, the desk path,
the declared sensitivities and the per-rule verdict. Read-only.

    nice -n 19 .venv/bin/python reports/recursive_loop/E111_code/e111.py > reports/recursive_loop/E111_result.txt
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

GB = "/home/alphabot/gazbot7"
PERIODS = ("TRAIN", "TEST", "FORWARD")
NDRAW = 1000
RULES = {
    "Q1 since_ext>=60":               (lambda d: d.since_ext_min >= 60, "since_ext_min"),
    "Q2 since_ext>=120":              (lambda d: d.since_ext_min >= 120, "since_ext_min"),
    "Q3 pullback>=6ATR":              (lambda d: d.pullback_atr >= 6, "pullback_atr"),
    "Q4 pullback>=8ATR":              (lambda d: d.pullback_atr >= 8, "pullback_atr"),
    "Q5 since>=60 & pull>=4":         (lambda d: (d.since_ext_min >= 60) & (d.pullback_atr >= 4), "since_ext_min"),
    "Q6 retest>=2 & since>=30":       (lambda d: (d.retest_gap_atr >= 2) & (d.since_ext_min >= 30), "since_ext_min"),
}
LOCK = 1000.0


def load(delay=False) -> pd.DataFrame:
    con = duckdb.connect()
    df = con.execute(f"""SELECT c.*, f.since_ext_min, f.pullback_atr, f.retest_gap_atr, f.new_ext_rate, f.hit37_delay_min, f.usd_allout_delay
        FROM read_parquet('{GB}/data/research/E110_census.parquet') c
        JOIN read_parquet('{GB}/data/research/E111_features.parquet') f USING (inst, slot_ts)""").df()
    if delay:
        df = df[df.usd_allout_delay.notna()].copy()
        df["usd_allout"], df["hit37_min"] = df.usd_allout_delay, df.hit37_delay_min
    df["D1"], df["D2"], df["D4"] = df.usd_allout <= -1000, df.usd_allout <= -2000, df.usd_allout <= -4000
    df["win"] = df.hit37_min.notna()
    return df.sort_values(["sess", "slot_ts"]).reset_index(drop=True)


def pct(x):
    return f"{x*100:5.1f}%" if np.isfinite(x) else "   - "


# ── matched-share pauses (per day) ───────────────────────────────────────────────────────────────────
def day_starts(s: pd.DataFrame):
    sess = s.sess.to_numpy()
    st = np.flatnonzero(np.r_[True, sess[1:] != sess[:-1]])
    return sess, st, np.r_[st[1:], len(sess)]


def matched(s, n_per_day, key, lowest=True):
    """pause n_per_day[i] rows of day i with the lowest (or highest) key; returns a bool mask"""
    sess, st, en = day_starts(s)
    kv = np.nan_to_num(key.astype(float), nan=np.inf if lowest else -np.inf)
    out = np.zeros(len(s), bool)
    for i, (a, b) in enumerate(zip(st, en)):
        n = n_per_day[i]
        if n:
            o = np.argsort(kv[a:b] if lowest else -kv[a:b], kind="stable")[:n]
            out[a + o] = True
    return out


def per_day_counts(s, m):
    sess, st, en = day_starts(s)
    cm = np.r_[0, np.cumsum(m)]
    return cm[en] - cm[st]


def caught_minus_paused(s, m):
    nd2 = s.D2.sum()
    return (s.D2.to_numpy()[m].sum() / nd2 if nd2 else np.nan) - m.mean()


def random_best_of(s, masks, rng):
    """1,000 draws: for each, the random analogue of every rule (same per-day counts), best caught-paused over the 6."""
    sess, st, en = day_starts(s)
    counts = [per_day_counts(s, m) for m in masks]
    d2 = s.D2.to_numpy(); nd2 = d2.sum()
    best = np.empty(NDRAW); each = np.empty((NDRAW, len(masks)))
    day_of = np.repeat(np.arange(len(st)), en - st)
    for k in range(NDRAW):
        u = rng.random(len(s))
        order = np.lexsort((u, day_of))
        rank = np.empty(len(s), np.int64); rank[order] = np.arange(len(s)) - np.repeat(st, en - st)
        for r, cnt in enumerate(counts):
            m = rank < np.repeat(cnt, en - st)
            each[k, r] = d2[m].sum() / nd2 - m.mean()
        best[k] = each[k].max()
    return best, each


def boot_kept_minus_all(s, m, reps=1000, rng=None):
    g = pd.DataFrame({"sess": s.sess.to_numpy(), "d2": s.D2.to_numpy(), "k": ~m})
    g["d2k"] = g.d2 & g.k
    a = g.groupby("sess").agg(n=("d2", "size"), d2=("d2", "sum"), nk=("k", "sum"), d2k=("d2k", "sum")).to_numpy()
    idx = rng.integers(0, len(a), size=(reps, len(a)))
    S = a[idx].sum(1)
    diff = S[:, 3] / np.maximum(S[:, 2], 1) - S[:, 1] / S[:, 0]
    return np.percentile(diff, [5, 95]) * 100


# ── desk path ────────────────────────────────────────────────────────────────────────────────────────
def desk(s: pd.DataFrame, paused: np.ndarray, all_days: np.ndarray):
    sess, st, en = day_starts(s)
    slot, hit, usd = s.slot_ts.to_numpy(), s.hit37_min.to_numpy(), s.usd_allout.to_numpy()
    pnl = {}; ntr = 0
    for a, b in zip(st, en):
        free, real, n = 0, 0.0, 0
        for i in range(a, b):
            if slot[i] < free or paused[i]:
                continue
            if real >= LOCK:
                break
            n += 1; real += usd[i]
            if np.isfinite(hit[i]):
                free = slot[i] + hit[i] * 60
            else:
                break
        if n:
            pnl[sess[a]] = real; ntr += n
    daily = np.array([pnl.get(d, 0.0) for d in all_days])
    traded = np.array(list(pnl.values()))
    cum = np.cumsum(daily); dd = (np.maximum.accumulate(cum) - cum).max() if len(cum) else 0
    sd = daily.std()
    return {"trades/day": ntr / len(all_days), "days traded": len(traded), "days+ %": (traded > 0).mean() * 100 if len(traded) else np.nan,
            "worst day": traded.min() if len(traded) else np.nan, "p5 day": np.percentile(daily, 5), "$/day": daily.mean(), "SD": sd,
            "CV": sd / abs(daily.mean()) if daily.mean() else np.inf, "maxDD": dd, "days<=-2k": int((daily <= -2000).sum()),
            "days<=-4k": int((daily <= -4000).sum())}


def desk_line(name, r):
    return (f"   {name:28}{r['trades/day']:>7.2f}{r['days traded']:>7}{r['days+ %']:>7.1f}{r['worst day']:>9.0f}{r['p5 day']:>8.0f}{r['$/day']:>8.1f}"
            f"{r['SD']:>7.0f}{r['CV']:>7.1f}{r['maxDD']:>9.0f}{r['days<=-2k']:>7}{r['days<=-4k']:>7}")


DESK_HDR = f"   {'':28}{'tr/day':>7}{'days':>7}{'days+%':>7}{'worst':>9}{'p5 day':>8}{'$/day':>8}{'SD':>7}{'CV':>7}{'maxDD':>9}{'<=-2k':>7}{'<=-4k':>7}"


def run(df: pd.DataFrame, title: str, rng, controls=True, verdict=None):
    print(f"\n{'='*150}\n{title}\n{'='*150}")
    res = {}
    for p in PERIODS:
        s = df[(df.period == p) & df.in_live_window].reset_index(drop=True)
        if not len(s):
            continue
        all_days = np.unique(s.sess.to_numpy())
        masks = {n: f(s).to_numpy() for n, (f, _) in RULES.items()}
        print(f"\n[{p}] live-window candidates {len(s):,} on {len(all_days)} days; D2 {s.D2.sum():,} ({pct(s.D2.mean())}), D4 {s.D4.sum():,} ({pct(s.D4.mean())}), wins {pct(s.win.mean())}")
        print(f"   {'rule':28}{'paused':>8}{'D2 caught':>10}{'D4 caught':>10}{'select':>7}{'D2 paused':>10}{'D2 kept':>9}{'wins paused':>12}"
              f"{'$ forgone':>12}{'$ avoided':>12}{'kept-all D2 90%CI':>20}{'n D2 paused':>12}")
        for n, m in masks.items():
            q, k = s[m], s[~m]
            sel = (q.D2.sum() / max(s.D2.sum(), 1)) / m.mean() if m.mean() else np.nan
            lo, hi = boot_kept_minus_all(s, m, rng=rng)
            res[(p, n)] = {"sel": sel, "ci": (lo, hi), "cmp": caught_minus_paused(s, m), "nd2p": int(q.D2.sum())}
            print(f"   {n:28}{pct(m.mean()):>8}{pct(q.D2.sum()/max(s.D2.sum(),1)):>10}{pct(q.D4.sum()/max(s.D4.sum(),1)):>10}{sel:>7.2f}"
                  f"{pct(q.D2.mean()):>10}{pct(k.D2.mean()):>9}{pct(q.win.sum()/max(s.win.sum(),1)):>12}"
                  f"{q.loc[q.usd_allout>0,'usd_allout'].sum():>12,.0f}{-q.loc[q.usd_allout<0,'usd_allout'].sum():>12,.0f}"
                  f"{f'{lo:+.2f}..{hi:+.2f}pp':>20}{int(q.D2.sum()):>12}")
        if controls:
            best, each = random_best_of(s, list(masks.values()), rng)
            b95 = np.percentile(best, 95)
            print(f"\n   CONTROLS - caught minus paused (pp of D2 share); RANDOM best-of-6 95th pct = {b95*100:+.2f}pp")
            print(f"   {'rule':28}{'rule':>9}{'RANDOM own 95%':>16}{'FLIP':>9}{'TIME':>9}{'beats all?':>12}")
            for r, (n, m) in enumerate(masks.items()):
                cnt = per_day_counts(s, m)
                key = s[RULES[n][1]].to_numpy()
                flip = matched(s, cnt, key, lowest=True)
                tim = matched(s, cnt, s.slot_ts.to_numpy(), lowest=False)
                cr, cf, ct = caught_minus_paused(s, m), caught_minus_paused(s, flip), caught_minus_paused(s, tim)
                ok = cr > b95 and cr > cf and cr > ct
                res[(p, n)].update({"beats": ok})
                print(f"   {n:28}{cr*100:>+8.2f}p{np.percentile(each[:, r], 95)*100:>+15.2f}p{cf*100:>+8.2f}p{ct*100:>+8.2f}p{('YES' if ok else 'no'):>12}")
        print(f"\n   DESK PATH (detector-only: flat-only, all-out +37.5 or 20:40Z flat, re-entry after a hit, +$1,000 day lock)")
        print(DESK_HDR)
        base = desk(s, np.zeros(len(s), bool), all_days)
        print(desk_line("BASELINE (no pause)", base))
        for n, m in masks.items():
            r = desk(s, m, all_days)
            res[(p, n)].update({"desk": r, "base": base})
            print(desk_line(n, r))
    if verdict is not None:
        verdict(res)
    return res


def verdicts(res):
    print(f"\n{'='*150}\nVERDICT per rule (declared clauses; ranked shortlist, never a single verdict)\n{'='*150}")
    for n in RULES:
        tr, te, fw = res.get(("TRAIN", n)), res.get(("TEST", n)), res.get(("FORWARD", n))
        why = []
        carried = tr and tr.get("beats")
        if not carried:
            why.append("does not beat RANDOM/FLIP/TIME on TRAIN")
        test_ok = te and te["ci"][1] < 0 and te["sel"] > 1
        fwd_ok = fw and fw["sel"] > 1 and fw["cmp"] > 0
        desk_ok = all(x and x["desk"]["worst day"] >= x["base"]["worst day"] and x["desk"]["days+ %"] >= x["base"]["days+ %"] for x in (tr, te, fw))
        if not test_ok: why.append("TEST CI does not exclude 0 on the improving side or selectivity <= 1")
        if not fwd_ok: why.append("FORWARD sign does not agree")
        if not desk_ok: why.append("desk path worsens worst day or days-positive on some period")
        if carried and test_ok and fwd_ok and desk_ok and min(x["nd2p"] for x in (tr, te, fw)) >= 30:
            v = "PROMISING"
        elif not carried:
            v = "REFUTED (a control beats it)"
        elif te["sel"] < 1 or fw["sel"] < 1:
            v = "REFUTED (wrong side out of TRAIN)"
        else:
            v = "PARK"
        print(f"   {n:28} {v:28} selectivity TRAIN/TEST/FWD {tr['sel']:.2f}/{te['sel']:.2f}/{fw['sel']:.2f}   " + ("; ".join(why) if why else "all clauses met"))


def main():
    rng = np.random.default_rng(111)
    print("E111 - 'THE TURN IS ALREADY IN' (spec reports/recursive_loop/E111_change.txt). Read-only; nothing trades.")
    print("Candidates = the E110 census live window (02:00-13:30Z after the 05:00 Paris veto); exit all-out +37.5 today's pts or 20:40Z flat; no stop.")
    print("select = (share of D2 caught) / (share paused): 1.00 is what a coin does. 'kept-all' = D2 rate of the kept entries minus all, day-cluster bootstrap.")
    df = load()
    print("\nFEATURE BANDS FIRST (counts before rules) - D2 rate by band, LIVE WINDOW")
    bands = {"since_ext_min": [0, 15, 30, 60, 120, 240, np.inf], "pullback_atr": [0, 2, 4, 6, 8, 11, np.inf],
             "retest_gap_atr": [-np.inf, .5, 2, 4, np.inf], "new_ext_rate": [-.01, 0.001, .25, .5, 1.01]}
    for col, ed in bands.items():
        print(f"\n  {col}")
        for p in PERIODS:
            s = df[(df.period == p) & df.in_live_window]
            b = pd.cut(s[col], ed, right=False)
            t = s.groupby(b, observed=True).agg(n=("D2", "size"), d2=("D2", "mean"), d4=("D4", "mean"), win=("win", "mean"), usd=("usd_allout", "mean"), days=("sess", "nunique"))
            print(f"   [{p}] overall D2 {pct(s.D2.mean())}  " + " | ".join(f"{str(i)}: n{r.n:,} D2 {r.d2*100:.1f}% D4 {r.d4*100:.1f}% ${r.usd:.0f}" for i, r in t.iterrows()))
    run(df, "MAIN - declared entry (close of the last closed bar)", rng, controls=True, verdict=verdicts)
    run(load(delay=True), "SENSITIVITY (a) - ENTRY DELAYED ONE MINUTE (live fills land a median 32 s after the decision)", rng, controls=False, verdict=None)
    d = df[~df.roll_adj]
    run(d, "SENSITIVITY (b) - without roll-adjacent sessions", rng, controls=False)
    for nm, m in (("EDT", df.edt), ("EST", ~df.edt), ("LONG", df.dir > 0), ("SHORT", df.dir < 0)):
        run(df[m], f"SENSITIVITY (c) - {nm} only", rng, controls=False)


if __name__ == "__main__":
    main()
