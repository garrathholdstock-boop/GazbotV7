"""ADAPTIVE-EXIT FIRST-LOOK BACKTEST — best exit per gate x regime x time-of-day.
Reprices each gate's real shadow entries (07-16..31, tick-honest entry_atr) on the forward
5s path, evaluating a GRID of scalp-R combos (swept for the less-trending tapes) + chandelier.
Regime-segmented per the discipline (score each policy on its HOME tape). Conservative
(same-bar stop-first), 1-ATR stop, $2/pt, $1.5/lot fee. Writes JSON for the HTML report."""
import sqlite3, json, numpy as np
from datetime import datetime, timezone
from collections import defaultdict

VPP, FEE, HORIZON_MIN = 2.0, 1.5, 60
cap=sqlite3.connect('data/capture.db'); sh=sqlite3.connect('data/shadow.db')

# gate family -> canonical shadow entry strategies
FAM = {
 'grind (mom)':      ['grind_fast'],
 'thrust/absveto':   ['thrust_loose','thrust_short_raw'],
 'rgv (fade)':       ['rg_long_fast','rg_short_025_raw'],
 'capitulation (fade)':['capit_loose'],
 'exhaustion (fade)':['exhaustion_rev'],
}
STRAT2FAM = {s:f for f,ss in FAM.items() for s in ss}

# ── load 5s bars once ──
bars=cap.execute("SELECT bar_ts,high,low,close FROM bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>=strftime('%s','2026-07-16') ORDER BY bar_ts").fetchall()
bts=np.array([b[0] for b in bars]); bh=np.array([b[1] for b in bars]); bl=np.array([b[2] for b in bars]); bc=np.array([b[3] for b in bars])

