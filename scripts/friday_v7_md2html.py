#!/usr/bin/env python3
"""Markdown -> light-theme HTML fragment, for the Friday report's stitcher.

★ WHY THIS EXISTS. The greenfield phases write their working as MARKDOWN dossiers
(`reports/friday_v7/sections/gf_*.md`) while every section fragment the build stitches is
light-theme HTML. Until now a human-written HTML section stood between the two, which meant a
lab that finished AFTER that section was written simply never reached the reader — which is what
happened this cycle: six of the seven labs re-ran on 2026-08-25 and `movement3_greenfield.html`
was still the 2026-08-22 file built when only VACUUM existed.

There is no `markdown` module on this box (checked, both interpreters), and adding a dependency
to the Friday tail is exactly the kind of thing that fails unattended at 02:00. So this is a
small deliberate subset, matching what the labs actually emit:

    # / ## / ### / ####   headings          (## -> h3, ### -> h4 — the SECTION owns h2)
    | a | b |             pipe tables, with the ---|--- separator and :---: alignment
    - / * / 1.            lists
    > quote               blockquote
    ```code```            fenced code
    ---                   horizontal rule
    **b** *i* `c`         inline emphasis and code

Everything else passes through as a paragraph. That is on purpose: a lab that invents a syntax
this does not know loses its formatting, never its TEXT. Silent text loss is the one failure a
report assembler must not have.
"""
from __future__ import annotations

import html
import re

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(?!\s)(.+?)\*\*")   # non-greedy: bold may CONTAIN *italic*
_ITAL = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def inline(t: str) -> str:
    """Escape, then re-introduce the inline markup. Order matters: escape FIRST so a lab that
    writes a literal <tag> in prose cannot inject markup into the report."""
    t = html.escape(t, quote=False)
    # a table cell escapes its own pipes as \| — undo that before anything else reads them
    t = t.replace(r"\|", "|")
    t = _INLINE_CODE.sub(lambda m: f"<code>{m.group(1)}</code>", t)
    t = _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", t)
    t = _ITAL.sub(lambda m: f"<em>{m.group(1)}</em>", t)
    t = _LINK.sub(lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>', t)
    # the labs write these as literal characters; they survive escaping, but the em/en dashes the
    # style guide uses get typed as "--" often enough to be worth normalising
    t = t.replace(" -- ", " &mdash; ")
    return t


def _is_table_sep(line: str) -> bool:
    s = line.strip().strip("|")
    return bool(s) and all(re.fullmatch(r"\s*:?-{2,}:?\s*", c) for c in s.split("|"))


def _cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    # split on unescaped pipes only
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


_NUMISH = re.compile(r"^[+\-−–]?[$€£]?[\d,]+(\.\d+)?[%×xRpt]*$")


def _td(cell: str) -> str:
    """Number cells get td.num so the light theme right-aligns them, as every hand-written
    fragment in this report does."""
    body = inline(cell)
    bare = re.sub(r"<[^>]+>", "", body).strip().replace("&minus;", "-")
    cls = ' class="num"' if _NUMISH.match(bare) else ""
    return f"<td{cls}>{body}</td>"


def md_to_html(md: str, *, h_offset: int = 1) -> str:
    """Render a lab dossier as a stitch-in HTML fragment.

    h_offset shifts every heading DOWN by that many levels, because the dossier's own `#` title
    sits inside a report section that already owns an <h2>. Two <h2>s in one section break the
    document outline and the PDF's bookmark tree.
    """
    out: list[str] = []
    lines = md.replace("\r\n", "\n").split("\n")
    i, n = 0, len(lines)
    para: list[str] = []

    def flush() -> None:
        # ★ Join the raw lines BEFORE inlining. Running inline() per line silently drops any
        # **bold** or *italic* that a lab wrapped across a newline — which is most of them, since
        # the dossiers are hard-wrapped at ~95 columns. That left 317 literal asterisks in the
        # first render of Movement 3.
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para.clear()

    while i < n:
        line = lines[i]
        s = line.strip()

        if not s:
            flush()
            i += 1
            continue

        if s.startswith("```"):
            flush()
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(html.escape(lines[i]))
                i += 1
            i += 1
            out.append("<pre><code>" + "\n".join(buf) + "</code></pre>")
            continue

        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", s):
            flush()
            out.append('<hr class="frag-sep">')
            i += 1
            continue

        m = re.match(r"(#{1,6})\s+(.*)", s)
        if m:
            flush()
            lvl = min(6, len(m.group(1)) + h_offset)
            out.append(f"<h{lvl}>{inline(m.group(2).strip())}</h{lvl}>")
            i += 1
            continue

        # table: a pipe row followed by a --- separator row
        if "|" in s and i + 1 < n and _is_table_sep(lines[i + 1]):
            flush()
            head = _cells(s)
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(_cells(lines[i]))
                i += 1
            t = ["<table><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr>"]
            for r in rows:
                # a row that is short or long is rendered as written rather than padded/dropped —
                # a malformed row is the lab's business, but losing it is the assembler's fault
                t.append("<tr>" + "".join(_td(c) for c in r) + "</tr>")
            t.append("</table>")
            out.append("".join(t))
            continue

        if s.startswith(">"):
            flush()
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append("<blockquote>" + inline(" ".join(x for x in buf if x)) + "</blockquote>")
            continue

        if re.match(r"[-*+]\s+", s) or re.match(r"\d+[.)]\s+", s):
            flush()
            ordered = bool(re.match(r"\d+[.)]\s+", s))
            items: list[str] = []
            while i < n:
                cur = lines[i]
                cs = cur.strip()
                mm = re.match(r"(?:[-*+]|\d+[.)])\s+(.*)", cs)
                if mm:
                    items.append(mm.group(1))
                elif cs and cur.startswith((" ", "\t")) and items:
                    items[-1] += " " + cs             # continuation of the previous bullet
                else:
                    break
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            continue

        para.append(s)
        i += 1

    flush()
    return "\n".join(out)


def strip_tags(h: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", h))


def word_count(h: str) -> int:
    return len(strip_tags(h).split())
