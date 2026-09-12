"""CHOP-SCALP step 3 — the TURN EVENT table (one expensive pass, many cheap sweeps).

For every 5s bar on every full-stack day, decides whether price is AT a trailing L-minute
extreme (a turn CANDIDATE), and if so records ~40 backward-looking features:

  regime   atr14 / atr_rel / er15 / er30 / er60 / vwap slope / ext_atr / range position
  tape     20s+60s signed aggressor net, volume, tick count, price move  (the footprint terms)
  book     depth.db-lineage 10-deep resting sizes at the last <=t snapshot, and their 20s trend
  L1       41ms event stream: best-quote size means/slopes, depletion and REFILL counts

plus the forward race: for a grid of target/stop pairs, which side is touched FIRST on the
real tick tape, with the entry filled at the next tick 1 tick adverse.

Nothing is filtered here except the extreme test and a 60s per-side cooldown — every
threshold in the report is applied downstream so the sweep is honest about its own grid.

⚠ FEE IS $1.50 PER ROUND TRIP. MNQ IS $2.00/POINT. Both live in cs2_common.py, nowhere else.
"""
import glob, os, sys
import duckdb, numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/reports/friday_v7/sections/cs2"
SYM = "MNQ"
TICK = 0.25
EXT_MIN = [10, 15, 20, 30]          # trailing-extreme lookbacks recorded (minutes)
COOLDOWN_S = 60

def day_files(day):
    return {s: f"{GB}/data/tape/{s}/{SYM}/{day}.parquet" for s in ("ticks", "bars", "depth", "book")}

def full_stack_days():
    have = {s: {os.path.basename(f)[:-8] for f in glob.glob(f"{GB}/data/tape/{s}/{SYM}/2026-*.parquet")}
            for s in ("ticks", "bars", "depth", "book")}
    return sorted(have["ticks"] & have["bars"] & have["depth"] & have["book"])

