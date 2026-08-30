#!/usr/bin/env python3
"""Build the interactive "Monday Playbook" picker from plays.json — GAZBOT V7 owner copy.

Forked from /home/alphabot/alphabot2/scripts/friday/build_playbook.py (V5 desk is retired) and
extended with the WINDOW axis. Rev2 · Q0 of the 2026-07-31 report made the point that the useful
grouping is not "verified vs exploratory" but WHEN it is safe to do the thing:

    SATURDAY       tournament changes — entry maths / roster. Post-Friday window only.
    MONDAY         arming + exit posture. Blocks new entries only, reversible per router tick.
    BUILD          code that does not exist yet; nothing goes live this week.
    HOLD           already right — the action is to leave it alone.
    NOT-AN-ACTION  looks like a play, is not one. Kept so it is not re-proposed next week.

Plays carrying a "window" key are grouped that way (ordered by "rank" inside each group). Plays
without one fall back to the original act/exploratory split, so old plays.json files still build.

Usage:
  python3 scripts/friday/build_playbook.py --plays reports/friday_v7/plays.json \
    --dates "Mon 27 Jul -> Fri 31 Jul 2026" --date-slug 2026-08-03 \
    --out-dir src/gazbot7/web_static --brand "GAZBOT V7 · MNQ Futures Desk"
"""
import argparse, json, re, html, pathlib

V7 = '/home/alphabot/gazbot7'
STATIC = V7 + '/src/gazbot7/web_static'
CSS_CANDIDATES = [
    STATIC + '/weekly_2026-07-31.html',
    '/home/alphabot/alphabot2/alphabot/dashboard/static/weekly_2026-06-26.html',
]

def esc(t): return _unescape_inline(html.escape('' if t is None else str(t)))


# ★2026-08-22 — INLINE MARKUP SURVIVES THE ESCAPE.
# This week's plays.json is the first to carry inline HTML in its prose (<code> around file
# and field names, <strong> for the number that decides a row, &mdash; between clauses).
# html.escape() rendered all of it as literal angle brackets: 69 visible "<code>...</code>"
# strings on the operator's own action card and 36 on the Monday playbook. Escaping is still
# the default — everything is escaped first — and only this fixed inline whitelist is put
# back. No attributes, no block tags, nothing that can change the page's structure.
_INLINE_OK = ("code", "strong", "em", "b", "i")


def _unescape_inline(t: str) -> str:
    for tag in _INLINE_OK:
        t = t.replace("&lt;%s&gt;" % tag, "<%s>" % tag).replace("&lt;/%s&gt;" % tag, "</%s>" % tag)
    for ent in ("mdash", "ndash", "middot", "rsquo", "lsquo", "ldquo", "rdquo", "times", "nbsp", "hellip", "ge", "le", "minus"):
        t = t.replace("&amp;%s;" % ent, "&%s;" % ent)
    return t

VLABEL = {'verified': '✓ VERIFIED', 'bug': '🔧 REAL BUG', 'refuted': '⚠ REFUTED', 'exploratory': '◦ EXPLORATORY'}

# The pill is the play's VERDICT. Since 2026-08-28 plays.json carries that in `tier`
# (LIVE / SHADOW / PARKED / REFUTED, sometimes with a qualifier); `verification` now
# holds the prose test that would confirm the play, which is not a pill and — because
# it contains <code> and quotes — silently broke the class attribute when used as one.
VLABEL.update({'live': '● LIVE', 'shadow': '◐ SHADOW', 'parked': '◦ PARKED'})
_TIERS = ('refuted', 'parked', 'shadow', 'live')


def verdict_id(p):
    tier = (p.get('tier') or '').strip().lower()
    for t in _TIERS:
        if tier.startswith(t):
            return t
    legacy = (p.get('verification') or '').strip().lower()
    return legacy if legacy in VLABEL else 'exploratory'


# window key -> (heading, blurb). Order here is the order on the page.
WINDOWS = [
    ('SATURDAY', '★ SATURDAY — do these TODAY or they wait a full week',
     'Tournament changes: these alter a gate&rsquo;s entry maths or the roster, and by standing rule they '
     'move only in the post-Friday window. Every row carries a revert path.'),
    ('MONDAY', '★ MONDAY — arming &amp; exit posture, reversible',
     'Owner is the durable router tick unless stated. These block or unblock NEW entries only &mdash; open '
     'positions still exit and stops are untouched. Any of it can be undone on the next 5-minute tick.'),
    ('BUILD', '🔨 BUILD — code that does not exist yet',
     'Nothing here goes near live capital this week.'),
    ('HOLD', '🛡 HOLD — already right, leave it alone',
     'Half of &ldquo;what do I do Monday&rdquo; is knowing what not to touch.'),
    ('NOT-AN-ACTION', '🚫 NOT an action — and why',
     'These look like plays and are not. Listed so they do not get re-proposed next week.'),
]
# Groups where "Live / Shadow / Skip" is not a meaningful choice — render as read-only cards.
NO_PICKER = {'HOLD', 'NOT-AN-ACTION'}

