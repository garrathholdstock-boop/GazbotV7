// GAZBOT V7 — watch page. Polls /api/status, populates the /mnq-style cockpit.
const $ = (id) => document.getElementById(id);
const money = (v) => (v == null ? "—" : (v >= 0 ? "+" : "") + Number(v).toFixed(2));
const cls = (v) => (v == null ? "" : Number(v) >= 0 ? "grn" : "red");

// phone tab switching
document.querySelectorAll(".tab").forEach((t) => {
  t.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("on"));
    t.classList.add("on");
    const tab = t.dataset.tab;
    document.querySelectorAll(".panel[data-tab]").forEach((p) =>
      p.classList.toggle("on", p.dataset.tab === tab)
    );
  };
});

function parisClock() {
  try {
    $("clock").textContent = new Date().toLocaleTimeString("en-GB", { timeZone: "Europe/Paris" });
  } catch (e) {}
}
setInterval(parisClock, 1000);
parisClock();

function setKpi(id, v) {
  const el = $(id);
  el.textContent = money(v);
  el.classList.remove("grn", "red");
  if (id !== "k-win") el.classList.add(cls(v));
}

function drawPrice(bars) {
  const svg = $("price-svg");
  if (!bars || bars.length < 2) { svg.innerHTML = ""; return; }
  const w = svg.clientWidth || 600, h = svg.clientHeight || 200;
  const xs = bars.map((b) => b[0]), ys = bars.map((b) => b[1]);
  const x0 = xs[0], x1 = xs[xs.length - 1], lo = Math.min(...ys), hi = Math.max(...ys);
  const px = (x) => ((x - x0) / (x1 - x0 || 1)) * w;
  const py = (y) => h - ((y - lo) / (hi - lo || 1)) * (h - 16) - 8;
  const d = bars.map((b, i) => (i ? "L" : "M") + px(b[0]).toFixed(1) + " " + py(b[1]).toFixed(1)).join(" ");
  const last = ys[ys.length - 1];
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.innerHTML =
    `<path d="${d}" fill="none" stroke="#37c9c9" stroke-width="1.5"/>` +
    `<text x="${w - 4}" y="${py(last) - 5}" text-anchor="end" fill="#37c9c9" font-size="14" font-family="monospace" font-weight="700">${last.toFixed(2)}</text>`;
}

async function tick() {
  let s;
  try { s = await (await fetch("api/status")).json(); } catch (e) { return; }
  // connection
  const c = $("conn");
  c.className = "conn" + (s.healthy ? "" : " off");
  $("conn-label").textContent = s.conn || "—";
  $("mode-chip").textContent = s.live ? "LIVE" : "DRY-RUN";
  $("mode-chip").className = "chip " + (s.live ? "bull" : "");
  // kpis
  setKpi("k-today", s.kpi?.today);
  setKpi("k-d7", s.kpi?.d7);
  setKpi("k-d30", s.kpi?.d30);
  $("k-win").textContent = s.kpi?.win == null ? "—" : s.kpi.win + "%";
  // position
  if (s.position) {
    $("pos-big").textContent = s.position.side;
    $("pos-big").className = "big " + (s.position.side === "LONG" ? "grn" : "red");
    $("pos-sub").textContent = "entry " + s.position.entry;
  } else {
    $("pos-big").textContent = "FLAT"; $("pos-big").className = "big"; $("pos-sub").textContent = "no open position";
  }
  // today
  $("d-realised").innerHTML = `<span class="${cls(s.kpi?.today)}">${money(s.kpi?.today)}</span>`;
  $("d-trades").textContent = s.kpi?.trades ?? "—";
  $("d-win").textContent = s.kpi?.win == null ? "—" : s.kpi.win + "%";
  // rolling
  $("rolltbl").innerHTML = `<tr><td>NET</td><td class="${cls(s.kpi?.today)}">${money(s.kpi?.today)}</td><td class="${cls(s.kpi?.d7)}">${money(s.kpi?.d7)}</td><td class="${cls(s.kpi?.d30)}">${money(s.kpi?.d30)}</td></tr>`;
  // trades
  $("tb-trades").textContent = s.trades?.length ?? "—";
  $("trades-meta").textContent = (s.trades?.length ?? 0) + " today";
  $("blotter").innerHTML = (s.trades && s.trades.length)
    ? s.trades.map((t) => `<tr><td>${t.t}</td><td><span class="pill ${t.side.toLowerCase()}">${t.side}</span></td><td class="mut">${t.exit}</td><td class="${cls(t.pnl)}">${money(t.pnl)}</td></tr>`).join("")
    : `<tr><td class="empty" colspan="4">no trades today</td></tr>`;
  // exec
  $("exec-pct").textContent = s.exec?.through == null ? "—" : s.exec.through + "%";
  $("exec-pct").className = "big " + (s.exec?.through >= 60 ? "grn" : s.exec?.through == null ? "" : "amb");
  $("exec-sub").textContent = `${s.exec?.fills ?? 0} fills · ${s.exec?.submitted ?? 0} submitted`;
  // shadow
  $("shadowtbl").innerHTML = (s.shadow && s.shadow.length)
    ? s.shadow.map((r) => `<tr><td>${r.strategy}</td><td>${r.n}</td><td class="${cls(r.pnl)}">${money(r.pnl)}</td><td>${r.win}%</td></tr>`).join("")
    : `<tr><td class="empty" colspan="4">no shadow trades yet</td></tr>`;
  // chart
  drawPrice(s.bars);
}

tick();
setInterval(tick, 3000);
