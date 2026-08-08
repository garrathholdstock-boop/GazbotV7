#!/usr/bin/env python
"""
EXECUTION-COST AUTOPSY — Stage 1: P&L waterfall (pure accounting, NO fill model).
Read-only. Decomposes realized net P&L per trade into:
    realized_net = gross_direction (entry-mid -> exit-mid, signed by side, x vpp x qty)
                 - spread_paid      (entry half-spread + exit half-spread, crossing the touch)
                 - fee_per_RT        (commission)
Mid at each fill = ASOF nearest-prior depth_snap best bid/ask -> mid=(bid1p+ask1p)/2.

Spread_paid is measured INDEPENDENTLY from depth mids:
    gross_fill      = (exit_price - entry_price) * sign * vpp * qty        [ledger prices]
    gross_direction = (exit_mid   - entry_mid)   * sign * vpp * qty        [depth mids]
    spread_paid     = gross_direction - gross_fill  ( = entry_half + exit_half in $ )
So the waterfall identity closes to the ledger-reconciliation residual only.

Spec: /home/alphabot/gazbot7/EXECUTION_COST_AUTOPSY_SCOPE.md  (Stage 1)
DO NOT COMMIT. No live service touched.
"""
import sqlite3
import duckdb
import pandas as pd
from datetime import datetime, timezone

GAZ_DB    = "/home/alphabot/gazbot7/data/gazbot7.db"
DEPTH_DB  = "/home/alphabot/gazbot7/data/depth.db"
SHADOW_DB = "/home/alphabot/alphabot2/data/alphabot.db"   # fut_shadow_sim_trades (has prices+ts)
VPP = 2.0  # MNQ $/point

def iso_to_ms(s):
    return int(datetime.fromisoformat(s).astimezone(timezone.utc).timestamp() * 1000)

# ---- load MNQ depth once into a DuckDB in-memory relation ----------------
con = duckdb.connect()
con.execute(f"ATTACH '{DEPTH_DB}' AS d (TYPE sqlite, READ_ONLY);")
depth = con.execute("""
    SELECT ts_ms,
           (bid1p+ask1p)/2.0 AS mid,
           (ask1p-bid1p)     AS spread
    FROM d.depth_snap
    WHERE symbol='MNQ' AND bid1p IS NOT NULL AND ask1p IS NOT NULL
    ORDER BY ts_ms
""").df()
con.execute("CREATE TABLE depth AS SELECT * FROM depth")

def asof_mid(fill_ms_series):
    """For each fill ms, nearest-prior depth mid+spread (last-known book at fill time)."""
    q = pd.DataFrame({"fill_ms": fill_ms_series.astype("int64")}).reset_index()
    con.register("fills_tmp", q)
    out = con.execute("""
        SELECT f.index AS idx, f.fill_ms,
               d.mid AS mid, d.spread AS touch
        FROM fills_tmp f
        ASOF LEFT JOIN depth d ON f.fill_ms >= d.ts_ms
        ORDER BY f.index
    """).df()
    con.unregister("fills_tmp")
    return out.set_index("idx")[["mid", "touch"]]

def decompose(df, label):
    """df must have: side, qty, entry_price, exit_price, entry_ms, exit_ms, fee, net_pnl."""
    df = df.copy().reset_index(drop=True)
    df["sign"] = df["side"].map({"LONG": 1.0, "SHORT": -1.0})

    em = asof_mid(df["entry_ms"]); xm = asof_mid(df["exit_ms"])
    df["entry_mid"]   = em["mid"].values
    df["entry_touch"] = em["touch"].values
    df["exit_mid"]    = xm["mid"].values
    df["exit_touch"]  = xm["touch"].values

    df["gross_fill"]      = df["sign"] * (df["exit_price"] - df["entry_price"]) * VPP * df["qty"]
    df["gross_direction"] = df["sign"] * (df["exit_mid"]   - df["entry_mid"])   * VPP * df["qty"]
    df["spread_paid"]     = df["gross_direction"] - df["gross_fill"]
    # residual: does ledger net == gross_fill - fee ?
    df["ledger_resid"]    = df["net_pnl"] - (df["gross_fill"] - df["fee"])

    # --- split spread_paid into quoted-touch-cross (passive-recoverable) vs
    #     beyond-touch slippage (mostly stop/flush fills == real adverse direction,
    #     NOT recoverable by a resting limit; charging it to "cost" is a fake win) ---
    import numpy as _np
    e_half = df["sign"] * (df["entry_price"] - df["entry_mid"])   # $ per pt, signed (>0 = paid)
    x_half = df["sign"] * (df["exit_mid"]   - df["exit_price"])
    def _q(half, touch):
        return _np.clip(_np.minimum(half, touch / 2.0), 0, None)  # capped at the quoted half-spread
    e_q = _q(e_half, df["entry_touch"]); x_q = _q(x_half, df["exit_touch"])
    df["touch_cost"] = (e_q + x_q) * VPP * df["qty"]               # PASSIVE-RECOVERABLE ceiling
    df["entry_touch_cost"] = e_q * VPP * df["qty"]                 # passive-ENTRY-only ceiling (Stage 2)
    df["beyond_slip"] = df["spread_paid"] - df["touch_cost"]       # excess (stops/flush) ~ real direction

    n = len(df)
    tot = dict(
        n=n,
        gross_direction=df["gross_direction"].sum(),
        spread_paid=df["spread_paid"].sum(),
        fee=df["fee"].sum(),
        net=df["net_pnl"].sum(),
        gross_fill=df["gross_fill"].sum(),
        ledger_resid=df["ledger_resid"].sum(),
        avg_entry_touch=df["entry_touch"].mean(),
        avg_exit_touch=df["exit_touch"].mean(),
        avg_spread_per_rt=df["spread_paid"].mean(),
        avg_fee_per_rt=df["fee"].mean(),
        avg_cost_per_rt=(df["spread_paid"] + df["fee"]).mean(),
        tot_cost=(df["spread_paid"].sum() + df["fee"].sum()),
        touch_cost=df["touch_cost"].sum(),
        avg_touch_cost=df["touch_cost"].mean(),
        entry_touch_cost=df["entry_touch_cost"].sum(),
        avg_entry_touch_cost=df["entry_touch_cost"].mean(),
        beyond_slip=df["beyond_slip"].sum(),
        avg_beyond_slip=df["beyond_slip"].mean(),
        robust_gross=df["gross_direction"].sum() - df["beyond_slip"].sum(),
    )
    return df, tot