def _sentences(t, n):
    """First n sentences of t — the card 'hook', keeping previous weeks' terse style."""
    parts = re.split(r'(?<=[.!?])\s+', (t or '').strip())
    out = ' '.join(parts[:n]).strip()
    return out, ' '.join(parts[n:]).strip()


def hook_and_rest(p):
    """Short hook shown on the card; everything else folds behind 'why ▾'."""
    if p.get('hook'):
        return p['hook'], (p.get('rationale') or '')
    return _sentences(p.get('rationale') or '', 2)


def short_play(p):
    """Cards in previous weeks were 1-3 sentences. Keep the rest behind the expander."""
    head, tail = _sentences(p.get('play') or '', 3)
    return head, tail


def card(p, pickable=True):
    vid = verdict_id(p)
    live_locked = vid in ('refuted', 'parked', 'exploratory')
    default = p.get('suggested_mode', 'skip')
    if live_locked and default == 'live': default = 'shadow'
    money = p.get('money_gbp', 0)
    money_html = f'<span class="pk-money">£{round(money)}/wk</span> · ' if money else ''
    sup = ''
    if 'SUPERSEDES' in (p.get('play') or ''):
        sup = '<span class="pk-sup">SUPERSEDES an earlier row</span>'

    if not pickable:
        opts, note = '', ''
    else:
        buttons = []
        for mode, lbl in (('shadow', 'Shadow'), ('live', 'Live'), ('skip', 'Skip')):
            dis = ' disabled title="Refuted/exploratory — must survive a week in shadow first"' if (mode == 'live' and live_locked) else ''
            buttons.append(f'<button class="pk-opt" data-mode="{mode}"{dis}>{lbl}</button>')
        opts = f'<div class="pk-opts">{"".join(buttons)}</div>'
        note = '<div class="pk-note">Live locked — prove it in shadow first.</div>' if live_locked else ''

    play_head, play_tail = short_play(p)
    hook, rest = hook_and_rest(p)
    detail = ''
    if play_tail or rest:
        body = ''
        if play_tail:
            body += f'<div class="pk-more-play">{esc(play_tail)}</div>'
        if rest:
            body += f'<div class="pk-more-why">{esc(rest)}</div>'
        detail = f'<details class="pk-det"><summary>why &amp; the full detail</summary>{body}</details>'

    cls = 'pk-card' + ('' if pickable else ' pk-static')
    return (f'<div class="{cls}" id="p-{esc(p["id"])}" data-id="{esc(p["id"])}" data-default="{default}" data-pick="{int(pickable)}">'
            f'<div class="pk-top"><span class="pk-ref">{esc(p.get("section_ref",""))} · {esc(p.get("topic",""))}</span>'
            f'<span class="pill v-{vid}">{VLABEL.get(vid,vid)}</span></div>'
            f'{sup}'
            f'<div class="pk-play">{esc(play_head)}</div>'
            f'<div class="pk-meta">{money_html}{esc(hook)}</div>'
            f'{detail}{opts}{note}</div>')


SHORT_W = {'SATURDAY': 'Sat (today)', 'MONDAY': 'Mon', 'BUILD': 'Build', 'HOLD': 'Hold', 'NOT-AN-ACTION': 'Not an action'}


