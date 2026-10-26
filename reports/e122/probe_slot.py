"""Rebuild the exact replay prompt for one slot (flat book, no presses yet) and re-ask it N times per arm."""
import sys, json, datetime as dt, concurrent.futures as cf
sys.path.insert(0, "/home/alphabot/gazbot7/reports/recursive_loop/E112_code")
import replay as R
S, L, H, DB = R.S, R.L, R.H, R.DB
day, hhmm, N = sys.argv[1], sys.argv[2], int(sys.argv[3]); arms = sys.argv[4].split(",")
R.CUR["sym"] = "MGC"; S.VPP = R.INST["MGC"]["pv"]
d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
op = int(dt.datetime.fromisoformat(f"{day}T{hhmm}:00+00:00").timestamp())
bars = R.day_bars(day); page = [b for b in bars if b[0] < d0 + 13*3600 + 1800]
upto = [b for b in page if b[0] + 60 <= op]; px = upto[-1][3]
series_all = L.series_for(dt.date.fromisoformat(day))
def prompt(arm):
    cfg = R.ARM_CFG[arm]; MECH = R.mech_for(day, cfg); rec = {"presses": []}
    mil_now = H.mil_pivot(L.confirmed_turns([b for b in series_all if b[0] + 60 <= op]), op - 60)
    ppos, pdone, ptrades = R.real_book(rec, None, op, bars, px)
    cut_ = L.veto_cutoff(op)
    st_ = {"now_utc": hhmm + "Z", "mins_to_us_open": max(0, (d0 + 13*3600 + 1800 - op)//60),
           "before_veto": MECH["veto_utc"] if cut_ is not None and op < cut_ else None,
           "mil_dir": mil_now[1] if mil_now else None, "mil_cap": cfg["milcap"],
           "mil_since": dt.datetime.fromtimestamp(mil_now[0], R.UTC).strftime("%H:%MZ") if mil_now else None,
           "mil_claims": 0, "trades": ptrades, "day_usd": 0.0, "lock_usd": R.LOCK}
    head, _ = DB.build(MECH, st_)
    return head + "\n\n=== THE TAPE ===\n" + S.context(upto, op, ppos, "", pdone, True, band=False, leg_list=False, mil=False, card=False,
        window_note=R.WINDOW_NOTE.format(flat=MECH["flat_utc"]),
        header=R.HEADER.format(sym="MGC", day=day, now=hhmm, veto=MECH["veto_utc"], open=MECH["us_open_utc"]), open_note="")
P = {a: prompt(a) for a in arms}
import difflib
if len(arms) == 2:
    print("PROMPT DIFF:"); [print(" ", l) for l in difflib.unified_diff(P[arms[0]].splitlines(), P[arms[1]].splitlines(), lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++","---")]
open(f"/tmp/claude-0/-home-alphabot-gazbot7/cab4b96b-8f19-514c-8ff4-78261bd96b46/scratchpad/prompt_{day}_{hhmm.replace(':','')}_{arms[0]}.txt","w").write(P[arms[0]])
jobs = [(a, i) for i in range(N) for a in arms]
with cf.ThreadPoolExecutor(3) as ex:
    res = list(ex.map(lambda j: (j[0], S.ask(P[j[0]])), jobs))
out = {}
for a, d in res:
    out.setdefault(a, []).append(d); print(f"{a:9} {d.get('action'):12} {d.get('conf')} | {str(d.get('reason'))[:170]}", flush=True)
for a in arms:
    print(a, "ENTER", sum(1 for d in out[a] if str(d.get('action','')).startswith('ENTER')), "/", len(out[a]), "errors", sum(1 for d in out[a] if d.get('error')))
