"""THE CLIP TEST. Every winner above banks exactly $97 = Lot A $40 - fee + Lot B $60 - fee.
That is the QUIET-TAPE CLIP (exit_overrides atr_split=22: when entry ATR < 22pt, Lot A takes a
flat $40 and Lot B max(1.75xATR, $60)). A run STARTS quiet and then expands — so the clip keys
off exactly the wrong number. Reprice the identical fires with the clip OFF."""
import json,sys
from dataclasses import replace
sys.path.insert(0,"/home/alphabot/gazbot7/scripts"); sys.path.insert(0,"/home/alphabot/gazbot7/src")
from m2_idle_gates import LOTS, replay_lot, TK_TS, TK_PX, VPP, FEE, M2
from bisect import bisect_left
res=json.load(open(f"{M2}/results.json"))

def price(g, side, s, atr, clip: bool):
    i=bisect_left(TK_TS, s*1000); ems, epx = int(TK_TS[i]), float(TK_PX[i])
    out=[]
    for spec in LOTS[g]:
        sp = spec if clip else replace(spec, atr_split=0.0)
        pt,why,ts = replay_lot(sp, side, ems, epx, atr)
        out.append({"lot":sp.tag,"usd":pt*VPP-FEE,"why":why,"pt":pt,"hold":(ts-ems)/60000.0})
    return out

for arm in ("A_as_live","D_ungated"):
    print(f"\n===== {arm}: live exit stack vs the SAME fires with the quiet-tape clip OFF =====")
    on=off=0.0
    for x in res["arms"][arm]["per_run"]:
        for g,fi in x["fires"].items():
            a=price(g,fi["side"],fi["s"],fi["atr"],True)
            b=price(g,fi["side"],fi["s"],fi["atr"],False)
            ua, ub = sum(l["usd"] for l in a), sum(l["usd"] for l in b)
            on+=ua; off+=ub
            print(f"  {x['run']} {g:17s} ceil${x['ceil']:3d} atr{fi['atr']:5.1f}  "
                  f"CLIP ${ua:8.2f} [{'/'.join(l['why'] for l in a)}]   "
                  f"NO-CLIP ${ub:8.2f} [{'/'.join(l['why'] for l in b)}]  delta ${ub-ua:+8.2f}")
    print(f"  TOTAL  clip ${on:,.2f}   no-clip ${off:,.2f}   delta ${off-on:+,.2f}")