def summary_table(plays):
    """At-a-glance summary — the whole week's recommendation on one screen, before any cards."""
    rows = []
    for key, _h, _b in WINDOWS:
        grp = sorted([p for p in plays if p.get('window') == key], key=lambda p: p.get('rank', 99))
        for i, p in enumerate(grp):
            vid = verdict_id(p)
            money = p.get('money_gbp', 0)
            first = ' pk-wfirst' if i == 0 else ''
            wcell = (f'<td class="pk-w pk-w-{key.lower().replace("-","")}" rowspan="{len(grp)}">{SHORT_W.get(key,key)}</td>'
                     if i == 0 else '')
            rows.append(
                f'<tr class="{first}">{wcell}'
                f'<td class="num">{p.get("rank","")}</td>'
                f'<td><a href="#p-{esc(p["id"])}">{esc(p.get("topic",""))}</a></td>'
                f'<td class="num">{("£"+str(round(money))) if money else "—"}</td>'
                f'<td><span class="pill v-{vid}">{VLABEL.get(vid,vid)}</span></td></tr>')
    return ('<div class="pk-group">📋 THE WHOLE WEEK ON ONE SCREEN</div>'
            '<p class="pk-blurb">Every recommendation, in the order it is safe to do it. Tap any row to jump to its card.</p>'
            '<div class="pk-tw"><table class="pk-sum"><thead><tr><th>When</th><th>#</th><th>Recommendation</th>'
            '<th>£/wk</th><th>Verdict</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>')

