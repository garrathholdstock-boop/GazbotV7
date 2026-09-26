#!/usr/bin/env python3
"""SECTION 2 — WHAT THE TAPE LOOKED LIKE WHEN HE PRESSED.

Replicates tape_reader.context()'s numeric facts at EVERY minute of the press sessions, so the
press population and the all-minutes baseline are measured with one ruler — including that
ruler's own quirks. Validated press-by-press against the captured facts first.

⚠ DESCRIPTIVE ONLY. There are no recorded NEGATIVES (zero `pass` rows), so nothing here is a
decision boundary and no threshold is tuned on it.
"""
from __future__ import annotations
import datetime as dt, json, sqlite3
import numpy as np, pandas as pd, duckdb

GB = "/home/alphabot/gazbot7"
OPEN_S = 13 * 3600 + 30 * 60


def load5s(t_from, t_to, symbol="MNQ"):
    con = duckdb.connect(); con.execute(f"attach '{GB}/data/capture.db' as c (read_only)")
    return con.execute(f"""select bar_ts,open,high,low,close,volume from c.bars
        where symbol='{symbol}' and timeframe='5s' and bar_ts>={t_from} and bar_ts<{t_to}
        order by bar_ts""").df()


def to_min(d):
    g = d.assign(t=(d.bar_ts // 60) * 60).groupby("t").agg(
        o=("open", "first"), h=("high", "max"), l=("low", "min"),
        c=("close", "last"), v=("volume", "sum")).reset_index()
    return g


def facts_from(m1: pd.DataFrame, now_ts: float) -> dict | None:
    """tape_reader.context() verbatim: the 24h 1-min frame, its RTH-anchored 'session', the
    running extremes, the volume VWAP and the 14-minute MEAN HIGH-LOW RANGE it calls ATR."""
    if len(m1) < 20:
        return None
    px = float(m1.c.iloc[-1])
    nd = dt.datetime.fromtimestamp(now_ts, dt.UTC)
    today = m1[m1.t % 86400 >= OPEN_S] if (nd.hour * 3600 + nd.minute * 60) >= OPEN_S else m1
    sess = today if len(today) > 5 else m1.tail(120)
    hi, lo = float(sess.h.max()), float(sess.l.min())
    o = float(sess.o.iloc[0]); rng = max(hi - lo, 1e-9)
    vwap = float((sess.c * sess.v).sum() / max(sess.v.sum(), 1e-9))
    atr = float(np.maximum(m1.h - m1.l, 0.25).rolling(14).mean().iloc[-1])
    return dict(price=px, day_open=o, day_high=hi, day_low=lo, vwap=vwap, atr=atr,
                pos_in_range=(px - lo) / rng, sess_bars=len(sess), sess_t0=int(sess.t.iloc[0]),
                vwap_atr=(px - vwap) / max(atr, 1e-9))


# ── LEGS: the leg_survival.py definition, evaluated causally ────────────────────────────────
def legs_of(mm: pd.DataFrame, k_retrace=1.0, min_start=8):
    cl = mm.c.values.astype(float); ts = mm.t.values.astype(np.int64)
    atr = pd.Series(np.maximum(mm.h.values - mm.l.values, 0.25)).rolling(14, min_periods=5).mean().values
    n = len(cl); out = []; i = 20
    while i < n - 2:
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            i += 1; continue
        mv = cl[i] - cl[i - min_start]
        if abs(mv) < a:
            i += 1; continue
        sgn = 1 if mv > 0 else -1
        start = i - min_start; ext = cl[i]; j = i; exts = {i: cl[i]}
        while j + 1 < n and ts[j + 1] - ts[start] < 86400:
            j += 1; px = cl[j]
            if sgn * (px - ext) > 0:
                ext = px
            elif sgn * (ext - px) >= k_retrace * a:
                break
            exts[j] = ext
        if j - start >= 10:
            out.append(dict(start=start, detect=i, end=j, sgn=sgn, atr=a, exts=exts, c0=cl[start]))
        i = j + 1
    return out


def leg_at(legs, idx):
    for L in legs:
        if L["detect"] <= idx <= L["end"]:
            ext = L["exts"].get(idx)
            if ext is None:
                continue
            tv = L["sgn"] * (ext - L["c0"])
            return dict(alive=True, dir=1 if L["sgn"] > 0 else -1, age=int(idx - L["start"]),
                        travel_pt=float(tv), travel_atr=float(tv / max(L["atr"], 1e-9)))
    return dict(alive=False, dir=0, age=None, travel_pt=None, travel_atr=None)


def main():
    t0 = int(dt.datetime(2026, 9, 12, tzinfo=dt.UTC).timestamp())
    t1 = int(dt.datetime(2026, 9, 19, tzinfo=dt.UTC).timestamp())
    s5 = load5s(t0, t1)
    MALL = to_min(s5)
    tvals = MALL.t.values
    print(f"5s rows {len(s5):,} -> minute bars {len(MALL):,}")

    # ── presses, deduped on (kind, request.raw) ─────────────────────────────────────────────
    rs = [json.loads(l) for l in open(f"{GB}/data/operator_reads.jsonl") if l.strip()]
    seen = {}
    for r in rs:
        raw = (r.get("request") or {}).get("raw")
        key = (r["kind"], raw) if raw else ("NOREQ", r["ts"])
        seen.setdefault(key, r)
    presses = sorted(seen.values(), key=lambda r: r["ts"])
    kinds = pd.Series([p["kind"] for p in presses]).value_counts().to_dict()
    print(f"raw rows {len(rs)} -> distinct presses {len(presses)}  {kinds}")

    rows = []
    for r in presses:
        raw = (r.get("request") or {}).get("raw") or ""
        parts = raw.split("|")
        side = parts[1] if len(parts) > 1 and parts[1] in ("BUY", "SELL") else None
        f = r.get("facts") or {}
        pos = f.get("position") or {}
        rows.append(dict(ts=r["ts"], t=dt.datetime.fromisoformat(r["ts"]).timestamp(),
                         kind=r["kind"], side=side, has_raw=bool(raw),
                         price=f.get("price"), atr=f.get("atr"), pir=f.get("pos_in_range"),
                         vwap=f.get("vwap"), day_open=f.get("day_open"),
                         day_high=f.get("day_high"), day_low=f.get("day_low"),
                         drift=(f.get("drift") or {}).get("direction"),
                         drift_ok=(f.get("drift") or {}).get("confirmed"),
                         drift_min=(f.get("drift") or {}).get("minutes"),
                         pos_entered=pos.get("entered"), pos_closed=pos.get("closed"),
                         lots_open=pos.get("lots_open"), note=pos.get("note"),
                         ctx_err=r.get("context_error")))
    P = pd.DataFrame(rows)
    P["vwap_atr"] = (P.price - P.vwap) / P.atr
    P["date"] = P.ts.str[:10]
    P["hour"] = pd.to_datetime(P.ts, format="mixed", utc=True).dt.hour

    # ── the all-minutes baseline, one ruler ────────────────────────────────────────────────
    sess_dates = sorted(P[P.side.notna()].date.unique())
    print(f"press sessions: {sess_dates}")
    base = []
    lo_all = int(dt.datetime.fromisoformat(sess_dates[0]).replace(tzinfo=dt.UTC).timestamp())
    hi_all = P.t.max()
    idx = np.searchsorted(tvals, [lo_all, hi_all])
    for i in range(idx[0], idx[1] + 1):
        now = float(tvals[i]) + 60.0          # evaluated at the END of that minute
        lo = int(now) - 86400
        a = np.searchsorted(tvals, lo)
        m1 = MALL.iloc[a:i + 1]
        fx = facts_from(m1, now)
        if fx is None:
            continue
        base.append(dict(t=float(tvals[i]), i=i, **fx))
    B = pd.DataFrame(base)
    B["date"] = pd.to_datetime(B.t, unit="s", utc=True).dt.strftime("%Y-%m-%d")
    B["hour"] = pd.to_datetime(B.t, unit="s", utc=True).dt.hour
    print(f"baseline minutes {len(B):,}")

    # ── legs, over the whole minute frame ──────────────────────────────────────────────────
    for k in (1.0, 3.0):
        L = legs_of(MALL, k_retrace=k)
        st = [leg_at(L, i) for i in B.i]
        B[f"leg{k}_alive"] = [s["alive"] for s in st]
        B[f"leg{k}_dir"] = [s["dir"] for s in st]
        B[f"leg{k}_age"] = [s["age"] for s in st]
        B[f"leg{k}_tatr"] = [s["travel_atr"] for s in st]
        B[f"leg{k}_tpt"] = [s["travel_pt"] for s in st]
        pi = np.searchsorted(tvals, P.t.values, side="right") - 1
        stp = [leg_at(L, int(j)) for j in pi]
        P[f"leg{k}_alive"] = [s["alive"] for s in stp]
        P[f"leg{k}_dir"] = [s["dir"] for s in stp]
        P[f"leg{k}_age"] = [s["age"] for s in stp]
        P[f"leg{k}_tatr"] = [s["travel_atr"] for s in stp]
        P[f"leg{k}_tpt"] = [s["travel_pt"] for s in stp]

    # ── ATR percentile against its own recent distribution (trailing 1,440 open minutes) ────
    atr_series = B.set_index("t").atr
    def atr_pct(ts, a):
        w = atr_series[(atr_series.index <= ts) & (atr_series.index > ts - 86400)]
        return float((w < a).mean() * 100) if len(w) > 60 else np.nan
    B["atr_pct"] = [atr_pct(t, a) for t, a in zip(B.t, B.atr)]
    P["atr_pct"] = [atr_pct(t, a) if pd.notna(a) else np.nan for t, a in zip(P.t, P.atr)]

    # ── outcomes, GROUPED BY ENTRY ─────────────────────────────────────────────────────────
    c = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
    tr = pd.read_sql("select * from trades where opened_at >= '2026-09-14'", c)
    tr["t0"] = pd.to_datetime(tr.opened_at, format="mixed", utc=True)
    tr["t1"] = pd.to_datetime(tr.closed_at, format="mixed", utc=True)
    tr = tr[~tr.data_quality.fillna("").str.startswith("EXCLUDE:")]
    ent = (tr.groupby(["opened_at", "side", "entry_price"], as_index=False)
             .agg(lots=("qty", "sum"), pnl=("pnl_usd", "sum"), n_rows=("id", "count"),
                  t0=("t0", "first"), last_out=("t1", "max"),
                  bad=("data_quality", lambda s: s.fillna("").str.startswith("BADFILL:").any()),
                  src=("entry_source", "first")))
    ent["pnl1"] = [float(g[g.qty == 1].pnl_usd.sum()) if len(g[g.qty == 1]) else np.nan
                   for _, g in tr.groupby(["opened_at", "side", "entry_price"])]
    ent = ent.sort_values("t0").reset_index(drop=True)

    match = []
    for _, p in P.iterrows():
        pt = pd.Timestamp(p.ts)
        m = ent[(ent.t0 >= pt - pd.Timedelta(seconds=30)) & (ent.t0 <= pt + pd.Timedelta(seconds=180))]
        match.append(m.index[0] if len(m) else None)
    P["entry_ix"] = match
    P = P.join(ent[["lots", "pnl", "pnl1", "bad", "last_out", "t0", "n_rows"]], on="entry_ix",
               rsuffix="_e")
    P["hold_min"] = (P.last_out - P.t0).dt.total_seconds() / 60

    P.to_csv("/tmp/op_press.csv", index=False)
    B.to_csv("/tmp/op_base.csv", index=False)
    ent.to_csv("/tmp/op_entries.csv", index=False)
    print(f"entries in trades since 09-14: {len(ent)}")
    print("-> /tmp/op_press.csv /tmp/op_base.csv /tmp/op_entries.csv")


if __name__ == "__main__":
    main()
