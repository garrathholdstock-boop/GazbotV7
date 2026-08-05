#!/usr/bin/env python3
"""SIM REGISTRY — a permanent NUMBER for every sim, so one can be named in one word.

Operator, 2026-08-05: "can you make sure all sims have a number identifier so its easy for me to ask
you?" — after asking about "sw grind a and b k20", four tokens for one arm of one A/B.

★ THE WHOLE POINT IS THAT THE NUMBERS NEVER MOVE. Numbering by sort order would renumber the slate
every time a variant is added or cut — and the slate already went 28 -> 18 on 08-02. "Sim 14" would
then quietly mean something different next week, which is worse than having no numbers at all. So:

    IDs are ALLOCATED ONCE and PERSISTED to data/sim_registry.json. New sims take the next free number.
    A retired sim KEEPS its number forever, shows as RETIRED, and the number is NEVER reissued.

An index is a position; an identifier is a promise. This file keeps the promise.

★ SOURCES ARE UNIONED. A sim exists if the live slate declares it OR either book has rows for it.
Neither alone is complete — a freshly-armed arm has no rows yet, a retired one has rows but no
declaration — and reading one and calling it "all the sims" is the failure that had the dashboard
showing 6 of 8 gates.

★ P&L COMES FROM shadow_real.real_pnl, NEVER shadow_trades.ceiling_pnl. The latter is a bar-price
ceiling the repricer has not honoured yet; memory [[shadow-sim-understates-losses]] measured live
losses at 1.1-3.1x modelled, so every shadow loss is a FLOOR. Rows still awaiting repricing are
flagged, not silently averaged in.

★ OPEN POSITIONS ARE COUNTED AND SHOWN, because a paired A/B read on closed trades alone would
flatter whichever arm defers its losers. `open` here = entries recorded with no exit yet.

★ BUT THE BIAS THAT ACTUALLY BITES ON THIS DESK IS OCCUPANCY, NOT OPEN TRADES. Every arm holds ONE
position at a time, so a wider-stop arm holds longer and simply MISSES entries its tight-stop twin
takes. On 2026-08-05 sw_grind_B_k20 held 22:09->05:28 and sat out five entries that cost k10 $126.50 —
it looked better partly by being busy. That is a real mechanism, not an artefact, but it is luck about
WHICH entries the long hold covered, and two days cannot tell the difference. Compare arms on the
SHARED entries first, then state the occupancy effect separately.

  PYTHONPATH=src .venv/bin/python scripts/sim_registry.py                  # numbered table
  PYTHONPATH=src .venv/bin/python scripts/sim_registry.py --stats          # + P&L per sim
  PYTHONPATH=src .venv/bin/python scripts/sim_registry.py --id 14          # one sim by number
  PYTHONPATH=src .venv/bin/python scripts/sim_registry.py --match sw_grind # by name fragment
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

GB = "/home/alphabot/gazbot7"
REG = f"{GB}/data/sim_registry.json"
SHADOW = f"{GB}/data/shadow.db"


def _ro(path):
    if not os.path.exists(path):
        return None
    try:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    except Exception:
        return None


def discover():
    """Every sim name findable, from the declared slate AND from the book. {name: {sources}}."""
    found: dict[str, set] = {}

    def add(n, src):
        if n:
            found.setdefault(str(n), set()).add(src)

    try:
        sys.path.insert(0, f"{GB}/src")
        import gazbot7.runner as rn
        import gazbot7.shadow as sh                                    # noqa: F401
        for mod in (rn, sh):
            for attr in dir(mod):
                if not any(k in attr.lower() for k in ("slate", "variant", "shadow")):
                    continue
                obj = getattr(mod, attr)
                try:
                    seq = obj() if callable(obj) else obj
                    for v in (seq or []):
                        add(getattr(v, "name", None), "slate")
                except Exception:
                    continue
    except Exception:
        pass

    con = _ro(SHADOW)
    if con:
        for tbl in ("shadow_real", "shadow_trades"):
            try:
                for (n,) in con.execute(
                        f"SELECT DISTINCT strategy FROM {tbl} WHERE strategy IS NOT NULL"):
                    add(n, "book")
            except Exception:
                continue
        con.close()
    return found


def load_reg():
    if os.path.exists(REG):
        try:
            with open(REG) as fh:
                d = json.load(fh)
            return int(d.get("next", 1)), dict(d.get("ids", {}))
        except Exception:
            pass
    return 1, {}


def save_reg(nxt, ids):
    tmp = REG + ".tmp"
    with open(tmp, "w") as fh:
        json.dump({"next": nxt, "ids": ids}, fh, indent=1, sort_keys=True)
    os.replace(tmp, REG)          # atomic — a half-written registry would scramble every ID


def family(name: str) -> str:
    n = name.lower()
    if n.startswith("sw_"):
        return "stop-width A/B"
    if n.startswith("cx_"):
        return "clip A/B"
    if n.startswith("cl-"):
        return "courtroom"
    return "shadow variant"


def stats():
    """Per-sim: closed count, repriced P&L, win rate, unrepriced rows, and OPEN entries."""
    con = _ro(SHADOW)
    if not con:
        return {}
    out: dict[str, dict] = {}
    try:
        q = """SELECT t.strategy,
                      sum(CASE WHEN t.exit_ts IS NOT NULL THEN 1 ELSE 0 END),
                      sum(CASE WHEN t.exit_ts IS NULL  THEN 1 ELSE 0 END),
                      sum(CASE WHEN r.real_pnl IS NOT NULL THEN r.real_pnl ELSE 0 END),
                      sum(CASE WHEN r.real_pnl > 0 THEN 1 ELSE 0 END),
                      sum(CASE WHEN r.real_pnl IS NULL THEN 1 ELSE 0 END)
               FROM shadow_trades t LEFT JOIN shadow_real r ON r.trade_id = t.id
               GROUP BY 1"""
        for s, closed, opn, tot, w, unrep in con.execute(q):
            out[str(s)] = {"closed": closed or 0, "open": opn or 0, "tot": float(tot or 0),
                           "win": int(w or 0), "unrepriced": int(unrep or 0)}
    except Exception:
        pass
    con.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--id", type=int)
    ap.add_argument("--match")
    a = ap.parse_args()

    found = discover()
    nxt, ids = load_reg()
    known = set(ids)
    for n in sorted(found):                       # sorted so the first build is deterministic
        if n not in ids:
            ids[n] = nxt
            nxt += 1
    if set(ids) != known:
        save_reg(nxt, ids)
        print(f"registry: {len(set(ids) - known)} new sim(s) numbered, {len(ids)} total -> {REG}\n")

    rows = sorted((i, n) for n, i in ids.items())
    if a.id:
        rows = [r for r in rows if r[0] == a.id]
    if a.match:
        rows = [r for r in rows if a.match.lower() in r[1].lower()]
    st = stats() if a.stats else {}

    hdr = f"{'#':>4}  {'sim':<26}{'family':<17}{'state':<9}"
    print(hdr + (f"{'closed':>7}{'open':>6}{'P&L':>10}{'win':>6}  flag" if a.stats else "source"))
    fam = None
    for i, n in rows:
        f = family(n)
        if a.stats and f != fam:
            fam = f
        src = found.get(n, set())
        line = f"{i:>4}  {n:<26}{f:<17}{('LIVE' if src else 'RETIRED'):<9}"
        if a.stats:
            s = st.get(n)
            if s and (s["closed"] or s["open"]):
                wr = 100 * s["win"] / s["closed"] if s["closed"] else 0
                line += f"{s['closed']:>7}{s['open']:>6}{s['tot']:>10.0f}{wr:>5.0f}%"
                flags = []
                if s["open"]:
                    flags.append("OPEN-BIAS")
                if s["unrepriced"]:
                    flags.append(f"{s['unrepriced']} unrepriced")
                if s["closed"] < 40:
                    flags.append("n<40")
                line += "  " + ("; ".join(flags) if flags else "ok")
            else:
                line += f"{'—':>7}{'—':>6}{'—':>10}{'—':>6}  no rows"
        else:
            line += "  " + (",".join(sorted(src)) if src else "—")
        print(line)
    if not rows:
        print("  (no sims matched)")

    print(f"\n{len(ids)} sims numbered. Numbers are PERMANENT — a retired sim keeps its number and it")
    print('is never reissued. Ask by number: "how is sim 14 doing?"')
    if a.stats:
        print("⚠ OPEN-BIAS: that sim holds unclosed entries — exclude it from any paired A/B read.")
        print("⚠ OCCUPANCY: an arm holds ONE position at a time, so it MISSES entries while busy. A")
        print("  wider stop holds longer and can lead partly by sitting out a bad patch. Compare the")
        print("  SHARED entries first, then state the occupancy effect separately.")
        print("⚠ n<40: below the threshold at which a forward A/B is allowed to claim anything.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