PICKER_CSS = """<style>
.pk-intro{font-size:16.5px;color:#33404f}
.pk-group{font-size:20px;color:var(--navy);margin:34px 0 4px;padding-bottom:6px;border-bottom:2px solid var(--gold);font-weight:700}
.pk-blurb{font-size:13.5px;color:var(--ink2);margin:0 0 10px;font-style:italic}
.pk-card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0;box-shadow:0 1px 3px rgba(15,41,66,.05);font-family:ui-sans-serif,system-ui,sans-serif;border-left:4px solid var(--line)}
.pk-card.m-live{border-left-color:var(--pos)} .pk-card.m-shadow{border-left-color:var(--gold)} .pk-card.m-skip{border-left-color:#c9cdd3}
.pk-card.pk-static{background:#fbfbfc;border-left-color:#c9cdd3}
.pk-top{display:flex;justify-content:space-between;gap:10px;align-items:center}
.pk-ref{font:700 12px ui-monospace,Menlo,monospace;color:var(--gold)}
.pk-sup{display:inline-block;margin-top:6px;font:700 10.5px ui-sans-serif,system-ui,sans-serif;letter-spacing:.05em;background:#fdecea;color:var(--neg);padding:2px 7px;border-radius:4px}
.pk-play{font-size:15.5px;color:var(--ink);margin:7px 0 4px;font-family:Georgia,serif;line-height:1.45}
.pk-meta{font-size:12.5px;color:var(--ink2);line-height:1.55} .pk-money{font-weight:800;color:var(--navy)}
.pk-opts{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden;margin-top:9px}
.pk-opt{padding:7px 16px;font:600 13px ui-sans-serif,system-ui,sans-serif;cursor:pointer;background:#fff;border:0;border-right:1px solid var(--line)}
.pk-opt:last-child{border-right:0}
.pk-opt[data-mode=live].on{background:#eafaf0;color:var(--pos)}
.pk-opt[data-mode=shadow].on{background:#fff5e0;color:#9a6b00}
.pk-opt[data-mode=skip].on{background:#eef0f2;color:var(--ink2)}
.pk-opt:disabled{opacity:.3;cursor:not-allowed;text-decoration:line-through}
.pk-bar{position:sticky;bottom:12px;background:var(--navy);color:#fff;padding:14px 18px;border-radius:12px;margin:26px 0 10px;display:flex;gap:14px;align-items:center;flex-wrap:wrap;font-family:ui-sans-serif,system-ui,sans-serif;box-shadow:0 4px 18px rgba(15,41,66,.25)}
.pk-bar .cnt{font-size:15px} .pk-bar .cnt b{font-size:20px}
.pk-btn{background:var(--gold);color:#fff;border:0;border-radius:8px;padding:11px 18px;font:700 14px ui-sans-serif,system-ui,sans-serif;cursor:pointer;margin-left:auto}
.pk-btn.alt{background:#0088cc;margin-left:8px}
.pill.v-verified{background:#eafaf0;color:var(--pos)} .pill.v-bug{background:#e7edf5;color:var(--navy)}
.pill.v-refuted{background:#fdecea;color:var(--neg)} .pill.v-exploratory{background:#f1f1f1;color:var(--ink2)}
.pill.v-live{background:#eafaf0;color:var(--pos)} .pill.v-shadow{background:#fdf6e3;color:#8a6d1f}
.pill.v-parked{background:#f1f1f1;color:var(--ink2)}
.pk-note{font-size:12.5px;color:var(--ink2);font-style:italic;margin-top:3px}
.pk-btn.ghost{background:transparent;color:#fff;border:1px solid rgba(255,255,255,.45);margin-left:8px}
.pk-toast{position:fixed;left:50%;bottom:26px;transform:translate(-50%,14px);background:var(--navy);color:#fff;
  padding:12px 20px;border-radius:10px;font:600 14px ui-sans-serif,system-ui,sans-serif;z-index:1000;
  box-shadow:0 6px 24px rgba(15,41,66,.35);opacity:0;transition:opacity .25s,transform .25s;max-width:90vw;text-align:center}
.pk-toast.go{opacity:1;transform:translate(-50%,0)}
.pk-ov{position:fixed;inset:0;background:rgba(15,41,66,.55);z-index:999;display:flex;align-items:center;
  justify-content:center;padding:16px}
.pk-sheet{background:#fff;border-radius:14px;max-width:640px;width:100%;padding:18px;box-shadow:0 12px 40px rgba(0,0,0,.3);
  font-family:ui-sans-serif,system-ui,sans-serif}
.pk-sheet-h{font:700 17px ui-sans-serif,system-ui,sans-serif;color:var(--navy);margin-bottom:4px}
.pk-sheet-s{font-size:13.5px;color:var(--ink2);margin-bottom:10px;line-height:1.5}
.pk-sheet-t{width:100%;height:230px;font:12.5px/1.5 ui-monospace,Menlo,monospace;padding:10px;border:1px solid var(--line);
  border-radius:9px;resize:vertical;color:var(--ink);background:#fbfbfc;-webkit-user-select:text;user-select:text}
.pk-sheet-b{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.pk-sheet-b .pk-btn{margin-left:0}
.pk-sheet .pk-btn.ghost{color:var(--ink2);border-color:var(--line)}
.pk-tw{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:10px 0 4px}
.pk-sum{border-collapse:collapse;width:100%;font-family:ui-sans-serif,system-ui,sans-serif;font-size:13.5px;min-width:520px}
.pk-sum th{text-align:left;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink2);border-bottom:2px solid var(--line);padding:7px 9px;white-space:nowrap}
.pk-sum td{border-bottom:1px solid var(--line);padding:8px 9px;vertical-align:top}
.pk-sum td.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums;font-weight:700;color:var(--navy)}
.pk-sum a{color:var(--ink);text-decoration:none;border-bottom:1px dotted var(--gold)}
.pk-sum a:hover{color:var(--navy)}
.pk-sum tr.pk-wfirst td{border-top:2px solid var(--line)}
.pk-sum td.pk-w{font:700 12px ui-sans-serif,system-ui,sans-serif;white-space:nowrap;vertical-align:top;color:#fff;background:var(--navy);border-radius:4px 0 0 4px}
.pk-sum td.pk-wsaturday{background:#9a6b00} .pk-sum td.pk-wmonday{background:var(--navy)}
.pk-sum td.pk-wbuild{background:#4a5a6a} .pk-sum td.pk-whold{background:#6b7a89} .pk-sum td.pk-wnotanaction{background:#9aa3ac}
.pk-det{margin-top:8px;border-top:1px dashed var(--line);padding-top:6px}
.pk-det summary{cursor:pointer;font:600 12.5px ui-sans-serif,system-ui,sans-serif;color:var(--gold);list-style:none}
.pk-det summary::-webkit-details-marker{display:none}
.pk-det summary:before{content:"▸ ";}
.pk-det[open] summary:before{content:"▾ ";}
.pk-more-play{font-size:14px;color:var(--ink);margin:8px 0 6px;font-family:Georgia,serif;line-height:1.45}
.pk-more-why{font-size:12.5px;color:var(--ink2);line-height:1.55}
@media(max-width:680px){.pk-sum{font-size:12.5px}}
.pk-warn{background:#fff8e6;border:1px solid var(--gold);border-left:5px solid var(--gold);border-radius:10px;padding:13px 16px;margin:16px 0;font-size:14.5px;color:#4a3a10;font-family:ui-sans-serif,system-ui,sans-serif;line-height:1.55}
.pk-warn b{color:var(--navy)}
</style>"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plays', required=True)
    ap.add_argument('--dates', required=True)
    ap.add_argument('--date-slug', required=True)
    ap.add_argument('--out-dir', default=STATIC)
    ap.add_argument('--brand', default='GAZBOT V7 · MNQ Futures Desk')
    ap.add_argument('--banner', default='', help='optional HTML banner above the groups (headline correction etc.)')
    a = ap.parse_args()

    plays = json.load(open(a.plays))
    css = None
    for c in CSS_CANDIDATES:
        p = pathlib.Path(c)
        if p.exists():
            m = re.search(r'<style>.*?</style>', p.read_text(), re.S)
            if m:
                css = m.group(0); break
    if css is None:
        raise SystemExit('no CSS template found: ' + ', '.join(CSS_CANDIDATES))

    body = [f'<div class="masthead"><div class="brand">{esc(a.brand)}</div>',
            '<h1>Weekly Playbook</h1>',
            f'<div class="dates">My recommendations from the forensic report · Week of {esc(a.dates)}</div></div>',
            '<p class="pk-intro">Every concrete recommendation from the report, one card each, '
            '<b>grouped by when it is safe to do it</b> rather than by which section wrote it. Tap '
            '<b>Shadow</b>, <b>Live</b> or <b>Skip</b>. Picks save automatically — when you are done hit '
            '<b>Copy my picks</b> or <b>Send to Telegram</b> and they come back to me for the shadow-vs-live '
            'conversation. <b>Refuted &amp; exploratory plays cannot go Live</b> until they survive a week in '
            'shadow — that guardrail is built in.</p>']
    if a.banner:
        body.append(a.banner)

    used = set()
    windowed = any('window' in p for p in plays)
    if windowed:
        body.append(summary_table(plays))
        for key, heading, blurb in WINDOWS:
            grp = sorted([p for p in plays if p.get('window') == key], key=lambda p: p.get('rank', 99))
            if not grp: continue
            used.update(id(p) for p in grp)
            body.append(f'<div class="pk-group">{heading}</div><p class="pk-blurb">{blurb}</p>')
            body += [card(p, pickable=(key not in NO_PICKER)) for p in grp]
        rest = [p for p in plays if id(p) not in used]
    else:
        rest = plays
    if rest:
        act = [p for p in rest if p.get('verification') in ('verified', 'bug')]
        exp = [p for p in rest if p.get('verification') not in ('verified', 'bug')]
        if act:
            body.append('<div class="pk-group">✅ Act on these — survived proof &amp; real bugs</div>')
            body += [card(p) for p in act]
        if exp:
            body.append('<div class="pk-group">🔍 Exploratory — shadow-test only</div>')
            body += [card(p) for p in exp]

    body.append('<div class="pk-bar"><span class="cnt"><b id="nLive">0</b> live &nbsp; <b id="nShadow">0</b> shadow '
                '&nbsp; <b id="nSkip">0</b> skip</span>'
                '<button class="pk-btn" id="copyBtn">📋 Copy my picks</button>'
                '<button class="pk-btn alt" id="tgBtn">✈ Send to Telegram</button></div>'
                '<div class="foot">Picks are stored only in this browser until you send them. Nothing is armed '
                'automatically — every Live pick is a conversation first.</div>')

    JS = """<script>
