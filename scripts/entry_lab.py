#!/usr/bin/env python3
"""ENTRY LAB — is the drift CONFIRMATION a good entry, and is it STABLE?

Reads reports/entry_lab/signal_series.json (built by entry_chatter.py: the real drift.compute()
replayed minute-by-minute over the lake). Emits candidate entry rules as rider_lab session lists
(day, minute, dir) so the SHARED harness scores them — no re-derived P&L anywhere.

conf_min convention is rider_lab's: minute = number of session bars used by compute(), entry is the
OPEN of clock minute OPEN_MIN+minute+1.
"""
import json, statistics as st, sys
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")
import rider_lab as RL

SER = json.load(open("/home/alphabot/gazbot7/reports/entry_lab/signal_series.json"))

def series(day):
    return {r[0]: r for r in SER[day]["series"]}      # i -> [i, conf, dir, eff, rt, px, net]

def price_at(day, i):
    s = series(day)
    return s[i][5] if i in s else None

def entry_px(day, i):
    """what rider_lab will actually pay for conf_min=i (open of the NEXT bar ~ close of bar i)."""
    return price_at(day, i + 1)

# ── rule generators: day -> (minute, dir) or None ───────────────────────────────
def rule_persist(day, N=1, redir=False):
    """first i where `confirmed` has held N consecutive minutes in the SAME direction."""
    run, last = 0, ""
    for i, conf, d, eff, rt, px, net in SER[day]["series"]:
        if conf and d and (d == last or run == 0):
            run = run + 1 if d == last else 1
            last = d
            if run >= N:
                return (i, d)
        else:
            run, last = 0, ""
    return None

def rule_clock(day, minute, mode="drift"):
    """enter at a fixed session minute. direction: drift's net sign at that minute, or long-only."""
    s = series(day)
    if minute not in s:
        return None
    r = s[minute]
    if mode == "long":
        return (minute, "UP")
    d = r[2] or ("UP" if r[6] > 0 else "DOWN")
    return (minute, d)

def rule_clock_conf(day, minute):
    """fixed clock, but only take the day if drift is confirmed AT that minute."""
    s = series(day)
    if minute not in s or not s[minute][1] or not s[minute][2]:
        return None
    return (minute, s[minute][2])

def sess_from(rule, longonly=False, shortonly=False):
    out = []
    for day in sorted(SER):
        r = rule(day)
        if not r:
            continue
        m, d = r
        if longonly and d != "UP":
            continue
        if shortonly and d != "DOWN":
            continue
        out.append({"day": day, "minute": m, "dir": d, "year": day[:4]})
    return out

# ── scoring: every rule reported across entry_delay_min 0/2/4/8, split by year ──
DELAYS = (0, 2, 4, 8)

def score(con, S, cfg=None, label=""):
    import copy
    cfg = copy.copy(cfg or RL.Cfg())
    if not S:
        raise ValueError("empty session list")
    out = {"label": label, "n_days": len(S), "by_delay": {}}
    for dly in DELAYS:
        cfg.entry_delay_min = dly
        rows = RL.run_all(con, cfg, S)
        s = RL.summarise(rows, f"d{dly}")
        s["y2025"] = RL.summarise([r for r in rows if r["day"][:4] == "2025"])
        s["y2026"] = RL.summarise([r for r in rows if r["day"][:4] == "2026"])
        s["up"] = RL.summarise([r for r in rows if r["dir"] == "UP"])
        s["dn"] = RL.summarise([r for r in rows if r["dir"] == "DOWN"])
        out["by_delay"][dly] = s
    tots = [out["by_delay"][d]["total"] for d in DELAYS]
    out["min_total"] = min(tots)
    out["spread"] = max(tots) - min(tots)
    out["all_green"] = all(t > 0 for t in tots)
    return out

def line(r):
    b = r["by_delay"]
    return (f"{r['label']:<34} n={r['n_days']:>3} | "
            + " ".join(f"d{d}:{b[d]['total']:>+8.0f}" for d in DELAYS)
            + f" | min {r['min_total']:>+8.0f} spread {r['spread']:>8.0f}"
            + f" | 25:{b[0]['y2025']['total']:>+7.0f}/{b[8]['y2025']['total']:>+7.0f}"
            + f" 26:{b[0]['y2026']['total']:>+7.0f}/{b[8]['y2026']['total']:>+7.0f}"
            + f" | grn {b[0]['green']:>4.1f}/{b[8]['green']:>4.1f}")

def rule_retrace(day, frac=0.5, N=1, deadline=90, need_bars=True):
    """After the drift confirms, DON'T chase. Wait for price to trade back to
    open + frac*(conf_px - open) and enter on the next bar. frac=1 -> the confirmation price itself
    (immediate), frac=0 -> all the way back to the 13:30 open. No touch by `deadline` -> no trade."""
    r = rule_persist(day, N)
    if not r:
        return None
    i, d = r
    s = series(day)
    op = SER[day]["open"]
    conf_px = s[i][5]
    lim = op + frac * (conf_px - op)
    sgn = 1 if d == "UP" else -1
    for j in range(i, min(deadline, max(s)) + 1):
        px = s[j][5]
        if sgn * (px - lim) <= 0:
            return (j, d)
    return None
