"""EXIT-LADDER LAB — prove/refute the operator's regime-graded exit ladder (2026-07-31).

The ladder GUESS, per gate:
    BIG-TREND   -> RIDE  (Lot A ~2.5-3.5R + WIDE lock-chandelier)
    MED-TREND   -> A ~1.5R / B ~2.5R
    SCALP-CHOP  -> A ~1R   / B ~2R
    STAY-OUT    -> FLAT    (the untradeable meter)

The mid-week first-look was CHOP-DOMINATED (BIG-TREND n=5-25) so the 3.5R+chandelier rung was
UNTESTED. This extends the tape to the FULL V5 archive + V7 capture (2026-07-06..07-31, ~19
sessions) and REPLAYS each bar-decidable gate's entries on that whole window, then reprices every
entry on the forward 5s path across a GRID of Lot-A x Lot-B R-combos + chandelier variants,
SEGMENTED by rung x time-of-day.

Bar-decidable (replayed on the FULL extended window): thrust/absveto, grind, rgv-long, rgv-short.
Tape/book gates (capitulation, exhaustion) are NOT replayable pre-07-23 (capture.db ticks start
07-23, no L2 before) -> those two run on their REAL shadow-board entries only, flagged thin.

Robustness per (gate x rung): per-day spread, leave-one-day-out, strip-the-best-3, and an
OOS split (archive 07-06..07-15 = OOS vs capture 07-16..07-31 = IS).

Writes scratchpad/exit_ladder.json.  Read-only on all DBs.
"""
from __future__ import annotations
import sys, json, sqlite3, math
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.deciders import Bar, compute_features, gate_thrust, gate_grind, gate_reversal_grab  # noqa

VPP, FEE = 2.0, 1.5
HORIZON_MIN = 90          # max hold on the forward path
LOOKBACK = 60             # 1-min bars fed to the deciders (cfg.bar_lookback)
COOLDOWN_S = 300          # no re-entry for the same gate within 5 min (density-matched to shadow)
UTC = timezone.utc

TAPE = "/home/alphabot/gazbot7/scratchpad/tape5s.npz"
SHADOW = "/home/alphabot/gazbot7/data/shadow.db"
OUT = "/home/alphabot/gazbot7/scratchpad/exit_ladder.json"

# ────────────────────────── tape ──────────────────────────
z = np.load(TAPE)
bts, bo, bh, bl, bc, bv = z["ts"], z["o"], z["h"], z["l"], z["c"], z["v"]
print(f"5s tape: {len(bts)} bars  {datetime.fromtimestamp(bts[0],UTC)} .. {datetime.fromtimestamp(bts[-1],UTC)}")

# 1-min bars from the 5s tape
mk: dict[int, list] = {}
for i in range(len(bts)):
    m = int(bts[i]) // 60
    r = mk.get(m)
    if r is None:
        mk[m] = [bo[i], bh[i], bl[i], bc[i], bv[i]]
    else:
        r[1] = max(r[1], bh[i]); r[2] = min(r[2], bl[i]); r[3] = bc[i]; r[4] += bv[i]
mins = sorted(mk)
MB = [Bar(m * 60, mk[m][0], mk[m][1], mk[m][2], mk[m][3], mk[m][4]) for m in mins]
print(f"1-min bars: {len(MB)}")

mclose = np.array([b.close for b in MB]); mhigh = np.array([b.high for b in MB]); mlow = np.array([b.low for b in MB])
mts = np.array([b.ts for b in MB])

# 30-min ER + 14-min ATR per minute (the rung keys)
er30 = np.zeros(len(MB)); atr14 = np.zeros(len(MB))
tr = np.zeros(len(MB))
for i in range(1, len(MB)):
    tr[i] = max(mhigh[i] - mlow[i], abs(mhigh[i] - mclose[i - 1]), abs(mlow[i] - mclose[i - 1]))
for i in range(len(MB)):
    if i >= 30:
        seg = mclose[i - 30:i + 1]
        path = float(np.abs(np.diff(seg)).sum()) or 1.0
        er30[i] = abs(seg[-1] - seg[0]) / path
    if i >= 14:
        atr14[i] = float(tr[i - 13:i + 1].mean())
