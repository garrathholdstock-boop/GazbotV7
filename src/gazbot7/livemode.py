"""THE PAPER/REAL BOUNDARY — an account allowlist, and a LIVE mode that must earn its limits.

★★★2026-09-26 AUDIT, FINDING 09. NOT ONE ACCOUNT NUMBER APPEARED ANYWHERE IN THIS CODEBASE. The
only thing separating paper from real money was which credentials the `ib-gateway` container logs in
with: change that one environment variable and all three desks trade a live account instantly, with
no code change, no confirmation, and the same risk limits — which per finding 03 are none.

Operator, on the January plan: "if i want to put $30k into this in january, what do we need on it to
make it safe". This is the first thing. A boundary that lives in a container's environment is not a
boundary; it is a coincidence.

★ WHAT THIS DOES, AND THE ONE THING IT DOES NOT.
  · `assert_account_allowed()` — refuses to proceed against an account nobody listed. This is the
    accident guard: a gateway pointed at the wrong login stops, loudly, instead of trading.
  · `mode()` — PAPER or LIVE, derived from the ACCOUNT, never from a flag someone can forget. An
    account that is not in either list is UNKNOWN, which is refused, not guessed.
  · `live_preflight()` — in LIVE mode the protections that are optional on paper become mandatory,
    and the desk refuses to start without them. On paper it returns clean and changes nothing.
  · It does NOT arm anything by itself and it CANNOT stop paper trading. Every function below is a
    no-op while the connected account is the paper account.

⚠⚠⚠ THE PAPER DESK MUST KEEP WORKING EXACTLY AS IT DOES TODAY. Operator, 2026-09-26: "just dont
switch on any kill switches while paper trading. i want to be able to trade and learn." So the
LIVE-only requirements below are gated on `mode() == "LIVE"` and nothing else, and
`tests/test_livemode.py` asserts that a paper account passes every check with nothing armed.

⚠ Deliberately NO network access in this module. It is handed an account id by whoever already has
a connection, so it can be tested without a broker and can never itself be the thing that hangs.
"""

from __future__ import annotations

import json
import os

GB = "/home/alphabot/gazbot7"
CONF = f"{GB}/data/live_mode.json"

#: The paper account this desk has always run on. Hard-coded as the FLOOR, not the whole story —
#: data/live_mode.json may add more — so that a missing or corrupt config file cannot silently
#: un-recognise the paper account and take the desk down. Fail-safe direction: paper keeps working.
PAPER_ACCOUNTS = ("DUQ191770",)

#: Real-money accounts. Empty until the operator puts one here deliberately. An account appearing
#: in this list is the ONLY way LIVE mode can ever be entered, and doing so turns on every
#: requirement in live_preflight().
LIVE_ACCOUNTS: tuple[str, ...] = ()


def _conf() -> dict:
    try:
        with open(CONF) as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


def paper_accounts() -> tuple[str, ...]:
    c = _conf().get("paper_accounts") or []
    return tuple(dict.fromkeys([*PAPER_ACCOUNTS, *(str(a).strip() for a in c if str(a).strip())]))


def live_accounts() -> tuple[str, ...]:
    c = _conf().get("live_accounts") or []
    return tuple(dict.fromkeys([*LIVE_ACCOUNTS, *(str(a).strip() for a in c if str(a).strip())]))


def mode(account: str | None) -> str:
    """'PAPER' | 'LIVE' | 'UNKNOWN', decided by the ACCOUNT ID.

    ⚠ Never by a config flag. A flag is a thing someone forgets to change in both directions; the
    account id is what the money actually sits in. `UNKNOWN` exists so that an unlisted account can
    never be quietly treated as either — it is refused by assert_account_allowed().
    """
    # ⚠ CASE- AND WHITESPACE-INSENSITIVE (2026-09-26 review). An account id is the same account
    # whatever its case, so a hand-typed config entry must not become a refused order — that is a
    # false refusal with no safety benefit, and this guard exists to stop ACCIDENTS, not typos.
    a = (account or "").strip().upper()
    if not a:
        return "UNKNOWN"
    if a in {x.upper() for x in paper_accounts()}:
        return "PAPER"
    if a in {x.upper() for x in live_accounts()}:
        return "LIVE"
    return "UNKNOWN"


