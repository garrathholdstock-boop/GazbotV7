/* GAZBOT V7 — MNQ DESK (read-only presentation)
 * Reuses: /api/futures/mnq (MNQ-scoped header/rolling/gates/blotter/curve),
 *         /api/futures/us-terminal (holdings/activity-DTT/regime/margin — filter to MNQ),
 *         /api/futures/bars/<MNQ|MGC> (hero price — MGC is watch-only, no overlays).
 * No writes, no order entry. Numbers are net-of-fees (canonical desk P&L); sim numbers
 * are NOT rendered here (this is the live MNQ desk), so the honest-real_pnl rule is met
 * by omission. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  /* ★2026-09-24 FIXED SIZE, by his instruction — the stepper went with the old DESK panel. */
  const BUY_LOTS = 4;
  const RIDER_USD = [100, 200, 400, 600];
  /* ★★2026-09-24 SAFE SETTERS. Merging DESK/CHART/HOLD into TRADE removed eight elements that
     renderers still wrote to, and $() returns null for a missing id — ONE of those throws inside
     the render loop and the WHOLE dashboard goes blank with no error the operator can see. That
     exact failure nearly shipped in the 09-18 rebuild too. Write through these, not directly. */
  /* ★★★2026-09-24 REPORT OUR OWN FAILURES. A dashboard that breaks in the browser is invisible
     from the server: every endpoint 200s, every test passes, and the operator sees a blank panel.
     `catch (e) { }` in the render loop was the worst of it — an exception mid-pass leaves
     everything after it unrendered and says NOTHING. Now it says something. */
  let _errN = 0;
  const report = (where, e) => {
    try { console.error(where, e); } catch (_) { }
    if (_errN++ > 20) return;                 // never let a broken tick flood the wire
    try {
      fetch("api/control/clienterr", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ where: where, msg: String((e && e.message) || e),
                               stack: String((e && e.stack) || "").slice(0, 800),
                               ua: navigator.userAgent }),
      }).catch(() => { });
    } catch (_) { }
  };
  window.addEventListener("error", (ev) => report("window.onerror", ev.error || ev.message));
  window.addEventListener("unhandledrejection", (ev) => report("unhandledrejection", ev.reason));
  /* ⚠ Wrap a renderer so ONE failure cannot take the rest of the pass with it — and so the failure
     is named. Silent partial renders are exactly how the last three blank panels happened. */
  const guard = (name, fn) => { try { fn(); } catch (e) { report(name, e); } };

  const setTxt = (id, v) => { const e = $(id); if (e) e.textContent = v; };
  const setHtml = (id, v) => { const e = $(id); if (e) e.innerHTML = v; };
  // ★★★2026-08-21 ONE ACCESSOR FOR "TODAY", because three call sites disagreed with the headline.
  // `header.today` is the TOURNAMENT ONLY; `today_total` is both desks. The headline was fixed on
  // 08-13 and pos-realised / curve-end / tb-desk were left reading the tournament number — so on
  // 08-21 the blotter listed two rider losses while "Realised today" showed $0.00, and the
  // REALISED CURVE (whose query has no desk filter at all, so the line already includes the rider)
  // carried a label that excluded it. A right number beside a wrong one is worse than either alone:
  // nothing tells the operator which to believe. Falls back to h.today for an older API build.
  const deskToday = (h) => (h && h.today_total != null ? h.today_total : (h ? h.today : null));
  const POLL_FAST_MS = 1000;   // chart / price / ribbon / DTT — as live as the feed allows
  const POLL_SLOW_MS = 5000;   // header P&L / blotter / leaderboard / gate perf
  // ★2026-09-02 `sym` — which contract the hero chart draws. MNQ is the desk; MGC is WATCH-ONLY
  // (no gold desk trades from this page), which is why every MNQ-derived overlay is suppressed
  // when it is selected. See renderHero().
  let STATE = { mnq: null, us: null, tour: null, promo: null, bars: null, drill: null, tf: 120, sym: "MNQ" };  // tf = chart window in minutes (2h default)

  /* ---------- formatting ---------- */
  const nf = (v, d = 2) => (v == null || isNaN(v)) ? "—" : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const usd = (v, d = 0) => (v == null || isNaN(v)) ? "—" : "$" + nf(Math.abs(v), d);
  // ★2026-08-29 DAY = since 00:00 Europe/Paris = the CME reopen. Resolved AT CALL TIME, not once:
  // minutes-since-the-reopen grows every minute, so a value captured on click would be stale by the
  // next poll and the chart would silently stop extending. Computed from the browser's own Paris
  // midnight so it follows CEST/CET without a second timezone rule to drift.
  function tfMinutes(mode) {
    if (mode !== "session") return parseInt(mode, 10) || 120;
    const now = new Date();
    const paris = new Date(now.toLocaleString("en-US", { timeZone: "Europe/Paris" }));
    const mid = new Date(paris); mid.setHours(0, 0, 0, 0);
    let mins = Math.floor((paris - mid) / 60000);
    if (mins < 5) mins += 24 * 60;                 // just after midnight — show the session just ended
    return Math.max(30, Math.min(1500, mins));     // 1500 = the server's cap
  }

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
      /* ★2026-09-18 the tournament fetch is gone with its panel — it no longer trades, and its
         payload was two non-empty values. `api/futures/context` replaces it with the things he
         actually reads before pressing. */
      const ctx = await getJSON("api/futures/context").catch(() => null);
      if (ctx) STATE.ctx = ctx;
      if (STATE.tfMode === "session") STATE.tf = tfMinutes("session");   // DAY keeps extending
      try { STATE.bars = await getJSON("api/futures/bars/" + STATE.sym + "?timeframe=1m&count=" + STATE.tf); } catch (e) { /* keep last */ }
      guard("fast.renderConn", () => renderConn(us != null));
      guard("fast.renderSafety", renderSafety);
      guard("fast.renderHero", renderHero);
      guard("fast.renderHolding", renderHolding);
      guard("fast.renderContext", renderContext);
    } finally { _fastBusy = false; }
  }
  async function slowTick() {
    if (_slowBusy) return; _slowBusy = true;
    try {
      const mnq = await getJSON("api/futures/mnq").catch(() => null);
      if (mnq) STATE.mnq = mnq;
      /* execution + promotion fetches retired with their panels (2026-09-18). */
      /* ★2026-09-24 20 TRADING sessions = a rolling 4 weeks. `n` is sessions, not calendar
         days — a fortnight of calendar is only ~11 sessions, which is what he was seeing. */
      const days = await getJSON("api/futures/days?n=20").catch(() => null);
      if (days) STATE.days = days;
      const m = STATE.mnq || {};
      guard("slow.renderHeader", () => renderHeader(m));
      guard("slow.renderTrade", () => renderTrade(m));
      guard("slow.renderTrades", () => renderTrades(m));
      guard("slow.renderTabBadges", () => renderTabBadges(m));
      guard("slow.renderDays", renderDays);
      if (STATE.drill) guard("slow.reAggregateDrill", reAggregateDrill);
    } finally { _slowBusy = false; }
  }

  /* ---------- MNQ slices out of us-terminal ---------- */
  const mnqHoldings = () => ((STATE.us && STATE.us.holdings) || []).filter((h) => (h.label === "MNQ" || h.symbol === "MNQ"));
  const mnqActivity = () => (((STATE.us && STATE.us.activity) || []).filter((a) => a.symbol === "MNQ" || a.label === "MNQ")[0]) || null;

  /* ========================================================================= */
  /* ⚠2026-09-24 renderAll() WAS DELETED HERE. It was dead code — nothing had called it since the
     two-tier fastTick/slowTick split — and it was a live trap: it invoked all eleven renderers
     WITHOUT the guard() wrapper, so wiring it back up would have restored the exact failure the
     guards exist to prevent (one throw mid-pass leaves everything after it unrendered, silently).
     The two tick functions above are the only render entry points; add to those, guarded. */

  /* ---------- EXECUTION HEALTH (signal → fill through-rate + slippage + blocks) ---------- */
  function renderConn(ok) {
    const conn = $("conn"), lbl = $("conn-label");
    const act = mnqActivity();
    const open = act ? !!act.session_active : null;
    conn.className = "conn" + (ok ? "" : " off");
    lbl.textContent = ok ? "CONNECTED" : "DISCONNECTED";
    const mk = $("mkt-chip");
    // ★ DUAL-SPAN so the phone can show the short form without the JS knowing the breakpoint. CSS
    // picks one; both are static strings, no interpolation. "MARKET OPEN" is ~95px of nowrap chip
    // that a 320px row cannot spare, and the word MARKET carries no information here.
    const dual = (long, short) => `<span class="lg">${long}</span><span class="sm">${short}</span>`;
    if (!ok) { mk.innerHTML = dual("—", "—"); mk.className = "chip"; }
    else if (open === false) { mk.innerHTML = dual("MARKET CLOSED", "CLOSED"); mk.className = "chip chop"; }
    else { mk.innerHTML = dual("MARKET OPEN", "OPEN"); mk.className = "chip bull"; }
    // the safety pill (was the dead regime chip) is owned by renderSafety()
  }

  function renderHeader(m) {
    const h = m.header || {};
    $("expiry").textContent = m.expiry || "—";
    // ★2026-09-02 the hero header follows the CHART's symbol, not the desk's — this runs on the
    // slow tick and would otherwise stamp the MNQ expiry back over a gold chart every 5s.
    setTxt("hero-expiry", (STATE.sym === "MNQ") ? (m.expiry || "—") : "gold · watch-only");
    $("k-fee").textContent = m.fee_per_rt != null ? "−$" + nf(m.fee_per_rt, 2) + "/RT" : "NET";
    const set = (id, v, d = 0) => { const el = $(id); el.textContent = money(v, d); el.className = "v " + cls(v); };
    // ★2026-08-13 TODAY is the WHOLE desk now, with the two books underneath. The day-rider is a
    // separate service on its own clientId holding for hours, and its P&L appeared in no total at
    // all — the operator watched it hold and then saw nothing. Week that prompted it: tournament
    // −$438 while the rider made +$1,183.50. Falls back to h.today (tournament-only) so an older
    // API build still renders rather than showing "—".
    const total = deskToday(h);
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
  const sideMini = (s) => `<span class="${s === "SHORT" ? "red" : "grn"}">${s}</span>`;

  /* ---------- hero price chart ---------- */
  // ★2026-09-02 One place that states, in words, what the chart is showing and what it is NOT.
  // The strip above the chart (RVOL/SESSION/VWAP/ADVERSE), the armed-gate ribbon and the
  // distance-to-trigger row below are all the MNQ desk's and do not change with this toggle —
  // an unlabelled MNQ meter sitting over a gold chart is precisely the confusion to avoid.
  function setSymNote(want, served, got) {
    const el = $("symnote");
    setTxt("hero-sym", served === null ? want : got);
    if (!el) return;
    if (served === null) { el.innerHTML = `<span class="dim3">loading ${want}…</span>`; return; }
    if (served === "?") {
      // The bars payload carries no symbol, so this API build predates the toggle and serves MNQ
      // only. Naming the fix beats a silent fallback: the chart is NOT what the button says.
      el.innerHTML = `<span class="red">this API build serves MNQ only — restart gazbot7-web to chart ${want}</span>`;
      return;
    }
    if (served !== want) {
      el.innerHTML = `<span class="red">showing ${served}, not ${want} — the ${want} fetch failed, this is the last good payload</span>`;
      return;
    }
    el.innerHTML = (got === "MNQ")
      ? ""
      : `gold · WATCH-ONLY — meters, gates and fills on this page are the <b>MNQ</b> desk's`;
  }

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
    // ★2026-09-02 WHICH CONTRACT IS THIS? THE PAYLOAD ANSWERS, NOT THE TOGGLE. The fetch keeps the
    // last good bars on error (by design — a blank chart is worse than a stale one), so a failed
    // MGC request leaves MNQ bars in STATE while the button reads MGC. Labelling those "MGC" is
    // the exact multi-symbol confusion this desk has already paid for, so the server echoes the
    // symbol it actually queried and everything below keys off THAT. A mismatch is shown as a
    // warning instead of a mislabelled chart.
    const want = STATE.sym;
    //   null = nothing fetched yet (a real "loading", because the toggle clears STATE.bars)
    //   "?"  = an API build that predates the symbol echo, which serves MNQ and nothing else
    const served = STATE.bars ? (STATE.bars.symbol || "?") : null;
    const got = (served && served !== "?") ? served : "MNQ";
    const isMNQ = (got === "MNQ");
    setSymNote(want, served, got);
    const W = Math.max(320, Math.round(host.clientWidth));
    const H = Math.max(160, Math.round(host.clientHeight));
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    if (bars.length < 2) { svg.innerHTML = `<text x="${(W / 2).toFixed(0)}" y="${(H / 2).toFixed(0)}" fill="#5c6b78" font-size="15" text-anchor="middle">no bars yet</text>`; return; }
    /* ★2026-09-24 THE PRICE AXIS RAN OFF THE LEFT EDGE ON THE PHONE. An MNQ price at one decimal
       ("30377.0") is 7 monospace characters; at 12px that is ~50px, anchored END at plotL-6 = 50,
       so it began at x ≈ -0.4 — half a character outside the SVG. Whole points (5 chars) at 9.5px
       is ~29px, which sits comfortably inside a 40px margin AND hands 16px back to the chart.
       ⚠ Losing the decimal costs nothing: these are GRIDLINE labels, not quotes — the live price
       is on the holding card above, to the tick. */
    const ML = 40, MT = 10, MB = 18;              // margins: left = price axis, bottom = time axis
    // bar.ts is an ISO string ("2026-07-13T16:40:00+00:00") — parse to epoch SECONDS so the time axis
    // is numeric AND aligns with the fills (which use Date.parse(...)/1000). Without this every X was NaN.
    const T = (b) => Date.parse(b.ts) / 1000;
    const t0 = T(bars[0]), t1 = T(bars[bars.length - 1]), tspan = Math.max(1, t1 - t0);
    // ⚠ EVERY ONE OF THESE IS THE MNQ DESK'S. On gold they are not "roughly right", they are
    //   another instrument's numbers — vwap 29,188 against a 4,400 tape, this desk's fills, this
    //   desk's ATR. Suppressed at the SOURCE rather than filtered at each draw site, so a future
    //   overlay added below inherits the guard instead of having to remember it.
    const a = isMNQ ? mnqActivity() : null;
    const holds = isMNQ ? mnqHoldings() : [];
    const hold = holds[0] || null;
    const fills = isMNQ ? ((STATE.mnq && STATE.mnq.blotter) || []) : [];
    // ATR context for the RIGHT axis: 1 ATR in points = atr_pct (already a % of price) / 100 * price.
    // Each gridline is then labelled by its distance from the CURRENT price in ATRs, so the vertical
    // scale reads as volatility context, not just raw price.
    const refP = (a && a.last) || bars[bars.length - 1].close;
    const atrPts = (a && typeof a.atr_pct === "number" && a.atr_pct > 0) ? (a.atr_pct / 100) * refP : null;
    const MR = atrPts ? 34 : 10;                  // widen the right margin to hold the ATR-distance axis
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
      g += `<text x="${plotL - 5}" y="${(y + 3.5).toFixed(1)}" fill="#8a99a6" font-size="9.5" font-family="ui-monospace,SFMono-Regular,monospace" text-anchor="end">${nf(p, 0)}</text>`;
      if (atrPts) {
        const dd = (p - refP) / atrPts;
        const lbl = (dd >= 0 ? "+" : "−") + nf(Math.abs(dd), 1);
        g += `<text x="${(plotR + 4).toFixed(1)}" y="${(y + 3.5).toFixed(1)}" fill="#6b8f8f" font-size="9" font-family="ui-monospace,SFMono-Regular,monospace" text-anchor="start">${lbl}</text>`;
      }
    }
    // label the right axis so the +/- numbers read as ATRs (bottom-right, on the time-axis line)
    if (atrPts) g += `<text x="${(plotR + 4).toFixed(1)}" y="${(H - 5).toFixed(1)}" fill="#6b8f8f" font-size="8" letter-spacing="0.4" font-family="ui-monospace,SFMono-Regular,monospace" text-anchor="start">ATR</text>`;
    // X axis — 4 time ticks across the window (first left-anchored, last right-anchored so neither clips)
    for (let i = 0; i <= 3; i++) {
      const t = t0 + tspan * i / 3, x = X(t);
      const anc = i === 0 ? "start" : (i === 3 ? "end" : "middle");
      g += `<line x1="${x.toFixed(1)}" y1="${plotT}" x2="${x.toFixed(1)}" y2="${plotB}" stroke="#212b35" stroke-width="1" opacity="0.3"/>`;
      g += `<text x="${x.toFixed(1)}" y="${H - 6}" fill="#8a99a6" font-size="9.5" font-family="ui-monospace,SFMono-Regular,monospace" text-anchor="${anc}">${hm(t)}</text>`;
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
  }
  const line = (x1, y1, x2, y2, c, dash) => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${c}" stroke-width="1" stroke-dasharray="${dash}" opacity="0.7"/>`;
  function tri(x, y, col, up) {
    const s = 5;
    return up
      ? `<polygon points="${x},${y - s} ${x - s},${y + s} ${x + s},${y + s}" fill="${col}"/>`
      : `<polygon points="${x},${y + s} ${x - s},${y - s} ${x + s},${y - s}" fill="${col}"/>`;
  }

  /* ---------- desk stats ---------- */
  /* ★★★2026-09-24 renderDesk -> renderTrade. The old one wrote to TWENTY-THREE ids and eighteen
     of them no longer exist (direction meters, DESK·TODAY, ROLLING, LOSSES·BY·EXIT, the rider
     ladder, the stay-out box, the buy stepper...). $() returns null for a missing element, so
     leaving any of them would throw on every tick and take the WHOLE dashboard down — a removed
     panel becoming a blank page with no error the operator can see. Every write below is guarded
     and every id is one that exists in the TRADE panel.
     ⚠ The button wiring lives here, as it did before, because it is re-bound on each render. */
  function renderTrade(m) {
    const hold = mnqHoldings();
    const open = hold.length ? hold[0] : null;

    const q = $("orb-qty"); if (q) q.textContent = String(BUY_LOTS);
    const op = $("orb-pos");
    if (op) op.textContent = open ? ((open.qty > 0 ? "LONG " : "SHORT ") + Math.abs(open.qty)) : "flat";
    const fb = $("flat-all"); if (fb) fb.disabled = !open;
    /* ★2026-09-24 DISABLE BUY/SELL WHILE HOLDING. The rider refuses a second entry ("already in a
       position — flatten before buying again"), which is correct — but arriving as an alert AFTER
       he has pressed and typed a PIN makes a correct refusal feel like a broken button. Show the
       state instead of reporting it. */
    [["buy-long", "BUY"], ["buy-short", "SELL"]].forEach(([id, lab]) => {
      const b = $(id); if (!b) return;
      b.disabled = !!open;
      b.title = open ? "Already in a position — flatten first" : "";
      const em = b.querySelector("em");
      if (em) em.textContent = open ? "holding" : String(BUY_LOTS);
    });

    if (!STATE._wired) {
      STATE._wired = true;

      /* ── BUY / SELL. FIXED 4 LOTS by his instruction, PIN kept: these place an order.
         ⚠ The ladder is the rider's standing one ($100/$200/$400/$600 per lot) — the stepper and
         the per-lot target boxes went with the old panel, so the defaults travel here. */
      const send = (side) => {
        const tg = RIDER_USD.slice(0, BUY_LOTS);
        if (!window.confirm(
          side + " " + BUY_LOTS + " lots of MNQ at market?\n\n"
          + tg.map((v, i) => "  L" + (i + 1) + "  $" + v).join("\n")
          + "\n\nTHERE IS NO STOP. The only exits are your buttons, STEP AWAY, and the 20:40Z hard flat.")) return;
        const pin = window.prompt("PIN");
        if (!pin) return;
        fetch("api/control/dayrider-buy", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pin: pin, side: side, qty: BUY_LOTS, targets: tg }),
        }).then((r) => { if (!r.ok) throw new Error("server said " + r.status); return r.json(); })
          .then((j) => window.alert(j && j.ok ? j.msg : "Not sent: " + ((j && j.error) || "unknown")))
          .catch((e) => window.alert("Not sent: " + e.message));
      };
      const bl = $("buy-long"), bs = $("buy-short");
      if (bl) bl.onclick = () => send("BUY");
      if (bs) bs.onclick = () => send("SELL");

      /* ── FLATTEN. NO PIN, by his instruction: it only ever reduces risk, and friction on a kill
         switch costs money. The confirm stays because a circular target is easy to hit by
         accident — he can click straight through it. */
      const fl = $("flat-all");
      if (fl) {
        fl.onclick = () => {
          const h2 = mnqHoldings();
          if (!h2.length) { window.alert("Nothing to flatten — you are flat."); return; }
          if (!window.confirm("FLATTEN " + Math.abs(h2[0].qty) + " lot(s) at market?")) return;
          fl.disabled = true;
          fetch("api/control/dayrider-claim", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ lot: "all", flatten: true }),
          }).then((r) => { if (!r.ok) throw new Error("server said " + r.status); return r.json(); })
            .then((j) => { if (!j || !j.ok) window.alert("Not sent: " + ((j && j.error) || "?")); })
            .catch((e) => window.alert("Not sent: " + e.message))
            .finally(() => { fl.disabled = false; });
        };
      }

      /* ── STEP AWAY. Arming needs no PIN (it REDUCES risk); disarming does. */
      const sb = $("sa-btn");
      if (sb) {
        sb.onclick = () => {
          const armed = !!(STATE.ctx && STATE.ctx.step_away && STATE.ctx.step_away.armed);
          const body = { armed: !armed };
          if (armed) {
            const pin = window.prompt("PIN to DISARM the step-away guard");
            if (!pin) return;
            body.pin = pin;
          } else {
            const el = $("sa-loss"), tpEl = $("sa-tp");
            body.limit_usd = (el && Number(el.value)) || 200;
            /* ⚠ 0 or blank means NO take-profit, not a take-profit of zero — which would fire the
               instant the position was green by a cent. */
            const tp = tpEl && Number(tpEl.value);
            if (tp && tp > 0) body.take_profit_usd = tp;
            if (!window.confirm("Arm STEP AWAY?\n\n"
              + "• flatten at −$" + body.limit_usd + "\n"
              + (body.take_profit_usd ? "• flatten at +$" + body.take_profit_usd + "\n" : "• no take-profit\n")
              + "\nDisarms the moment it fires, and at the 22:00Z reopen.")) return;
          }
          sb.disabled = true;
          fetch("api/control/step-away", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }).then((r) => { if (!r.ok) throw new Error("server said " + r.status); return r.json(); })
            .then((j) => window.alert(j && j.ok ? j.msg : "Failed: " + ((j && j.error) || "?")))
            .catch((e) => window.alert("Failed: " + e.message))
            .finally(() => { sb.disabled = false; });
        };
      }

      /* ── PASS. No PIN and no confirm, deliberately: it places no order, and any friction that
         makes him skip recording a pass defeats the point — the sample IS the product. */
      const pb = $("pass-btn");
      if (pb) {
        pb.onclick = () => {
          const n = $("pass-note");
          pb.disabled = true;
          fetch("api/control/pass", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ note: (n && n.value) || "" }),
          }).then((r) => { if (!r.ok) throw new Error("server said " + r.status); return r.json(); })
            .then((j) => {
              pb.textContent = j && j.ok ? "noted" : "failed";
              if (n) n.value = "";
              setTimeout(() => { pb.textContent = "PASS"; pb.disabled = false; }, 2000);
            })
            .catch((e) => {
              pb.textContent = "failed";
              window.alert("Pass NOT recorded: " + e.message);
              setTimeout(() => { pb.textContent = "PASS"; pb.disabled = false; }, 2000);
            });
        };
      }
    }
  }

  /* ---------- holding — the multi-slot tournament (one card per open slot) ---------- */
  /* ★★★2026-09-24 THE HOLDING CARD, rebuilt for the TRADE tab. Operator: "i like the live p&L and
     the entry price and current price. and the tiered take profit buttons. but i only need the
     first 2. after that i usually flatten everything using flatten button above."
     So: live P&L as the biggest thing on the card, entry and last beneath it, and TWO tier buttons.
     Tiers 3 and 4 are gone — FLATTEN above covers them, which is what he actually does.
     ⚠ It still POSTs a request; the RIDER flattens on its own tick through its own ownership
     check. A dashboard that placed orders directly is how 2026-08-06 happened. */

  /* ════════════════════════════════════════════════════════════════════════════════════════════
     THE ON-PAGE ALERT — beats the Telegram push by ~9 seconds, while the tab is in front of him
     ════════════════════════════════════════════════════════════════════════════════════════════
     ★★★2026-09-24. Operator: "the telegram sometimes comes 10 seconds after the event. any way of
     speeding it up? or thats life?" MEASURED, end to end:
         tape -> detection   <= 1.00s   (MD_STREAM publishes MNQ at exactly 1 Hz)
         python spawn         0.039s
         Telegram API POST    0.043s
         ------------------------------
         desk-side total     <= 1.1s
     So the ~10s is entirely Telegram -> Apple push -> handset. There is no lever on that. But this
     page is ALREADY connected and ALREADY polling at 1 Hz, so for the one case that matters — the
     tab open in front of him — it can fire in about a second with no push service in the path.

     ⚠⚠⚠ AN ADDITION TO TELEGRAM, NEVER A REPLACEMENT. It lives only while the tab is open AND
     foregrounded (iOS suspends timers in a background tab), so it cannot be relied on and must
     never be allowed to feel like it can. Telegram stays the alarm channel of record.

     ⚠ THE LADDER IS DELIBERATELY THE SAME ONE `rider_peak_watch` USES — arm $200, a rung every
     $50, give-back $75 off the high. Two surfaces alerting on two different definitions of "worth
     looking at" would teach him that one of them is lying. `tests/test_dashboard_alert.py` asserts
     these three numbers against that script's defaults, so a change to either side fails the suite
     rather than silently drifting the page out of step with the phone.
  */
  var AL_ARM = 200, AL_STEP = 50, AL_GIVEBACK = 75;
  var AL = { on: false, unlocked: false, peak: 0, armed: false, rung: 0, holding: false, gave: false,
           /* ⚠ what the SERVER last told us each step-away box should be — so a stored value is
              delivered once and never re-imposed over an edit he has made. */
           saSeen: {} };

  function alSave() { try { localStorage.setItem("gz_alerts", AL.on ? "1" : "0"); } catch (e) { } }
  function alLabel() {
    // ⚠ The label must distinguish "off" from "on but the browser has not let us make a sound yet".
    // Reporting ON while silent is the instrument-that-reports-healthy failure in miniature.
    setTxt("al-lab", !AL.on ? "ALERTS off" : (AL.unlocked ? "ALERTS on" : "ALERTS tap"));
    var b = $("al-btn"); if (b) b.classList.toggle("on", AL.on && AL.unlocked);
  }

  /* iOS will not play audio that no gesture asked for. The toggle IS that gesture; if the
     preference was already on from a previous visit we unlock on his first touch anywhere. */
  function alUnlock() {
    if (AL.unlocked || !AL.on) return;
    var a = $("al-snd"); if (!a) return;
    var p = a.play();
    if (p && p.then) {
      p.then(function () { a.pause(); a.currentTime = 0; AL.unlocked = true; alLabel(); })
       .catch(function () { /* still locked — the label keeps saying "tap" and that is the truth */ });
    } else { AL.unlocked = true; alLabel(); }
  }

  function alBeep(times, rate) {
    var a = $("al-snd"); if (!a || !AL.on || !AL.unlocked) return;
    var n = 0;
    (function go() {
      if (n++ >= times) return;
      try { a.pause(); a.currentTime = 0; a.playbackRate = rate || 1; a.play(); } catch (e) { }
      if (n < times) setTimeout(go, 180);
    })();
  }

  function alFire(kind, text) {
    // ⚠ The flash and the title are NOT decoration — they are the half that still works when the
    // handset is muted, when audio never unlocked, or when the tab is behind something.
    var f = $("al-flash");
    if (f) {
      f.textContent = text;
      f.classList.remove("show"); void f.offsetWidth; f.classList.add("show");
      setTimeout(function () { f.classList.remove("show"); }, 6000);
    }
    document.title = text + " · GAZBOT V7";
    setTimeout(function () { document.title = "GAZBOT V7 · MNQ DESK"; }, 20000);
    // Android/desktop only — iOS Safari has no Vibration API at all, so this is a bonus, never the
    // mechanism. Guarded because calling an absent function would kill the rest of the render pass.
    try { if (navigator.vibrate) navigator.vibrate(kind === "giveback" ? [90, 60, 90] : 140); } catch (e) { }
    if (kind === "arm") alBeep(3, 1);
    else if (kind === "giveback") alBeep(2, 0.72);
    else alBeep(1, 1);
  }

  /* Called from renderHolding with the live total. Pure ladder logic — no fetch, no order path. */
  function alCheck(pnl, side, qty) {
    if (!AL.on) return;
    if (pnl > AL.peak) { AL.peak = pnl; AL.gave = false; }
    if (!AL.armed && pnl >= AL_ARM) {
      AL.armed = true; AL.rung = Math.floor(pnl / AL_STEP) * AL_STEP;
      alFire("arm", "+$" + Math.round(pnl) + " — START WATCHING");
      return;
    }
    if (!AL.armed) return;
    var next = AL.rung + AL_STEP;
    if (pnl >= next) {
      AL.rung = Math.floor(pnl / AL_STEP) * AL_STEP;
      alFire("rung", "PEAK +$" + AL.rung + " · " + side + " " + qty);
      return;
    }
    if (!AL.gave && AL.peak - pnl >= AL_GIVEBACK) {
      AL.gave = true;
      alFire("giveback", "OFF THE HIGH — peak $" + Math.round(AL.peak) + ", now $" + Math.round(pnl));
    }
  }

  function alFlat() {
    // ⚠ Reset on FLAT, never on a reload: a fresh page mid-position starts with peak 0 and would
    // re-arm at $200 on a position he was already told about. That is the cost of this living in
    // the page, and it is why Telegram remains the record.
    AL.peak = 0; AL.armed = false; AL.rung = 0; AL.gave = false;
  }

  function alInit() {
    try { AL.on = localStorage.getItem("gz_alerts") === "1"; } catch (e) { }
    alLabel();
    var b = $("al-btn");
    if (b) b.onclick = function () {
      AL.on = !AL.on; alSave();
      if (AL.on) { alUnlock(); alFire("rung", "ALERTS ON — you will hear the $" + AL_ARM + " arm"); }
      alLabel();
    };
    ["touchend", "click"].forEach(function (ev) {
      document.addEventListener(ev, alUnlock, { once: false, passive: true });
    });
  }

  function renderHolding() {
    const holds = mnqHoldings();
    const body = $("hold-body");
    if (!body) return;
    if (!holds.length) {
      setTxt("hold-meta", "flat");
      body.innerHTML = `<div class="empty">flat — no position</div>`;
      if (AL.holding) { AL.holding = false; alFlat(); }
      return;
    }
    const h = holds[0];
    const side = h.side || (h.qty < 0 ? "SHORT" : "LONG");
    const tot = holds.reduce((s2, x) => s2 + (x.pnl_usd || 0), 0);
    setTxt("hold-meta", `${holds.length} open`);
    // ⚠ guard()ed: a throw in the alert must never take the holding card down with it. The card is
    // what he actually trades from; the beep is a convenience on top of it.
    if (!AL.holding) { AL.holding = true; alFlat(); }
    guard("alert.check", function () { alCheck(tot, side, Math.abs(h.qty || 0)); });
    const doneSet = h.targets_done || [];
    /* ⚠ only the first TWO rungs, by his instruction */
    const tiers = h.entry_gate === "day_rider"
      ? RIDER_USD.slice(0, 2).map((u, i) =>
          `<button data-claim="${i + 1}"${doneSet.indexOf(i) >= 0 ? " disabled" : ""}`
          + ` title="Claim lot ${i + 1} — fires in profit OR loss">+$${u}</button>`).join("")
      : "";
    body.innerHTML =
      `<div class="hc-top">`
      + `<span class="hc-side ${side.toLowerCase()}">${side} ${Math.abs(h.qty || 0)}</span>`
      + `<span class="hc-pnl ${cls(tot)}">${money(tot, 0)}</span></div>`
      + `<div class="hc-px">`
      + `<span><i>entry</i>${nf(h.avg, 2)}</span>`
      + `<span><i>last</i>${nf(h.last, 2)}</span>`
      + `<span><i>held</i>${holdStr(h.held_seconds)}</span>`
      + (h.protected ? "" : `<span><i>stop</i><span class="neg">NAKED</span></span>`)
      + `</div>`
      + (tiers ? `<div class="hc-tp">${tiers}</div>` : "");
    Array.prototype.forEach.call(body.querySelectorAll("[data-claim]"), (b) => {
      b.onclick = () => {
        const lot = b.getAttribute("data-claim");
        if (!window.confirm(`Claim lot ${lot}? It fires in profit OR loss.`)) return;
        const pin = window.prompt("PIN");
        if (!pin) return;
        b.disabled = true;
        fetch("api/control/dayrider-claim", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pin: pin, lot: Number(lot) }),
        }).then((r) => { if (!r.ok) throw new Error("server said " + r.status); return r.json(); })
          .then((j) => { if (!j || !j.ok) { window.alert("Not sent: " + ((j && j.error) || "?")); b.disabled = false; } })
          .catch((e) => { window.alert("Not sent: " + e.message); b.disabled = false; });
      };
    });
  }

  /* Shared by the holdings card and the DESK ladder — one implementation, so the two
     surfaces can never drift into asking the rider for different things. */
  function wireClaims(root, holds) {
    Array.prototype.forEach.call(root.querySelectorAll("[data-claim]"), (b) => {
      b.onclick = () => {
        const dr = holds.filter((x) => x.entry_gate === "day_rider")[0];
        const pnl = dr ? nf(dr.pnl_usd, 2) : "?";
        const which = b.getAttribute("data-claim");
        const isAll = which === "all";
        if (!window.confirm(
          (isAll ? "Flatten EVERY remaining day-rider lot?" : "Claim/kill lot " + which + "?")
          + "\n\nPosition is showing " + pnl + " right now.\n\n"
          + "It exits on the rider's next tick (~0.1s via the claim path; 60s is the fallback), "
          + "so the fill will not be exactly this number.\n\n"
          + "There is NO STOP on the rider — this fires whether the lot is green or red.\n\n"
          + (isAll ? "This ENDS its session: it will not re-enter today."
                   : "The other lots stay open and keep their targets."))) return;
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
          body: JSON.stringify(isAll ? { pin: pin } : { pin: pin, lot: Number(which) }),
        }).then((r) => {
          /* Check the STATUS before parsing. A 404 returns an HTML error page,
             r.json() throws on it, and the catch below then blamed the network —
             which is how a wrong URL spent a press looking like a dead line. */
          if (!r.ok) throw new Error("server said " + r.status);
          return r.json();
        }).then((j) => {
          b.textContent = j && j.ok ? "Claimed" : (isAll ? "ALL" : "L" + which);
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

  /* ---------- the SAFETY chip ---------- */
  /* ★★★2026-09-18 NOW FED BY api/futures/context. Retiring the tournament PANEL also retired its
     fetch, and this read STATE.tour — the chip would have shown "SAFETY —" forever while HALTED and
     NAKED went unreported. It is guarded, so nothing throws and nothing complains. The desk block
     moved onto context precisely so this could not happen. */
  function renderSafety() {
    const d = (STATE.ctx && STATE.ctx.desk) || null;
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
    const _nUn = blot.filter((t) => t.uncounted).length;
    $("trades-meta").textContent = blot.length + " today · newest first"
      + (_nUn ? " · " + _nUn + " not counted" : "");
    const h = m.header || {};
    $("curve-end").textContent = "ends " + money(deskToday(h), 2);
    drawCurve(m.curve || []);
    // phone → ultra-short: side L/S, 3-letter gate, 2-3 letter exit, whole-$ and 1-dp % so the columns fit
    const ph = window.matchMedia("(max-width:899px)").matches;
    const sideCell = (s) => ph
      ? `<span class="${s === "SHORT" ? "red" : "grn"}">${s === "SHORT" ? "S" : "L"}</span>`
      : sideMini(s);
    // ★2026-08-21 A `BADFILL:` row is SHOWN but NOT COUNTED — the fill price came from a broken
    // execution (08-21: a lot filled 30pt outside the visible book at a price two hours stale), so
    // it must never reach the P&L, the curve or a gate ranking. It is struck through and marked so
    // the row cannot be read as money, and so the blotter count never silently disagrees with the
    // header again.
    $("blotter").innerHTML = blot.length ? blot.map((t) =>
      `<tr${t.uncounted ? ' class="uncounted" title="' + esc(t.flag || "") + ' — shown for the record, excluded from P&L"' : ""}><td>${parisHM(t.time)}</td><td>${sideCell(t.side)}</td><td class="txt2">${esc(gateAbbr(t.gate, ph))}</td><td class="dim3">${esc(exitAbbr(t.exit, ph))}${t.uncounted ? ' <span class="badfill">BAD FILL</span>' : ""}</td><td class="${t.uncounted ? "mut" : cls(t.pnl_usd)}">${money(t.pnl_usd, ph ? 0 : 2)}</td><td class="${t.uncounted ? "mut" : cls(t.pnl_pct)}">${pct(t.pnl_pct, ph ? 1 : 2)}</td></tr>`
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

  /* ---------- the metric strip: what he reads before pressing ---------- */
  /* ★★2026-09-24 FOUR METRICS, not ten. Operator kept ATR, EFFICIENCY and RVOL; POSITION AGE was
     added because it is the ONLY one here with a measured price attached — holds over 3 hours are
     -$7,023 across 22 entries, his most expensive pattern. Leg/tunnel/session/VWAP/breadth/event
     were dropped on his instruction. Every write is guarded: the ids they used are gone. */
  function renderContext() {
    const c = STATE.ctx; if (!c) return;
    const n = (v, d2) => (v == null ? "—" : Number(v).toFixed(d2 === undefined ? 1 : d2));
    setTxt("ctx-atr", n(c.atr));
    setTxt("ctx-er", n(c.er30, 3));
    const rv = $("ctx-rvol");
    if (rv) {
      rv.textContent = c.rvol == null ? "—" : c.rvol.toFixed(2) + "x";
      /* ⚠ contract-blind across a roll — bars carry no contract column. Accurate today (no roll in
         the 10-day baseline); degrades for ~10 days after each quarterly roll. */
      rv.title = (c.rvol_caveat || "") + (c.rvol_n_days ? ` · baseline ${c.rvol_n_days}d` : "");
    }
    /* ★★★2026-09-24 PULSE AND FLOW — "is this surge backed and real?"
       ⚠⚠ BOTH ARE DESCRIPTIVE AND THE COLOUR MUST NOT IMPLY OTHERWISE. Green here means "volume is
       expanding" / "buyers are crossing the spread", NEVER "this will continue". Measured on the 5
       sessions of tick data we retain, backed surges extended a median +5.25pt over the next 5 min
       against +0.50pt unbacked — which ORDERS correctly and is NOT a result at n=170 clustered in
       5 days. The colour is a reading of NOW, and the tooltip says so.
       ⚠ `surge` is absent outside US hours and on a shut venue — a dash, never a confident 0.00. */
    const sg = c.surge || {}, pu = $("ctx-pulse"), fl = $("ctx-flow");
    if (pu) {
      pu.textContent = sg.pulse == null ? "—" : sg.pulse.toFixed(2) + "x";
      pu.className = sg.pulse == null ? "" : (sg.pulse >= 1.5 ? "pos" : (sg.pulse < 0.6 ? "warn" : ""));
    }
    if (fl) {
      /* ⚠ SIGNED AND EXPLICIT. A bare "0.42" reads as a magnitude; he needs the SIDE at a glance. */
      fl.textContent = sg.flow == null ? "—"
        : (sg.flow > 0 ? "+" : "") + (sg.flow * 100).toFixed(0) + "%";
      /* ★★2026-09-24 HYSTERESIS ON THE COLOUR, NOT ON THE NUMBER.
         The window dropped 120s -> 30s so the number keeps up with the tape. Measured over 6h of
         ticks, that alone would flip the colour 328 times an hour — once every ELEVEN SECONDS —
         and a cell that strobes is one he stops seeing. Entering at ±0.20 and only leaving below
         ±0.12 brings it to 147/hr (one per 25s) with no cost to the number's responsiveness.
         ⚠ A threshold without hysteresis manufactures churn — the same fault as the |net|>40
         router rule that had no dwell band.
         ⚠ State lives here, across polls, because that is the only place continuity exists; the
         server is stateless per request and would have to persist a file to do this. */
      if (sg.flow == null) { fl.className = ""; AL.flowState = 0; }
      else {
        var f = sg.flow, st = AL.flowState || 0;
        if (st === 0) { if (Math.abs(f) >= 0.20) st = f > 0 ? 1 : -1; }
        else if (Math.abs(f) < 0.12) st = 0;
        else if (Math.sign(f) !== st && Math.abs(f) >= 0.20) st = f > 0 ? 1 : -1;
        AL.flowState = st;
        fl.className = st > 0 ? "pos" : (st < 0 ? "neg" : "");
      }
    }

    /* ★★★2026-09-24 CVD AND THE DIVERGENCE FLAG.
       Built after he pushed back on FLOW: "its essentially 30 seconds delayed? so the tape has
       already done the corresponding move? if so its useless." Not delayed — a 30s WINDOW ends NOW
       — but MEASURED, an episode of |flow|>=0.20 has a MEDIAN LIFE OF 3 SECONDS, so the average
       outlives the thing it averages. CVD does not forget, so it can show sustained pressure.
       ⚠⚠ THE NUMBER AGREEING WITH THE CHART MEANS NOTHING — aggressive buying is largely WHAT
       MOVES PRICE, so CVD tracking the session (+0.98 over 5 sessions) is near-tautological. The
       DIVERGE cell is the whole reason this is here.
       ⚠ DESCRIPTIVE. Amber says the two disagree; it does not say which one wins. */
    const cv = c.cvd || {}, cvEl = $("ctx-cvd"), dvEl = $("ctx-div");
    if (cvEl) {
      cvEl.textContent = cv.cvd == null ? "—"
        : (cv.cvd > 0 ? "+" : "") + (Math.abs(cv.cvd) >= 1000
          ? (cv.cvd / 1000).toFixed(1) + "k" : String(cv.cvd));
      cvEl.className = cv.cvd == null ? "" : (cv.cvd > 0 ? "pos" : (cv.cvd < 0 ? "neg" : ""));
    }
    if (dvEl) {
      /* ★★★2026-09-24 SHOW THE TWO NUMBERS, NOT THE VERDICT. Operator: "how do u know from what
         youve given me about price being at the top of the session or not? and aggression has
         drained away. how do i see that" — and the answer was that he COULD NOT. `px_pos` and
         `cvd_pos` existed only in a `title` tooltip, and he is on the iPhone ~96% of the time,
         where there is no hover. I had built a flag whose INPUTS were invisible and then explained
         his open position using them.
         ⚠⚠ A DERIVED VERDICT WHOSE INPUTS CANNOT BE SEEN IS UNAUDITABLE. "in line" told him
         nothing he could check, disagree with, or learn to read. The pair "81·43" tells him where
         price sits in the session range and where CVD sits in its own — which IS the divergence,
         and lets him watch it approach rather than only hear it arrive.
         ⚠ AMBER, NEVER GREEN OR RED. A divergence is not a side; colouring it like a direction
         would be the page asserting an edge nobody has measured. */
      const pp = cv.px_pos, cp = cv.cvd_pos;
      dvEl.textContent = (pp == null || cp == null) ? "—"
        : Math.round(pp * 100) + "·" + Math.round(cp * 100);
      dvEl.className = cv.divergence ? "warn" : "";
      dvEl.title = pp == null ? ""
        : "PRICE is at " + Math.round(pp * 100) + "% of today's range, CVD at "
          + Math.round(cp * 100) + "% of its own."
          + (cv.divergence ? "  ⚠ " + cv.divergence.toUpperCase()
             + " — they disagree, which does NOT say which one wins."
             : "  They are in line.")
          + "  Fires bearish above 85·50, bullish below 15·50.";
    }

    /* ★★★2026-09-24 THE TWO RANGE GAUGES. He asked for these the moment he understood that
       PX·CVD % is a POSITION ON A SCALE and not a share of a quantity — "can you put the high and
       low of both price and that somewhere for me?"
       ⚠ A percentage without its endpoints is a number he has to TAKE ON TRUST. With the low and
       high beside it he can do the arithmetic himself, and the difference between an instrument he
       can check and an oracle he cannot is the difference between one he uses and one he ignores.
       ⚠ The dot is placed from the SAME px_pos/cvd_pos the flag uses — never recomputed here, or
       the gauge and the flag could disagree and nothing would say which was right. */
    (function ranges() {
      const se = c.session || {};
      const put = (loId, hiId, dotId, lo, hi, pos, fmt) => {
        setTxt(loId, lo == null ? "—" : fmt(lo));
        setTxt(hiId, hi == null ? "—" : fmt(hi));
        const dot = $(dotId);
        if (dot) dot.style.left = (pos == null ? 50 : Math.max(0, Math.min(1, pos)) * 100) + "%";
      };
      /* ⚠⚠⚠ THE WINDOW'S endpoints, NOT the session's. Using se.low/se.high printed a SESSION
         range under a dot positioned on the 3-HOUR scale — 30680/30998 shown while the real window
         was 30838/30952, so the labels implied 65% where the marker sat at 43%. He asked what the
         range was telling him and was doing the arithmetic, which is exactly how a gauge that
         misstates its own scale gets caught. ⚠ Falls back to the session only if the window figures
         are absent, and then the dot has nothing better either. */
      put("rg-px-lo", "rg-px-hi", "rg-px-dot",
          cv.px_lo != null ? cv.px_lo : se.low,
          cv.px_hi != null ? cv.px_hi : se.high, cv.px_pos,
          (x) => nf(x, 2));
      /* ★★2026-09-24 TINT THE PRICE TRACK AT VWAP — his ask, after the CVD heat landed.
         "High in the range" carries no inherent side; ABOVE OR BELOW THE DAY'S AVERAGE PRICE does.
         Green above VWAP, red below, split AT VWAP — which is rarely the midpoint, so "above half"
         and "above VWAP" are genuinely different statements and the tick has to be drawn.
         ⚠ Same rule as the CVD gauge: the marker's colour follows the SIDE (last vs vwap), never
         its position in the range, because a lopsided day makes those disagree.
         ⚠ Hidden, and the track left plain, when VWAP is outside the range — it can sit outside
         after a gap, and a tick pinned to an end would assert a boundary that is not on the
         scale. */
      const vw = se.vwap, plo = se.low, phi = se.high, vt = $("rg-px-vwap");
      const vin = vw != null && plo != null && phi != null && phi > plo && vw >= plo && vw <= phi;
      if (vt) {
        vt.hidden = !vin;
        if (vin) vt.style.left = ((vw - plo) / (phi - plo)) * 100 + "%";
      }
      const ptk = vt && vt.parentNode;
      if (ptk) {
        if (vin) {
          const vp = ((vw - plo) / (phi - plo)) * 100;
          ptk.style.background =
            "linear-gradient(to right, rgba(192,57,43,.20) 0%, rgba(192,57,43,.20) " + vp
            + "%, rgba(31,111,67,.20) " + vp + "%, rgba(31,111,67,.20) 100%)";
        } else {
          ptk.style.background = "var(--line2)";
        }
      }
      const pdot = $("rg-px-dot");
      if (pdot) pdot.style.background = (vw == null || se.last == null) ? "var(--txt)"
        : (se.last > vw ? "#4ade80" : (se.last < vw ? "#ef6a5c" : "var(--txt)"));
      put("rg-cv-lo", "rg-cv-hi", "rg-cv-dot", cv.cvd_lo, cv.cvd_hi, cv.cvd_pos,
          (x) => (x > 0 ? "+" : "") + Math.round(x).toLocaleString());
      /* ★★★ WHERE ZERO FALLS ON THAT SCALE. The range is anchored to TODAY'S extremes, so zero is
         NOT the midpoint: on 2026-09-24 it sat at 39% against -8,072/+12,469. He read 43% as "back
         on the sellers side" within a minute of seeing the gauge, and he was reading it exactly as
         the design invited. Dot RIGHT of the tick = buyers cumulatively ahead. Dot LEFT = sellers.
         ⚠ Hidden when zero is outside the range — a one-sided session would otherwise pin the tick
         to an end and imply a neutral point that is not on the scale at all. */
      const z = $("rg-cv-zero");
      const lo = cv.cvd_lo, hi = cv.cvd_hi;
      const inside = lo != null && hi != null && hi > lo && lo <= 0 && hi >= 0;
      if (z) {
        z.hidden = !inside;
        if (inside) z.style.left = ((0 - lo) / (hi - lo)) * 100 + "%";
      }
      /* ★★★2026-09-24 HEAT THE CVD TRACK BY SIDE — his ask: "heat map code them to show buy or
         sell? the cvd one at least."
         The track splits AT ZERO, not at the midpoint: red left of zero is sellers' territory,
         green right of it is buyers'. So the gauge answers "which side are we on" by colour and
         "how far into today's swing" by position, and the two no longer have to be held in the
         head at once — which is the confusion that produced "does 43% mean its back on the
         sellers side?" (it did not; zero sat at 39%).
         ⚠ FAINT (0.20/0.16 alpha). This is a 3px background behind a marker that must stay the
         most legible thing on the strip — a saturated track would read as the data.
         ⚠ When zero is off the scale the WHOLE track takes the one side it is on. A split drawn
         at a boundary that is not on the scale would be a lie about where neutral is.
         ⚠ The DOT takes its colour from the SIGN of cvd, never from its position in the range —
         those disagree whenever the range is lopsided, and the sign is the thing he asked for. */
      const tk = z && z.parentNode;
      if (tk) {
        if (inside) {
          const zp = ((0 - lo) / (hi - lo)) * 100;
          tk.style.background =
            "linear-gradient(to right, rgba(192,57,43,.20) 0%, rgba(192,57,43,.20) " + zp
            + "%, rgba(31,111,67,.20) " + zp + "%, rgba(31,111,67,.20) 100%)";
        } else if (lo != null && hi != null) {
          tk.style.background = (lo > 0 ? "rgba(31,111,67,.16)" : "rgba(192,57,43,.16)");
        }
      }
      const cdot = $("rg-cv-dot");
      if (cdot) cdot.style.background = cv.cvd == null ? "var(--txt)"
        : (cv.cvd > 0 ? "#4ade80" : (cv.cvd < 0 ? "#ef6a5c" : "var(--txt)"));
    })();

    /* ★★ POSITION AGE IS A GUARD, NOT A STAT. Amber past 3h, red past 8h — the buckets are
       measured, not decorative: over-8h holds are 0 winners from 4. */
    const po = c.position, pa = $("ctx-posage");
    if (pa) {
      pa.textContent = po ? (po.age_min >= 60
        ? Math.floor(po.age_min / 60) + "h" + String(po.age_min % 60).padStart(2, "0")
        : po.age_min + "m") : "flat";
      pa.className = po ? (po.band === "ABANDONED" ? "neg" : po.band === "long" ? "warn" : "") : "";
    }
    /* ★ STEP AWAY must LOOK different when armed — a guard that looks identical armed and
       disarmed is one he will forget he set. */
    const sa = c.step_away || {}, sb2 = $("sa-btn");
    /* ★★2026-09-24 THE LIMITS STICK BETWEEN ARMS. Operator: "can we make the step away limits
       stick between arms?" — they were reset to the HTML defaults (200/300) on every page load,
       so every arm after the first meant retyping the numbers he had just chosen, with the phone
       keyboard, often while walking into something.
       ★ SOURCE IS THE SERVER, not localStorage: step_away.json keeps limit_usd/take_profit_usd
       after firing, so the values follow him to any device and survive a browser wipe. The guard
       and the page then agree by construction rather than by coincidence.
       ⚠ NEVER WRITE INTO A FIELD HE IS TYPING IN. A poll lands every second and would eat the
       keystroke he is halfway through. */
    (function stickyLimits() {
      /* ★★★2026-09-25 FIXED — IT WAS OVERWRITING HIM ONCE A SECOND. Operator: "the dashboard
         doesnt let me adjust the prices in the step away. i change the $500 TP to lower and it
         just changes itself back to $500."
         ⚠⚠⚠ AND IT IS A SAFETY BUG, NOT A UI ANNOYANCE. He could type 300, look away, and arm a
         guard set to the 500 he had just rejected — a stop or a target he never chose, on a live
         position, with the page showing the number he did not pick.
         THE FAULT: `document.activeElement` only protects the field WHILE HE IS TYPING IN IT. The
         moment he taps Done or taps away it blurs, and the very next poll — within one second —
         wrote the stored value straight back over his edit. On a phone every edit ends in a blur,
         so on a phone it was unusable by construction.
         ★ THE FIX: deliver a value ONCE PER CHANGE OF THE SERVER VALUE, never on every poll. If we
         have already delivered this exact stored value, the box belongs to HIM until the server's
         own number changes — which happens when he arms, and that is the act that commits it. */
      const pairs = [["sa-loss", sa.limit_usd], ["sa-tp", sa.take_profit_usd]];
      pairs.forEach(([id, v]) => {
        const el = $(id);
        if (!el || v == null) return;
        const want = String(Math.round(Number(v)));
        if (AL.saSeen[id] === want) return;          // already delivered — his edits are his
        if (el === document.activeElement) return;   // and never fight a keystroke in flight
        AL.saSeen[id] = want;
        el.value = want;
      });
    })();
    if (sb2) sb2.className = "orb away" + (sa.armed ? " armed" : "");
    setTxt("sa-lab", sa.armed ? "ARMED" : "STEP AWAY");
    setTxt("sa-state", sa.armed
      ? `−$${Math.round(sa.limit_usd)}` + (sa.take_profit_usd ? ` / +$${Math.round(sa.take_profit_usd)}` : "")
      : "off");
  }

  /* ---------- last 14 sessions, tap a row to open it ---------- */
  const DAYS_OPEN = new Set();

  /* ★★★2026-09-24 THE DAY-BAR STRIP — "that graph that you made on the reports tab are we getting
     better... big green bars for big winning days and inverse red for losing."
     Same language as progress.html (green #1f6f43 / red #c0392b, one bar per session, hung off a
     centre zero line) but LIVE off STATE.days instead of a generated snapshot, so it is never a
     week out of date the way a static report is.
     ⚠ SCALED TO THE LARGEST ABSOLUTE DAY IN THE WINDOW, and the zero line sits in the MIDDLE with
     equal room above and below. A scale fitted separately to the up and down sides would make a
     -$2,222 day look the same height as a +$857 one, which is the single most misleading thing a
     P&L chart can do.
     ⚠ Oldest LEFT, newest RIGHT — days_json returns newest-first, so this reverses. Reading a time
     axis backwards is a mistake you only notice after you have drawn a conclusion from it. */
  function renderDayBars(rows) {
    const host = $("days-bars");
    if (!host) return;
    if (!rows || !rows.length) { host.innerHTML = ""; return; }
    const d = rows.slice().reverse();
    const mx = Math.max(1, ...d.map((r) => Math.abs(r.pnl || 0)));
    const W = 1000, H = 120, MID = H / 2, gap = 2;
    const bw = Math.max(3, (W - gap * d.length) / d.length);
    let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img"`
      + ` aria-label="Daily realised P&L, one bar per session">`
      + `<line x1="0" y1="${MID}" x2="${W}" y2="${MID}" stroke="var(--line2)" stroke-width="1"/>`;
    d.forEach((r, i) => {
      const v = r.pnl || 0;
      const h = Math.max(1.5, (Math.abs(v) / mx) * (MID - 6));
      const x = i * (bw + gap);
      const y = v >= 0 ? MID - h : MID;
      svg += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}"`
        + ` height="${h.toFixed(1)}" rx="1.5" fill="${v >= 0 ? "#1f6f43" : "#c0392b"}"`
        + ` opacity=".92"><title>${r.day}  ${v >= 0 ? "+" : ""}${Math.round(v)}`
        + `  (${r.entries} entries)</title></rect>`;
    });
    svg += "</svg>";
    host.innerHTML = svg;
    const g = d.filter((r) => (r.pnl || 0) > 0).length;
    /* ⚠ GREEN DAYS AND TOTAL P&L ARE DIFFERENT QUESTIONS and the strip shows both, because one
       big red day can outweigh nine green ones — which is this desk's actual loss profile. */
    setTxt("days-bars-note", `${g}/${d.length} green · worst ${money(-mx, 0)} · best `
      + money(Math.max(...d.map((r) => r.pnl || 0)), 0));
  }

  function renderDays() {
    const d = STATE.days; const tb = $("days-tbl"); if (!d || !tb) return;
    const body = tb.querySelector("tbody"); if (!body) return;
    const rows = d.days || [];
    const tot = rows.reduce((s, x) => s + (x.pnl || 0), 0);
    const sum = $("days-sum");
    /* ★ SAY WHICH QUESTION THIS ANSWERS. The header and this table once disagreed by $330 on a
       carry-in trade and nothing on the page said which to believe. */
    if (sum) sum.textContent = rows.length
      ? `· ${rows.length} sessions · ${money(tot, 0)} · realised` : "";
    guard("days.bars", () => renderDayBars(rows));
    body.innerHTML = "";
    rows.forEach((r) => {
      const tr = document.createElement("tr");
      tr.className = "dayrow" + (DAYS_OPEN.has(r.day) ? " open" : "");
      const pf = r.pf == null ? "—" : r.pf.toFixed(2);
      /* ⚠ "entries" are DECISIONS. The rows in `trades` are scale-out EXITS of one entry, so a
         per-row count overstates his activity ~2.5x — the drill below shows the exits. */
      tr.innerHTML =
        `<td class="d"><span class="chev">${DAYS_OPEN.has(r.day) ? "▾" : "▸"}</span> ${r.day.slice(5)}</td>` +
        `<td class="s">${r.entries}t</td>` +
        `<td class="s">${r.wins}/${r.losses}</td>` +
        `<td class="s">PF ${pf}</td>` +
        `<td class="p ${(r.pnl || 0) >= 0 ? "pos" : "neg"}">${money(r.pnl, 0)}</td>`;
      tr.onclick = () => {
        if (DAYS_OPEN.has(r.day)) DAYS_OPEN.delete(r.day); else DAYS_OPEN.add(r.day);
        renderDays();
      };
      body.appendChild(tr);
      if (!DAYS_OPEN.has(r.day)) return;
      const dr = document.createElement("tr");
      dr.className = "drill";
      /* ★★2026-09-18 REBUILT. Operator: "everything dark grey and not colour coded. not showing
         the things i want. i want time of day. points. p&l green or red. do it in an elegant drop
         down please its ugly the way it is."
         So: TIME, side pill, entry→exit, POINTS, P&L — points and P&L both coloured by sign, and a
         left accent bar per row so a winning and a losing trade are distinguishable at a glance on
         a phone without reading a single digit.
         ⚠ POINTS ARE DIRECTION-CORRECTED: a SHORT that falls is a WINNER. Rendering exit-minus-
         entry raw would show every profitable short as negative — a number reading as its own
         negation, the same defect fixed in leg_watch's messages on 09-15. */
      const sub = (r.trades || []).map((t) => {
        const win = (t.pnl || 0) >= 0;
        const sgn = t.side === "SHORT" ? -1 : 1;
        const pts = (t.entry != null && t.exit != null) ? (t.exit - t.entry) * sgn : null;
        const held = (new Date(t.closed) - new Date(t.opened)) / 60000;
        const cls = win ? "pos" : "neg";
        /* ⚠ FIXED WIDTHS, or one row wrecks the column. On 2026-09-15 the BADFILL row is an
           AVERAGE of fabricated fills and carries FOUR decimals (29306.625 -> 29269.3125) where
           every other row is clean 2dp, so that day's drill opened visibly misaligned. MNQ ticks
           in 0.25 so 2dp is exact for any real price; an averaged one rounds, and that row is
           flagged anyway. Same for qty: the DB stores it as a float, so "4.0" not "4". */
        const px = (v) => (v == null ? "—" : Number(v).toFixed(2));
        /* ⚠ And a 421-minute hold sat beside 16m neighbours as a raw "421m". Hours past two. */
        const dur = !isFinite(held) ? "—"
          : held < 120 ? Math.round(held) + "m"
          : Math.floor(held / 60) + "h" + String(Math.round(held % 60)).padStart(2, "0");
        /* ⚠ A carried trade was OPENED on an earlier day — showing a bare time would imply it
           started today. Mark it, or the time column lies. */
        const car = t.carried ? `<span class="car" title="opened ${(t.opened || "").slice(0, 10)}">↱</span>` : "";
        return `<tr class="dt ${win ? "w" : "l"}${t.flag ? " flagged" : ""}"` +
               (t.flag ? ` title="${t.flag}"` : "") + `>` +
               `<td class="tm">${car}${(t.opened || "").slice(11, 16)}</td>` +
               `<td><span class="pill ${t.side === "SHORT" ? "short" : "long"}">${t.side}</span>` +
               `<span class="q">${Math.round(t.qty)}</span></td>` +
               `<td class="px">${px(t.entry)} <span class="ar">→</span> ${px(t.exit)}</td>` +
               `<td class="pt ${cls}">${pts == null ? "—" : (pts > 0 ? "+" : "") + pts.toFixed(1)}</td>` +
               `<td class="pl ${cls}">${money(t.pnl, 0)}</td>` +
               `<td class="meta">${dur}</td>` +
               `<td class="meta">${(t.reason || "").replace("MANUAL_CLAIM", "hand").replace("TARGET_", "T").replace("CLOCK_FLAT", "20:40 flat")}</td>` +
               `</tr>`;
      }).join("");
      dr.innerHTML = `<td colspan="5"><table class="sub">${sub}</table>` +
        (r.flagged ? `<div class="note">${r.flagged} row(s) struck through: a real trade whose PRICE came from a fabricated fill — shown, never counted.</div>` : "") +
        `</td>`;
      body.appendChild(dr);
    });
  }

  /* ---------- tab badges (phone) ---------- */
  function renderTabBadges(m) {
    const h = m.header || {};
    const hold = mnqHoldings();
    $("tb-desk").textContent = deskToday(h) != null ? money(deskToday(h), 0) : "—";
    setTxt("tb-hold", hold.length ? money(hold.reduce((s, x) => s + (x.pnl_usd || 0), 0), 0) : "flat");
    /* ★★2026-09-18 `trades_today` is TOURNAMENT-ONLY, exactly like `today` was. The P&L badge was
       fixed on 08-13 via deskToday() and the COUNT beside it was left reading the tournament — so
       on 2026-09-18 it showed "0 trades" next to "+$1,630" on a fifteen-trade day. A right number
       beside a wrong one is worse than either alone. */
    const nTr = (h.trades_rider != null || h.trades_tournament != null)
      ? (h.trades_rider || 0) + (h.trades_tournament || 0)
      : h.trades_today;
    $("tb-trades").textContent = (nTr != null ? nTr : "—");
    const dd = (STATE.days && STATE.days.days) || null;
    const tbd = $("tb-days");
    if (tbd) tbd.textContent = dd && dd.length ? money(dd.reduce((s, x) => s + (x.pnl || 0), 0), 0) : "—";
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
        /* ⚠⚠ DOUBLE rAF. A panel revealed this frame has not been LAID OUT yet, so clientHeight
           is still 0 — and renderHero's zero-size guard (written to skip a hidden tab) returns
           without drawing. That is the 09-02 failure exactly: a chart box measuring ZERO, no error
           anywhere, blank for nine days. One frame to apply the class, the next to measure it. */
        requestAnimationFrame(() => requestAnimationFrame(() => {
          guard("tabshow.renderHero", renderHero);
          guard("tabshow.renderHolding", renderHolding);
          guard("tabshow.renderDays", renderDays);
          guard("tabshow.renderTrades", () => renderTrades(STATE.mnq || {}));
        }));
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
    /* ⚠ [data-min] — NOT every .tf in the bar. The MNQ/MGC pair lives in #tfbar too (one
       line, by his instruction), so a bare "#tfbar .tf" strips `on` off the SYMBOL button
       on every phone load and the pair renders with neither selected. */
    document.querySelectorAll("#tfbar .tf[data-min]").forEach((x) => x.classList.toggle("on", x.dataset.min === "60"));
    STATE.tfMode = "60";
  }
  // ★2026-09-02 symbol selector — same WINDOW toggles, different series. The choice is remembered
  // so a phone that reloads mid-watch comes back to the contract he was watching; MNQ on anything
  // unexpected, because the desk's own instrument is the safe default.
  try {
    const saved = localStorage.getItem("gz7.chartSym");
    if (saved === "MGC") STATE.sym = "MGC";
  } catch (e) { /* private mode — MNQ default is correct */ }
  /* ★★★2026-09-24 THESE SELECT [data-sym] INSIDE #tfbar. They used to name a container id
     that the TRADE merge DELETED when it moved the MNQ/MGC pair into the timeframe bar — so
     querySelectorAll returned an empty list and the whole symbol toggle went dead in silence.
     Three consequences, none of which threw anything:
       (a) no click handler was ever attached, so MNQ/MGC could not switch the contract;
       (b) the generic "#tfbar .tf" handler below DID match them, so tapping MGC ran the TIMEFRAME
           handler instead — dataset.min is undefined there, so it reset the window to 2h, cleared
           the window highlight, and re-fetched MNQ;
       (c) a remembered MGC choice in localStorage set STATE.sym but was never reflected in the
           buttons, so a gold chart could render with the pair showing neither symbol lit.
     ⚠ SELECT BY THE ATTRIBUTE THE HANDLER READS. A handler that reads dataset.sym must select
       [data-sym]; one that reads dataset.min must select [data-min]. Sharing one container is
       fine — sharing one selector is not. */
  document.querySelectorAll("#tfbar .tf[data-sym]").forEach((x) => x.classList.toggle("on", x.dataset.sym === STATE.sym));
  document.querySelectorAll("#tfbar .tf[data-sym]").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("#tfbar .tf[data-sym]").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    STATE.sym = b.dataset.sym === "MGC" ? "MGC" : "MNQ";
    STATE.bars = null;            // ⚠ drop the other contract's bars NOW — one poll of gold prices
                                  //   drawn under an MNQ label is exactly the confusion to avoid
    try { localStorage.setItem("gz7.chartSym", STATE.sym); } catch (e) { }
    try { renderHero(); } catch (e) { }          // repaint immediately: "loading MGC…", not stale MNQ
    fastTick();
  }));

  // timeframe selector — switch the chart window + refetch immediately
  document.querySelectorAll("#tfbar .tf[data-min]").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("#tfbar .tf[data-min]").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    STATE.tfMode = b.dataset.min;                  // "session" stays dynamic; a number is fixed
    STATE.tf = tfMinutes(b.dataset.min);
    fastTick();
  }));

  alInit();
  clock(); setInterval(clock, 1000);
  slowTick(); fastTick();
  setInterval(fastTick, POLL_FAST_MS);
  setInterval(slowTick, POLL_SLOW_MS);
  // the chart draws in pixel space → re-fit it to the new box on resize (debounced), not just next tick
  let _rz; window.addEventListener("resize", () => { clearTimeout(_rz); _rz = setTimeout(() => { try { renderHero(); } catch (e) { } }, 120); });
})();
