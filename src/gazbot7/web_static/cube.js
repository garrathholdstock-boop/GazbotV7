/* GAZBOT V7 — CUBE tab. The daily capture X-ray: market x session-phase heatmap, three
   measures (regime / P&L / flow), per-contract drill, daily-themes strip.
   Read-only over api/cube. Vanilla JS. Faithful port of the retired V5 Cube. */
(function () {
  "use strict";

  var REGIME_ABBR = { trending: "TREND", chop: "CHOP", shock: "SHOCK", dead: "DEAD" };
  var PHASE_LABEL = { overnight: "O/NIGHT", eu_session: "EU", us_open: "US OPEN",
    us_midday: "MIDDAY", us_pm: "US PM" };
  // default to P&L so the top-level grid opens HEAT-MAPPED by win/loss (green won / red lost)
  // instead of all-green regime. REGIME/FLOW remain one tap away.
  var state = { measure: "pnl", data: null };

  async function getJSON(url) {
    try { var r = await fetch(url); if (!r.ok) return null; return await r.json(); }
    catch (e) { return null; }
  }
  function fmtNum(x, d) { return (x === null || x === undefined) ? "—" : Number(x).toFixed(d === undefined ? 2 : d); }
  function clamp(x, lo, hi) { return Math.max(lo, Math.min(hi, x)); }

  // ---- cell rendering per measure -------------------------------------------------
  function cellRegime(cell) {
    if (!cell.cycles) return null;
    var reg = cell.dominant_regime;
    if (!reg) return null;
    var pct = (cell.regime_mix && cell.regime_mix[reg]) || 0;
    return { cls: "rg-" + reg, op: clamp(pct / 100, 0.35, 1),
      val: REGIME_ABBR[reg] || reg, sub: pct.toFixed(0) + "% · " + cell.cycles + "c" };
  }
  function cellPnl(cell, maxAbs) {
    if (!cell.trades) return null;
    var pnl = cell.pnl || 0;
    var op = clamp(Math.abs(pnl) / (maxAbs || 1), 0.3, 1);
    return { cls: pnl >= 0 ? "rg-trending" : "rg-shock", op: op,
      val: (pnl >= 0 ? "+" : "") + fmtNum(pnl, 0), sub: cell.trades + "t · " + (cell.win_rate === null ? "—" : Math.round(cell.win_rate * 100) + "%w") };
  }
  function cellFlow(cell, maxAbs) {
    if (cell.avg_ofi === null || cell.avg_ofi === undefined) return null;
    var ofi = cell.avg_ofi;
    var op = clamp(Math.abs(ofi) / (maxAbs || 1), 0.3, 1);
    return { cls: ofi >= 0 ? "rg-trending" : "rg-shock", op: op,
      val: (ofi >= 0 ? "+" : "") + fmtNum(ofi, 1), sub: cell.cycles + "c" };
  }

  function maxAbsFor(grid, markets, phases, pick) {
    var m = 0;
    markets.forEach(function (mk) { phases.forEach(function (ph) {
      var v = pick(grid[mk][ph]); if (v !== null && v !== undefined) m = Math.max(m, Math.abs(v));
    }); });
    return m || 1;
  }

  function renderGrid() {
    var d = state.data; var t = document.getElementById("grid");
    if (!d || !d.grid || !d.markets || !d.markets.length) { t.innerHTML = ""; return; }
    var markets = d.markets, phases = d.phases;
    var maxPnl = maxAbsFor(d.grid, markets, phases, function (c) { return c.trades ? c.pnl : null; });
    var maxOfi = maxAbsFor(d.grid, markets, phases, function (c) { return c.avg_ofi; });

    var html = "<thead><tr><th class='rowh'></th>";
    phases.forEach(function (p) { html += "<th>" + (PHASE_LABEL[p] || p) + "</th>"; });
    html += "</tr></thead><tbody>";
    markets.forEach(function (mk) {
      html += "<tr><th class='rowh'>" + mk + "</th>";
      phases.forEach(function (ph) {
        var cell = d.grid[mk][ph];
        var v = state.measure === "pnl" ? cellPnl(cell, maxPnl)
              : state.measure === "flow" ? cellFlow(cell, maxOfi)
              : cellRegime(cell);
        if (!v) {
          html += "<td class='empty' data-empty='1'>·</td>";
        } else {
          html += "<td class='" + v.cls + "' style='opacity:" + v.op.toFixed(2) +
            "' data-mk='" + mk + "' data-ph='" + ph + "'>" +
            "<div class='cval'>" + v.val + "</div><div class='csub'>" + v.sub + "</div></td>";
        }
      });
      html += "</tr>";
    });
    html += "</tbody>";
    t.innerHTML = html;
    var tds = t.querySelectorAll("td[data-mk]");
    for (var i = 0; i < tds.length; i++) {
      tds[i].addEventListener("click", function () { openDrill(this.dataset.mk, this.dataset.ph); });
    }
  }

  function renderLegend() {
    var el = document.getElementById("legend");
    if (state.measure === "regime") {
      el.innerHTML = ["trending", "chop", "shock", "dead"].map(function (r) {
        return "<span class='lk'><span class='sw sw-" + r + "'></span>" + r + "</span>";
      }).join("") + "<span class='lk' style='color:#678'>intensity = % of phase in that regime</span>";
    } else if (state.measure === "pnl") {
      el.innerHTML = "<span class='lk'><span class='sw sw-trending'></span>net profit</span>" +
        "<span class='lk'><span class='sw sw-shock'></span>net loss</span><span class='lk' style='color:#678'>intensity = magnitude</span>";
    } else {
      el.innerHTML = "<span class='lk'><span class='sw sw-trending'></span>net buying (OFI+)</span>" +
        "<span class='lk'><span class='sw sw-shock'></span>net selling (OFI−)</span><span class='lk' style='color:#678'>intensity = magnitude</span>";
    }
  }

  function renderThemes() {
    var el = document.getElementById("themes"); var th = state.data && state.data.themes;
    if (!th || !th.prescription_md) {
      el.innerHTML = "<div class='empty'>Daily themes generate nightly (Claude-authored). None yet for this day.</div>";
      return;
    }
    var tier = th.confidence_tier ? "<span class='tier'>" + th.confidence_tier + "</span>" : "";
    var verdict = th.verdict ? "<span class='verdict'>" + escapeHtml(th.verdict) + tier + "</span>" : "";
    el.innerHTML = verdict + "<div class='md'>" + mdLite(th.prescription_md) + "</div>";
  }

  function renderNote() {
    var el = document.getElementById("note");
    el.textContent = (state.data && state.data.note) ? state.data.note : "";
  }

  // ---- drill ----------------------------------------------------------------------
  function openDrill(mk, ph) {
    var d = state.data; var rows = (d.drill && d.drill[mk] && d.drill[mk][ph]) || [];
    document.getElementById("drill-title").textContent = mk + " · " + (PHASE_LABEL[ph] || ph) + " — per contract";
    var body = document.getElementById("drill-body");
    if (!rows.length) { body.innerHTML = "<div class='empty' style='color:#678;padding:8px'>No contracts captured in this cell.</div>"; }
    else {
      var h = "<table class='drill-tbl'><thead><tr><th>contract</th><th>regime</th><th>OFI</th>" +
        "<th>net_atr</th><th>cycles</th><th>trades</th><th>win%</th><th>P&L</th><th>gates</th></tr></thead><tbody>";
      var tPnl = 0, tCycles = 0, tTrades = 0, tWins = 0;
      rows.forEach(function (r) {
        var pnlCls = r.pnl > 0 ? "pos" : (r.pnl < 0 ? "neg" : "");
        var gates = Object.keys(r.gates || {}).map(function (g) { return g + "×" + r.gates[g]; }).join(", ");
        h += "<tr><td>" + r.symbol + "</td><td>" + (r.dominant_regime || "—") + "</td><td>" +
          fmtNum(r.avg_ofi, 1) + "</td><td>" + fmtNum(r.avg_net_atr, 2) + "</td><td>" + r.cycles +
          "</td><td>" + r.trades + "</td><td>" + (r.win_rate === null ? "—" : Math.round(r.win_rate * 100)) +
          "</td><td class='" + pnlCls + "'>" + fmtNum(r.pnl, 0) + "</td><td>" + escapeHtml(gates || "—") + "</td></tr>";
        tPnl += r.pnl || 0; tCycles += r.cycles || 0; tTrades += r.trades || 0;
        if (r.win_rate !== null && r.win_rate !== undefined) tWins += Math.round(r.win_rate * (r.trades || 0));
      });
      // TOTAL row so the cell's overall P&L is visible at the bottom.
      var tCls = tPnl > 0 ? "pos" : (tPnl < 0 ? "neg" : "");
      var tWinPct = tTrades ? Math.round((tWins / tTrades) * 100) : "—";
      h += "<tr class='total'><td><b>TOTAL</b></td><td></td><td></td><td></td><td>" + tCycles +
        "</td><td>" + tTrades + "</td><td>" + tWinPct + "</td><td class='" + tCls + "'><b>" +
        fmtNum(tPnl, 0) + "</b></td><td></td></tr>";
      body.innerHTML = h + "</tbody></table>";
    }
    document.getElementById("drill").hidden = false;
  }

  // ---- tiny markdown + escape -----------------------------------------------------
  function escapeHtml(s) { return String(s).replace(/[&<>]/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]; }); }
  function mdLite(s) {
    var h = escapeHtml(s);
    h = h.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\n\n/g, "</p><p>").replace(/\n/g, "<br>");
    return "<p>" + h + "</p>";
  }

  // ---- load -----------------------------------------------------------------------
  async function loadDay(day) {
    var d = await getJSON("api/cube/" + encodeURIComponent(day));
    state.data = d || { grid: {}, markets: [], phases: [], note: "CUBE unavailable." };
    document.getElementById("cube-day").textContent = (d && d.day) || day;
    renderThemes(); renderLegend(); renderGrid(); renderNote();
    document.getElementById("drill").hidden = true;
  }

  async function init() {
    var btns = document.querySelectorAll(".meas");
    for (var i = 0; i < btns.length; i++) {
      btns[i].addEventListener("click", function () {
        state.measure = this.dataset.m;
        var all = document.querySelectorAll(".meas");
        for (var j = 0; j < all.length; j++) all[j].classList.toggle("on", all[j] === this);
        renderLegend(); renderGrid();
      });
    }
    document.getElementById("drill-close").addEventListener("click", function () {
      document.getElementById("drill").hidden = true;
    });
    var sel = document.getElementById("day-select");
    sel.addEventListener("change", function () { loadDay(this.value); });

    var av = await getJSON("api/cube/available-days");
    var days = (av && av.days) || [];
    if (days.length) {
      sel.innerHTML = days.map(function (d) { return "<option value='" + d + "'>" + d + "</option>"; }).join("");
      await loadDay(days[0]);
    } else {
      sel.innerHTML = "<option>—</option>";
      await loadDay("latest");
    }
    tickClock(); setInterval(tickClock, 1000);
  }
  function tickClock() {
    var el = document.getElementById("clock");
    if (el) el.textContent = new Date().toLocaleTimeString("en-GB", { timeZone: "Europe/Paris", hour12: false });
  }
  document.addEventListener("DOMContentLoaded", init);
})();
