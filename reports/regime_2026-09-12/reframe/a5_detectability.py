"""A5. THE DETECTABILITY ARITHMETIC — the number that decides whether the game is winnable.

Nothing here is a backtest. It is the sample-size arithmetic that every edge on this desk must
satisfy, fed with THIS desk's own measured per-trade dispersion.

Sources, all live and clean:
  - data/gazbot7.db trades, data_quality IS NULL (the desk's own exclusion flags respected),
    qty = 1 ONLY, because the paper engine fabricates a 0.1% adverse price on every lot beyond
    the first (memory: paper-fills-fabricate-a-0-1-percent-adverse-price) - $2,916.50 over 32
    orders, which is larger than the whole booked loss net of the gate roster.
  - Mesfin (2026) gross edge ceiling 1.05-1.50 pt, quoted in the brief as established.
  - friction 1.25pt = $2.50 per MNQ round trip.
"""
import sqlite3, numpy as np, pandas as pd
OUT="/home/alphabot/gazbot7/reports/regime_2026-09-12/reframe"
c=sqlite3.connect('file:/home/alphabot/gazbot7/data/gazbot7.db?mode=ro',uri=True)
df=pd.read_sql("""select substr(closed_at,1,10) d, gate, qty, pnl_usd, fees_usd, exit_reason,
   (julianday(closed_at)-julianday(opened_at))*1440 hold_min from trades where data_quality is null""",c)
one=df[df.qty==1]
gates=one[~one.gate.str.startswith("day_rider")]
rider=one[one.gate.str.startswith("day_rider")]
print("=== THE LIVE RECORD, 2026-07-16..2026-09-11, 45 sessions ===")
print(f"ALL booked trades          n={len(df):>4}  lots={df.qty.sum():>6.0f}  net ${df.pnl_usd.sum():>10,.2f}  commissions ${df.fees_usd.sum():>8,.2f}")
for lab,x in [("qty=1 (uncontaminated)",one),("  of which GATE roster",gates),("  of which DAY RIDER",rider)]:
    g=x.pnl_usd.sum()+x.fees_usd.sum()
    print(f"{lab:<26} n={len(x):>4}  net ${x.pnl_usd.sum():>10,.2f}  gross-of-commission ${g:>9,.2f}  = {g/len(x)/2.0:>6.2f} pt/trade  median hold {x.hold_min.median():>5.1f} min")
mult=df[df.qty>1]
print(f"qty>1 (FABRICATED FILLS)   n={len(mult):>4}  lots={mult.qty.sum():>6.0f}  net ${mult.pnl_usd.sum():>10,.2f}   <- not a measurement")

print("\n=== PER-TRADE DISPERSION (qty=1, gate roster) ===")
v=gates.pnl_usd.values
sd=v.std(ddof=1); mu=v.mean()
print(f"n={len(v)}  mean ${mu:.2f}  sd ${sd:.2f}  = {sd/2.0:.1f} MNQ points per trade")
tpd=len(df)/45
print(f"trade rate: {tpd:.1f} trades/session ({len(df)} trades / 45 sessions)")

print("\n=== WHAT IT COSTS JUST TO PLAY, per year, at the desk's own trade rate ===")
fee=1.50; spread=0.25*2.0  # $1.50/RT commission + one 0.25pt tick = $0.50
for n,lab in [(tpd,"the desk's actual rate"),(11,"the brief's ~11 signals/day"),(1,"one trade a day")]:
    ann=n*252*(fee+spread)
    print(f"  {n:>5.1f} trades/session ({lab:<24}) -> ${ann:>8,.0f}/yr per lot = {100*ann/30000:>5.1f}% of a $30,000 account, BEFORE any P&L")

print("\n=== HOW LONG TO PROVE AN EDGE AT THE DOCUMENTED CEILING ===")
print("  net edge = gross ceiling - 1.25pt friction; sd = this desk's measured %.1f pt/trade" % (sd/2.0))
print(f"  {'gross pt':>9} {'net pt':>7} {'$/trade':>8} {'trades for t=2':>15} {'sessions @%.0f/day'%tpd:>18} {'years':>7}")
for gr in (1.05,1.25,1.50,1.75,2.00,3.00):
    net=gr-1.25
    if net<=0:
        print(f"  {gr:>9.2f} {net:>7.2f} {net*2:>8.2f}   never - negative expectancy"); continue
    n_needed=(2*(sd/2.0)/net)**2
    print(f"  {gr:>9.2f} {net:>7.2f} {net*2:>8.2f} {n_needed:>15,.0f} {n_needed/tpd:>18,.0f} {n_needed/tpd/252:>7.1f}")

print("\n=== THE SAME ARITHMETIC FOR A ONE-TRADE-A-DAY, OVERNIGHT-HORIZON BOOK ===")
a=pd.read_csv(f"{OUT}/a3_arms_ET.csv"); r=a[(a.arm=='ONITE')&(a.period=='ALL')].iloc[0]
sd_on=r.sd; mu_on=r.net_pt
print(f"  MNQ overnight arm: net {mu_on:.2f}pt, sd {sd_on:.1f}pt -> sessions for t=2 = {(2*sd_on/mu_on)**2:,.0f} = {(2*sd_on/mu_on)**2/252:.1f} years")
print(f"  ratio of sd to edge:  intraday gate roster {sd/2.0/0.25:,.0f}x (at a +0.25pt net edge)   overnight {sd_on/mu_on:,.1f}x")
print("\nNOTE the direction of that comparison: the overnight arm's edge-to-noise ratio is ~%.0fx better"
      % (((sd/2.0)/0.25)/(sd_on/mu_on)))
