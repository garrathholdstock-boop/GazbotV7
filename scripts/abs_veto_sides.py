"""abs_veto_55s — the SAME robustness battery as scripts/abs_veto_robustness.py, run per SIDE.

The scope asks the promotion question two-sided: does the LONG side earn on its own, does the
SHORT side earn on its own, or is one side carrying the other? Same tick-repriced real_pnl,
same buckets (headline / per-day / regime / walk-forward / head-to-head vs un-vetoed thrust).
Read-only. DuckDB.
"""
from __future__ import annotations
import duckdb, json

SHADOW = "/home/alphabot/gazbot7/data/shadow.db"
CAP = "/home/alphabot/gazbot7/data/capture.db"
WEEK0 = "2026-07-27"

con = duckdb.connect()
con.execute(f"ATTACH '{SHADOW}' AS s (TYPE sqlite, READ_ONLY)")
con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
con.execute("""
CREATE TABLE feat AS
WITH m1 AS (SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) c
            FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' GROUP BY 1),
st AS (SELECT m, c, abs(c-lag(c) OVER w) step FROM m1 WINDOW w AS (ORDER BY m))
SELECT m, abs(c-first_value(c) OVER w30)/NULLIF(SUM(step) OVER w30,0) er
FROM st WINDOW w30 AS (ORDER BY m ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)
""")
rows = con.execute("""
WITH t AS (SELECT id, strategy, side, entry_ts FROM s.shadow_trades
           WHERE strategy IN ('abs_veto_55s','abs_veto_50s','abs_veto_60s','thrust_loose',
                              'thrust_short_raw','thrust_short_absveto55'))
SELECT t.strategy, t.side, t.entry_ts, r.real_pnl,
       strftime(to_timestamp(t.entry_ts),'%Y-%m-%d') AS d,
       coalesce(f.er,0) AS er
FROM t JOIN s.shadow_real r ON r.trade_id=t.id
ASOF LEFT JOIN feat f ON f.m <= t.entry_ts
ORDER BY t.entry_ts
""").fetchall()


def stats(v):
    n = len(v)
    if not n:
        return None
    net = sum(v); w = [x for x in v if x > 0]; l = [x for x in v if x <= 0]
    eq = pk = dd = 0.0
    for x in v:
        eq += x; pk = max(pk, eq); dd = min(dd, eq - pk)
    return dict(n=n, net=round(net, 1), win=round(100 * len(w) / n),
                avgW=round(sum(w) / len(w), 1) if w else 0, avgL=round(sum(l) / len(l), 1) if l else 0,
                worst=round(min(v), 1), exp=round(net / n, 2), maxdd=round(dd, 1))


def sel(strat, side=None, week=False):
    return [r[3] for r in rows if r[0] == strat and (side is None or r[1] == side)
            and (not week or r[4] >= WEEK0)]


out = {}
print("═══ abs_veto_55s — BOTH SIDES, tick-repriced real_pnl ═══\n")
print("1) HEADLINE per side (all-time + this week)")
hdr = f"{'bucket':28}{'n':>5}{'net$':>9}{'win%':>6}{'avgW':>7}{'avgL':>7}{'$/tr':>8}{'maxDD':>8}"
print(hdr)
for strat in ("abs_veto_55s", "abs_veto_50s", "abs_veto_60s"):
    for side in ("LONG", "SHORT", None):
        for wk in (False, True):
            s = stats(sel(strat, side, wk))
            if not s:
                continue
            lbl = f"{strat} {side or 'BOTH':5} {'wk' if wk else 'all'}"
            out[lbl] = s
            print(f"{lbl:28}{s['n']:>5}{s['net']:>9}{s['win']:>6}{s['avgW']:>7}{s['avgL']:>7}{s['exp']:>8}{s['maxdd']:>8}")

