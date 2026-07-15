// GAZBOT V7 — watch page. Polls /api/status, populates the /mnq-style cockpit.
// Defensive: every DOM write is guarded, so a missing element can never abort the
// render (the bug that blanked the chart — the old JS threw on stale IDs).
const $ = (id) => document.getElementById(id);
const set = (id, v) => { const e = $(id); if (e) e.textContent = v; };
const setHTML = (id, v) => { const e = $(id); if (e) e.innerHTML = v; };
const money = (v) => (v == null ? "—" : (v >= 0 ? "+" : "") + Number(v).toFixed(2));
const cls = (v) => (v == null ? "" : Number(v) >= 0 ? "grn" : "red");
const tms = (iso) => { const t = Date.parse(iso); return isNaN(t) ? null : t / 1000; };
const VPP = 2; // MNQ $/point

// phone tab switching — redraw charts when a tab becomes visible (0-size while hidden)
document.querySelectorAll(".tab").forEach((t) => {
  t.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("on"));
    t.classList.add("on");
    const tab = t.dataset.tab;
    document.querySelectorAll(".panel[data-tab]").forEach((p) => p.classList.toggle("on", p.dataset.tab === tab));
    if (window._s) draw(window._s);
  };
});

function parisClock() {
  try { set("clock", new Date().toLocaleTimeString("en-GB", { timeZone: "Europe/Paris" })); } catch (e) {}
}
setInterval(parisClock, 1000); parisClock();

function setKpi(id, v) {
  const el = $(id); if (!el) return;
  el.textContent = money(v);
  el.classList.remove("grn", "red");
  el.classList.add(cls(v));
}

function drawPrice(bars, vwap, fills, price) {
  const svg = $("price-svg"); if (!svg) return;
  if (!bars || bars.length < 2) { svg.innerHTML = ""; return; }
  const w = svg.clientWidth || 600, h = svg.clientHeight || 220;
  const xs = bars.map((b) => b[0]), ys = bars.map((b) => b[1]);
  const x0 = xs[0], x1 = xs[xs.length - 1];
  let lo = Math.min(...ys), hi = Math.max(...ys);
  if (vwap) { lo = Math.min(lo, vwap); hi = Math.max(hi, vwap); }
  (fills || []).forEach((f) => [f.entry, f.exit].forEach((p) => { if (p) { lo = Math.min(lo, p); hi = Math.max(hi, p); } }));
  const px = (x) => ((x - x0) / (x1 - x0 || 1)) * w;
  const py = (y) => h - ((y - lo) / (hi - lo || 1)) * (h - 20) - 10;
  let out = "";
  for (let i = 0; i <= 4; i++) { const gy = 10 + (i / 4) * (h - 20); out += `<line x1="0" y1="${gy}" x2="${w}" y2="${gy}" stroke="#2a3441" stroke-width="0.5" opacity="0.5"/>`; }
  if (vwap) { const vy = py(vwap).toFixed(1); out += `<line x1="0" y1="${vy}" x2="${w}" y2="${vy}" stroke="#37c9c9" stroke-width="1" stroke-dasharray="4 3" opacity="0.85"/>`; }
  const d = bars.map((b, i) => (i ? "L" : "M") + px(b[0]).toFixed(1) + " " + py(b[1]).toFixed(1)).join(" ");
  out += `<path d="${d}" fill="none" stroke="#c6d2db" stroke-width="1.5"/>`;
  (fills || []).forEach((f) => {
    const col = f.side === "LONG" ? "#37d07a" : "#ff5a5f";
    const eo = tms(f.opened_at), ec = tms(f.closed_at);
    if (eo && f.entry) out += `<circle cx="${px(eo).toFixed(1)}" cy="${py(f.entry).toFixed(1)}" r="3.5" fill="${col}"/>`;
    if (ec && f.exit) out += `<circle cx="${px(ec).toFixed(1)}" cy="${py(f.exit).toFixed(1)}" r="3.5" fill="none" stroke="${col}" stroke-width="1.6"/>`;
  });
  const last = price != null ? price : ys[ys.length - 1];
  out += `<text x="${w - 4}" y="${(py(last) - 5).toFixed(1)}" text-anchor="end" fill="#c6d2db" font-size="13" font-family="monospace" font-weight="700">${Number(last).toFixed(2)}</text>`;
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.innerHTML = out;
}

function drawCurve(trades) {
  const svg = $("curve-svg"); if (!svg) return;
  if (!trades || !trades.length) { svg.innerHTML = ""; set("curve-end", "—"); return; }
  const seq = trades.slice().reverse(); // API is newest-first
  let cum = 0; const pts = seq.map((t) => (cum += (t.pnl || 0)));
  const w = 1000, h = 120, lo = Math.min(0, ...pts), hi = Math.max(0, ...pts);
  const px = (i) => (i / (pts.length - 1 || 1)) * w;
  const py = (v) => h - ((v - lo) / (hi - lo || 1)) * (h - 12) - 6;
  const d = pts.map((v, i) => (i ? "L" : "M") + px(i).toFixed(1) + " " + py(v).toFixed(1)).join(" ");
  const z = py(0).toFixed(1);
  svg.innerHTML = `<line x1="0" y1="${z}" x2="${w}" y2="${z}" stroke="#2a3441" stroke-width="0.5"/>` +
    `<path d="${d}" fill="none" stroke="${cum >= 0 ? "#37d07a" : "#ff5a5f"}" stroke-width="1.5"/>`;
  set("curve-end", money(cum));
}

