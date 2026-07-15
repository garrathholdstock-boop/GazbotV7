"""GAZBOT V7 — execution health monitor (D9). Fills-based, no false positives.

The V5 monitor CRIT'd on a benign event: a partial-fill scalp that recorded via
the ~2-min backfill looked like "fills WEDGED", firing an unnecessary gateway
reboot that cascaded (re-stuck the 5s farm → MD bounce). That happened because
V5 conflated "recording deferred" with "fills ceased".

In V7 that conflation is impossible: there is **no backfill path** — every fill
is a real-time execDetails fill recorded atomically (D3). So the monitor measures
ACTUAL fills, and a CRIT means fills genuinely ceased while signals fired — a real
wedge, unambiguously. A normal 2-lot scalp (the thing that false-CRIT'd V5) reads
OK. Clean-room: nothing copied.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HealthVerdict:
    submitted: int
    fills: int
    rejects: int
    status: str  # OK / WARN / CRIT
    detail: str


def classify_execution(*, submitted: int, fills: int, rejects: int, min_submitted_crit: int = 3) -> tuple[str, str]:
    """Pure classifier. CRIT only when fills actually ceased under real activity."""
    if rejects >= min_submitted_crit and fills == 0:
        return "CRIT", f"{rejects} rejects / 0 fills — orders rejected, execution down"
    if submitted >= min_submitted_crit and fills == 0:
        return "CRIT", f"{submitted} signals submitted / 0 fills — execution WEDGED"
    if submitted > 0 and fills == 0:
        return "WARN", f"{submitted} submitted / 0 fills (below CRIT threshold — watch)"
    return "OK", f"{fills} fills / {submitted} submitted / {rejects} rejects"


def execution_health(store, *, since_iso: str) -> HealthVerdict:
    submitted = store.execute(
        "SELECT COUNT(*) FROM signals WHERE outcome='submitted' AND ts>=?", (since_iso,)
    ).fetchone()[0]
    rejects = store.execute(
        "SELECT COUNT(*) FROM signals WHERE outcome='rejected' AND ts>=?", (since_iso,)
    ).fetchone()[0]
    fills = store.execute(
        "SELECT COUNT(*) FROM fills WHERE ingested_at>=?", (since_iso,)
    ).fetchone()[0]
    status, detail = classify_execution(submitted=submitted, fills=fills, rejects=rejects)
    return HealthVerdict(submitted, fills, rejects, status, detail)