print("\n2) PER-DAY per side (abs_veto_55s)")
days = sorted({r[4] for r in rows if r[0] == 'abs_veto_55s'})
perday = {}
print(f"{'day':12}{'LONG n':>8}{'LONG $':>9}{'SHORT n':>9}{'SHORT $':>9}{'TOTAL $':>10}")
for d in days:
    L = [r[3] for r in rows if r[0] == 'abs_veto_55s' and r[1] == 'LONG' and r[4] == d]
    S = [r[3] for r in rows if r[0] == 'abs_veto_55s' and r[1] == 'SHORT' and r[4] == d]
    perday[d] = dict(Ln=len(L), L=round(sum(L), 1), Sn=len(S), S=round(sum(S), 1),
                     tot=round(sum(L) + sum(S), 1))
    print(f"{d:12}{len(L):>8}{sum(L):>9.1f}{len(S):>9}{sum(S):>9.1f}{sum(L)+sum(S):>10.1f}")
out['perday'] = perday

print("\n3) REGIME split per side (30-min ER at entry: chop<0.18 / trend>=0.18)")
reg = {}
print(f"{'bucket':28}{'n':>5}{'net$':>9}{'win%':>6}{'$/tr':>8}")
for side in ("LONG", "SHORT"):
    for name, lo, hi in (("chop ER<0.18", -1, 0.18), ("trend ER>=0.18", 0.18, 9)):
        v = [r[3] for r in rows if r[0] == 'abs_veto_55s' and r[1] == side and lo <= r[5] < hi]
        s = stats(v)
        if s:
            reg[f"{side} {name}"] = s
            print(f"{side+' '+name:28}{s['n']:>5}{s['net']:>9}{s['win']:>6}{s['exp']:>8}")
out['regime'] = reg

print("\n4) WALK-FORWARD halves per side (by trade order)")
wf = {}
for side in ("LONG", "SHORT"):
    v = [r[3] for r in rows if r[0] == 'abs_veto_55s' and r[1] == side]
    h = len(v) // 2
    for nm, vv in (("first half", v[:h]), ("second half", v[h:])):
        s = stats(vv)
        wf[f"{side} {nm}"] = s
        print(f"{side+' '+nm:28}{s['n']:>5}{s['net']:>9}{s['win']:>6}{s['exp']:>8}")
out['walkforward'] = wf

print("\n5) HEAD-TO-HEAD vs un-vetoed thrust_loose, per side")
h2h = {}
for side in ("LONG", "SHORT"):
    a = stats(sel('abs_veto_55s', side)); b = stats(sel('thrust_loose', side))
    h2h[side] = dict(veto=a, raw=b, delta=round(a['net'] - b['net'], 1),
                     per_tr_delta=round(a['exp'] - b['exp'], 2))
    print(f"  {side}: abs_veto_55s n={a['n']} ${a['net']:+.0f} ({a['win']}%w, ${a['exp']:+.2f}/tr)  vs  "
          f"thrust_loose n={b['n']} ${b['net']:+.0f} ({b['win']}%w, ${b['exp']:+.2f}/tr)  → Δ ${a['net']-b['net']:+.0f}")
out['h2h'] = h2h

print("\n6) The live-slot A/B (short-only + chandelier): thrust_short_raw vs thrust_short_absveto55")
for strat in ("thrust_short_raw", "thrust_short_absveto55"):
    s = stats(sel(strat))
    print(f"  {strat:26}n={s['n']:>3} net=${s['net']:+.0f} win={s['win']}% $/tr={s['exp']:+.2f} maxDD=${s['maxdd']:.0f}")
# same-window compare
w0 = min(r[2] for r in rows if r[0] == 'thrust_short_absveto55')
a = stats([r[3] for r in rows if r[0] == 'thrust_short_raw' and r[2] >= w0])
b = stats([r[3] for r in rows if r[0] == 'thrust_short_absveto55'])
print(f"  same-window (from {w0}): raw n={a['n']} ${a['net']:+.0f}  vs  absveto55 n={b['n']} ${b['net']:+.0f}  "
      f"→ Δ ${b['net']-a['net']:+.0f}")
out['ab_slot'] = dict(raw_same_window=a, absveto55=b, delta=round(b['net'] - a['net'], 1))

json.dump(out, open('/home/alphabot/gazbot7/scratchpad/abs_veto_sides.json', 'w'), indent=1, default=float)
print("\nwrote scratchpad/abs_veto_sides.json")