def waterfall_str(t, label):
    g = t["gross_direction"]; s = t["spread_paid"]; f = t["fee"]; net = t["net"]
    def pct(x):
        return f"{100*x/g:+7.1f}%" if abs(g) > 1e-9 else "   n/a "
    L = []
    L.append(f"===== {label}  (n={t['n']}) =====")
    L.append(f"  gross_direction (mid->mid) : ${g:+10.2f}   {pct(g)}")
    L.append(f"  - spread_paid (touch cross): ${-s:+10.2f}   {pct(-s)}")
    L.append(f"  - fee (commission)         : ${-f:+10.2f}   {pct(-f)}")
    L.append(f"  = net (ledger)             : ${net:+10.2f}   {pct(net)}")
    L.append(f"    [reconc: gross_fill ${t['gross_fill']:+.2f} - fee = ${t['gross_fill']-f:+.2f}; "
             f"ledger resid ${t['ledger_resid']:+.2f}]")
    L.append(f"  avg touch spread: entry {t['avg_entry_touch']:.4f}pt  exit {t['avg_exit_touch']:.4f}pt  "
             f"(=${t['avg_entry_touch']*VPP:.2f}/{t['avg_exit_touch']*VPP:.2f} full)")
    L.append(f"  cost per RT: spread ${t['avg_spread_per_rt']:.3f} + fee ${t['avg_fee_per_rt']:.3f} "
             f"= ${t['avg_cost_per_rt']:.3f}   | total cost over sample ${t['tot_cost']:.2f}")
    L.append(f"  spread_paid SPLIT:")
    L.append(f"     quoted touch-cross (PASSIVE-RECOVERABLE ceiling): ${t['touch_cost']:.2f} tot  "
             f"${t['avg_touch_cost']:.3f}/RT")
    L.append(f"        of which ENTRY-side only (Stage-2 passive-entry target): ${t['entry_touch_cost']:.2f} tot  "
             f"${t['avg_entry_touch_cost']:.3f}/RT")
    L.append(f"     beyond-touch slippage (stop/flush ~= real direction, NOT recoverable): "
             f"${t['beyond_slip']:.2f} tot  ${t['avg_beyond_slip']:.3f}/RT")
    L.append(f"  ROBUST gross-direction (beyond-touch reclassified as direction): ${t['robust_gross']:+.2f}")
    return "\n".join(L)

def winner_loser(df, label):
    L = [f"----- {label}: winners vs losers -----"]
    for name, sub in [("WINNERS (net>0)", df[df["net_pnl"] > 0]),
                      ("LOSERS  (net<=0)", df[df["net_pnl"] <= 0])]:
        if len(sub) == 0:
            L.append(f"  {name}: none"); continue
        gd = sub["gross_direction"].sum(); sp = sub["spread_paid"].sum(); fe = sub["fee"].sum()
        net = sub["net_pnl"].sum()
        cost = sp + fe
        avg_absmove = (sub["gross_direction"].abs()).mean()
        L.append(f"  {name}: n={len(sub)}  net=${net:+.2f}  gross_dir=${gd:+.2f}  "
                 f"spread=${sp:.2f}  fee=${fe:.2f}")
        L.append(f"      avg |gross_dir| move=${avg_absmove:.2f}/RT  "
                 f"cost=${cost:.2f} ({'inf' if abs(gd)<1e-9 else f'{100*cost/abs(gd):.1f}%'} of |gross_dir|)  "
                 f"avg cost/RT=${(sp+fe).sum()/len(sub) if False else (sub['spread_paid']+sub['fee']).mean():.3f}")
    return "\n".join(L)