# ---------------------------------------------------------------- per-day feature build
def build_day(day, con):
    f = day_files(day)
    b5 = con.execute(f"""SELECT bar_ts ts, open,high,low,close,volume FROM read_parquet('{f['bars']}')
                         WHERE symbol='{SYM}' AND timeframe='5s' ORDER BY bar_ts""").df()
    if len(b5) < 500:
        return None
    # ---- 1-min regime frame (lagged: only COMPLETED minutes are visible to a decision)
    b5["m"] = (b5.ts // 60) * 60
    m1 = b5.groupby("m").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                             close=("close", "last"), volume=("volume", "sum")).reset_index()
    pc = m1.close.shift(1)
    tr = np.maximum(m1.high - m1.low, np.maximum((m1.high - pc).abs(), (m1.low - pc).abs()))
    m1["atr14"] = tr.rolling(14).mean()
    for w in (15, 30, 60):
        net = (m1.close - m1.close.shift(w)).abs()
        path = m1.close.diff().abs().rolling(w).sum()
        m1[f"er{w}"] = np.where(path > 0, net / path, np.nan)
    tp = (m1.high + m1.low + m1.close) / 3
    m1["vwap"] = (tp * m1.volume).cumsum() / m1.volume.cumsum()
    m1["vwap_slope15"] = m1.vwap - m1.vwap.shift(15)
    m1["hi60"] = m1.high.rolling(60, min_periods=20).max()
    m1["lo60"] = m1.low.rolling(60, min_periods=20).min()
    m1["mrng"] = m1.atr14                                  # alias kept for readability
    keep = ["m", "atr14", "er15", "er30", "er60", "vwap", "vwap_slope15", "hi60", "lo60"]
    m1s = m1[keep].copy()
    m1s["m"] = m1s.m + 60                                   # visible only from the NEXT minute
    b5 = b5.merge(m1s, on="m", how="left").ffill()

    # ---- trailing extremes on the 5s grid (shifted by one bar: the decision is at bar CLOSE)
    for L in EXT_MIN:
        n = L * 12
        b5[f"hi{L}"] = b5.high.rolling(n, min_periods=n // 2).max()
        b5[f"lo{L}"] = b5.low.rolling(n, min_periods=n // 2).min()
    b5 = b5.dropna(subset=["atr14", "er30", "hi30", "lo30"]).reset_index(drop=True)
    if len(b5) < 200:
        return None

    # ---- candidate mask: this bar's high IS the trailing L-extreme (L = the SHORTEST, 10m)
    px = b5.close.values
    ev = []
    for side, col, cmpv in (("SHORT", "hi10", b5.high.values), ("LONG", "lo10", b5.low.values)):
        ref = b5[col].values
        hit = (cmpv >= ref - 1e-9) if side == "SHORT" else (cmpv <= ref + 1e-9)
        idx = np.flatnonzero(hit)
        last = -10**9
        for i in idx:
            t = b5.ts.values[i]
            if t - last < COOLDOWN_S:
                continue
            last = t
            ev.append((int(t), side, int(i)))
    if not ev:
        return None
    ev.sort()
    E = pd.DataFrame(ev, columns=["ts", "side", "i"])
    # ⚠ `bar_ts` is the bar's START. The extreme that defines the event is only KNOWN at the bar's
    # CLOSE, so every feature cutoff and the race entry must use ts+5. Using ts entered the trade
    # BEFORE the high/low it was reacting to and produced a 0.19 target rate on both sides — an
    # anti-look-ahead that guarantees the stop.
    E["dts"] = E.ts + 5
    for c in ["close", "high", "low", "atr14", "er15", "er30", "er60", "vwap", "vwap_slope15",
              "hi60", "lo60", "hi10", "lo10", "hi15", "lo15", "hi20", "lo20", "hi30", "lo30"]:
        E[c] = b5[c].values[E.i.values]
    E["date"] = day
    return E, b5

# ---------------------------------------------------------------- tape / footprint features
def tape_feats(E, con, f):
    t = con.execute(f"""SELECT ts_ms, price, size, aggressor FROM read_parquet('{f['ticks']}')
                        WHERE symbol='{SYM}' ORDER BY ts_ms""").df()
    ts = t.ts_ms.values; pr = t.price.values; sz = t["size"].values
    sgn = np.where(t.aggressor.values == "buy", 1.0, np.where(t.aggressor.values == "sell", -1.0, 0.0))
    csz = np.concatenate([[0.0], np.cumsum(sz)])
    cnet = np.concatenate([[0.0], np.cumsum(sz * sgn)])
    cn = np.arange(len(ts) + 1, dtype=float)
    end = np.searchsorted(ts, E.dts.values * 1000, side="left")         # ticks strictly BEFORE the close
    out = {}
    for W in (20, 60):
        beg = np.searchsorted(ts, (E.dts.values - W) * 1000, side="left")
        out[f"vol{W}"] = csz[end] - csz[beg]
        out[f"net{W}"] = cnet[end] - cnet[beg]
        out[f"ntk{W}"] = cn[end] - cn[beg]
        p0 = np.where(beg < len(pr), pr[np.clip(beg, 0, len(pr) - 1)], np.nan)
        p1 = np.where(end > 0, pr[np.clip(end - 1, 0, len(pr) - 1)], np.nan)
        out[f"mv{W}"] = p1 - p0
    for k, v in out.items():
        E[k] = v
    E["last_px"] = np.where(end > 0, pr[np.clip(end - 1, 0, len(pr) - 1)], np.nan)
    return E, ts, pr

# ---------------------------------------------------------------- 10-deep book (250ms depth)
def depth_feats(E, con, f):
    cols = ["ts_ms", "imbalance"] + [f"{s}{i}s" for i in range(1, 11) for s in ("bid", "ask")]
    d = con.execute(f"SELECT {','.join(cols)} FROM read_parquet('{f['depth']}') "
                    f"WHERE symbol='{SYM}' ORDER BY ts_ms").df()
    if len(d) < 100:
        for c in ("d_b1", "d_a1", "d_b5", "d_a5", "d_b10", "d_a10", "d_imb",
                  "d_b1_d20", "d_a1_d20", "d_b5_d20", "d_a5_d20"):
            E[c] = np.nan
        return E
    dts = d.ts_ms.values
    B = {i: d[f"bid{i}s"].values for i in range(1, 11)}
    A = {i: d[f"ask{i}s"].values for i in range(1, 11)}
    b1, a1 = B[1], A[1]
    b5 = sum(B[i] for i in range(1, 6)); a5 = sum(A[i] for i in range(1, 6))
    b10 = sum(B[i] for i in range(1, 11)); a10 = sum(A[i] for i in range(1, 11))
    j = np.clip(np.searchsorted(dts, E.dts.values * 1000, side="right") - 1, 0, len(dts) - 1)
    j20 = np.clip(np.searchsorted(dts, (E.dts.values - 20) * 1000, side="right") - 1, 0, len(dts) - 1)
    E["d_b1"], E["d_a1"] = b1[j], a1[j]
    E["d_b5"], E["d_a5"] = b5[j], a5[j]
    E["d_b10"], E["d_a10"] = b10[j], a10[j]
    E["d_imb"] = d.imbalance.values[j]
    E["d_b1_d20"] = b1[j] - b1[j20]
    E["d_a1_d20"] = a1[j] - a1[j20]
    E["d_b5_d20"] = b5[j] - b5[j20]
    E["d_a5_d20"] = a5[j] - a5[j20]
    return E

# ---------------------------------------------------------------- 41ms L1 dynamics
def l1_feats(E, con, f):
    """capture.db-lineage `book` at level 0 — the 41ms event stream, which sees fleeting quotes the
    250ms depth sample cannot. Gives the DEPLETION and REFILL counts over the last 20s."""
    q = con.execute(f"""SELECT ts_ms, side, price, size FROM read_parquet('{f['book']}')
                        WHERE symbol='{SYM}' AND level=0 ORDER BY ts_ms""").df()
    if len(q) < 100:
        for c in ("l1_b_mean", "l1_a_mean", "l1_b_slope", "l1_a_slope",
                  "l1_b_refill", "l1_a_refill", "l1_b_pull", "l1_a_pull", "l1_n"):
            E[c] = np.nan
        return E
    res = {}
    for tag, sd in (("b", "bid"), ("a", "ask")):
        s = q[q.side == sd]
        ts = s.ts_ms.values; sz = s["size"].values.astype(float); pp = s.price.values
        csum = np.concatenate([[0.0], np.cumsum(sz)])
        cn = np.arange(len(ts) + 1, dtype=float)
        dsz = np.concatenate([[0.0], np.diff(sz)])
        samep = np.concatenate([[False], np.diff(pp) == 0])
        refill = np.concatenate([[0.0], np.cumsum(((dsz > 0) & samep).astype(float))])
        pull = np.concatenate([[0.0], np.cumsum(((dsz < 0) & samep).astype(float))])
        e = np.searchsorted(ts, E.dts.values * 1000, side="left")
        g = np.searchsorted(ts, (E.dts.values - 20) * 1000, side="left")
        n = np.maximum(cn[e] - cn[g], 1.0)
        res[f"l1_{tag}_mean"] = (csum[e] - csum[g]) / n
        res[f"l1_{tag}_refill"] = refill[e] - refill[g]
        res[f"l1_{tag}_pull"] = pull[e] - pull[g]
        first = np.clip(g, 0, len(sz) - 1); last = np.clip(e - 1, 0, len(sz) - 1)
        res[f"l1_{tag}_slope"] = sz[last] - sz[first]
        res["l1_n"] = n
    for k, v in res.items():
        E[k] = v
    return E

# ---------------------------------------------------------------- the forward race
def race(E, ts, pr, grid_pt):
    """First-touch race on the REAL tick tape. Entry = the first tick strictly AFTER the bar close,
    filled 1 tick ADVERSE (we cross the spread). Then, for each (target,stop) in points, which is
    touched first inside the horizon. Returns per-cell outcome arrays.
    ⚠ A leg still open at the horizon is marked OPEN and carried at its mark — never predicted."""
    HOR_S = 900
    e0 = np.searchsorted(ts, E.dts.values * 1000, side="left")
    ok = e0 < len(ts)
    ent = np.where(ok, pr[np.clip(e0, 0, len(pr) - 1)], np.nan)
    sh = (E.side.values == "SHORT")
    fill = ent + np.where(sh, -TICK, TICK)                # adverse by one tick
    hor = np.searchsorted(ts, (E.dts.values + HOR_S) * 1000, side="right")
    E["entry"] = fill
    E["ok"] = ok
    out = {}
    for (tp, sp) in grid_pt:
        res = np.full(len(E), 0.0); dur = np.full(len(E), np.nan); kind = np.full(len(E), "OPEN", dtype=object)
        for k in range(len(E)):
            if not ok[k]:
                kind[k] = "NOFILL"; continue
            a, b = e0[k], hor[k]
            if b <= a:
                kind[k] = "NOFILL"; continue
            seg = pr[a:b]
            if sh[k]:
                tgt = fill[k] - tp; stp = fill[k] + sp
                it = np.argmax(seg <= tgt) if (seg <= tgt).any() else -1
                is_ = np.argmax(seg >= stp) if (seg >= stp).any() else -1
            else:
                tgt = fill[k] + tp; stp = fill[k] - sp
                it = np.argmax(seg >= tgt) if (seg >= tgt).any() else -1
                is_ = np.argmax(seg <= stp) if (seg <= stp).any() else -1
            if it < 0 and is_ < 0:
                res[k] = (seg[-1] - fill[k]) * (-1 if sh[k] else 1); kind[k] = "OPEN"
                dur[k] = (ts[b - 1] - ts[a]) / 1000.0
            elif is_ < 0 or (it >= 0 and it <= is_):
                res[k] = tp; kind[k] = "TARGET"; dur[k] = (ts[a + it] - ts[a]) / 1000.0
            else:
                res[k] = -sp; kind[k] = "STOP"; dur[k] = (ts[a + is_] - ts[a]) / 1000.0
        out[f"r_{tp}_{sp}"] = res
        out[f"k_{tp}_{sp}"] = kind
        out[f"d_{tp}_{sp}"] = dur
    for k, v in out.items():
        E[k] = v
    return E

GRID = [(t, s) for t in (2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0) for s in (3.0, 4.0, 5.0, 6.0, 8.0, 10.0)]

if __name__ == "__main__":
    days = full_stack_days()
    only = sys.argv[1:] if len(sys.argv) > 1 else days
    con = duckdb.connect(config={"memory_limit": "2GB", "threads": 3})
    os.makedirs(f"{OUT}/ev", exist_ok=True)
    for day in only:
        dst = f"{OUT}/ev/{day}.parquet"
        if os.path.exists(dst):
            print(f"[skip] {day}", flush=True); continue
        f = day_files(day)
        r = build_day(day, con)
        if r is None:
            print(f"[none] {day}", flush=True); continue
        E, b5 = r
        E, ts, pr = tape_feats(E, con, f)
        E = depth_feats(E, con, f)
        E = l1_feats(E, con, f)
        E = race(E, ts, pr, GRID)
        con.register('E_out', E)
        con.execute(f"COPY E_out TO '{dst}' (FORMAT PARQUET)")
        con.unregister('E_out')
        print(f"[ok] {day}  events={len(E)}  short={(E.side=='SHORT').sum()}  long={(E.side=='LONG').sum()}", flush=True)