class AccountNotAllowed(RuntimeError):
    """The connected account is not one anybody listed. Refuse rather than trade."""


def assert_account_allowed(account: str | None, *, what: str = "place an order") -> str:
    """Return the mode, or raise. THE ACCIDENT GUARD.

    ⚠ It is not security — nothing here stops a determined change to the config. It makes the
    ACCIDENT impossible, which is the failure that actually happens: a gateway relogged into the
    wrong account, a copied container env, a restored backup pointing somewhere else. The same
    reasoning as web.py's ORDER_PATHS Referer gate after the 2026-09-24 −$842.50 incident.
    """
    m = mode(account)
    if m == "UNKNOWN":
        raise AccountNotAllowed(
            f"refusing to {what}: account {account!r} is in neither the paper nor the live "
            f"allowlist (paper={paper_accounts()}, live={live_accounts()}). If this is intended, "
            f"add it to {CONF} deliberately.")
    return m


# ── LIVE-only requirements ────────────────────────────────────────────────────────────────────
#: Each entry: (key in live_mode.json, human description of why real money needs it).
#: ⚠ These are the audit's MUST tier. A desk that cannot satisfy them has no business holding $30k,
#: and the honest way to enforce that is to refuse to start rather than to warn in a log.
LIVE_REQUIREMENTS = (
    ("venue_stop_armed", "a resting catastrophe stop at the broker — the only protection that "
                         "survives this box dying (audit finding 01)"),
    # ★★★2026-09-26, added by the adversarial review of the audit's own work. Arming the stop is not
    # the same as knowing it works, and on this desk that gap has a name:
    # [[stop-unfilled-contfuture-root-cause]] — "ContFuture stops don't trigger", banked and for a
    # long time unfixed. The rider's stop was placing a plain StopOrder on a ContFuture, i.e. the one
    # form already known not to fire; both defects are now corrected (concrete front month +
    # StopLimitOrder, copied from broker_adapter's proven pattern) and NEITHER IS VERIFIED LIVE,
    # because the switch has never been on.
    # So January cannot start on an assumption: set this only after watching a real stop REST at the
    # venue and FILL. Verify on the paper account with 1 lot and a deliberately near trigger.
    ("venue_stop_verified", "the catastrophe stop OBSERVED resting at the venue and filling — "
                            "arming it is not the same as knowing it works "
                            "([[stop-unfilled-contfuture-root-cause]])"),
    ("equity_loss_limit_usd", "an equity-sourced daily loss limit that can flatten, read from "
                              "IBKR and not from our own ledger (audit finding 03)"),
    ("max_lots", "an explicit lot ceiling — the clean book is single-lot positive and every "
                 "multi-lot number measures the simulator (audit finding 12)"),
    ("margin_floor_usd", "an excess-liquidity floor that pages (audit finding 02)"),
    ("deadman_url", "an off-box dead-man's switch, so silence is detectable (audit finding 08)"),
)


def live_preflight(account: str | None) -> tuple[bool, list[str]]:
    """(ok, missing) — what real money requires that is not configured yet.

    ⚠⚠ ON PAPER THIS ALWAYS RETURNS (True, []) AND CHECKS NOTHING. That is deliberate and tested:
    the paper desk must keep trading exactly as it does today while these are still being built.
    """
    if mode(account) != "LIVE":
        return True, []
    c = _conf()
    missing = [f"{k}: {why}" for k, why in LIVE_REQUIREMENTS if not c.get(k)]
    return (not missing), missing


def describe(account: str | None) -> str:
    """One line for a log or a health file. Says the mode AND what it implies."""
    m = mode(account)
    if m == "PAPER":
        return f"PAPER ({account}) — LIVE requirements not enforced, by design"
    if m == "LIVE":
        ok, missing = live_preflight(account)
        return (f"LIVE ({account}) — all {len(LIVE_REQUIREMENTS)} requirements configured" if ok
                else f"LIVE ({account}) — MISSING {len(missing)}: {'; '.join(missing)}")
    return f"UNKNOWN ACCOUNT ({account}) — refused"


def env_flag(name: str, default: bool = False) -> bool:
    """Small helper so the LIVE-only switches below read the same way everywhere."""
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")
