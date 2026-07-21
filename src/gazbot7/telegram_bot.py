"""GAZBOT V7 — Telegram command bot (the operator's phone control for the tournament).

The desk already SENDS to Telegram (notify.py); this is the RECEIVE side. Garrath texts a
small, safe command set and the bot actions it by writing the SAME ``gate_switches.env`` the
tournament re-reads live — so gates toggle from the phone, no restart, and it works even when
the Claude session is offline (it's a standing service).

SAFE BY DESIGN:
- Only the authorized chat_id (from alphabot2/.env TELEGRAM_CHAT) is obeyed; anything else is
  ignored (a stranger who finds the bot can do nothing).
- The ONLY mutating command is per-gate on/off (an intraday tactical switch — NEW entries only;
  an open position still exits normally). Everything else is READ-ONLY status. No flatten, no
  restart, no live-toggle, no roster change — those stay operator+Termius / the Saturday call.

Stdlib only (urllib) — no new deps. Clean-room; the command logic is pure + tested, the
long-poll loop is the thin I/O shell."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime

log = logging.getLogger("tgbot")

_ENV = "/home/alphabot/alphabot2/.env"
_DATA = "/home/alphabot/gazbot7/data"
_SWITCH = os.path.join(_DATA, "gate_switches.env")
_HEALTH = os.path.join(_DATA, "core_health.json")
_DB = os.path.join(_DATA, "gazbot7.db")
_OFF = ("off", "0", "no", "false", "disable", "disabled")

_HELP = ("GAZBOT tournament — commands:\n"
         "/status — desk health + open slots\n"
         "/gates — each gate: on/off + today P&L\n"
         "/off <gate> — stop a gate's NEW entries today (open pos still exits)\n"
         "/on <gate> — re-enable a gate\n"
         "/help — this")


# ── env + roster ──────────────────────────────────────────────────────────────
def load_env(path: str = _ENV) -> dict:
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return env


def roster() -> list:
    from .slot_strategy import tournament_slots
    return [s.tag for s in tournament_slots()]


# ── pure command logic (tested) ────────────────────────────────────────────────
def parse_command(text: str) -> tuple:
    """'/off thrust_short' → ('off', 'thrust_short'). Strips a @botname suffix. Lowercases
    the command, keeps the arg as given. Non-commands → ('', '')."""
    text = (text or "").strip()
    if not text.startswith("/"):
        return ("", "")
    parts = text.split()
    cmd = parts[0][1:].split("@", 1)[0].lower()
    arg = parts[1] if len(parts) > 1 else ""
    return (cmd, arg)


def apply_gate_switch(text: str, gate: str, state: str) -> str:
    """Return the switch-file content with ``gate=state`` set — updating its line in place or
    appending, preserving all other lines/comments. Pure."""
    out, found = [], False
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s and s.split("=", 1)[0].strip() == gate:
            out.append(f"{gate}={state}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{gate}={state}")
    return "\n".join(out) + "\n"


def disabled_from(text: str) -> set:
    off = set()
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            if v.strip().lower() in _OFF:
                off.add(k.strip())
    return off


# ── read-only renders ──────────────────────────────────────────────────────────
def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def render_status(health: dict, disabled: set) -> str:
    if not health:
        return "desk: no health snapshot (tournament down?)"
    p = health.get("protection") or {}
    slots = p.get("slots") or []
    held = ", ".join(f"{s.get('gate')} {s.get('side')} {s.get('qty'):g}"
                     f"{'' if s.get('stop_coid') else ' ⚠NAKED'}" for s in slots) or "flat"
    safety = "HALTED" if health.get("halted") else ("⚠UNVERIFIED" if p.get("unverified_cycles") else "ok")
    line = (f"desk: {'HEALTHY' if health.get('healthy') else 'UNHEALTHY'} · {safety} · "
            f"live={health.get('place_live')}\nholding: {held}")
    if disabled:
        line += f"\ndisabled today: {', '.join(sorted(disabled))}"
    return line


def render_gates(disabled: set, pnl_by_gate: dict) -> str:
    rows = []
    for g in roster():
        state = "OFF" if g in disabled else "on"
        pnl = pnl_by_gate.get(g)
        pstr = f"${pnl:+.0f}" if pnl is not None else "—"
        rows.append(f"{'🔴' if g in disabled else '🟢'} {g:16} {state:3}  today {pstr}")
    return "gates (🟢on/🔴off · today P&L):\n" + "\n".join(rows)


def _today_pnl_by_gate(db_path=_DB) -> dict:
    out = {}
    try:
        from . import pnl as pnlmod
        t0 = pnlmod.paris_day_start_utc(datetime.now(UTC))
        c = sqlite3.connect(db_path)
        for gate, net in c.execute(
            "SELECT gate, ROUND(SUM(pnl_usd),1) FROM trades WHERE symbol='MNQ' AND closed_at>=? "
            "AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE') GROUP BY gate", (t0,)):
            out[gate] = net
        c.close()
    except Exception:
        pass
    return out


# ── command dispatch (I/O: reads health/db, writes the switch file) ─────────────
def handle(cmd: str, arg: str, *, switch_path=_SWITCH, health_path=_HEALTH, db_path=_DB) -> str:
    gates = roster()
    if cmd in ("start", "help", ""):
        return _HELP
    if cmd == "status":
        health = json.loads(_read(health_path) or "{}") if _read(health_path) else {}
        return render_status(health, disabled_from(_read(switch_path)))
    if cmd == "gates":
        return render_gates(disabled_from(_read(switch_path)), _today_pnl_by_gate(db_path))
    if cmd in ("off", "on"):
        if not arg:
            return f"usage: /{cmd} <gate>  (gates: {', '.join(gates)})"
        if arg not in gates:
            return f"unknown gate '{arg}'. valid: {', '.join(gates)}"
        state = "off" if cmd == "off" else "on"
        new = apply_gate_switch(_read(switch_path), arg, state)
        try:
            tmp = switch_path + ".tmp"
            with open(tmp, "w") as f:
                f.write(new)
            os.replace(tmp, switch_path)
        except OSError as e:
            return f"failed to write switch file: {e}"
        verb = "DISABLED for the day (new entries stop; open position still exits)" if state == "off" \
            else "RE-ENABLED"
        return f"✓ {arg} {verb}. The tournament picks this up live (no restart)."
    return f"unknown command /{cmd}. /help for the list."


# ── the long-poll loop (I/O shell) ──────────────────────────────────────────────
def _api(token, method, params, timeout=35):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(url, data=data, timeout=timeout) as r:  # noqa: S310 (fixed api host)
        return json.loads(r.read())


def run(*, poll_s: int = 30) -> None:
    env = load_env()
    token, chat = env.get("TELEGRAM_TOKEN", ""), str(env.get("TELEGRAM_CHAT", ""))
    if not token or not chat:
        raise SystemExit("TELEGRAM_TOKEN/CHAT not configured in " + _ENV)
    log.info("tgbot up — authorized chat %s, gates=%s", chat, roster())
    offset = None
    while True:
        try:
            params = {"timeout": poll_s}
            if offset is not None:
                params["offset"] = offset
            res = _api(token, "getUpdates", params, timeout=poll_s + 10)
            for upd in res.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message") or {}
                if str(msg.get("chat", {}).get("id")) != chat:   # only the operator's chat
                    continue
                cmd, arg = parse_command(msg.get("text", ""))
                if not cmd:
                    continue
                reply = handle(cmd, arg)
                log.info("cmd /%s %s -> %s", cmd, arg, reply.splitlines()[0])
                try:
                    _api(token, "sendMessage", {"chat_id": chat, "text": reply}, timeout=15)
                except Exception:
                    log.warning("reply send failed")
        except Exception as e:  # a poll error must never kill the bot
            log.warning("poll error: %s", e)
            time.sleep(5)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    run()


if __name__ == "__main__":
    raise SystemExit(main())