def move_buckets(df, label):
    """Cost drag vs move size: bucket by |gross_direction| $."""
    d = df.copy()
    d["absmove"] = d["gross_direction"].abs()
    edges = [0, 10, 25, 50, 100, 1e9]
    names = ["$0-10", "$10-25", "$25-50", "$50-100", "$100+"]
    d["bkt"] = pd.cut(d["absmove"], bins=edges, labels=names, include_lowest=True)
    L = [f"----- {label}: cost drag by |gross_direction| bucket -----"]
    for nm in names:
        sub = d[d["bkt"] == nm]
        if len(sub) == 0:
            continue
        cost = (sub["spread_paid"] + sub["fee"]).sum()
        gd_abs = sub["absmove"].sum()
        frac = 100*cost/gd_abs if gd_abs > 1e-9 else float("nan")
        L.append(f"  {nm:8s} n={len(sub):4d}  sum|gross|=${gd_abs:9.2f}  cost=${cost:8.2f}  "
                 f"cost/|gross|={frac:6.1f}%  net=${sub['net_pnl'].sum():+9.2f}")
    return "\n".join(L)

# ============================ LIVE LEDGER =================================
lc = sqlite3.connect(GAZ_DB)
live = pd.read_sql_query(
    "SELECT side, qty, entry_price, exit_price, opened_at, closed_at, "
    "pnl_usd, fees_usd FROM trades WHERE symbol='MNQ'", lc)
lc.close()
live["entry_ms"] = live["opened_at"].map(iso_to_ms)
live["exit_ms"]  = live["closed_at"].map(iso_to_ms)
live = live.rename(columns={"fees_usd": "fee", "pnl_usd": "net_pnl"})
live_df, live_t = decompose(live, "LIVE")

# ============================ SHADOW SET =================================
sc = sqlite3.connect(SHADOW_DB)
shad = pd.read_sql_query(
    "SELECT side, entry_price, exit_price, entry_ts, exit_ts, pnl_usd, fee_rt, value_per_point "
    "FROM fut_shadow_sim_trades WHERE symbol='MNQ' AND status='CLOSED' "
    "AND exit_ts IS NOT NULL", sc)
sc.close()
# restrict to depth coverage window
DEPTH_MIN_S = int(depth["ts_ms"].min() // 1000)
DEPTH_MAX_S = int(depth["ts_ms"].max() // 1000)
shad = shad[(shad["entry_ts"] >= DEPTH_MIN_S) & (shad["exit_ts"] <= DEPTH_MAX_S)].copy()
shad["qty"] = 1.0
shad["entry_ms"] = (shad["entry_ts"] * 1000).astype("int64")
shad["exit_ms"]  = (shad["exit_ts"] * 1000).astype("int64")
shad = shad.rename(columns={"fee_rt": "fee", "pnl_usd": "net_pnl"})
shad_df, shad_t = decompose(shad, "SHADOW")

# ============================ REPORT =====================================
out = []
out.append("############ EXECUTION-COST AUTOPSY — STAGE 1 (accounting) ############")
out.append(f"depth coverage: {datetime.utcfromtimestamp(DEPTH_MIN_S)} .. {datetime.utcfromtimestamp(DEPTH_MAX_S)} UTC")
out.append(f"MNQ vpp=${VPP}/pt")
out.append("")
out.append(waterfall_str(live_t, "LIVE V7 DESK LEDGER (gazbot7.db trades, MNQ)"))
out.append(winner_loser(live_df, "LIVE"))
out.append(move_buckets(live_df, "LIVE"))
out.append("")
out.append(waterfall_str(shad_t, "SHADOW SET (alphabot.db fut_shadow_sim_trades, MNQ, in depth window)"))
out.append(winner_loser(shad_df, "SHADOW"))
out.append(move_buckets(shad_df, "SHADOW"))
out.append("")
# overall touch-spread sanity from raw depth
overall = con.execute("SELECT AVG(spread) a, MEDIAN(spread) m, "
                      "COUNT(*) FILTER(WHERE spread=0.25)*1.0/COUNT(*) f025, "
                      "COUNT(*) FILTER(WHERE spread=0.5)*1.0/COUNT(*) f050 FROM depth").df().iloc[0]
out.append(f"RAW MNQ touch spread (all snaps): mean {overall.a:.4f}pt  median {overall.m:.4f}pt  "
           f"| share@0.25pt={overall.f025:.1%}  share@0.50pt={overall.f050:.1%}  "
           f"(=${overall.a*VPP:.2f} mean full spread)")

print("\n".join(out))
