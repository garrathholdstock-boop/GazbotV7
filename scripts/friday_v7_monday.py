#!/usr/bin/env python3
"""Build the MONDAY PLAYBOOK from reports/friday_v7/plays.json.

One card per play, grouped by the window in which it is safe to do it. Every card carries the
five things the operator asked for and nothing is allowed to be missing:

    the gate / mechanism · the regime condition that ARMS it · the EXIT ·
    the evidence TIER (LIVE / SHADOW / PARKED / REFUTED) · the KILL CRITERION

It reads the SAME plays.json the Friday report's action card is rendered from, so the two
documents cannot drift apart — that was the whole point of moving number/owner/revert onto the
play itself.

  python3 scripts/friday_v7_monday.py --slug 2026-08-08
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import pathlib
import re
import sys

PLAYS = "/home/alphabot/gazbot7/reports/friday_v7/plays.json"
OUT = "/home/alphabot/gazbot7/src/gazbot7/web_static"

WINDOWS = (
    # ★2026-08-08 — ordered by EXECUTION LOGIC, not by headline size. Work them top to bottom.
    ("SATURDAY", "w-sat", "Tonight — this window shuts at the Sunday 22:00 UTC reopen",
     "Code and config changes that need a tournament restart, in the order they should be done. "
     "<b>#1 and #2 are forced</b> — <code>gazbot7-gate-reactivate.timer</code> arms every "
     "<code>=off</code> gate at 22:00 UTC Sunday, so for both of them &ldquo;decide later&rdquo; is "
     "not one of the available states. <b>#3&ndash;#6 are safety and measurement</b>, and they come "
     "before the two experiments at the bottom because those experiments cannot be judged without "
     "them. None of this is a new mechanism."),
    ("MONDAY", "w-mon", "At the desk — switch-file and router config, all reversible",
     "Nothing here needs a deploy. Every one of these is <code>gate_switches.env</code>, the router "
     "config or a rule written into the tick prompt, and comes back inside five minutes. "
     "<b>#1 needs nothing but a decision</b> — the router already owns the lever, and it is the "
     "largest single number in the report."),
    ("BUILD", "w-build", "Next — nothing on this list goes live this week",
     "Shadow slates, instrumentation and the method fixes that decide whether next Friday's numbers "
     "can be trusted at all. <b>#1 gates #4</b>, and gates every future study that concludes "
     "&ldquo;exit earlier&rdquo;: the shadow repricer leaks past its own stops on 44% of trades, "
     "which is exactly the bias that makes cutting early look good. ⚠ Nothing from this week's "
     "greenfield is eligible to go live: 17 in-sample days earns SHADOW at most."),
    ("HOLD", "w-hold", "Leave alone — these are already right",
     "Standing findings and things already in production. The action is to <em>not</em> touch them, "
     "and the evidence for not touching them is written out so nobody re-opens the question."),
    ("NOT-AN-ACTION", "w-not", "Withdrawn / refuted — kept on the card so nobody re-proposes them",
     "Every one of these was a live proposal at some point this week. They are printed with the test "
     "that killed them so next Friday's agent does not dig the same hole."),
)

TIER_CLASS = {"LIVE": "t-live", "SHADOW": "t-shadow", "PARKED": "t-parked", "REFUTED": "t-refuted"}

CSS = """
:root{
  --bg:#f7f5f0; --card:#ffffff; --ink:#1a2230; --muted:#5a6472; --line:#e2ddd2;
  --navy:#0f2942; --sat:#a4262c; --mon:#0f2942; --build:#8a6d0b; --hold:#1f6f43; --not:#6b7280;
  --live:#1f6f43; --shadow:#b8860b; --parked:#4b5563; --refuted:#c0392b;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font:16px/1.6 Georgia,"Iowan Old Style",serif;-webkit-text-size-adjust:100%}
.wrap{max-width:1080px;margin:0 auto;padding:0 18px 72px}
.masthead{background:var(--navy);color:#fff;margin:0 -18px 26px;padding:34px 24px 28px}
.masthead .kicker{font:700 11px/1.4 ui-sans-serif,system-ui,sans-serif;letter-spacing:.18em;
                  text-transform:uppercase;color:#9fc6e8}
.masthead h1{margin:.22em 0 .16em;font-size:2.05em;line-height:1.15;letter-spacing:-.01em}
.masthead .dates{margin:0;color:#c3d4e4;font-size:.95em}
@media(min-width:760px){.masthead{margin:0 -18px 30px;border-radius:0 0 14px 14px}}

.intro{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 22px;
       margin:0 0 26px}
.intro p{margin:.5em 0}
.intro p:first-child{margin-top:0}.intro p:last-child{margin-bottom:0}

.counts{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0 0;padding:0;list-style:none}
.counts li{font:700 12px/1 ui-sans-serif,system-ui,sans-serif;letter-spacing:.06em;
           text-transform:uppercase;color:#fff;border-radius:999px;padding:8px 13px}
.c-sat{background:var(--sat)}.c-mon{background:var(--mon)}.c-build{background:var(--build)}
.c-hold{background:var(--hold)}.c-not{background:var(--not)}

h2.win{margin:36px 0 2px;padding:11px 16px;border-radius:10px 10px 0 0;color:#fff;
       font:700 14px/1.35 ui-sans-serif,system-ui,sans-serif;letter-spacing:.09em;text-transform:uppercase}
.w-sat{background:var(--sat)}.w-mon{background:var(--mon)}.w-build{background:var(--build)}
.w-hold{background:var(--hold)}.w-not{background:var(--not)}
.winsub{margin:0 0 18px;padding:11px 16px;background:#efece4;border:1px solid var(--line);
        border-top:0;border-radius:0 0 10px 10px;color:var(--muted);font-size:.93em}

.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 22px;
      margin:0 0 16px}
.card>header{display:flex;gap:12px;align-items:flex-start;flex-wrap:wrap}
.rk{flex:0 0 auto;min-width:2.1em;height:2.1em;display:grid;place-items:center;background:var(--navy);
    color:#fff;border-radius:8px;font:800 15px/1 ui-sans-serif,system-ui,sans-serif}
.card h3{flex:1 1 260px;margin:0;font-size:1.13em;line-height:1.35;color:var(--navy)}
.tier{flex:0 0 auto;font:800 10.5px/1 ui-sans-serif,system-ui,sans-serif;letter-spacing:.1em;
      text-transform:uppercase;padding:7px 11px;border-radius:999px;color:#fff;white-space:nowrap}
.t-live{background:var(--live)}.t-shadow{background:var(--shadow)}
.t-parked{background:var(--parked)}.t-refuted{background:var(--refuted)}
.play{margin:14px 0 0;font-size:1.02em}

dl.spec{margin:16px 0 0;padding:0;display:grid;grid-template-columns:1fr;gap:0;
        border-top:1px solid var(--line)}
@media(min-width:720px){dl.spec{grid-template-columns:8.6em 1fr}}
dl.spec dt{padding:11px 0 3px;font:800 10.5px/1.4 ui-sans-serif,system-ui,sans-serif;
           letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
dl.spec dd{margin:0;padding:0 0 11px;border-bottom:1px solid var(--line)}
@media(min-width:720px){
  dl.spec dt{padding:12px 14px 12px 0;border-bottom:1px solid var(--line)}
  dl.spec dd{padding:12px 0}
}
dl.spec dd:last-of-type,dl.spec dt:last-of-type{border-bottom:0}
dd.kill{color:#7d1f13}
dd.num{font-size:.97em}

/* ★2026-08-08 — a blocked play must read as blocked before anything else on its card. */
.blocked{margin:13px 0 0;padding:10px 13px;border-radius:8px;font-size:.94em;
         background:#fdf2ef;border:1px solid #e3b6ab;color:#7d1f13}
.blocked b{letter-spacing:.03em}
.blocked code{background:#fff;border:1px solid #e3b6ab;border-radius:4px;padding:1px 5px}
/* DEFERRED reads amber, not red — it is a sequencing hold, not a defect. */
.deferred{margin:13px 0 0;padding:10px 13px;border-radius:8px;font-size:.94em;
          background:#fdf8ea;border:1px solid #ddc98a;color:#6b520a}
.deferred b{letter-spacing:.03em}
.deferred span{display:block;margin-top:5px;font-size:.93em;color:#7a6320}
/* ★ the play ledger — deliberately plain, so an ungraded row looks ungraded. */
.ledger{margin:12px 0 0;font-size:.86em;color:var(--muted)}
.ledger b{color:var(--ink)}
.ledger code{background:#f4f2ed;border:1px solid var(--line);border-radius:4px;padding:1px 6px}

/* ═══ THE PICKER ═══ carried over from the 07-31 playbook, same class names, same copy
   payload, same localStorage contract — so the operator's muscle memory still works and the
   text pasted back into chat parses the way it always has. */
.pk-card.m-live{border-left:4px solid #1f6f43}
.pk-card.m-shadow{border-left:4px solid #8a6d0b}
.pk-card.m-skip{border-left:4px solid #c9cdd3;background:#fbfbfa}
.pk-card.pk-static{border-left:4px solid #d9d4c8}
.pk-opts{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden;margin-top:13px}
.pk-opt{padding:8px 18px;font:600 13px ui-sans-serif,system-ui,sans-serif;cursor:pointer;
        background:#fff;border:0;border-right:1px solid var(--line);color:var(--muted)}
.pk-opt:last-child{border-right:0}
.pk-opt[data-mode=live].on{background:#eafaf0;color:#1f6f43}
.pk-opt[data-mode=shadow].on{background:#fff5e0;color:#8a6d0b}
.pk-opt[data-mode=skip].on{background:#eef0f2;color:var(--ink)}
.pk-opt:disabled{opacity:.32;cursor:not-allowed;text-decoration:line-through}
.pk-why{display:block;margin-top:7px;font-size:.82em;color:var(--muted);font-style:italic}
.pk-bar{position:sticky;bottom:12px;z-index:50;background:var(--navy);color:#fff;padding:14px 18px;
        border-radius:12px;margin:26px 0 10px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;
        font-family:ui-sans-serif,system-ui,sans-serif;box-shadow:0 4px 18px rgba(15,41,66,.25)}
.pk-bar .cnt{font-size:15px}.pk-bar .cnt b{font-size:20px}
.pk-btn{background:#8a6d0b;color:#fff;border:0;border-radius:8px;padding:11px 18px;
        font:700 14px ui-sans-serif,system-ui,sans-serif;cursor:pointer;margin-left:auto}
.pk-btn.alt{background:#0088cc;margin-left:8px}
.pk-btn.ghost{background:transparent;color:#fff;border:1px solid rgba(255,255,255,.45);margin-left:8px}
.pk-toast{position:fixed;left:50%;bottom:26px;transform:translate(-50%,14px);background:var(--navy);
  color:#fff;padding:12px 20px;border-radius:10px;font:600 14px ui-sans-serif,system-ui,sans-serif;
  z-index:1000;box-shadow:0 6px 24px rgba(15,41,66,.35);opacity:0;
  transition:opacity .25s,transform .25s;max-width:90vw;text-align:center}
.pk-toast.go{opacity:1;transform:translate(-50%,0)}
.pk-ov{position:fixed;inset:0;background:rgba(15,41,66,.55);z-index:999;display:flex;
       align-items:center;justify-content:center;padding:16px}
.pk-sheet{background:#fff;border-radius:14px;max-width:640px;width:100%;padding:18px;
          box-shadow:0 12px 40px rgba(0,0,0,.3);font-family:ui-sans-serif,system-ui,sans-serif}
.pk-sheet-h{font:700 17px ui-sans-serif,system-ui,sans-serif;color:var(--navy);margin-bottom:4px}
.pk-sheet-s{font-size:13.5px;color:var(--muted);margin-bottom:10px;line-height:1.5}
.pk-sheet-t{width:100%;height:230px;font:12.5px/1.5 ui-monospace,Menlo,monospace;padding:10px;
  border:1px solid var(--line);border-radius:9px;resize:vertical;color:var(--ink);background:#fbfbfc;
  -webkit-user-select:text;user-select:text}
.pk-sheet-b{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.pk-sheet-b .pk-btn{margin-left:0}
.pk-sheet .pk-btn.ghost{color:var(--muted);border-color:var(--line)}
@media print{.pk-bar,.pk-opts{display:none}}

.foot{margin:14px 0 0;padding:13px 15px;background:#faf8f4;border:1px solid var(--line);
      border-radius:9px;font-size:.9em;color:var(--muted)}
.foot b{color:var(--ink)}
.foot span+span{margin-left:.5em;padding-left:.7em;border-left:1px solid var(--line)}

code{background:#eee9df;padding:.1em .35em;border-radius:.25em;
     font:.86em/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-word}
.caveat{background:#fff6f4;border:1px solid #e0a99e;border-left:5px solid var(--refuted);
        border-radius:10px;padding:16px 20px;margin:26px 0 0}
.caveat h3{margin:0 0 .4em;font-size:1em;color:#8a1c10;letter-spacing:.05em;text-transform:uppercase}
.caveat p{margin:.5em 0}.caveat p:last-child{margin-bottom:0}
a{color:#12558a}
"""


def esc(s) -> str:
    return html.escape(str(s))


def tier_head(tier: str) -> str:
    return re.split(r"[^A-Z]", tier.strip().upper(), maxsplit=1)[0]


# ★2026-08-08 — which windows the operator actually PICKS on. HOLD is "leave alone, the action
# is to not touch it" and NOT-AN-ACTION is "withdrawn, kept so nobody re-proposes it"; neither
# is a decision, so both render static and stay out of the counts. That keeps the pasted picks
# to the 35 plays that are genuinely a choice.
PICKABLE = {"SATURDAY", "MONDAY", "BUILD"}


def default_mode(p: dict) -> tuple[str, bool, str]:
    """(default pick, is the LIVE option disabled, why) — from the play's own evidence tier.

    A REFUTED or PARKED play cannot be armed live off this card, and a play blocked on another
    play cannot be shipped at all yet. Disabling the button is better than trusting the reader
    to remember the tier three screens down.
    """
    head = tier_head(p["tier"])
    if p.get("blocked_by"):
        return "skip", True, f"LIVE is disabled — blocked on {p['blocked_by']}."
    if p.get("deferred_until"):
        return "skip", True, (f"LIVE is disabled this week — deferred until "
                              f"{p['deferred_until']}. The evidence is good; the hold is about "
                              f"being able to measure it.")
    if head == "LIVE":
        return "live", False, ""
    if head == "SHADOW":
        return "shadow", True, "LIVE is disabled — SHADOW tier must survive a week in shadow first."
    if head == "PARKED":
        return "skip", True, "LIVE is disabled — PARKED: the revival condition has not been met."
    return "skip", True, "LIVE is disabled — REFUTED. Kept on the card so it is not re-proposed."


def card(p: dict) -> str:
    tier = p["tier"]
    cls = TIER_CLASS.get(tier_head(tier), "t-parked")
    # ★2026-08-08 — a play that cannot be done yet must SAY SO at the top of its own card.
    # This week's one real dependency is the exhaustion exit revert waiting on the shadow
    # repricer fix; without the banner it reads as ready to ship.
    blocked = (f'<p class="blocked"><b>&#9888;&nbsp;BLOCKED</b> &mdash; do not ship this until '
               f'<code>{esc(p["blocked_by"])}</code> has landed.</p>'
               ) if p.get("blocked_by") else ""
    # ★2026-08-08 — DEFERRED is not BLOCKED and not REJECTED. The evidence is good; the play is
    # held because shipping it now would make another play unmeasurable. Say both halves, or it
    # gets read as a rejection and quietly dropped next week.
    if p.get("deferred_until"):
        blocked += (f'<p class="deferred"><b>&#8987;&nbsp;DEFERRED</b> &mdash; not rejected. '
                    f'Ship after {esc(p["deferred_until"])}. '
                    f'<span>{esc(p["deferred_reason"])}</span></p>')
    # ★ The play ledger, rendered so an unfilled row is obvious rather than invisible. This is
    # the field set the REV2 audit had to hand-derive for all 24 of last week's plays.
    st = esc(p.get("status") or "PROPOSED")
    ts = esc(p.get("shipped_ts") or "—")
    oc = esc(p.get("outcome") or "not yet graded")

    # ─── the picker ───
    mode, live_off, why = default_mode(p)
    pickable = p.get("window") in PICKABLE
    ref = f"{p.get('window', '')} #{p.get('rank', '—')} · {p['topic']}"
    if pickable:
        opts = ('<div class="pk-opts">'
                f'<button class="pk-opt" data-mode="live"'
                f'{" disabled title=" + chr(34) + esc(why) + chr(34) if live_off else ""}>Live</button>'
                '<button class="pk-opt" data-mode="shadow">Shadow</button>'
                '<button class="pk-opt" data-mode="skip">Skip</button></div>'
                + (f'<span class="pk-why">{esc(why)}</span>' if why else ''))
        attrs = (f' data-id="{esc(p["id"])}" data-default="{mode}" data-pick="1"')
        kls = f"card pk-card m-{mode}"
    else:
        opts, attrs, kls = "", ' data-pick="0"', "card pk-card pk-static"

    return f"""
<article class="{kls}" id="{esc(p['id'])}"{attrs}>
  <header>
    <span class="rk">{esc(p.get('rank', '—'))}</span>
    <h3 class="pk-ref" data-ref="{esc(ref)}">{esc(p['topic'])}</h3>
    <span class="tier {cls}">{esc(tier)}</span>
  </header>
  {blocked}
  <p class="play pk-play">{esc(p['play'])}</p>
  <dl class="spec">
    <dt>Mechanism</dt><dd>{esc(p['mechanism'])}</dd>
    <dt>Arms when</dt><dd>{esc(p['arms_when'])}</dd>
    <dt>Exit</dt><dd>{esc(p['exit'])}</dd>
    <dt>The number</dt><dd class="num">{esc(p['number'])}</dd>
    <dt>Kill criterion</dt><dd class="kill">{esc(p['kill'])}</dd>
    <dt>Why</dt><dd>{esc(p['rationale'])}</dd>
  </dl>
  <p class="ledger"><b>Ledger:</b> status <code>{st}</code>
    &nbsp;·&nbsp; shipped <code>{ts}</code>
    &nbsp;·&nbsp; outcome <code>{oc}</code></p>
  {opts}
  <p class="foot"><span><b>Owner:</b> {esc(p['owner'])}</span
    ><span><b>Revert:</b> {esc(p['revert'])}</span
    ><span><b>Evidence:</b> {esc(p['section_ref'])}</span
    ><span><b>Verify by:</b> {esc(p['verification'])}</span
    ><span><b>Mode:</b> {esc(p['suggested_mode'])}</span></p>
</article>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default=dt.date.today().isoformat())
    a = ap.parse_args()

    plays = json.loads(pathlib.Path(PLAYS).read_text())
    if not plays:
        print("FATAL — plays.json is empty; there is no playbook to build.", file=sys.stderr)
        return 2

    required = ("mechanism", "arms_when", "exit", "tier", "kill", "number", "owner", "revert")
    bad = [f"{p['id']}: {k}" for p in plays for k in required if not str(p.get(k, "")).strip()]
    if bad:
        print("FATAL — plays missing required playbook fields:", file=sys.stderr)
        for b in bad:
            print("  " + b, file=sys.stderr)
        return 3

    tiers: dict[str, int] = {}
    for p in plays:
        t = tier_head(p["tier"])
        tiers[t] = tiers.get(t, 0) + 1

    body = []
    counts = []
    for wname, cls, strap, blurb in WINDOWS:
        rows = sorted([p for p in plays if p.get("window") == wname],
                      key=lambda p: (p.get("rank", 99), p["id"]))
        counts.append(f'<li class="c-{cls[2:]}">{esc(wname)} · {len(rows)}</li>')
        # ★ the `pk-group` class is what the picker's groupOf() walks back to for the [WINDOW]
        # label in the copied text. Renaming it silently unlabels every pasted pick.
        body.append(f'<h2 class="win pk-group {cls}" id="w-{cls[2:]}">{esc(wname)} &nbsp;·&nbsp; {strap} '
                    f'&nbsp;·&nbsp; {len(rows)} {"play" if len(rows) == 1 else "plays"}</h2>')
        body.append(f'<p class="winsub">{blurb}</p>')
        body.extend(card(p) for p in rows)
    n_pick = sum(1 for p in plays if p.get("window") in PICKABLE)

    doc = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GAZBOT V7 — Monday playbook {esc(a.slug)}</title>
<style>{CSS}</style></head><body><div class="wrap">

<div class="masthead">
  <p class="kicker">GAZBOT V7 · MNQ futures desk · PAPER</p>
  <h1>The Monday playbook</h1>
  <p class="dates">Week of Mon 3 &rarr; Fri 7 August 2026 &nbsp;·&nbsp; built {esc(a.slug)}
     &nbsp;·&nbsp; {len(plays)} plays, five windows</p>
</div>

<div class="intro">
  <p>Every concrete recommendation from the Friday report, one card each, grouped by <strong>when it is
  safe to do it</strong> rather than by which section wrote it. This page and the report's action card are
  rendered from the same <code>reports/friday_v7/plays.json</code>, so they cannot disagree.</p>
  <p>Each card states the <strong>mechanism</strong>, the <strong>regime condition that arms it</strong>,
  the <strong>exit</strong>, the <strong>evidence tier</strong> and &mdash; the one that matters most
  &mdash; the <strong>kill criterion</strong>. A play with no way to be proven wrong does not belong on
  this card.</p>
  <p><strong>Evidence tiers across all {len(plays)} plays:</strong>
     LIVE {tiers.get('LIVE', 0)} &nbsp;·&nbsp; SHADOW {tiers.get('SHADOW', 0)} &nbsp;·&nbsp;
     PARKED {tiers.get('PARKED', 0)} &nbsp;·&nbsp; REFUTED {tiers.get('REFUTED', 0)}.
     <a href="/v7/static/weekly_{esc(a.slug)}.html">Read the full report &rarr;</a></p>
  <ul class="counts">{''.join(counts)}</ul>
</div>

{''.join(body)}

<div class="caveat">
  <h3>Read this before you size anything on this page</h3>
  <p><strong>Every repriced number is a ceiling.</strong> Fills are modelled at the exact
  stop/target/trail level with no slippage, and this desk's standing finding is that live losses run
  <strong>1.1&ndash;3.1&times; modelled</strong>. Treat the policy as the edge and the headline dollar as
  decoration.</p>
  <p><strong>The fee is $1.50 per round trip</strong> ($0.75/side) &mdash; venue truth, all 487 closed
  trades carry <code>fees_usd=1.50</code>. Every greenfield number was re-priced from the ~$5/RT the
  hunts originally used; the correction is linear and <em>helps</em> everything, so a loser it rescues
  was never killed by cost in the first place.</p>
  <p><strong>Nothing from this week's greenfield lab is a LIVE play.</strong> The OPEN RIDER is the only
  survivor of three hunts, its skeptic panel voted 2&ndash;1 rather than 3&ndash;0, and 17 in-sample days
  earns SHADOW at most. It is on this card as BUILD, with four conditions that must ALL clear before it
  is even discussed for promotion.</p>
  <p><strong>n is small nearly everywhere.</strong> Where a section could not compute something it says
  &ldquo;not computed&rdquo; rather than carrying a guess, and that convention is preserved here.</p>
</div>

<div class="pk-bar">
  <span class="cnt"><b id="nLive">0</b> live &nbsp; <b id="nShadow">0</b> shadow &nbsp;
    <b id="nSkip">0</b> skip</span>
  <button class="pk-btn" id="copyBtn">📋 Copy my picks</button>
  <button class="pk-btn alt" id="tgBtn">✈ Send to Telegram</button>
  <button class="pk-btn ghost" id="resetBtn">Reset</button>
</div>
<p class="foot">Picks live only in this browser until you send them. Nothing arms automatically &mdash;
every Live pick is a conversation first. HOLD and NOT-AN-ACTION cards carry no selector: the action
on those is to leave them alone.</p>

</div>
<script>
var KEY='gazPicks_{esc(a.slug)}';
var picks=JSON.parse(localStorage.getItem(KEY)||'{{}}');
function save(){{localStorage.setItem(KEY,JSON.stringify(picks));}}
document.querySelectorAll('.pk-card').forEach(function(c){{
  if(c.dataset.pick!=='1')return;
  var id=c.dataset.id; if(!(id in picks)) picks[id]=c.dataset.default;
  c.querySelectorAll('.pk-opt').forEach(function(b){{
    b.addEventListener('click',function(){{ if(b.disabled)return; picks[id]=b.dataset.mode; save(); paint(); }});
  }});
}});
function paint(){{
  var nL=0,nS=0,nK=0;
  document.querySelectorAll('.pk-card').forEach(function(c){{
    if(c.dataset.pick!=='1')return;
    var id=c.dataset.id, m=picks[id]||'skip';
    c.className='card pk-card m-'+m;
    c.querySelectorAll('.pk-opt').forEach(function(b){{ b.classList.toggle('on', b.dataset.mode===m && !b.disabled); }});
    if(m==='live')nL++; else if(m==='shadow')nS++; else nK++;
  }});
  document.getElementById('nLive').textContent=nL;
  document.getElementById('nShadow').textContent=nS;
  document.getElementById('nSkip').textContent=nK;
}}
function groupOf(c){{
  var n=c.previousElementSibling;
  while(n){{ if(n.classList&&n.classList.contains('pk-group')) return n.textContent.trim(); n=n.previousElementSibling; }}
  return '';
}}
function summary(){{
  var L=[],S=[],K=[];
  document.querySelectorAll('.pk-card').forEach(function(c){{
    if(c.dataset.pick!=='1')return;
    var id=c.dataset.id, m=picks[id]||'skip';
    var ref=c.querySelector('.pk-ref').getAttribute('data-ref').trim();
    var play=c.querySelector('.pk-play').textContent.trim().replace(/\\s+/g,' ');
    if(play.length>240) play=play.slice(0,237)+'...';
    var line='• '+ref+'\\n    id: '+id+'\\n    '+play;
    if(m==='live')L.push(line); else if(m==='shadow')S.push(line); else K.push('• '+ref);
  }});
  var t='GAZBOT V7 Monday playbook — my picks ({esc(a.slug)})\\n\\n';
  t+='ARM LIVE ('+L.length+'):\\n'+(L.join('\\n')||'  (none)');
  t+='\\n\\nSHADOW ('+S.length+'):\\n'+(S.join('\\n')||'  (none)');
  t+='\\n\\nSKIP ('+K.length+'):\\n'+(K.join('\\n')||'  (none)');
  t+='\\n\\nLet\\u2019s discuss which of these go in.';
  return t;
}}
function toast(msg){{
  var d=document.createElement('div'); d.className='pk-toast'; d.textContent=msg;
  document.body.appendChild(d);
  setTimeout(function(){{ d.classList.add('go'); }},10);
  setTimeout(function(){{ d.classList.remove('go'); setTimeout(function(){{ d.remove(); }},300); }},2600);
}}
/* Copy WITHOUT navigator.clipboard as the primary path — that API does not exist on an
   insecure (http) origin, which is exactly how this dashboard is served locally. This is the
   bug that turned last week's copy button into a useless one-line prompt(). */
function legacyCopy(t){{
  var ta=document.createElement('textarea');
  ta.value=t; ta.setAttribute('readonly','');
  ta.style.cssText='position:fixed;top:50%;left:-9999px;opacity:0';
  document.body.appendChild(ta);
  var ok=false;
  try{{ ta.select(); ta.setSelectionRange(0,t.length); ok=document.execCommand('copy'); }}catch(e){{ ok=false; }}
  ta.remove();
  return ok;
}}
function showSheet(t, copied){{
  var ov=document.createElement('div'); ov.className='pk-ov';
  ov.innerHTML='<div class="pk-sheet">'
    +'<div class="pk-sheet-h">'+(copied?'\\u2713 Copied to your clipboard':'Your picks — select and copy')+'</div>'
    +'<div class="pk-sheet-s">'+(copied
        ? 'Paste it to me in chat. The full text is below if you want to check it.'
        : 'This browser blocked the automatic copy. Tap <b>Select all</b>, then long-press &rarr; Copy.')+'</div>'
    +'<textarea class="pk-sheet-t" spellcheck="false"></textarea>'
    +'<div class="pk-sheet-b"><button class="pk-btn" data-a="sel">Select all</button>'
    +'<button class="pk-btn alt" data-a="tg">\\u2708 Telegram</button>'
    +'<button class="pk-btn ghost" data-a="close">Close</button></div></div>';
  document.body.appendChild(ov);
  var ta=ov.querySelector('.pk-sheet-t'); ta.value=t;
  ov.addEventListener('click',function(e){{
    var a=e.target.getAttribute&&e.target.getAttribute('data-a');
    if(e.target===ov||a==='close'){{ ov.remove(); return; }}
    if(a==='sel'){{ ta.focus(); ta.select(); ta.setSelectionRange(0,t.length);
      if(legacyCopy(t)) toast('Copied'); }}
    if(a==='tg'){{ window.open('https://t.me/share/url?url=&text='+encodeURIComponent(t),'_blank'); }}
  }});
}}
function doCopy(){{
  var t=summary();
  if(navigator.clipboard&&window.isSecureContext){{
    navigator.clipboard.writeText(t).then(
      function(){{ toast('Picks copied — paste them to me in chat.'); }},
      function(){{ showSheet(t, legacyCopy(t)); }});
  }} else {{
    showSheet(t, legacyCopy(t));
  }}
}}
document.getElementById('copyBtn').addEventListener('click',doCopy);
document.getElementById('tgBtn').addEventListener('click',function(){{
  window.open('https://t.me/share/url?url=&text='+encodeURIComponent(summary()),'_blank');
}});
document.getElementById('resetBtn').addEventListener('click',function(){{
  if(!confirm('Reset all {n_pick} picks to their default tier?'))return;
  picks={{}}; document.querySelectorAll('.pk-card').forEach(function(c){{
    if(c.dataset.pick==='1') picks[c.dataset.id]=c.dataset.default; }});
  save(); paint(); toast('Reset to defaults');
}});
paint();
</script>
</body></html>
"""
    out = f"{OUT}/monday_{a.slug}.html"
    pathlib.Path(out).write_text(doc)
    st = pathlib.Path(out).stat()
    print(f"playbook → {out} ({st.st_size:,} bytes, {len(plays)} plays)")
    print("  tiers: " + " · ".join(f"{k} {v}" for k, v in sorted(tiers.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
