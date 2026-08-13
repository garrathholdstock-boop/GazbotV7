/* GAZBOT V7 — MNQ DESK (read-only presentation)
 * Reuses: /api/futures/mnq (MNQ-scoped header/rolling/gates/blotter/curve),
 *         /api/futures/us-terminal (holdings/activity-DTT/regime/margin — filter to MNQ),
 *         /api/futures/bars/MNQ (hero price).
 * No writes, no order entry. Numbers are net-of-fees (canonical desk P&L); sim numbers
 * are NOT rendered here (this is the live MNQ desk), so the honest-real_pnl rule is met
 * by omission. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const POLL_FAST_MS = 1000;   // chart / price / ribbon / DTT — as live as the feed allows
  const POLL_SLOW_MS = 5000;   // header P&L / blotter / leaderboard / gate perf
  let STATE = { mnq: null, us: null, tour: null, promo: null, bars: null, drill: null, tf: 120 };  // tf = chart window in minutes (2h default)

  /* ---------- formatting ---------- */
  const nf = (v, d = 2) => (v == null || isNaN(v)) ? "—" : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const usd = (v, d = 0) => (v == null || isNaN(v)) ? "—" : "$" + nf(Math.abs(v), d);
  function money(v, d = 0) { // signed, coloured class handled by caller
    if (v == null || isNaN(v)) return "—";
    const s = v < 0 ? "−" : (v > 0 ? "+" : "");
    return s + "$" + nf(Math.abs(v), d);
  }
  const pct = (v, d = 2) => (v == null || isNaN(v)) ? "—" : (v >= 0 ? "+" : "−") + nf(Math.abs(v), d) + "%";
  const cls = (v) => v == null || isNaN(v) ? "" : (v > 0 ? "pos" : (v < 0 ? "neg" : ""));
  // Compact gate/exit labels — the full code names (thrust_cont, DAYTRADE_ADVERSE_CUT) overflow the
  // narrow phone columns. These are DISPLAY-ONLY; drill keys still use the raw gate name.
  // tiny=true → the ultra-short phone forms (THR/VET/ORB, R1/R2/ABS/ADV/REC) for the squished blotter.
  function gateAbbr(g, tiny) {
    if (!g || g === "—") return "—";
    const k = String(g).toLowerCase().replace(/_(long|short)$/, "");
    if (tiny) {
      const T = {   // the 6 live V7 tournament gates (base names; _long/_short stripped above)
        rgv: "RGV", grind: "GRD", capitulation: "CAP", thrust: "THR", exhaustion: "EXH",
      };
      return T[k] || k.toUpperCase().replace(/[_-]/g, "").slice(0, 3);
    }
    const M = {
      rgv: "RGV", grind: "GRIND", capitulation: "CAPIT", thrust: "THRUST", exhaustion: "EXHST",
    };
    return M[k] || k.toUpperCase().replace(/[_-]/g, "").slice(0, 6);
  }
  function exitAbbr(x, tiny) {
    if (!x || x === "—") return "—";
    const c = String(x).replace(/^exit:/, "");
    if (tiny) {
      const T = {
        DAYTRADE_RATCHET_1: "R1", DAYTRADE_RATCHET_2: "R2",
        DAYTRADE_ADVERSE_CUT: "ADV", DAYTRADE_ABSORPTION_CUT: "ABS",
        DAYTRADE_FLAT_CLOCK: "CLK", DAYTRADE_PROFIT_LOCK: "LOC", DAYTRADE_FORCE_KILL: "FK",
        STOP_LOSS: "STP", MANUAL: "MAN", RECONSTRUCTED_BACKFILL: "REC", TRAIL: "TRL",
      };
      return T[c] || c.replace(/^DAYTRADE_/, "").toUpperCase().slice(0, 3);
    }
    const M = {
      DAYTRADE_RATCHET_1: "RATCH1", DAYTRADE_RATCHET_2: "RATCH2",
      DAYTRADE_ADVERSE_CUT: "ADVERSE", DAYTRADE_ABSORPTION_CUT: "ABSORB",
      DAYTRADE_FLAT_CLOCK: "CLOCK", DAYTRADE_PROFIT_LOCK: "LOCK", DAYTRADE_FORCE_KILL: "FORCE",
      STOP_LOSS: "STOP", MANUAL: "MANUAL", RECONSTRUCTED_BACKFILL: "BACKFILL", TRAIL: "TRAIL",
    };
    return M[c] || c.replace(/^DAYTRADE_/, "").toUpperCase().slice(0, 8);
  }
  function parisHM(iso) {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleTimeString("en-GB", { timeZone: "Europe/Paris", hour: "2-digit", minute: "2-digit" }); }
    catch (e) { return "—"; }
  }
  function holdStr(sec) {
    if (sec == null) return "—";
    sec = Math.max(0, Math.floor(sec));
    const m = Math.floor(sec / 60), s = sec % 60;
    if (m >= 60) return Math.floor(m / 60) + "h" + String(m % 60).padStart(2, "0");
    return m + "m" + String(s).padStart(2, "0");
  }
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const sidePill = (side) => `<span class="pill ${side === "SHORT" ? "short" : "long"}">${side || "LONG"}</span>`;

  /* ---------- fetch ---------- */
  async function getJSON(url) {
    const r = await fetch(url, { headers: { "Cache-Control": "no-cache" } });
    if (!r.ok) throw new Error(url + " -> " + r.status);
    return r.json();
  }

  // Two-tier refresh (2026-07-13): the price chart + ribbon + DTT + holding update FAST (1s) off the
  // light bars/activity feeds; the heavy panels (header P&L, blotter, leaderboard, gate perf) stay at
  // POLL_SLOW_MS so they don't flicker or reset scroll every second. In-flight guards stop ticks stacking
  // if a fetch runs long.
  let _fastBusy = false, _slowBusy = false;
  async function fastTick() {
    if (_fastBusy) return; _fastBusy = true;
    try {
      const us = await getJSON("api/futures/us-terminal").catch(() => null);
      if (us) STATE.us = us;
      const tour = await getJSON("api/futures/tournament").catch(() => null);
      if (tour) STATE.tour = tour;
      try { STATE.bars = await getJSON("api/futures/bars/MNQ?timeframe=1m&count=" + STATE.tf); } catch (e) { /* keep last */ }
      try { renderConn(us != null); renderSafety(); renderRibbonAndDTT(); renderHero(); renderHolding(); renderTournament(); } catch (e) { console.error("fast", e); }
    } finally { _fastBusy = false; }
  }
  async function slowTick() {
    if (_slowBusy) return; _slowBusy = true;
    try {
      const mnq = await getJSON("api/futures/mnq").catch(() => null);
      if (mnq) STATE.mnq = mnq;
      const ex = await getJSON("api/futures/execution").catch(() => null);
      if (ex) STATE.exec = ex;
      const promo = await getJSON("api/futures/promotion").catch(() => null);
      if (promo) STATE.promo = promo;
      const m = STATE.mnq || {};
      try {
        renderHeader(m); renderDesk(m); renderTrades(m); renderTabBadges(m); renderExec(STATE.exec); renderPromotion();
        if (STATE.drill) reAggregateDrill();
      } catch (e) { console.error("slow", e); }
    } finally { _slowBusy = false; }
  }

  /* ---------- MNQ slices out of us-terminal ---------- */
  const mnqHoldings = () => ((STATE.us && STATE.us.holdings) || []).filter((h) => (h.label === "MNQ" || h.symbol === "MNQ"));
  const mnqActivity = () => (((STATE.us && STATE.us.activity) || []).filter((a) => a.symbol === "MNQ" || a.label === "MNQ")[0]) || null;

  /* ========================================================================= */
  function renderAll(ok) {
    const m = STATE.mnq || {};
    renderConn(ok);
    renderHeader(m);
    renderRibbonAndDTT();
    renderHero();
    renderSafety();
    renderDesk(m);
    renderHolding();
    renderTournament();
    renderPromotion();
    renderTrades(m);
    renderTabBadges(m);
    renderExec(STATE.exec);
    if (STATE.drill) reAggregateDrill(); // keep an open drill live
  }

  /* ---------- EXECUTION HEALTH (signal → fill through-rate + slippage + blocks) ---------- */
  function renderExec(e) {
    e = e || {};
    const c = e.current || null;
    const f = e.funnel || {};
    const pctEl = $("exec-pct"), subEl = $("exec-sub"), badge = $("tb-exec");
    if (!c || !f.submitted) {           // no entries yet today → honest empty state (not "broken")
      pctEl.textContent = "—"; pctEl.className = "big mut";
      subEl.textContent = c ? "no entries submitted yet today" : "monitor warming up…";
      $("exec-funnel").innerHTML = '<div class="empty">no entries yet today</div>';
      $("exec-blocks").innerHTML = '<tr><td class="empty" colspan="2">none</td></tr>';
      $("exec-pergate").innerHTML = '<tr><td class="empty" colspan="7">—</td></tr>';
      $("exec-slip").textContent = "—";
      if (badge) badge.textContent = "—";
      return;
    }
    const pct = c.pct;
    pctEl.textContent = pct + "%";
    pctEl.className = "big " + (c.level === "CRIT" ? "neg" : (pct >= 90 ? "pos" : pct >= 70 ? "warn" : "neg"));
    subEl.textContent = f.filled + "/" + f.submitted + " entries filled" + (f.nofill ? " · " + f.nofill + " no-fill" : "");
    if (badge) badge.textContent = pct + "%";

    // the funnel: submitted → filled, with the misses called out
    const miss = (f.nofill || 0) + (f.rejected || 0);
    const seg = (label, n, klass) => n > 0
      ? `<div class="fn-seg ${klass}" style="flex:${n}"><b>${n}</b><span>${label}</span></div>` : "";
    $("exec-funnel").innerHTML =
      `<div class="fn-bar">${seg("filled", f.filled, "fn-ok")}${seg("no-fill", f.nofill, "fn-miss")}${seg("rejected", f.rejected, "fn-rej")}</div>`
      + `<div class="fn-cap">${f.submitted} submitted → <span class="grn">${f.filled} bought</span>${miss ? ` · <span class="red">${miss} missed</span>` : ""}</div>`;

    const slip = $("exec-slip");
    if (c.slip_ticks != null) {
      slip.textContent = (c.slip_ticks > 0 ? "+" : "") + nf(c.slip_ticks, 1) + " tk (" + money(c.slip_usd, 2) + ")";
      slip.className = "val" + (c.slip_ticks > 4 ? " neg" : "");
    } else { slip.textContent = "—"; slip.className = "val"; }

    const bt = $("exec-blocks"), bl = c.blocks || {};
    const keys = Object.keys(bl).filter((k) => bl[k] > 0);
    bt.innerHTML = keys.length
      ? keys.map((k) => "<tr><td>" + esc(k) + "</td><td class='neg'>" + bl[k] + "</td></tr>").join("")
      : '<tr><td class="empty" colspan="2">none — every entry filled</td></tr>';

    const pg = e.per_gate || [];
    $("exec-pergate").innerHTML = pg.length ? pg.map((r) =>
      `<tr><td>${esc(gateAbbr(r.gate))}</td><td class="${r.side === "SHORT" ? "red" : "grn"}">${(r.side || "")[0] || ""}</td>`
      + `<td>${r.submitted}</td><td>${r.filled}</td>`
      + `<td class="${r.through == null ? "" : (r.through >= 90 ? "grn" : "amb")}">${r.through == null ? "—" : r.through + "%"}</td>`
      + `<td class="${r.nofill ? "red" : ""}">${r.nofill || 0}</td>`
      + `<td>${r.slip_ticks == null ? "—" : (r.slip_ticks > 0 ? "+" : "") + nf(r.slip_ticks, 1) + "tk"}</td></tr>`
    ).join("") : '<tr><td class="empty" colspan="7">—</td></tr>';

    const tr = $("exec-trend"), t = e.trend || [];
    tr.innerHTML = t.length
      ? t.map((x) => {
          const col = x.level === "CRIT" ? "neg" : (x.level === "WARN" ? "warn" : "pos");
          const h = Math.max(6, Math.round((x.pct / 100) * 40));
          return '<span class="exec-bar ' + col + '" title="' + x.pct + "% · " + x.events + 'ev" style="height:' + h + 'px"></span>';
        }).join("")
      : '<div class="empty">—</div>';
  }

  function renderConn(ok) {
    const conn = $("conn"), lbl = $("conn-label");
    const act = mnqActivity();
    const open = act ? !!act.session_active : null;
    conn.className = "conn" + (ok ? "" : " off");
    lbl.textContent = ok ? "CONNECTED" : "DISCONNECTED";
    const mk = $("mkt-chip");
    if (!ok) { mk.textContent = "—"; mk.className = "chip"; }
    else if (open === false) { mk.textContent = "MARKET CLOSED"; mk.className = "chip chop"; }
    else { mk.textContent = "MARKET OPEN"; mk.className = "chip bull"; }
    // the safety pill (was the dead regime chip) is owned by renderSafety()
  }

  function renderHeader(m) {
    const h = m.header || {};
    $("expiry").textContent = m.expiry || "—";
    $("hero-expiry").textContent = m.expiry || "—";
    $("k-fee").textContent = m.fee_per_rt != null ? "−$" + nf(m.fee_per_rt, 2) + "/RT" : "NET";
    const set = (id, v, d = 0) => { const el = $(id); el.textContent = money(v, d); el.className = "v " + cls(v); };
    // ★2026-08-13 TODAY is the WHOLE desk now, with the two books underneath. The day-rider is a
    // separate service on its own clientId holding for hours, and its P&L appeared in no total at
    // all — the operator watched it hold and then saw nothing. Week that prompted it: tournament
    // −$438 while the rider made +$1,183.50. Falls back to h.today (tournament-only) so an older
    // API build still renders rather than showing "—".
    const total = h.today_total != null ? h.today_total : h.today;
    set("k-today", total); set("k-yest", h.yest); set("k-d2", h.d2); set("k-d7", h.d7); set("k-d30", h.d30);
    const sub = (id, label, v) => {
      const el = $(id); if (!el) return;
      el.textContent = v == null ? label + " —" : label + " " + money(v, 0);
      el.className = cls(v);
    };
    sub("k-today-trn", "TRN", h.today_tournament);
    sub("k-today-rdr", "RDR", h.today_rider);
    $("k-win").textContent = h.win_today != null ? h.win_today + "%" : "—";
  }

  /* ---------- ribbon + distance-to-trigger ---------- */
  function renderRibbonAndDTT() {
    const a = mnqActivity();
    const rib = $("ribbon");
    if (!a || !a.is_known) {
      rib.innerHTML = `<div class="empty" style="width:100%">no live tape — md-daemon dark or session closed</div>`;
      $("dtt").innerHTML = `<div class="empty">—</div>`;
      $("hero-state").textContent = "● no tape";
      return;
    }
    $("hero-state").textContent = "● " + (a.state || a.session_regime || "live");
    const violCls = { asleep: "v-dead", calm: "v-dead", normal: "v-ok", elevated: "v-warn", violent: "v-hot" };
    const erCls = { trend: "v-ok", mixed: "v-warn", chop: "v-dead" };
    const erWord = { trend: "clean · ride", chop: "messy · chop", mixed: "mixed" };
    const tiles = [
      { l: "ATR · how big", v: a.atr_pts == null ? "—" : nf(a.atr_pts, 1) + "pt",
        sub: a.atr_usd == null ? "" : "$" + a.atr_usd + "/lot · " + (a.violence || "").toUpperCase(),
        cls: violCls[a.violence] || "" },
      { l: "EFFICIENCY · how clean", v: a.er == null ? "—" : nf(a.er, 2),
        sub: a.day_type ? (a.day_type.toUpperCase() + " · " + (erWord[a.day_type] || "")) : "",
        cls: erCls[a.day_type] || "" },
      { l: "LAST", v: a.last == null ? "—" : nf(a.last, 1), sub: "price", cls: "" },
      { l: "VWAP", v: a.vwap == null ? "—" : nf(a.vwap, 1),
        sub: (a.last != null && a.vwap != null) ? (a.last >= a.vwap ? "▲ above" : "▼ below") : "", cls: "" },
    ];
    rib.innerHTML = tiles.map((t) =>
      `<div class="rtile ${t.cls}"><div class="l">${t.l}</div><div class="v">${esc(t.v)}</div><div class="l dim3">${esc(t.sub || "")}</div></div>`
    ).join("")
      + `<div class="read-hint">📖 <b>real move</b> = ATR ≥16pt (big/violent) · a <b>clean line</b> (ER ≥0.18) · price travels 8+ ATR one way. Small ATR or messy ER = sit.</div>`;

    const gates = a.gates || [];
    $("dtt").innerHTML = gates.length ? gates.map((g) => {
      const p = Math.max(0, Math.min(100, g.prox || 0));
      const fire = p >= 100;
      return `<div class="dtt-row">
        <span class="dl">${esc(gateAbbr(g.gate))} ${g.side && g.side !== "—" ? sideMini(g.side) : ""}</span>
        <span class="dbar"><span class="dfill ${fire ? "fire" : ""}" style="width:${p}%"></span></span>
        <span class="dpct">${p}</span>
        <span class="dblk">${esc(fire ? "FIRE" : (g.blocker || ""))}</span></div>`;
    }).join("") : `<div class="empty">no armed-gate telemetry (md tape idle)</div>`;
  }
  const sideMini = (s) => `<span class="${s === "SHORT" ? "red" : "grn"}">${s}</span>`;

  /* ---------- hero price chart ---------- */
  function renderHero() {
    const svg = $("price-svg");
    const host = svg.parentElement;               // .chart-host — the real pixel box
    // Skip while the CHART tab is HIDDEN on phone (display:none → clientHeight 0). Drawing then would
    // bake a bogus viewBox that gets stretched into the pane on show (the "squished at top" bug). The
    // tab-switch handler re-calls renderHero the moment it becomes visible, so it draws at the true size.
    if (host.clientHeight === 0 || host.clientWidth === 0) return;
    const bars = (STATE.bars && STATE.bars.bars || []).filter((b) => typeof b.close === "number" && b.ts);
    // Draw in TRUE PIXEL SPACE: viewBox == the host's pixel size, so text is never distorted (the old
    // stretched viewBox forced axis labels into fragile HTML overlays). preserveAspectRatio is moot at 1:1.
    const W = Math.max(320, Math.round(host.clientWidth));
    const H = Math.max(160, Math.round(host.clientHeight));
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    if (bars.length < 2) { svg.innerHTML = `<text x="${(W / 2).toFixed(0)}" y="${(H / 2).toFixed(0)}" fill="#5c6b78" font-size="15" text-anchor="middle">no bars yet</text>`; $("chart-legend").innerHTML = ""; return; }
    const ML = 56, MT = 10, MB = 20;              // margins: left = price axis, bottom = time axis
    // bar.ts is an ISO string ("2026-07-13T16:40:00+00:00") — parse to epoch SECONDS so the time axis
    // is numeric AND aligns with the fills (which use Date.parse(...)/1000). Without this every X was NaN.
    const T = (b) => Date.parse(b.ts) / 1000;
    const t0 = T(bars[0]), t1 = T(bars[bars.length - 1]), tspan = Math.max(1, t1 - t0);
    const a = mnqActivity();
    const holds = mnqHoldings();
    const hold = holds[0] || null;
    const fills = (STATE.mnq && STATE.mnq.blotter) || [];
    // ATR context for the RIGHT axis: 1 ATR in points = atr_pct (already a % of price) / 100 * price.
    // Each gridline is then labelled by its distance from the CURRENT price in ATRs, so the vertical
    // scale reads as volatility context, not just raw price.
    const refP = (a && a.last) || bars[bars.length - 1].close;
    const atrPts = (a && typeof a.atr_pct === "number" && a.atr_pct > 0) ? (a.atr_pct / 100) * refP : null;
    const MR = atrPts ? 50 : 12;                  // widen the right margin to hold the ATR-distance axis
    const plotL = ML, plotR = W - MR, plotT = MT, plotB = H - MB;
    // y-scale to the PRICE BARS with padding so the line is CENTRED vertically — never crushed by a
    // far-away stop or an out-of-window fill (a 0.5% stop would squash the real action into a sliver).
    // Reference levels are drawn only when they fall INSIDE this range; the stop lives on the HOLD tab.
    let lo = Infinity, hi = -Infinity;
    bars.forEach((b) => { lo = Math.min(lo, b.close); hi = Math.max(hi, b.close); });
    const pad = Math.max((hi - lo) * 0.15, lo * 0.0004);   // 15% top/bottom → line sits centred
    lo -= pad; hi += pad;
    let rng = hi - lo; if (rng < 1e-6) { lo -= 1; hi += 1; rng = hi - lo; }
    const inRange = (p) => (typeof p === "number" && p >= lo && p <= hi);
    const X = (t) => plotL + (plotR - plotL) * Math.max(0, Math.min(1, (t - t0) / tspan));
    const Y = (p) => plotT + (plotB - plotT) * (1 - (p - lo) / rng);
    const hm = (ts) => { try { return new Date(ts * 1000).toLocaleTimeString("en-GB", { timeZone: "Europe/Paris", hour: "2-digit", minute: "2-digit" }); } catch (e) { return ""; } };

    let g = "";
    // Y axis — 5 price gridlines. LEFT label = price; RIGHT label = distance from current price in ATRs.
    for (let i = 0; i <= 4; i++) {
      const p = lo + rng * i / 4, y = Y(p);
      g += `<line x1="${plotL}" y1="${y.toFixed(1)}" x2="${plotR}" y2="${y.toFixed(1)}" stroke="#212b35" stroke-width="1" opacity="0.7"/>`;
      g += `<text x="${plotL - 6}" y="${(y + 4).toFixed(1)}" fill="#8a99a6" font-size="12" font-family="ui-monospace,SFMono-Regular,monospace" text-anchor="end">${nf(p, 1)}</text>`;
      if (atrPts) {
        const dd = (p - refP) / atrPts;
        const lbl = (dd >= 0 ? "+" : "−") + nf(Math.abs(dd), 1);
        g += `<text x="${(plotR + 6).toFixed(1)}" y="${(y + 4).toFixed(1)}" fill="#6b8f8f" font-size="11" font-family="ui-monospace,SFMono-Regular,monospace" text-anchor="start">${lbl}</text>`;
      }
    }
    // label the right axis so the +/- numbers read as ATRs (bottom-right, on the time-axis line)
    if (atrPts) g += `<text x="${(plotR + 6).toFixed(1)}" y="${(H - 6).toFixed(1)}" fill="#6b8f8f" font-size="9" letter-spacing="0.5" font-family="ui-monospace,SFMono-Regular,monospace" text-anchor="start">ATR</text>`;
    // X axis — 4 time ticks across the window (first left-anchored, last right-anchored so neither clips)
    for (let i = 0; i <= 3; i++) {
      const t = t0 + tspan * i / 3, x = X(t);
      const anc = i === 0 ? "start" : (i === 3 ? "end" : "middle");
      g += `<line x1="${x.toFixed(1)}" y1="${plotT}" x2="${x.toFixed(1)}" y2="${plotB}" stroke="#212b35" stroke-width="1" opacity="0.3"/>`;
      g += `<text x="${x.toFixed(1)}" y="${H - 6}" fill="#8a99a6" font-size="12" font-family="ui-monospace,SFMono-Regular,monospace" text-anchor="${anc}">${hm(t)}</text>`;
    }
    // vwap reference (a real price level) — only if it falls in the price range
    if (a && inRange(a.vwap)) g += `<line x1="${plotL}" y1="${Y(a.vwap).toFixed(1)}" x2="${plotR}" y2="${Y(a.vwap).toFixed(1)}" stroke="#37c9c9" stroke-width="1" stroke-dasharray="4 4" opacity="0.6"/>`;
    // held position lines per open slot — entry (grey) + stop (red), drawn only when in range
    holds.forEach((h) => {
      if (inRange(h.avg)) g += line(plotL, Y(h.avg), plotR, Y(h.avg), "#8a99a6", "2 3");
      if (inRange(h.stop)) g += line(plotL, Y(h.stop), plotR, Y(h.stop), "#ff5a5f", "3 3");
    });
    // price polyline
    const pts = bars.map((b) => X(T(b)).toFixed(1) + "," + Y(b.close).toFixed(1)).join(" ");
    g += `<polyline points="${pts}" fill="none" stroke="#c6d2db" stroke-width="1.5"/>`;
    // fills (today) — entry ▲ / exit ▼, long green / short red
    fills.forEach((f) => {
      const col = f.side === "SHORT" ? "#ff5a5f" : "#37d07a";
      const te = f.opened_at ? Date.parse(f.opened_at) / 1000 : null;
      const tx = f.time ? Date.parse(f.time) / 1000 : null;
      if (te && te >= t0 && te <= t1 && inRange(f.entry)) g += tri(X(te), Y(f.entry), col, true);
      if (tx && tx >= t0 && tx <= t1 && inRange(f.exit_price)) g += tri(X(tx), Y(f.exit_price), col, false);
    });
    // live last-price tag — pinned to the very TOP-RIGHT corner, in the padded empty band above the
    // centred line so it never sits on top of the price point. Drawn last = on top.
    const lastP = (a && a.last) || bars[bars.length - 1].close;
    if (lastP != null) {
      const txt = nf(lastP, 2), tw = txt.length * 8 + 10, by = 1;
      g += `<rect x="${(plotR - tw).toFixed(1)}" y="${by}" width="${tw}" height="17" rx="3" fill="#37c9c9"/>`;
      g += `<text x="${(plotR - tw / 2).toFixed(1)}" y="${by + 12.5}" fill="#04110f" font-size="12" font-weight="700" font-family="ui-monospace,SFMono-Regular,monospace" text-anchor="middle">${txt}</text>`;
    }
    svg.innerHTML = g;
    const leg = [];
    leg.push(`<span><span class="sw" style="background:#c6d2db"></span>MNQ price</span>`);
    if (a && a.vwap) leg.push(`<span><span class="sw" style="background:#37c9c9"></span>VWAP ${nf(a.vwap, 1)}</span>`);
    if (holds.some((h) => h.stop)) leg.push(`<span><span class="sw" style="background:#ff5a5f"></span>stop</span>`);
    leg.push(`<span>▲ entry · ▼ exit · <span class="grn">long</span>/<span class="red">short</span></span>`);
    if (atrPts) leg.push(`<span>right axis = ATR from price · 1 ATR ≈ ${nf(atrPts, 1)}pt (${nf(a.atr_pct, 2)}%)</span>`);
    if (a && a.last) leg.push(`<span class="cyan">last ${nf(a.last, 2)}</span>`);
    $("chart-legend").innerHTML = leg.join("");
  }
  const line = (x1, y1, x2, y2, c, dash) => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${c}" stroke-width="1" stroke-dasharray="${dash}" opacity="0.7"/>`;
  function tri(x, y, col, up) {
    const s = 5;
    return up
      ? `<polygon points="${x},${y - s} ${x - s},${y + s} ${x + s},${y + s}" fill="${col}"/>`
      : `<polygon points="${x},${y + s} ${x - s},${y - s} ${x + s},${y - s}" fill="${col}"/>`;
  }

  /* ---------- desk stats ---------- */
  function renderDesk(m) {
    const hold = mnqHoldings();
    const unreal = hold.reduce((s, h) => s + (h.pnl_usd || 0), 0);
    const anyOpen = hold.length > 0;
    const ue = $("unreal");
    ue.textContent = anyOpen ? money(unreal, 2) : "—";
    ue.className = "big " + (anyOpen ? cls(unreal) : "mut");
    $("unreal-sub").textContent = anyOpen ? (hold.length + " slot" + (hold.length > 1 ? "s" : "") + " open") : "FLAT — no open slots";

    // positioning (desk-level)
    const h = m.header || {};
    const openContracts = hold.reduce((s, x) => s + Math.abs(x.qty || 0), 0);
    $("pos-open").textContent = anyOpen ? String(openContracts) : "0";
    const pr = $("pos-realised"); pr.textContent = money(h.today, 2); pr.className = "val " + cls(h.today);
    $("pos-trades").textContent = h.trades_today != null ? h.trades_today : "—";
    $("pos-win").textContent = h.win_today != null ? h.win_today + "%" : "—";

    // rolling table (net / win / N — PF & MaxDD not computed in V7)
    const roll = m.rolling || {};
    const rk = ["1D", "7D", "30D"];
    const rrow = (label, fn) => `<tr><td>${label}</td>` + rk.map((k) => fn(roll[k] || {})).join("") + `</tr>`;
    $("rolltbl").innerHTML =
      rrow("Net", (s) => `<td class="${cls(s.pnl)}">${money(s.pnl, 0)}</td>`) +
      rrow("Win", (s) => `<td>${s.win == null ? "—" : s.win + "%"}</td>`) +
      rrow("N", (s) => `<td>${s.trades || 0}</td>`);

    // losses by exit (now wired)
    const lb = m.loss_buckets || [];
    $("lossbkt").innerHTML = lb.length ? lb.map((r) =>
      `<tr><td>${esc(exitAbbr(r.cause))}</td><td>${r.n}</td><td class="neg">${money(r.usd, 0)}</td></tr>`
    ).join("") : `<tr><td class="empty" colspan="3">no losses today</td></tr>`;
  }

  /* ---------- holding — the multi-slot tournament (one card per open slot) ---------- */
  function renderHolding() {
    const holds = mnqHoldings();
    const meta = $("hold-meta");
    const body = $("hold-body");
    if (!holds.length) {
      meta.textContent = "flat";
      body.innerHTML = `<div class="empty" style="padding:26px 4px"><div style="font-size:16px;letter-spacing:2px;color:var(--txt2)">FLAT</div><div style="margin-top:6px">no open MNQ slots</div></div>`;
      return;
    }
    const totUnreal = holds.reduce((s, h) => s + (h.pnl_usd || 0), 0);
    meta.innerHTML = `${holds.length} slot${holds.length > 1 ? "s" : ""} open · <span class="${cls(totUnreal)}">${money(totUnreal, 2)}</span>`;
    const card = (h) => {
      const side = h.side || (h.qty < 0 ? "SHORT" : "LONG");
      const prot = h.protected
        ? `<span class="prot-ok">stop ${h.stop != null ? nf(h.stop, 2) : "armed"}</span>`
        : `<span class="prot-naked">⚠ NAKED</span>`;
      const rows = [
        ["Contracts", `${Math.abs(h.qty || 0)} × ${nf(h.multiplier, 0)}`],
        ["Unrealised", `<span class="${cls(h.pnl_usd)}">${money(h.pnl_usd, 2)} · ${pct(h.pnl_pct, 2)}</span>`],
        ["Entry", nf(h.avg, 2)],
        ["Last", `<span class="cyan">${nf(h.last, 2)}</span>`],
        ["Stop", h.stop ? `<span class="red">${nf(h.stop, 2)}</span>` : "—"],
        ["Time in trade", holdStr(h.held_seconds)],
      ];
      /* ★ CLAIM PROFIT — day rider only (2026-08-10, operator).
         "if im actively watching and its at $300 i can go bang and put it to bed."
         The button only appears on the day rider's own row, beside the live P&L
         it is claiming, so there is no doubt about which position is being
         banked. It does NOT flatten from here: it POSTs a request and the day
         rider flattens on its own next tick through its own ownership check.
         A dashboard that placed orders directly is how 2026-08-06 happened. */
      const claim = h.entry_gate === "day_rider"
        ? `<button class="claimbtn" data-claim="1">Claim profit</button>` : "";
      return `<div class="slot-card">`
        + `<div class="hold-head">${sidePill(side)}<span class="sym">${esc(gateAbbr(h.entry_gate))}</span>${prot}${claim}</div>`
        + rows.map((r) => `<div class="row"><span class="k">${r[0]}</span><span class="val">${r[1]}</span></div>`).join("")
        + `</div>`;
    };
    body.innerHTML = holds.map(card).join("");

    /* Wired after render because the cards are rebuilt on every poll. The
       confirm states the two things that surprise people: it is not instant,
       and it ends the session. */
    Array.prototype.forEach.call(body.querySelectorAll("[data-claim]"), (b) => {
      b.onclick = () => {
        const dr = holds.filter((x) => x.entry_gate === "day_rider")[0];
        const pnl = dr ? nf(dr.pnl_usd, 2) : "?";
        if (!window.confirm(
          "Claim the day rider's position?\n\n"
          + "Showing " + pnl + " right now.\n\n"
          + "It flattens on the day rider's next tick — up to about 60 seconds — so the fill "
          + "will not be exactly this number.\n\n"
          + "This ENDS its session: it will not re-enter today.")) return;
        const pin = window.prompt("PIN");
        if (!pin) return;
        b.disabled = true; b.textContent = "Claiming…";
        /* RELATIVE, no leading slash — every other call in this file is relative
           and it is load-bearing: the dashboard is mounted under /v7/, so a
           leading slash resolves to the domain ROOT, which is not routed to this
           backend. That spelling failed as "no connection" without ever leaving
           the browser. */
        fetch("api/control/dayrider-claim", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pin: pin }),
        }).then((r) => {
          /* Check the STATUS before parsing. A 404 returns an HTML error page,
             r.json() throws on it, and the catch below then blamed the network —
             which is how a wrong URL spent a press looking like a dead line. */
          if (!r.ok) throw new Error("server said " + r.status);
          return r.json();
        }).then((j) => {
          b.textContent = j && j.ok ? "Claimed" : "Claim profit";
          b.disabled = !!(j && j.ok);
          window.alert(j && j.ok ? j.msg : "Not claimed: " + ((j && j.error) || "unknown"));
        }).catch((e) => {
          b.disabled = false; b.textContent = "Claim profit";
          window.alert("Not claimed — " + (e && e.message ? e.message : "no connection")
            + ".\n\nThe position is untouched.");
        });
      };
    });
  }

  /* ---------- tournament — the 6-gate scoreboard ---------- */
  function renderSafety() {
    const d = (STATE.tour && STATE.tour.desk) || null;
    const chip = $("safety-chip");
    if (!chip) return;
    if (!d) { chip.textContent = "SAFETY —"; chip.className = "chip"; return; }
    const lvl = d.safety || "green";
    const txt = d.halted ? "HALTED" : d.any_naked ? "NAKED" : d.unverified_cycles ? "UNVERIFIED"
      : (d.flat ? "FLAT · protected" : (d.live_count + " live · protected"));
    chip.textContent = "SAFETY · " + txt;
    chip.className = "chip safety-" + lvl;
    const halt = $("halt");
    if (halt) halt.classList.toggle("on", !!d.halted);
  }

  function renderTournament() {
    const t = STATE.tour;
    if (!t) return;
    const holds = mnqHoldings();
    $("tourn-slots").innerHTML = holds.length ? holds.map((h) => {
      const side = h.side || "LONG";
      const prot = h.protected ? `<span class="prot-ok">◈ stop</span>` : `<span class="prot-naked">⚠ NAKED</span>`;
      return `<div class="slot-tile">
        <div class="st-top">${sidePill(side)}<b>${esc(gateAbbr(h.entry_gate))}</b>${prot}</div>
        <div class="st-pnl ${cls(h.pnl_usd)}">${money(h.pnl_usd, 2)}</div>
        <div class="st-sub">${Math.abs(h.qty || 0)} @ ${nf(h.avg, 1)} · ${holdStr(h.held_seconds)}</div>
      </div>`;
    }).join("") : `<div class="empty">flat — no open slots</div>`;

    const g = t.gates || [];
    $("tourn-rows").innerHTML = g.length ? g.map((r, i) => {
      const dot = r.live ? `<span class="live-dot" title="live now"></span>` : "";
      // armed (taking new entries) vs benched (off in gate_switches.env). This is the
      // "what gates are live" the operator couldn't read off the dashboard before.
      const status = r.enabled === false
        ? `<span class="gpill off" title="benched — takes no new entries">BENCHED</span>`
        : `<span class="gpill on" title="armed — taking new entries">ON</span>`;
      const clk = r.n ? "clickable" : "";       // only gates with trades have a drill
      // week-to-date winner/loser expectancy (operator's low-win-rate/big-winner lens):
      // avg winner $, avg loser $ (both shown as plain magnitudes), and their delta.
      const plain = (v) => v == null ? "·" : "$" + nf(Math.abs(v), 0);
      const wkT = r.wk_n
        ? `week-to-date: ${r.wk_wins}W / ${r.wk_losses}L · expectancy ${money(r.wk_exp, 1)}/trade`
        : "no trades this week";
      return `<tr class="${r.enabled === false ? "benched " : ""}${r.relegate ? "releg " : ""}${clk}" data-key="${esc(r.gate)}|${r.side}">
        <td>${r.relegate ? "🔻" : (i + 1)}</td>
        <td>${dot}${esc(gateAbbr(r.gate))} ${status}</td>
        <td class="${r.side === "SHORT" ? "red" : "grn"}">${r.side[0]}</td>
        <td class="${r.live ? cls(r.open_unreal) : "mut"}">${r.live ? money(r.open_unreal, 0) : "·"}</td>
        <td class="${r.n ? cls(r.realized) : "mut"}">${r.n ? money(r.realized, 0) : "·"}</td>
        <td class="tot ${cls(r.total)}">${money(r.total, 0)}</td>
        <td>${r.n}</td>
        <td>${r.win_pct == null ? "—" : r.win_pct + "%"}</td>
        <td>${r.pf == null ? "—" : nf(r.pf, 2)}</td>
        <td class="wk ${r.wk_avg_win == null ? "mut" : "pos"}" title="${r.wk_wins || 0} winners this week">${plain(r.wk_avg_win)}</td>
        <td class="wk ${r.wk_avg_loss == null ? "mut" : "neg"}" title="${r.wk_losses || 0} losers this week">${plain(r.wk_avg_loss)}</td>
        <td class="wk ${cls(r.wk_delta)}" title="${esc(wkT)}">${r.wk_delta == null ? "·" : money(r.wk_delta, 0)}</td>
      </tr>`;
    }).join("") : `<tr><td class="empty" colspan="12">—</td></tr>`;
    document.querySelectorAll("#tourn-rows tr.clickable").forEach((tr) => {
      tr.onclick = () => openDrill(tr.getAttribute("data-key"));
    });

    const d = t.desk || {};
    $("tourn-meta").textContent =
      `${d.enabled_count}/${d.roster_count} armed · ${d.live_count} live · today ${money(d.realized_today, 0)} · open ${money(d.open_unreal, 0)}`;
  }

  function renderPromotion() {
    const el = $("promo-rows");
    if (!el) return;
    const c = (STATE.promo && STATE.promo.candidates) || [];
    el.innerHTML = c.length ? c.slice(0, 10).map((r) =>
      `<tr class="${r.candidate ? "promo-cand" : ""}">`
      + `<td>${r.candidate ? "★" : ""}</td>`
      + `<td>${esc(r.variant)}</td>`
      + `<td class="dim3">${esc(r.family)}</td>`
      + `<td>${r.n}</td>`
      + `<td class="${cls(r.net)}">${money(r.net, 0)}</td>`
      + `<td class="${r.today_n ? cls(r.today) : "mut"}">${r.today_n ? money(r.today, 0) : "·"}</td>`
      + `<td>${r.win == null ? "—" : r.win + "%"}</td></tr>`
    ).join("") : '<tr><td class="empty" colspan="7">shadow warming up…</td></tr>';
  }
  // Position chart for the HOLD tab — modelled on the old futures_terminal drawHoldingChart:
  // price line coloured by P&L + an IN (entry) ref line always, STOP, and a gold LOCK line ONLY
  // when profit is actually locked (est_locked_profit>0 at avg×(1∓lp%)) — else it'd pin to the floor.
  function drawHoldChart(hold) {
    const svg = $("hold-svg"); if (!svg) return;
    const host = svg.parentElement;
    if (host.clientHeight === 0 || host.clientWidth === 0) return;   // HOLD tab hidden — draw on show instead
    const bars = (STATE.bars && STATE.bars.bars || []).filter((b) => typeof b.close === "number" && b.ts);
    const W = Math.max(240, Math.round(host.clientWidth));
    const H = Math.max(110, Math.round(host.clientHeight));
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    if (bars.length < 2) { svg.innerHTML = `<text x="${(W / 2) | 0}" y="${(H / 2) | 0}" fill="#5c6b78" font-size="13" text-anchor="middle">no bars yet</text>`; return; }
    const ML = 8, MR = 66, MT = 8, MB = 8;  // right margin holds the IN/STOP/LOCK price labels
    const plotL = ML, plotR = W - MR, plotT = MT, plotB = H - MB;
    const T = (b) => Date.parse(b.ts) / 1000;
    const t0 = T(bars[0]), t1 = T(bars[bars.length - 1]), tspan = Math.max(1, t1 - t0);
    const isShort = (hold.side === "SHORT") || (hold.qty < 0);
    const lockP = (typeof hold.est_lp_pct === "number" && hold.est_lp_pct > 0 && hold.avg > 0)
      ? (isShort ? hold.avg * (1 - hold.est_lp_pct / 100) : hold.avg * (1 + hold.est_lp_pct / 100)) : null;
    const refs = [];
    if (hold.avg) refs.push({ v: hold.avg, c: "#3fd97f", label: "IN " + nf(hold.avg, 1) });
    if (hold.stop) refs.push({ v: hold.stop, c: "#ff5d5d", label: "STOP " + nf(hold.stop, 1) });
    if (hold.est_locked_profit > 0 && lockP) refs.push({ v: lockP, c: "#f5d23d", label: "LOCK " + nf(lockP, 1) });
    let lo = Infinity, hi = -Infinity;
    bars.forEach((b) => { lo = Math.min(lo, b.close); hi = Math.max(hi, b.close); });
    refs.forEach((r) => { lo = Math.min(lo, r.v); hi = Math.max(hi, r.v); });
    let rng = hi - lo; if (rng < 1e-6) { lo -= 1; hi += 1; rng = hi - lo; }
    const X = (t) => plotL + (plotR - plotL) * Math.max(0, Math.min(1, (t - t0) / tspan));
    const Y = (p) => plotT + (plotB - plotT) * (1 - (p - lo) / rng);
    const stroke = (hold.pnl_usd > 1e-9) ? "#3fd97f" : "#ff5d5d";
    let g = "";
    refs.forEach((r) => {
      const y = Y(r.v);
      g += `<line x1="${plotL}" y1="${y.toFixed(1)}" x2="${plotR}" y2="${y.toFixed(1)}" stroke="${r.c}" stroke-width="1" stroke-dasharray="4 3" opacity="0.85"/>`;
      g += `<text x="${(plotR + 4).toFixed(1)}" y="${(y + 3.5).toFixed(1)}" fill="${r.c}" font-size="10.5" font-weight="600" font-family="ui-monospace,SFMono-Regular,monospace" text-anchor="start">${r.label}</text>`;
    });
    const pts = bars.map((b) => X(T(b)).toFixed(1) + "," + Y(b.close).toFixed(1)).join(" ");
    g += `<polyline points="${pts}" fill="none" stroke="${stroke}" stroke-width="1.5"/>`;
    svg.innerHTML = g;
  }
  function riskBar(h) {
    if (!h.stop || !h.avg || !h.last) return "";
    const vals = [h.stop, h.avg, h.last].filter((v) => v != null);
    let lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    const pad = Math.max(1e-6, (hi - lo) * 0.15); lo -= pad; hi += pad;
    const X = (p) => ((p - lo) / (hi - lo) * 100);
    const eX = X(h.avg), sX = X(h.stop), lX = X(h.last);
    const lossLeft = Math.min(eX, sX), lossW = Math.abs(eX - sX);
    return `<div class="riskbar">
      <div class="seg loss" style="left:${lossLeft}%;width:${lossW}%"></div>
      <div class="mk stop" style="left:${sX}%"></div><div class="cap" style="left:${sX}%">stop ${nf(h.stop, 0)}</div>
      <div class="mk entry" style="left:${eX}%"></div>
      <div class="mk last" style="left:${lX}%"></div><div class="cap" style="left:${lX}%;top:-14px">last ${nf(h.last, 0)}</div>
    </div>`;
  }

  /* ---------- today trades ---------- */
  function renderTrades(m) {
    const blot = m.blotter || [];
    $("trades-meta").textContent = blot.length + " today · newest first";
    const h = m.header || {};
    $("curve-end").textContent = "ends " + money(h.today, 2);
    drawCurve(m.curve || []);
    // phone → ultra-short: side L/S, 3-letter gate, 2-3 letter exit, whole-$ and 1-dp % so the columns fit
    const ph = window.matchMedia("(max-width:899px)").matches;
    const sideCell = (s) => ph
      ? `<span class="${s === "SHORT" ? "red" : "grn"}">${s === "SHORT" ? "S" : "L"}</span>`
      : sideMini(s);
    $("blotter").innerHTML = blot.length ? blot.map((t) =>
      `<tr><td>${parisHM(t.time)}</td><td>${sideCell(t.side)}</td><td class="txt2">${esc(gateAbbr(t.gate, ph))}</td><td class="dim3">${esc(exitAbbr(t.exit, ph))}</td><td class="${cls(t.pnl_usd)}">${money(t.pnl_usd, ph ? 0 : 2)}</td><td class="${cls(t.pnl_pct)}">${pct(t.pnl_pct, ph ? 1 : 2)}</td></tr>`
    ).join("") : `<tr><td class="empty" colspan="6">no MNQ trades today</td></tr>`;
  }
  function drawCurve(curve) {
    const svg = $("curve-svg");
    if (!curve.length) { svg.innerHTML = `<text x="500" y="60" fill="#5c6b78" font-size="14" text-anchor="middle">no realised trades today</text>`; return; }
    const W = 1000, H = 120, pad = 6;
    const ys = curve.map((c) => c.cum);
    let lo = Math.min(0, Math.min.apply(null, ys)), hi = Math.max(0, Math.max.apply(null, ys));
    const rng = Math.max(1e-6, hi - lo);
    const X = (i) => curve.length === 1 ? W / 2 : (i / (curve.length - 1) * W);
    const Y = (v) => pad + (H - 2 * pad) * (1 - (v - lo) / rng);
    let g = `<line x1="0" y1="${Y(0)}" x2="${W}" y2="${Y(0)}" stroke="#212b35" stroke-dasharray="3 3"/>`;
    const pts = curve.map((c, i) => X(i) + "," + Y(c.cum)).join(" ");
    const last = curve[curve.length - 1].cum;
    const col = last >= 0 ? "#37d07a" : "#ff5a5f";
    g += `<polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.6"/>`;
    g += `<polyline points="0,${Y(0)} ${pts} ${W},${Y(0)}" fill="${last >= 0 ? "rgba(55,208,122,.08)" : "rgba(255,90,95,.08)"}" stroke="none"/>`;
    svg.innerHTML = g;
  }

  /* ---------- gate leaderboard + drill ---------- */
  function renderGates(m) {
    const lb = m.leaderboard || {};
    $("lb-top").innerHTML = lbRows(lb.top);
    $("lb-bottom").innerHTML = lbRows(lb.bottom);
    // wire clicks
    document.querySelectorAll("#lb-top tr.clickable, #lb-bottom tr.clickable").forEach((tr) => {
      tr.onclick = () => openDrill(tr.getAttribute("data-key"));
    });
  }
  function lbRows(rows) {
    if (!rows || !rows.length) return `<tr><td class="empty" colspan="6">no attributed trades today</td></tr>`;
    return rows.map((r) =>
      `<tr class="clickable" data-key="${esc(r.gate)}|${r.side}"><td>${esc(gateAbbr(r.gate))}</td><td class="${r.side === "SHORT" ? "red" : "grn"}">${r.side}</td><td>${r.n}</td><td>${r.win_pct == null ? "—" : r.win_pct + "%"}</td><td>${r.pf == null ? "∞" : nf(r.pf, 2)}</td><td class="${cls(r.net)}">${money(r.net, 0)}</td></tr>`
    ).join("");
  }
  function openDrill(key) {
    STATE.drill = key;
    reAggregateDrill();
    $("drill-back").style.display = "block";
  }
  function reAggregateDrill() {
    const key = STATE.drill; if (!key) return;
    const rows = (STATE.mnq && STATE.mnq.drill && STATE.mnq.drill[key]) || [];
    const [gate, side] = key.split("|");
    $("drill-title").textContent = gateAbbr(gate) + " · " + side + " · today";
    const n = rows.length;
    const net = rows.reduce((s, r) => s + (r.pnl_usd || 0), 0);
    const wins = rows.filter((r) => r.pnl_usd > 0).length;
    const gw = rows.filter((r) => r.pnl_usd > 0).reduce((s, r) => s + r.pnl_usd, 0);
    const gl = -rows.filter((r) => r.pnl_usd < 0).reduce((s, r) => s + r.pnl_usd, 0);
    const pf = gl > 1e-9 ? gw / gl : null;
    const avg = n ? net / n : null;
    $("drill-agg").innerHTML =
      `<div class="row"><span class="k">Trades</span><span class="val">${n}</span></div>` +
      `<div class="row"><span class="k">Win rate</span><span class="val">${n ? Math.round(100 * wins / n) + "%" : "—"}</span></div>` +
      `<div class="row"><span class="k">Profit factor</span><span class="val">${pf == null ? "∞" : nf(pf, 2)}</span></div>` +
      `<div class="row"><span class="k">Avg / trade</span><span class="val ${cls(avg)}">${money(avg, 2)}</span></div>` +
      `<div class="row"><span class="k">Net (of fees)</span><span class="val ${cls(net)}">${money(net, 2)}</span></div>`;
    $("drill-rows").innerHTML = n ? rows.map((r) =>
      `<tr><td>${parisHM(r.time)}</td><td>${sideMini(r.side)}</td><td class="dim3">${esc(exitAbbr(r.exit))}</td><td>${nf(r.entry, 2)}</td><td>${nf(r.exit_price, 2)}</td><td class="${cls(r.pnl_usd)}">${money(r.pnl_usd, 2)}</td><td class="${cls(r.pnl_pct)}">${pct(r.pnl_pct, 2)}</td></tr>`
    ).join("") : `<tr><td class="empty" colspan="7">no trades</td></tr>`;
  }
  function closeDrill() { STATE.drill = null; $("drill-back").style.display = "none"; }

  /* ---------- tab badges (phone) ---------- */
  function renderTabBadges(m) {
    const h = m.header || {};
    const hold = mnqHoldings();
    $("tb-desk").textContent = h.today != null ? money(h.today, 0) : "—";
    $("tb-hold").textContent = hold.length ? money(hold.reduce((s, x) => s + (x.pnl_usd || 0), 0), 0) : "flat";
    $("tb-trades").textContent = (h.trades_today != null ? h.trades_today : "—");
    const d = (STATE.tour && STATE.tour.desk) || null;
    $("tb-tourn").textContent = d ? (d.live_count + "/" + d.roster_count) : "—";
  }

  /* ---------- tabs + clock ---------- */
  function initTabs() {
    document.querySelectorAll(".tab").forEach((t) => {
      t.onclick = () => {
        document.querySelectorAll(".tab").forEach((x) => x.classList.remove("on"));
        t.classList.add("on");
        const name = t.getAttribute("data-tab");
        document.querySelectorAll(".panel[data-tab]").forEach((p) => p.classList.toggle("on", p.getAttribute("data-tab") === name));
        // the just-shown panel now has real dimensions — redraw its chart at the true size (charts skip
        // while hidden, so this is what draws them crisply on show; requestAnimationFrame lets layout settle)
        requestAnimationFrame(() => { try { renderHero(); renderHolding(); renderTournament(); renderPromotion(); } catch (e) { } });
      };
    });
  }
  function clock() {
    try { $("clock").textContent = new Date().toLocaleTimeString("en-GB", { timeZone: "Europe/Paris", hour: "2-digit", minute: "2-digit", second: "2-digit" }); } catch (e) { }
  }

  // expose the few handlers the inline HTML calls
  window.MNQ = { closeDrill };
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrill(); });

  initTabs();
  // phone defaults to a 1h chart window — 2h is too dense on a narrow screen; desktop stays 2h
  if (window.matchMedia("(max-width:899px)").matches) {
    STATE.tf = 60;
    document.querySelectorAll("#tfbar .tf").forEach((x) => x.classList.toggle("on", x.dataset.min === "60"));
  }
  // timeframe selector — switch the chart window + refetch immediately
  document.querySelectorAll("#tfbar .tf").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("#tfbar .tf").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    STATE.tf = parseInt(b.dataset.min, 10) || 120;
    fastTick();
  }));

  clock(); setInterval(clock, 1000);
  slowTick(); fastTick();
  setInterval(fastTick, POLL_FAST_MS);
  setInterval(slowTick, POLL_SLOW_MS);
  // the chart draws in pixel space → re-fit it to the new box on resize (debounced), not just next tick
  let _rz; window.addEventListener("resize", () => { clearTimeout(_rz); _rz = setTimeout(() => { try { renderHero(); } catch (e) { } }, 120); });
})();