# per-minute trailing-30min ER for regime
mins={}
for ts,h,l,c in bars: mins[ts//60]=c
mk=sorted(mins); mc={k:mins[k] for k in mk}
er_at={}
mkarr=mk; mcl=[mc[k] for k in mk]
for i in range(len(mkarr)):
    if i>=30:
        seg=mcl[i-30:i+1]; path=sum(abs(seg[j]-seg[j-1]) for j in range(1,len(seg))) or 1
        er_at[mkarr[i]]=abs(seg[-1]-seg[0])/path
    else: er_at[mkarr[i]]=0.0

def regime(atr, ts):
    """The operator's exit-ladder rungs: BIG-TREND (ride) / MEDIUM-TREND / SCALP-CHOP (bank) /
    STAY-OUT (violent-or-dead — we don't trade it, but measure it)."""
    er=er_at.get(ts//60,0.0)
    if er>=0.50: return 'BIG-TREND'
    if er>=0.30: return 'MED-TREND'
    if atr>=22:  return 'STAY-OUT'     # violent chop — the untradeable rung
    return 'SCALP-CHOP'
def tod(ts):
    h=datetime.fromtimestamp(ts,timezone.utc).hour
    return 'US' if 13<=h<21 else 'ON'

# ── load entries ──
_ph=','.join('?'*len(STRAT2FAM))
rows=sh.execute("SELECT strategy,side,entry_ts,entry_price,entry_atr FROM shadow_trades WHERE entry_ts>=strftime('%s','2026-07-16') AND entry_atr>0 AND strategy IN ("+_ph+")",list(STRAT2FAM)).fetchall()

# ── per-entry forward excursion R-series ──
def excursions(side, entry, atr, i0):
    j1=min(i0+HORIZON_MIN*12, len(bts))
    h=bh[i0:j1]; l=bl[i0:j1]; c=bc[i0:j1]
    if len(h)==0: return None
    if side=='LONG': fav=(h-entry)/atr; adv=(entry-l)/atr; cf=(c-entry)/atr
    else:            fav=(entry-l)/atr; adv=(h-entry)/atr; cf=(entry-c)/atr
    return fav,adv,cf

def scalp(favcum, adv_stop_idx, target, cf_last):
    reach=np.argmax(favcum>=target) if favcum[-1]>=target else len(favcum)
    if favcum[-1]<target and favcum[0]<target and not (favcum>=target).any(): reach=len(favcum)
    if reach<=adv_stop_idx: return target
    if adv_stop_idx<len(favcum): return -1.0
    return max(min(cf_last,target),-1.0)

def chand(fav,adv,cf,mode):
    peak=0.0; stop_hit=len(fav)
    hit=np.argmax(adv>=1.0) if (adv>=1.0).any() else len(fav)
    for i in range(len(fav)):
        peak=max(peak,fav[i])
        k=(0.5 if peak>=6 else 3.5) if mode=='wide' else 1.5
        trail=peak-k
        if i>=hit: return -1.0
        if peak>0 and trail>0 and cf[i]<=trail: return trail
    return max(min(cf[-1],peak),-1.0)

# scalp-R grid (less-trending sweep) + chandelier policies
A_RS=[0.5,1.0,1.5,2.5,3.5]; B_RS=[1.0,1.5,2.0,2.5,3.5]
SCALP_COMBOS=[(a,b) for a in A_RS for b in B_RS if b>a]
# agg[(fam,regime)][policy] = list of per-signal 2-lot $
agg=defaultdict(lambda: defaultdict(list))
seen=set()
for strat,side,ts,ep,atr in rows:
    key=(strat,ts)
    if key in seen: continue
    seen.add(key)
    fam=STRAT2FAM[strat]; reg=regime(atr,ts); td=tod(ts)
    i0=int(np.searchsorted(bts,ts))
    ex=excursions(side,ep,atr,i0)
    if ex is None: continue
    fav,adv,cf=ex; favcum=np.maximum.accumulate(fav)
    adv_stop_idx=int(np.argmax(adv>=1.0)) if (adv>=1.0).any() else len(fav)
    cfl=cf[-1]
    def lot_usd(rr): return (rr*atr*VPP)-FEE
    # scalp combos
    for (a,b) in SCALP_COMBOS:
        ra=scalp(favcum,adv_stop_idx,a,cfl); rb=scalp(favcum,adv_stop_idx,b,cfl)
        agg[(fam,reg)][f"scalp {a}/{b}"].append(lot_usd(ra)+lot_usd(rb))
    # chandelier policies
    ra=scalp(favcum,adv_stop_idx,2.5,cfl); rbw=chand(fav,adv,cf,'wide')
    agg[(fam,reg)]["A2.5 + wideChand"].append(lot_usd(ra)+lot_usd(rbw))
    rw=chand(fav,adv,cf,'wide'); agg[(fam,reg)]["wideChand x2"].append(lot_usd(rw)*2)
    rt=chand(fav,adv,cf,'tight'); agg[(fam,reg)]["tightChand x2"].append(lot_usd(rt)*2)

# ── report ──
out={}
for (fam,reg),pol in sorted(agg.items()):
    best=None
    stats={}
    for p,vals in pol.items():
        if len(vals)<5: continue
        mean=sum(vals)/len(vals); tot=sum(vals); win=100*sum(1 for v in vals if v>0)/len(vals)
        stats[p]={'mean':round(mean,1),'tot':round(tot),'n':len(vals),'win':round(win)}
        if best is None or mean>stats[best]['mean']: best=p
    out.setdefault(fam,{})[reg]={'n':len(next(iter(pol.values()))),'best':best,'stats':stats}

json.dump(out,open('scratchpad/adaptive_exit_results.json','w'),indent=1)
# print summary: best policy per family x regime
print(f"{'family':20}{'regime':9}{'n':>5}  best-exit                 mean$/tr")
print('-'*72)
for fam in FAM:
    for reg in ['BIG-TREND','MED-TREND','SCALP-CHOP','STAY-OUT']:
        cell=out.get(fam,{}).get(reg)
        if not cell or not cell['best']: continue
        b=cell['best']; st=cell['stats'][b]
        print(f"{fam:20}{reg:9}{st['n']:>5}  {b:24} {st['mean']:+7.1f}  (win {st['win']}%)")