function draw(s) { drawPrice(s.bars, s.vwap, s.fills, s.price); drawCurve(s.trades); }

function unreal(pos, price) {
  if (!pos || price == null) return null;
  return (pos.side === "LONG" ? 1 : -1) * (price - pos.entry) * VPP * (pos.qty || 1);
}

async function tick() {
  let s;
  try { s = await (await fetch("api/status")).json(); } catch (e) { return; }
  window._s = s;
  const c = $("conn"); if (c) c.className = "conn" + (s.healthy ? "" : " off");
  set("conn-label", s.conn || "—");
  const chip = $("mode-chip"); if (chip) { chip.textContent = s.live ? "LIVE" : "DRY-RUN"; chip.className = "chip " + (s.live ? "bull" : ""); }
  setKpi("k-today", s.kpi?.today); setKpi("k-d7", s.kpi?.d7); setKpi("k-d30", s.kpi?.d30);
  set("k-win", s.kpi?.win == null ? "—" : s.kpi.win + "%");

  const pos = s.position, u = unreal(pos, s.price);
  if (pos) { setHTML("unreal", `<span class="${cls(u)}">${money(u)}</span>`); set("unreal-sub", `${pos.side} ${pos.qty || 1} @ ${pos.entry}`); }
  else { set("unreal", "—"); set("unreal-sub", "flat"); }
  setHTML("d-realised", `<span class="${cls(s.kpi?.today)}">${money(s.kpi?.today)}</span>`);
  set("d-trades", s.kpi?.trades ?? "—");
  set("d-win", s.kpi?.win == null ? "—" : s.kpi.win + "%");
  setHTML("rolltbl", `<tr><td>NET</td><td class="${cls(s.kpi?.today)}">${money(s.kpi?.today)}</td><td class="${cls(s.kpi?.d7)}">${money(s.kpi?.d7)}</td><td class="${cls(s.kpi?.d30)}">${money(s.kpi?.d30)}</td></tr>`);

  setHTML("gateperf", (s.gates && s.gates.length)
    ? s.gates.map((g) => `<tr><td class="cyan">${g.gate}</td><td><span class="pill ${(g.side || "").toLowerCase()}">${g.side}</span></td><td>${g.n}</td><td>${g.win}%</td><td class="${cls(g.net)}">${money(g.net)}</td></tr>`).join("")
    : `<tr><td class="empty" colspan="5">no gated trades today</td></tr>`);

  set("tb-hold", pos ? "1" : "0");
  if (pos) {
    set("hold-meta", `${pos.side} ${pos.qty || 1}`);
    setHTML("hold-body",
      `<div class="row"><span class="k">Side</span><span class="val ${pos.side === "LONG" ? "grn" : "red"}">${pos.side} ${pos.qty || 1}</span></div>
       <div class="row"><span class="k">Entry</span><span class="val">${pos.entry}</span></div>
       <div class="row"><span class="k">Stop</span><span class="val">${pos.stop ?? "—"}</span></div>
       <div class="row"><span class="k">Last</span><span class="val">${s.price ?? "—"}</span></div>
       <div class="row"><span class="k">Unrealised</span><span class="val ${cls(u)}">${money(u)}</span></div>
       <div class="row"><span class="k">Opened</span><span class="val mut">${(pos.opened_at || "").replace("T", " ").slice(0, 19)}</span></div>`);
  } else { set("hold-meta", "flat"); setHTML("hold-body", `<div class="empty">no open position</div>`); }

  set("tb-trades", s.trades?.length ?? "—");
  set("trades-meta", (s.trades?.length ?? 0) + " today");
  setHTML("blotter", (s.trades && s.trades.length)
    ? s.trades.map((t) => `<tr><td>${t.t}</td><td><span class="pill ${(t.side || "").toLowerCase()}">${t.side}</span></td><td class="cyan">${t.gate}</td><td class="mut">${t.exit}</td><td class="${cls(t.pnl)}">${money(t.pnl)}</td></tr>`).join("")
    : `<tr><td class="empty" colspan="5">no trades today</td></tr>`);

  const ep = $("exec-pct"); if (ep) { ep.textContent = s.exec?.through == null ? "—" : s.exec.through + "%"; ep.className = "big " + (s.exec?.through >= 60 ? "grn" : s.exec?.through == null ? "" : "amb"); }
  set("exec-sub", `${s.exec?.fills ?? 0} fills · ${s.exec?.submitted ?? 0} submitted`);
  const bf = $("exec-bf"); if (bf) { bf.textContent = s.backfills ?? "—"; bf.className = "val " + (s.backfills ? "red" : "grn"); }

  draw(s);
}

tick();
setInterval(tick, 3000);