var KEY='gazPicks_""" + a.date_slug + """';
var picks=JSON.parse(localStorage.getItem(KEY)||'{}');
function save(){localStorage.setItem(KEY,JSON.stringify(picks));}
document.querySelectorAll('.pk-card').forEach(function(c){
  if(c.dataset.pick!=='1')return;
  var id=c.dataset.id; if(!(id in picks)) picks[id]=c.dataset.default;
  c.querySelectorAll('.pk-opt').forEach(function(b){
    b.addEventListener('click',function(){ if(b.disabled)return; picks[id]=b.dataset.mode; save(); paint(); });
  });
});
function paint(){
  var nL=0,nS=0,nK=0;
  document.querySelectorAll('.pk-card').forEach(function(c){
    if(c.dataset.pick!=='1')return;
    var id=c.dataset.id, m=picks[id]||'skip';
    c.className='pk-card m-'+m;
    c.querySelectorAll('.pk-opt').forEach(function(b){ b.classList.toggle('on', b.dataset.mode===m && !b.disabled); });
    if(m==='live')nL++; else if(m==='shadow')nS++; else nK++;
  });
  document.getElementById('nLive').textContent=nL;
  document.getElementById('nShadow').textContent=nS;
  document.getElementById('nSkip').textContent=nK;
}
function groupOf(c){
  var n=c.previousElementSibling;
  while(n){ if(n.classList&&n.classList.contains('pk-group')) return n.textContent.trim(); n=n.previousElementSibling; }
  return '';
}
function summary(){
  var L=[],S=[];
  document.querySelectorAll('.pk-card').forEach(function(c){
    if(c.dataset.pick!=='1')return;
    var id=c.dataset.id, m=picks[id]||'skip';
    var ref=c.querySelector('.pk-ref').textContent.trim();
    var play=c.querySelector('.pk-play').textContent.trim();
    var g=groupOf(c).replace(/^[^A-Za-z]+/,'').split('—')[0].trim();
    if(m==='live')L.push('• ['+g+'] '+ref+' — '+play);
    else if(m==='shadow')S.push('• ['+g+'] '+ref+' — '+play);
  });
  var t='GAZBOT V7 Weekly Playbook — my picks ('+document.querySelector('.dates').textContent.replace('My recommendations from the forensic report · ','')+')\\n\\n';
  t+='ARM LIVE ('+L.length+'):\\n'+(L.join('\\n')||'  (none)')+'\\n\\nSHADOW ('+S.length+'):\\n'+(S.join('\\n')||'  (none)')+'\\n\\nLet\\u2019s discuss which of these go in.';
  return t;
}
function toast(msg){
  var d=document.createElement('div'); d.className='pk-toast'; d.textContent=msg;
  document.body.appendChild(d);
  setTimeout(function(){ d.classList.add('go'); },10);
  setTimeout(function(){ d.classList.remove('go'); setTimeout(function(){ d.remove(); },300); },2600);
}
// Copy without navigator.clipboard — that API does not exist on an insecure (http) origin,
// which is what sent this button into a useless single-line prompt() before.
function legacyCopy(t){
  var ta=document.createElement('textarea');
  ta.value=t;
  ta.setAttribute('readonly','');
  ta.style.cssText='position:fixed;top:50%;left:-9999px;opacity:0';
  document.body.appendChild(ta);
  var ok=false;
  try{ ta.select(); ta.setSelectionRange(0,t.length); ok=document.execCommand('copy'); }catch(e){ ok=false; }
  ta.remove();
  return ok;
}
function showSheet(t, copied){
  var ov=document.createElement('div'); ov.className='pk-ov';
  ov.innerHTML='<div class="pk-sheet">'
    +'<div class="pk-sheet-h">'+(copied?'✓ Copied to your clipboard':'Your picks — select and copy')+'</div>'
    +'<div class="pk-sheet-s">'+(copied
        ? 'Paste it to me in chat. The full text is below if you want to check it.'
        : 'This browser blocked the automatic copy. Tap <b>Select all</b>, then long-press &rarr; Copy.')+'</div>'
    +'<textarea class="pk-sheet-t" spellcheck="false"></textarea>'
    +'<div class="pk-sheet-b"><button class="pk-btn" data-a="sel">Select all</button>'
    +'<button class="pk-btn alt" data-a="tg">✈ Telegram</button>'
    +'<button class="pk-btn ghost" data-a="close">Close</button></div></div>';
  document.body.appendChild(ov);
  var ta=ov.querySelector('.pk-sheet-t'); ta.value=t;
  ov.addEventListener('click',function(e){
    var a=e.target.getAttribute&&e.target.getAttribute('data-a');
    if(e.target===ov||a==='close'){ ov.remove(); return; }
    if(a==='sel'){ ta.focus(); ta.select(); ta.setSelectionRange(0,t.length);
      if(legacyCopy(t)) toast('Copied'); }
    if(a==='tg'){ window.open('https://t.me/share/url?url=&text='+encodeURIComponent(t),'_blank'); }
  });
}
function doCopy(){
  var t=summary();
  if(navigator.clipboard&&window.isSecureContext){
    navigator.clipboard.writeText(t).then(
      function(){ toast('Picks copied — paste them to me in chat.'); },
      function(){ showSheet(t, legacyCopy(t)); });
  } else {
    showSheet(t, legacyCopy(t));
  }
}
document.getElementById('copyBtn').addEventListener('click',doCopy);
document.getElementById('tgBtn').addEventListener('click',function(){
  window.open('https://t.me/share/url?url=&text='+encodeURIComponent(summary()),'_blank');
});
paint();
</script>"""

    doc = ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
           f'<title>{esc(a.brand.split("·")[0].strip())} — Weekly Playbook</title>' + css + PICKER_CSS +
           '</head><body><div class="wrap">' + '\n'.join(body) + JS + '</div></body></html>')
    out = f'{a.out_dir}/monday_{a.date_slug}.html'
    pathlib.Path(out).write_text(doc)
    picks = sum(1 for p in plays if p.get('window') not in NO_PICKER)
    print(f"playbook: {len(doc)} bytes, {len(plays)} plays ({picks} pickable) -> {out}")

if __name__ == '__main__':
    main()