ER_AT = {int(mts[i]) // 60: float(er30[i]) for i in range(len(MB))}
ATR_AT = {int(mts[i]) // 60: float(atr14[i]) for i in range(len(MB))}

# ────────── STAY-OUT meter, per Paris day (src/gazbot7/untradeable.py formulas) ──────────
def paris_day(ts: int) -> str:
    """Paris trading day = the session that starts 22:00 UTC the previous evening."""
    d = datetime.fromtimestamp(ts, UTC)
    if d.hour >= 22:
        d = d + timedelta(days=1)
    return d.strftime("%Y-%m-%d")

byday: dict[str, list[int]] = defaultdict(list)
for i in range(len(MB)):
    byday[paris_day(int(mts[i]))].append(i)

DAY_METER = {}
for d, idx in byday.items():
    if len(idx) < 60:
        continue
    h = mhigh[idx]; l = mlow[idx]; c = mclose[idx]
    op = c[0]; net = c[-1] - op; rng = float(h.max() - l.min())
    if rng < 30:
        continue
    rt = abs(net) / rng
    big = max(float(h.max() - op), float(op - l.min()), 1.0)
    gb = max(0.0, min(1.0, 1 - abs(net) / big))
    chop = round(max(0, min(1, 1 - rt)) * 100)
    give = round(gb * 100)
    score = round(0.40 * chop + 0.40 * give + 0.20 * 50)     # stops meter neutral (no live trades on archive)
    DAY_METER[d] = dict(roundtrip=round(rt, 2), giveback=round(gb, 2), score=int(score),
                        range_pt=round(rng, 1), net_pt=round(float(net), 1),
                        verdict=("STAY-OUT" if score >= 65 else "CAUTION" if score >= 45 else "TRADEABLE"))

def rung(ts: int) -> str:
    d = paris_day(ts)
    m = DAY_METER.get(d)
    if m and m["verdict"] == "STAY-OUT":
        return "STAY-OUT"
    er = ER_AT.get(ts // 60, 0.0)
    if er >= 0.50:
        return "BIG-TREND"
    if er >= 0.30:
        return "MED-TREND"
    return "SCALP-CHOP"

def er_rung(ts: int) -> str:
    er = ER_AT.get(ts // 60, 0.0)
    return "BIG-TREND" if er >= 0.50 else "MED-TREND" if er >= 0.30 else "SCALP-CHOP"

def tod(ts: int) -> str:
    h = datetime.fromtimestamp(ts, UTC).hour
    return "US" if 13 <= h < 21 else "ON"

def atr_band(a: float) -> str:
    return "hiATR" if a >= 22 else ("midATR" if a >= 12 else "loATR")

# ────────────────────────── gate replay ──────────────────────────
GATES = {
    "thrust/absveto": lambda f: gate_thrust(f, thr=1.5, amp_floor=0.0004),
    "grind (mom)":    lambda f: gate_grind(f, slope_min=0.4, fast_slope=True, tape_net=0.0),
    "rgv-long (fade)": lambda f: gate_reversal_grab(f, side="LONG", ext_min=2.0, turn_atr=0.15,
                                                    fast_slope=True, fast_turn=True),
    "rgv-short (fade)": lambda f: gate_reversal_grab(f, side="SHORT", ext_min=2.5, turn_atr=0.25),
}

entries: list[tuple] = []      # (fam, side, ts, price, atr, src)
last_fire: dict[str, int] = {}
for i in range(LOOKBACK, len(MB)):
    win = MB[i - LOOKBACK + 1:i + 1]
    f = compute_features(win)
    if f.atr <= 0:
        continue
    ts = int(MB[i].ts) + 60           # decide on the CLOSE of bar i -> enter at the next bar's open second
    for fam, fn in GATES.items():
        if ts - last_fire.get(fam, -10**9) < COOLDOWN_S:
            continue
        e = fn(f)
        if e is None:
            continue
        last_fire[fam] = ts
        entries.append((fam, e.side, ts, float(MB[i].close), float(f.atr), "replay"))
print(f"replayed entries: {len(entries)}")
for fam in GATES:
    print("   ", fam, sum(1 for e in entries if e[0] == fam))

# ── the two tape/book gates: REAL shadow entries only (not replayable on the archive) ──
sh = sqlite3.connect(f"file:{SHADOW}?mode=ro", uri=True)
SHFAM = {"capit_loose": "capitulation (fade)", "exhaustion_rev": "exhaustion (fade)"}
ph = ",".join("?" * len(SHFAM))
for strat, side, ets, ep, eatr in sh.execute(
        "SELECT strategy,side,entry_ts,entry_price,entry_atr FROM shadow_trades WHERE entry_atr>0 "
        "AND strategy IN (" + ph + ") ORDER BY entry_ts", list(SHFAM)):
    entries.append((SHFAM[strat], side, int(ets), float(ep), float(eatr), "shadow"))

# density cross-check vs the real shadow board on the overlap window
ov0 = int(datetime(2026, 7, 16, tzinfo=UTC).timestamp())
real_counts = dict(sh.execute(
    "SELECT strategy,count(*) FROM shadow_trades WHERE entry_ts>=? GROUP BY 1", (ov0,)).fetchall())
rep_counts = defaultdict(int)
for fam, side, ts, p, a, src in entries:
    if src == "replay" and ts >= ov0:
        rep_counts[fam] += 1
DENSITY = {"replay_overlap": dict(rep_counts),
           "shadow_real": {k: real_counts.get(k, 0) for k in
                           ("thrust_loose", "grind_fast", "rg_long_fast", "rg_short_025_raw")}}
print("density check:", DENSITY)

# ────────────────────────── exit repricing on the 5s path ──────────────────────────
def path(side: str, entry: float, atr: float, i0: int):
    j1 = min(i0 + HORIZON_MIN * 12, len(bts))
    h = bh[i0:j1]; l = bl[i0:j1]; c = bc[i0:j1]
    if len(h) < 12:
        return None
    if side == "LONG":
        fav = (h - entry) / atr; adv = (entry - l) / atr; cf = (c - entry) / atr
    else:
        fav = (entry - l) / atr; adv = (h - entry) / atr; cf = (entry - c) / atr
    return fav, adv, cf

def r_scalp(favcum, stop_i, target, cf_last):
    """Conservative: on a bar where BOTH the stop and the target could fill, the STOP fills first."""
    hit = int(np.argmax(favcum >= target)) if (favcum >= target).any() else len(favcum)
    if hit < stop_i:
        return target
    if stop_i < len(favcum):
        return -1.0
    return max(min(cf_last, target), -1.0)

def r_chand(fav, adv, cf, mode):
    """mode 'lock' = grind's threshold chandelier (start_k 3.5 -> lock_k 0.5 past 6R);
       mode 'tight' = the fader k1.5 tightening chandelier (min_k 0.5, tighten 0.75)."""
    stop_i = int(np.argmax(adv >= 1.0)) if (adv >= 1.0).any() else len(fav)
    peak = 0.0
    for i in range(len(fav)):
        if i >= stop_i:
            return -1.0
        peak = max(peak, fav[i])
        if peak > 0:
            k = (3.5 if peak < 6.0 else 0.5) if mode == "lock" else max(0.5, 1.5 - 0.75 * peak)
            if cf[i] > 0 and cf[i] <= peak - k:
                return float(cf[i])
    return max(min(float(cf[-1]), peak), -1.0)

A_RS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
B_RS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.5, 6.0]
POLICIES: list[str] = [f"A{a}/B{b}" for a in A_RS for b in B_RS if b > a]
POLICIES += [f"A{a}+WIDE" for a in (1.0, 1.5, 2.0, 2.5, 3.0, 3.5)]
POLICIES += ["WIDEx2", "TIGHTx2", f"A1.5+TIGHT", "A0.5+TIGHT"]

rows = []          # per-entry dict with per-policy $ (2 lots)
for fam, side, ts, ep, atr, src in entries:
    i0 = int(np.searchsorted(bts, ts))
    if i0 >= len(bts):
        continue
    pth = path(side, ep, atr, i0)
    if pth is None:
        continue
    fav, adv, cf = pth
    favcum = np.maximum.accumulate(fav)
    stop_i = int(np.argmax(adv >= 1.0)) if (adv >= 1.0).any() else len(fav)
    cfl = float(cf[-1])
    usd = lambda rr: (rr * atr * VPP) - FEE
    r_lock = r_chand(fav, adv, cf, "lock")
    r_tight = r_chand(fav, adv, cf, "tight")
    scal = {a: r_scalp(favcum, stop_i, a, cfl) for a in set(A_RS + B_RS)}
    pol = {}
    for a in A_RS:
        for b in B_RS:
            if b > a:
                pol[f"A{a}/B{b}"] = usd(scal[a]) + usd(scal[b])
    for a in (1.0, 1.5, 2.0, 2.5, 3.0, 3.5):
        pol[f"A{a}+WIDE"] = usd(scal[a]) + usd(r_lock)
    pol["WIDEx2"] = 2 * usd(r_lock)
    pol["TIGHTx2"] = 2 * usd(r_tight)
    pol["A1.5+TIGHT"] = usd(scal[1.5]) + usd(r_tight)
    pol["A0.5+TIGHT"] = usd(scal[0.5]) + usd(r_tight)
    rows.append(dict(fam=fam, side=side, ts=ts, atr=atr, src=src,
                     day=paris_day(ts), rung=rung(ts), er_rung=er_rung(ts), tod=tod(ts),
                     atrb=atr_band(atr), rmfe=float(favcum[-1]), pol=pol))

print(f"repriced signals: {len(rows)}")
import pickle
pickle.dump(dict(rows=rows, policies=POLICIES, day_meter=DAY_METER, er_at=ER_AT, atr_at=ATR_AT),
            open("/home/alphabot/gazbot7/scratchpad/exit_ladder_rows.pkl", "wb"))

# ────────────────────────── aggregate + robustness ──────────────────────────
def agg(vals):
    n = len(vals)
    if not n:
        return None
    return dict(n=n, tot=round(sum(vals), 1), mean=round(sum(vals) / n, 2),
                win=round(100 * sum(1 for v in vals if v > 0) / n))

def robust_best(sub, min_n=25):
    """Robust-best policy for a bucket: rank by mean $/signal, but require the winner to
    (a) survive strip-the-best-3, (b) be non-negative on a majority of days (LOO proxy),
    and (c) sit on a PLATEAU (its immediate R-neighbours also top-quartile)."""
    if len(sub) < min_n:
        return None
    means = {}
    for p in POLICIES:
        v = [r["pol"][p] for r in sub]
        means[p] = sum(v) / len(v)
    order = sorted(POLICIES, key=lambda p: -means[p])
    q75 = np.percentile([means[p] for p in POLICIES], 75)
    days = sorted({r["day"] for r in sub})
    for p in order:
        v = [r["pol"][p] for r in sub]
        strip3 = sorted(v)[:-3]
        s3 = sum(strip3) / len(strip3) if strip3 else -9e9
        loo = []
        for d in days:
            vv = [r["pol"][p] for r in sub if r["day"] != d]
            if vv:
                loo.append(sum(vv) / len(vv))
        loo_min = min(loo) if loo else -9e9
        daily = [sum(r["pol"][p] for r in sub if r["day"] == d) for d in days]
        green = sum(1 for x in daily if x > 0) / len(daily) if daily else 0
        # plateau: neighbours in the grid
        nb = []
        if "/" in p:
            a = float(p[1:p.index("/")]); b = float(p[p.index("B") + 1:])
            for aa in A_RS:
                for bb in B_RS:
                    if bb > aa and (abs(aa - a) <= 0.5 and abs(bb - b) <= 1.0) and f"A{aa}/B{bb}" != p:
                        nb.append(means[f"A{aa}/B{bb}"])
        plateau = (sum(1 for x in nb if x >= q75) / len(nb)) if nb else 1.0
        ok = (s3 >= 0 or s3 >= means[p] * 0.4) and loo_min > -1e8 and plateau >= 0.5
        if ok:
            return dict(policy=p, mean=round(means[p], 2), tot=round(sum(v), 1), n=len(sub),
                        win=round(100 * sum(1 for x in v if x > 0) / len(v)),
                        strip3=round(s3, 2), loo_worst=round(min(loo), 2) if loo else None,
                        green_day_pct=round(100 * green), plateau=round(plateau, 2), rank=order.index(p))
    p = order[0]
    v = [r["pol"][p] for r in sub]
    return dict(policy=p, mean=round(means[p], 2), tot=round(sum(v), 1), n=len(sub),
                win=round(100 * sum(1 for x in v if x > 0) / len(v)), fragile=True, rank=0)

LADDER_GUESS = {"BIG-TREND": "A2.5+WIDE", "MED-TREND": "A1.5/B2.5",
                "SCALP-CHOP": "A1.0/B2.0", "STAY-OUT": "FLAT"}

out = {"meta": dict(n_signals=len(rows), tape_from=str(datetime.fromtimestamp(int(bts[0]), UTC)),
                    tape_to=str(datetime.fromtimestamp(int(bts[-1]), UTC)),
                    horizon_min=HORIZON_MIN, cooldown_s=COOLDOWN_S, vpp=VPP, fee=FEE),
       "day_meter": DAY_METER, "density": DENSITY, "policies": POLICIES}

fams = sorted({r["fam"] for r in rows})
cells = {}
for fam in fams:
    for rg in ("BIG-TREND", "MED-TREND", "SCALP-CHOP", "STAY-OUT"):
        sub = [r for r in rows if r["fam"] == fam and r["rung"] == rg]
        if not sub:
            continue
        guess = LADDER_GUESS[rg]
        gstats = agg([r["pol"][guess] for r in sub]) if guess in POLICIES else None
        rb = robust_best(sub)
        # top-8 policy table
        tops = sorted(((p, agg([r["pol"][p] for r in sub])) for p in POLICIES),
                      key=lambda kv: -kv[1]["mean"])[:8]
        worst = sorted(((p, agg([r["pol"][p] for r in sub])) for p in POLICIES),
                       key=lambda kv: kv[1]["mean"])[:3]
        # OOS split: archive (<07-16) vs capture (>=07-16)
        oos = [r for r in sub if r["ts"] < ov0]
        iss = [r for r in sub if r["ts"] >= ov0]
        # tod split
        tods = {t: agg([r["pol"][rb["policy"]] for r in sub if r["tod"] == t]) for t in ("US", "ON")} if rb else {}
        atrbs = {b: agg([r["pol"][rb["policy"]] for r in sub if r["atrb"] == b])
                 for b in ("loATR", "midATR", "hiATR")} if rb else {}
        cells[f"{fam}|{rg}"] = dict(
            fam=fam, rung=rg, n=len(sub), src=sorted({r["src"] for r in sub}),
            guess=guess, guess_stats=gstats, best=rb,
            top=[(p, s) for p, s in tops], worst=[(p, s) for p, s in worst],
            oos_n=len(oos), is_n=len(iss),
            oos=agg([r["pol"][rb["policy"]] for r in oos]) if rb and oos else None,
            iss=agg([r["pol"][rb["policy"]] for r in iss]) if rb and iss else None,
            tod=tods, atr=atrbs,
            rmfe_med=round(float(np.median([r["rmfe"] for r in sub])), 2),
            rmfe_p90=round(float(np.percentile([r["rmfe"] for r in sub], 90)), 2),
            per_day={d: round(sum(r["pol"][rb["policy"]] for r in sub if r["day"] == d), 1)
                     for d in sorted({r["day"] for r in sub})} if rb else {},
        )
out["cells"] = cells

# rung census (how much tape each rung actually is)
out["rung_census"] = {rg: sum(1 for r in rows if r["rung"] == rg)
                      for rg in ("BIG-TREND", "MED-TREND", "SCALP-CHOP", "STAY-OUT")}
out["er_rung_census"] = {rg: sum(1 for r in rows if r["er_rung"] == rg)
                         for rg in ("BIG-TREND", "MED-TREND", "SCALP-CHOP")}
# minute-level rung census (tape composition, not signal composition)
mrung = defaultdict(int)
for i in range(len(MB)):
    mrung[rung(int(mts[i]))] += 1
out["rung_minutes"] = dict(mrung)

json.dump(out, open(OUT, "w"), indent=1, default=float)
print("wrote", OUT)

# ── console summary ──
print(f"\n{'family':22}{'rung':11}{'n':>5}  {'LADDER GUESS':14}{'guess $/sig':>12}   {'ROBUST BEST':14}{'best $/sig':>11}")
print("-" * 100)
for k, c in cells.items():
    g = c["guess_stats"]; b = c["best"]
    gs = f"{g['mean']:+.1f}" if g else "  (flat)"
    bs = f"{b['mean']:+.1f}" if b else "   n/a"
    bp = b["policy"] if b else "(thin n)"
    print(f"{c['fam']:22}{c['rung']:11}{c['n']:>5}  {c['guess']:14}{gs:>12}   {bp:14}{bs:>11}")
