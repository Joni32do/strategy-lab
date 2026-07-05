/* Catan Lab — thin client over the catanatron Flask server (server/app.py).
 * No game logic here: the engine computes every move; we render and tune. */
(function () {
  "use strict";

  var API = ""; // same origin (Flask serves this page)
  var RES = ["WOOD", "BRICK", "SHEEP", "WHEAT", "ORE"];
  var ICON = { WOOD: "🌲", BRICK: "🧱", SHEEP: "🐑", WHEAT: "🌾", ORE: "⛰️" };
  var RESFILL = { WOOD: "#3f8f5a", BRICK: "#b5532e", SHEEP: "#9fd06a", WHEAT: "#e3b748", ORE: "#8993a4" };
  var DESERT = "#cdbb97";

  // Slider definitions: [key, label, min, max, step, hint, integer?]
  var METRIC = [
    ["vp", "VP weight", 0, 1, 0.01, "closeness to victory — should dominate"],
    ["production", "Production weight", 0, 1, 0.01, "economic engine (pips)"],
    ["expansion", "Expansion weight", 0, 1, 0.01, "buildable nodes / reach"],
    ["prod_norm", "Production = ‘full’ at", 4, 24, 1, "pips that count as a maxed economy"],
    ["expansion_norm", "Expansion = ‘full’ at", 2, 16, 1, "buildable nodes that count as full"],
  ];
  var TRADE = [
    ["lam_max", "λ ceiling", 0, 5, 0.1, "max weight put on the rival's gain"],
    ["lam_steepness", "λ steepness", 1, 20, 0.5, "how sharply λ switches on"],
    ["lam_midpoint", "λ midpoint", 0, 1, 0.02, "rival strength where λ = half of ceiling"],
    ["veto_vp_margin", "Hard veto within", 0, 4, 1, "refuse ALL trades if rival is this close to 10 VP", true],
    ["margin", "Min net to trade", 0, 2, 0.05, "value units the deal must clear"],
    ["premium_per_vp", "Premium per VP behind", 0, 2, 0.05, "extra value demanded per VP the rival leads"],
    ["scarcity_weight", "Scarcity value", 0, 3, 0.1, "worth of a resource you barely produce"],
    ["need_weight", "Need value", 0, 4, 0.1, "worth of a resource that completes a build"],
    ["base_value", "Base value", 0, 2, 0.1, "floor value of any resource"],
  ];

  var STRATEGY = [
    ["block_weight", "Blocking preference", 0, 3, 0.1, "prefer builds that deny an opponent expansion nodes (uses the VALUE brain)"],
  ];

  // Decision-boundary explorer: the inputs the trade-accept rule keys off. Any two
  // become the plot axes; the rest are held at .val (shown as sliders).
  var FEATURES = [
    { key: "opp_vp", label: "Opponent VP", min: 0, max: 10, step: 1, val: 6, int: true },
    { key: "my_vp", label: "Your VP", min: 0, max: 10, step: 1, val: 5, int: true },
    { key: "opp_strength", label: "Opponent strength", min: 0, max: 1, step: 0.02, val: 0.5 },
    { key: "my_gain", label: "Your gain (value)", min: 0, max: 4, step: 0.1, val: 1.6 },
    { key: "their_gain", label: "Their gain (value)", min: 0, max: 4, step: 0.1, val: 1.4 },
  ];
  var FEAT = {}; FEATURES.forEach(function (f) { FEAT[f.key] = f.val; });
  var VPS_TO_WIN = 10;
  var exp = { x: "opp_vp", y: "my_gain" };
  // preset "views" — clicking one collapses the n-dim surface onto that pair.
  var VIEWS = [
    { x: "opp_vp", y: "my_gain", name: "VP vs gain" },
    { x: "opp_strength", y: "their_gain", name: "strength vs their gain" },
    { x: "opp_vp", y: "opp_strength", name: "VP vs strength" },
    { x: "my_vp", y: "opp_vp", name: "the VP race" },
    { x: "their_gain", y: "my_gain", name: "gain vs gain" },
  ];

  var cfg = { weights: {}, trade: {} };
  var game = null; // {id, state}
  var autoTimer = null, simDebounce = null, simBusy = false;

  var $ = function (id) { return document.getElementById(id); };
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }

  function api(path, body) {
    return fetch(API + path, {
      method: body ? "POST" : "GET",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
  }

  // ---------------- sliders + curve ----------------
  function buildSliders(container, defs, store, defaults) {
    container.innerHTML = "";
    defs.forEach(function (d) {
      var key = d[0], label = d[1], min = d[2], max = d[3], step = d[4], hint = d[5], integer = d[6];
      store[key] = defaults[key];
      var wrap = el("div", "slider");
      var valTxt = integer ? store[key] : (+store[key]).toFixed(step < 0.1 ? 2 : 2);
      wrap.appendChild(el("div", "row", "<span>" + label + "</span><span class='val' id='v_" + key + "'>" + valTxt + "</span>"));
      var inp = el("input"); inp.type = "range"; inp.min = min; inp.max = max; inp.step = step; inp.value = store[key];
      inp.addEventListener("input", function () {
        store[key] = integer ? parseInt(inp.value, 10) : parseFloat(inp.value);
        $("v_" + key).textContent = integer ? store[key] : store[key].toFixed(2);
        onTune();
      });
      wrap.appendChild(inp);
      if (hint) wrap.appendChild(el("div", "hint", hint));
      container.appendChild(wrap);
    });
  }

  function lambda(s) {
    var t = cfg.trade, z = t.lam_steepness * (s - t.lam_midpoint);
    z = Math.max(-60, Math.min(60, z));
    return t.lam_max / (1 + Math.exp(-z));
  }

  function drawCurve() {
    var c = $("lamCurve"), ctx = c.getContext("2d");
    var W = c.width, H = c.height, pad = 30;
    ctx.clearRect(0, 0, W, H);
    var x0 = pad, x1 = W - 10, y0 = H - pad, y1 = 12;
    var ymax = Math.max(0.5, cfg.trade.lam_max);
    function X(s) { return x0 + s * (x1 - x0); }
    function Y(v) { return y0 + (v / ymax) * (y1 - y0); }
    // grid + axes
    ctx.strokeStyle = "#272d49"; ctx.lineWidth = 1; ctx.fillStyle = "#8b91b5"; ctx.font = "11px sans-serif";
    ctx.beginPath(); ctx.moveTo(x0, y1); ctx.lineTo(x0, y0); ctx.lineTo(x1, y0); ctx.stroke();
    [0, 0.25, 0.5, 0.75, 1].forEach(function (s) {
      ctx.fillText(s.toFixed(2), X(s) - 9, y0 + 14);
    });
    ctx.fillText("λ", x0 - 22, y1 + 6); ctx.fillText("0", x0 - 16, y0 + 3);
    ctx.fillText(ymax.toFixed(1), x0 - 22, y1 + 12);
    ctx.save(); ctx.fillStyle = "#8b91b5"; ctx.fillText("opponent strength →", X(0.32), y0 + 26); ctx.restore();
    // midpoint marker
    var mx = X(cfg.trade.lam_midpoint);
    ctx.strokeStyle = "rgba(155,123,255,.4)"; ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(mx, y1); ctx.lineTo(mx, y0); ctx.stroke(); ctx.setLineDash([]);
    // curve
    ctx.strokeStyle = "#9b7bff"; ctx.lineWidth = 2.5; ctx.beginPath();
    for (var i = 0; i <= 100; i++) { var s = i / 100; var px = X(s), py = Y(lambda(s)); i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); }
    ctx.stroke();
    // caption
    var t = cfg.trade;
    $("lamCap").innerHTML =
      "Weak rival → λ≈<b>" + lambda(0).toFixed(2) + "</b>, strong rival → λ≈<b>" + lambda(1).toFixed(2) +
      "</b>. Net deal value = <b>my&nbsp;gain − λ·their&nbsp;gain</b>. " +
      "Hard veto if rival is within <b>" + t.veto_vp_margin + " VP</b> of winning; " +
      "demand <b>+" + (+t.premium_per_vp).toFixed(2) + "</b> value per VP they lead.";
  }

  function onTune() {
    drawCurve();
    drawField();
    if ($("autoSim").checked) {
      clearTimeout(simDebounce);
      simDebounce = setTimeout(function () { runSim(20); }, 650);
    }
  }

  // ---------------- decision boundary explorer ----------------
  // The trade-accept rule, mirrored from server/policy.py:evaluate_trade so the
  // surface matches what the bot actually does (same lambda, same thresholds).
  var SCALE = 2.5;            // slack magnitude that maps to full colour
  var C_NEU = [36, 42, 64], C_ACC = [63, 179, 127], C_REJ = [224, 99, 127];
  var GN = 64, PAD = { l: 46, r: 12, t: 12, b: 36 };

  function featOf(name) { for (var i = 0; i < FEATURES.length; i++) if (FEATURES[i].key === name) return FEATURES[i]; }

  function decisionAt(f) {
    var t = cfg.trade;
    var lam = lambda(f.opp_strength);
    var net = f.my_gain - lam * f.their_gain;
    var required = t.margin + t.premium_per_vp * Math.max(0, f.opp_vp - f.my_vp);
    var vetoed = f.opp_vp >= VPS_TO_WIN - t.veto_vp_margin;
    var accept = !vetoed && f.my_gain > 0 && net >= required;
    return { net: net, required: required, vetoed: vetoed, accept: accept, slack: net - required, lam: lam };
  }

  function sampleAt(gx, gy) {
    var fx = featOf(exp.x), fy = featOf(exp.y);
    var f = {};
    FEATURES.forEach(function (ft) { f[ft.key] = FEAT[ft.key]; });
    f[exp.x] = fx.min + gx * (fx.max - fx.min);
    f[exp.y] = fy.min + gy * (fy.max - fy.min);  // gx,gy in [0,1]
    return decisionAt(f);
  }

  function drawField() {
    var c = $("boundary"); if (!c) return;
    var ctx = c.getContext("2d");
    var W = c.width, H = c.height;
    var px = PAD.l, py = PAD.t, pw = W - PAD.l - PAD.r, ph = H - PAD.t - PAD.b;
    ctx.clearRect(0, 0, W, H);

    // sample grid: row 0 = top = feature-y max
    var slack = [], veto = [];
    for (var j = 0; j < GN; j++) {
      slack[j] = []; veto[j] = [];
      var gy = 1 - j / (GN - 1);
      for (var i = 0; i < GN; i++) {
        var d = sampleAt(i / (GN - 1), gy);
        slack[j][i] = d.slack; veto[j][i] = d.vetoed;
      }
    }

    // heatmap into an offscreen GNxGN buffer, then scale up with smoothing (interpolation)
    var off = drawField._off || (drawField._off = document.createElement("canvas"));
    off.width = GN; off.height = GN;
    var octx = off.getContext("2d"), img = octx.createImageData(GN, GN);
    for (var jj = 0; jj < GN; jj++) for (var ii = 0; ii < GN; ii++) {
      var k = (jj * GN + ii) * 4, s = slack[jj][ii], rgb;
      if (veto[jj][ii]) rgb = [26, 30, 48];
      else {
        var m = Math.min(1, Math.abs(s) / SCALE), side = s >= 0 ? C_ACC : C_REJ, tt = 0.30 + 0.70 * m;
        rgb = [C_NEU[0] + (side[0] - C_NEU[0]) * tt, C_NEU[1] + (side[1] - C_NEU[1]) * tt, C_NEU[2] + (side[2] - C_NEU[2]) * tt];
      }
      img.data[k] = rgb[0]; img.data[k + 1] = rgb[1]; img.data[k + 2] = rgb[2]; img.data[k + 3] = 255;
    }
    octx.putImageData(img, 0, 0);
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = "high";
    ctx.drawImage(off, 0, 0, GN, GN, px, py, pw, ph);

    // veto hatch overlay (over the vetoed cells)
    ctx.save();
    ctx.strokeStyle = "rgba(120,132,180,.55)"; ctx.lineWidth = 1;
    for (var jv = 0; jv < GN - 1; jv++) for (var iv = 0; iv < GN - 1; iv++) {
      if (!veto[jv][iv]) continue;
      var X = px + (iv / (GN - 1)) * pw, Y = py + (jv / (GN - 1)) * ph;
      ctx.beginPath(); ctx.moveTo(X, Y + ph / (GN - 1)); ctx.lineTo(X + pw / (GN - 1), Y); ctx.stroke();
    }
    ctx.restore();

    // marching-squares boundary at slack = 0 (skip cells touching a veto corner)
    ctx.strokeStyle = "#f4f0ff"; ctx.lineWidth = 2;
    ctx.beginPath();
    for (var y2 = 0; y2 < GN - 1; y2++) for (var x2 = 0; x2 < GN - 1; x2++) {
      if (veto[y2][x2] || veto[y2 + 1][x2] || veto[y2][x2 + 1] || veto[y2 + 1][x2 + 1]) continue;
      contourCell(ctx, slack, x2, y2, px, py, pw, ph);
    }
    ctx.stroke();

    drawAxes(ctx, px, py, pw, ph);
  }

  // one marching-squares cell: draw the zero-crossing segment
  function contourCell(ctx, S, i, j, px, py, pw, ph) {
    var tl = S[j][i], tr = S[j][i + 1], br = S[j + 1][i + 1], bl = S[j + 1][i];
    var idx = (tl > 0 ? 8 : 0) | (tr > 0 ? 4 : 0) | (br > 0 ? 2 : 0) | (bl > 0 ? 1 : 0);
    if (idx === 0 || idx === 15) return;
    var cw = pw / (GN - 1), ch = ph / (GN - 1);
    var x0 = px + i * cw, y0 = py + j * ch;
    function ip(a, b) { return a / (a - b); } // fraction where slack crosses 0
    var T = { x: x0 + ip(tl, tr) * cw, y: y0 };
    var B = { x: x0 + ip(bl, br) * cw, y: y0 + ch };
    var L = { x: x0, y: y0 + ip(tl, bl) * ch };
    var R = { x: x0 + cw, y: y0 + ip(tr, br) * ch };
    var seg = [];
    switch (idx) {
      case 1: case 14: seg = [L, B]; break;
      case 2: case 13: seg = [B, R]; break;
      case 3: case 12: seg = [L, R]; break;
      case 4: case 11: seg = [T, R]; break;
      case 6: case 9: seg = [T, B]; break;
      case 7: case 8: seg = [L, T]; break;
      case 5: seg = [L, T]; ctx.moveTo(B.x, B.y); ctx.lineTo(R.x, R.y); break;
      case 10: seg = [L, B]; ctx.moveTo(T.x, T.y); ctx.lineTo(R.x, R.y); break;
    }
    if (seg.length === 2) { ctx.moveTo(seg[0].x, seg[0].y); ctx.lineTo(seg[1].x, seg[1].y); }
  }

  function drawAxes(ctx, px, py, pw, ph) {
    var fx = featOf(exp.x), fy = featOf(exp.y);
    ctx.strokeStyle = "#2a3050"; ctx.lineWidth = 1;
    ctx.strokeRect(px, py, pw, ph);
    ctx.fillStyle = "#8b91b5"; ctx.font = "11px sans-serif";
    function fmt(f, v) { return f.int ? String(Math.round(v)) : v.toFixed(1); }
    // x ticks
    [0, 0.5, 1].forEach(function (t) {
      var v = fx.min + t * (fx.max - fx.min), X = px + t * pw;
      ctx.textAlign = "center"; ctx.fillText(fmt(fx, v), X, py + ph + 14);
    });
    // y ticks
    [0, 0.5, 1].forEach(function (t) {
      var v = fy.min + t * (fy.max - fy.min), Y = py + (1 - t) * ph;
      ctx.textAlign = "right"; ctx.fillText(fmt(fy, v), px - 6, Y + 3);
    });
    ctx.textAlign = "center"; ctx.fillStyle = "#c7cbe6";
    ctx.fillText(fx.label + " ->", px + pw / 2, py + ph + 30);
    ctx.save(); ctx.translate(14, py + ph / 2); ctx.rotate(-Math.PI / 2);
    ctx.fillText(fy.label + " ->", 0, 0); ctx.restore();
  }

  function buildFixedSliders() {
    var host = $("fixedSliders"); host.innerHTML = "";
    FEATURES.forEach(function (f) {
      if (f.key === exp.x || f.key === exp.y) return;
      var wrap = el("div", "slider");
      var v = f.int ? Math.round(FEAT[f.key]) : (+FEAT[f.key]).toFixed(f.step < 0.1 ? 2 : 1);
      wrap.appendChild(el("div", "row", "<span>" + f.label + "</span><span class='val' id='fx_" + f.key + "'>" + v + "</span>"));
      var inp = el("input"); inp.type = "range"; inp.min = f.min; inp.max = f.max; inp.step = f.step; inp.value = FEAT[f.key];
      inp.addEventListener("input", function () {
        FEAT[f.key] = f.int ? parseInt(inp.value, 10) : parseFloat(inp.value);
        $("fx_" + f.key).textContent = f.int ? FEAT[f.key] : FEAT[f.key].toFixed(f.step < 0.1 ? 2 : 1);
        drawField();
      });
      wrap.appendChild(inp);
      host.appendChild(wrap);
    });
  }

  function syncViews() {
    var host = $("expViews"); if (!host) return;
    Array.prototype.forEach.call(host.children, function (chip) {
      var on = chip.dataset.x === exp.x && chip.dataset.y === exp.y;
      chip.classList.toggle("on", on);
    });
  }

  function setAxes(x, y) {
    if (x === y) { // don't allow a degenerate axis: bump the other one
      var alt = FEATURES.find(function (f) { return f.key !== x; });
      if (exp.x === x) y = alt.key; else x = alt.key;
    }
    exp.x = x; exp.y = y;
    $("axisX").value = x; $("axisY").value = y;
    buildFixedSliders(); syncViews(); drawField();
  }

  function initExplorer() {
    var sx = $("axisX"), sy = $("axisY");
    FEATURES.forEach(function (f) {
      [sx, sy].forEach(function (sel) { var o = el("option"); o.value = f.key; o.textContent = f.label; sel.appendChild(o); });
    });
    sx.value = exp.x; sy.value = exp.y;
    sx.addEventListener("change", function () { setAxes(sx.value, exp.y); });
    sy.addEventListener("change", function () { setAxes(exp.x, sy.value); });

    var vhost = $("expViews");
    VIEWS.forEach(function (v) {
      var chip = el("button", "exp-chip", v.name);
      chip.dataset.x = v.x; chip.dataset.y = v.y;
      chip.addEventListener("click", function () { setAxes(v.x, v.y); });
      vhost.appendChild(chip);
    });

    var c = $("boundary");
    c.addEventListener("mousemove", function (e) {
      var r = c.getBoundingClientRect(), scaleX = c.width / r.width, scaleY = c.height / r.height;
      var mx = (e.clientX - r.left) * scaleX, my = (e.clientY - r.top) * scaleY;
      var px = PAD.l, py = PAD.t, pw = c.width - PAD.l - PAD.r, ph = c.height - PAD.t - PAD.b;
      var gx = (mx - px) / pw, gy = 1 - (my - py) / ph;
      if (gx < 0 || gx > 1 || gy < 0 || gy > 1) { readout(null); return; }
      var fx = featOf(exp.x), fy = featOf(exp.y);
      var f = {}; FEATURES.forEach(function (ft) { f[ft.key] = FEAT[ft.key]; });
      var vx = fx.min + gx * (fx.max - fx.min), vy = fy.min + gy * (fy.max - fy.min);
      f[exp.x] = vx; f[exp.y] = vy;
      readout({ vx: vx, vy: vy, fx: fx, fy: fy, d: decisionAt(f) });
    });
    c.addEventListener("mouseleave", function () { readout(null); });

    buildFixedSliders(); syncViews();
  }

  function readout(o) {
    var tip = $("expTip"); if (!tip) return;
    if (!o) { tip.innerHTML = "hover the surface to read the decision at a point"; return; }
    var d = o.d, fmtx = o.fx.int ? Math.round(o.vx) : o.vx.toFixed(1), fmty = o.fy.int ? Math.round(o.vy) : o.vy.toFixed(1);
    var verdict = d.vetoed ? "<b class='rej'>veto</b>" : d.accept ? "<b class='acc'>accept</b>" : "<b class='rej'>refuse</b>";
    tip.innerHTML = o.fx.label + " <b>" + fmtx + "</b> &times; " + o.fy.label + " <b>" + fmty + "</b> &rarr; " +
      verdict + " &middot; slack <b>" + d.slack.toFixed(2) + "</b> (net " + d.net.toFixed(2) + " vs required " + d.required.toFixed(2) + ")";
  }

  // ---------------- simulate ----------------
  function runSim(nOverride) {
    if (simBusy) return;
    simBusy = true;
    var n = nOverride || parseInt($("nGames").value, 10);
    var box = $("simResult");
    box.innerHTML = "<p class='desc' style='margin-top:14px'><span class='spinner'></span> simulating " + n + " games…</p>";
    api("/api/simulate", {
      n: n, seed: parseInt($("seed").value, 10), opponent: $("opp").value,
      base_bot: $("baseBot").value, weights: cfg.weights, trade: cfg.trade, enable_trade: true,
    }).then(function (r) { renderSim(r); }).catch(function (e) {
      box.innerHTML = "<p class='desc'>error: " + e.message + "</p>";
    }).then(function () { simBusy = false; });
  }

  function renderSim(r) {
    var pct = function (x) { return (100 * x / r.games).toFixed(0) + "%"; };
    var box = $("simResult"); box.innerHTML = "";
    var bars = el("div", "winbars");
    function bar(name, cls, n) {
      var b = el("div", "winbar");
      b.innerHTML = "<span class='name'>" + name + "</span><div class='track'><div class='fill " + cls + "' style='width:" + pct(n) + "'></div></div><span class='pct'>" + n + " · " + pct(n) + "</span>";
      bars.appendChild(b);
    }
    bar("You", "you", r.you_wins); bar(r.opponent, "opp", r.opp_wins);
    if (r.draws) bar("None", "draw", r.draws);
    box.appendChild(bars);

    var grid = el("div", "stat-grid");
    grid.appendChild(el("div", "stat", "<div class='k'>Win rate</div><div class='v'>" + (100 * r.you_winrate).toFixed(0) + "%</div>"));
    grid.appendChild(el("div", "stat", "<div class='k'>Avg VP</div><div class='v'>" + r.avg_your_vp + "<span class='muted' style='font-size:.7rem'> v " + r.avg_opp_vp + "</span></div>"));
    grid.appendChild(el("div", "stat", "<div class='k'>Avg turns</div><div class='v'>" + r.avg_turns + "</div>"));
    box.appendChild(grid);

    var t = r.trades;
    box.appendChild(el("div", "trade-tally",
      "<b>" + t.offers + "</b> offers → <b>" + t.confirms + "</b> confirmed · " +
      t.accepts + " accepted · " + t.rejects + " rejected · " +
      "<b style='color:var(--avoid)'>" + t.vetoes + "</b> vetoed (leader refused)"));
  }

  // ---------------- step-through ----------------
  function newGame() {
    stopAuto();
    $("newGame").disabled = true;
    return api("/api/game", { opponent: $("opp").value, base_bot: $("baseBot").value, seed: parseInt($("seed").value, 10) || undefined, weights: cfg.weights, trade: cfg.trade })
      .then(function (r) {
        game = { id: r.game_id, state: r.state };
        $("log").innerHTML = "";
        ["step", "auto", "reset"].forEach(function (b) { $(b).disabled = false; });
        render();
        addLog({ note: "new game · seed " + r.seed + " · vs " + $("opp").value }, null, true);
      })
      .catch(function (e) { addLog({ note: "could not start: " + e.message }, null, true); })
      .then(function () { $("newGame").disabled = false; });
  }

  function step() {
    if (!game) return;
    return api("/api/game/" + game.id + "/tick", {}).then(function (r) {
      game.state = r.state;
      addLog(r.explanation, r, false);
      render();
      if (r.done) { stopAuto(); $("step").disabled = true; addLog({ note: "winner: " + (r.state.winner || "none") + " in " + r.state.num_turns + " turns" }, null, true); }
      return r.done;
    });
  }

  function stopAuto() { if (autoTimer) { clearInterval(autoTimer); autoTimer = null; $("auto").textContent = "Auto"; } }
  function toggleAuto() {
    if (autoTimer) { stopAuto(); return; }
    $("auto").textContent = "Pause";
    var tick = function () {
      step().then(function (done) {
        if (!done && autoTimer) { autoTimer = setTimeout(tick, 1010 - parseInt($("speed").value, 10)); }
      });
    };
    autoTimer = setTimeout(tick, 10);
  }

  // ---------------- rendering ----------------
  function colorMap() {
    var m = {};
    (game.state.players || []).forEach(function (p) { m[p.color] = p.is_you ? "var(--p0)" : "var(--p1)"; });
    return m;
  }

  function render() {
    renderPlayers();
    renderBoard();
  }

  function renderPlayers() {
    var st = game.state, host = $("players"); host.innerHTML = "";
    var ordered = st.players.slice().sort(function (a, b) { return (b.is_you ? 1 : 0) - (a.is_you ? 1 : 0); });
    ordered.forEach(function (p) {
      var cls = "pcard" + (p.color === st.current_color ? " turn" : "");
      var card = el("div", cls);
      var who = p.is_you ? "you" : "opp";
      var d = p.strength_detail;
      card.innerHTML =
        "<div class='ptitle'><span class='dot " + who + "'></span>" + (p.is_you ? "You" : p.color) +
        "<span class='vp'>" + p.vp + " VP" + (p.public_vp !== p.vp ? " (" + p.public_vp + " shown)" : "") + "</span></div>" +
        "<div class='strength-bar'><div class='fill " + who + "' style='width:" + (100 * p.strength).toFixed(0) + "%'></div></div>" +
        "<div class='strength-val'>strength <b style='color:var(--text)'>" + p.strength.toFixed(2) + "</b> · " +
        "vp " + d.vp_term.toFixed(2) + " · prod " + d.prod_term.toFixed(2) + " · reach " + d.exp_term.toFixed(2) + "</div>" +
        "<div class='hand'>" + RES.map(function (r, i) { return "<span class='res'>" + ICON[r] + p.hand[i] + "</span>"; }).join("") +
        "<span class='res' title='dev cards'>🃏" + p.dev_cards + "</span><span class='res' title='longest road'>🛣️" + p.longest_road + "</span></div>";
      host.appendChild(card);
    });
  }

  function renderBoard() {
    var B = window.CATAN_BOARD, st = game.state, cm = colorMap();
    if (!B) { $("board").innerHTML = "<div class='empty'>board geometry missing</div>"; return; }
    var ns = B.nodes;
    var svg = "<svg viewBox='0 0 " + B.W + " " + B.H + "' xmlns='http://www.w3.org/2000/svg'>";
    // tiles
    B.tiles.forEach(function (t, i) {
      var tile = st.tiles[i] || {};
      var fill = tile.resource ? (RESFILL[tile.resource] || DESERT) : DESERT;
      var pts = t.nodes.map(function (nid) { return ns[nid][0] + "," + ns[nid][1]; }).join(" ");
      svg += "<polygon class='hex' points='" + pts + "' fill='" + fill + "'/>";
      if (tile.number) {
        var red = (tile.number === 6 || tile.number === 8) ? " red" : "";
        svg += "<circle cx='" + t.cx + "' cy='" + t.cy + "' r='3.4' fill='#f3ecd8'/>";
        svg += "<text class='hex-num" + red + "' x='" + t.cx + "' y='" + t.cy + "'>" + tile.number + "</text>";
      }
      if (i === st.robber_tile) svg += "<circle cx='" + t.cx + "' cy='" + (t.cy - 0.2) + "' r='2.6' fill='#15151f' stroke='#000' stroke-width='.4'/>";
    });
    // ports
    if (B.ports) Object.keys(B.ports).forEach(function (nid) {
      var p = ns[nid]; var lab = B.ports[nid] === "ANY" ? "3:1" : ICON[B.ports[nid]] || "";
      svg += "<text class='port-label' x='" + p[0] + "' y='" + (p[1] - 2) + "'>" + lab + "</text>";
    });
    // roads
    (st.roads || []).forEach(function (r) {
      var a = ns[r.edge[0]], b = ns[r.edge[1]];
      svg += "<line class='road' x1='" + a[0] + "' y1='" + a[1] + "' x2='" + b[0] + "' y2='" + b[1] + "' stroke='" + (cm[r.color] || "#888") + "'/>";
    });
    // buildings
    Object.keys(st.buildings || {}).forEach(function (nid) {
      var bld = st.buildings[nid], p = ns[nid], col = cm[bld.color] || "#aaa";
      if (bld.type === "CITY")
        svg += "<rect class='node-bldg' x='" + (p[0] - 2.2) + "' y='" + (p[1] - 2.2) + "' width='4.4' height='4.4' rx='1' fill='" + col + "'/>";
      else
        svg += "<circle class='node-bldg' cx='" + p[0] + "' cy='" + p[1] + "' r='1.9' fill='" + col + "'/>";
    });
    svg += "</svg>";
    $("board").innerHTML = svg;
  }

  // ---------------- log ----------------
  var VERB = {
    ROLL: "rolls", END_TURN: "ends turn", BUILD_SETTLEMENT: "builds settlement",
    BUILD_CITY: "builds city", BUILD_ROAD: "builds road", BUY_DEVELOPMENT_CARD: "buys dev card",
    MOVE_ROBBER: "moves robber", DISCARD_RESOURCE: "discards", MARITIME_TRADE: "bank-trades",
    PLAY_KNIGHT_CARD: "plays knight", PLAY_MONOPOLY: "monopoly", PLAY_YEAR_OF_PLENTY: "year of plenty",
    PLAY_ROAD_BUILDING: "road building", OFFER_TRADE: "offers trade",
    ACCEPT_TRADE: "accepts", REJECT_TRADE: "rejects", CONFIRM_TRADE: "confirms trade", CANCEL_TRADE: "cancels trade",
  };

  function freqIcons(arr) {
    if (!arr) return "";
    return RES.map(function (r, i) { return arr[i] > 0 ? ICON[r] + (arr[i] > 1 ? arr[i] : "") : ""; }).join(" ").trim() || "∅";
  }

  function addLog(expl, r, system) {
    var log = $("log");
    if (log.querySelector(".empty")) log.innerHTML = "";
    if (system) { log.appendChild(el("div", "logentry", "<span class='act'>" + (expl.note || "") + "</span>")); log.scrollTop = log.scrollHeight; return; }
    if (!r) return;
    var who = r.actor_is_you ? "you" : "opp", whoName = r.actor_is_you ? "You" : r.actor;
    var kind = expl && expl.kind;
    var isTrade = kind === "offer" || kind === "respond" || kind === "confirm" || kind === "cancel";

    if (isTrade && expl.reasoning) {
      var x = expl.reasoning, entry = el("div", "logentry trade");
      var badge, label;
      if (kind === "offer") { badge = "<span class='badge ok'>offer</span>"; label = "offers a trade"; }
      else if (kind === "confirm") { entry.classList.add("confirm"); badge = "<span class='badge ok'>deal</span>"; label = "confirms trade"; }
      else if (kind === "respond") {
        var acc = expl.note === "accept";
        badge = acc ? "<span class='badge ok'>accept</span>" : (x.vetoed ? "<span class='badge veto'>veto</span>" : "<span class='badge no'>reject</span>");
        if (x.vetoed) entry.classList.add("veto");
        label = acc ? "accepts the offer" : (x.vetoed ? "refuses — rival near victory" : "declines the offer");
      } else { badge = "<span class='badge no'>cancel</span>"; label = "cancels"; }

      var tr = expl.trade;
      var tradeLine = tr ? "<div class='trade-line'>gives <b>" + freqIcons(tr.give) + "</b> ⇄ gets <b>" + freqIcons(tr.get) + "</b>" + (tr.with ? " · with " + tr.with : "") + "</div>" : "";
      entry.innerHTML =
        "<div><span class='who " + who + "'>" + whoName + "</span> " + label + " " + badge + "</div>" + tradeLine +
        "<div class='reason'>" +
        "<span>rival strength <b>" + x.opp_strength + "</b></span>" +
        "<span>λ <b>" + x["lambda"] + "</b></span>" +
        "<span>my gain <b>" + x.my_gain + "</b></span>" +
        "<span>their gain <b>" + x.their_gain + "</b></span>" +
        "<span>net <b>" + x.net + "</b></span>" +
        "<span>required <b>" + x.required + "</b></span>" +
        "</div>";
      log.appendChild(entry);
    } else {
      var act = r.action ? (VERB[r.action.type] || r.action.type.toLowerCase().replace(/_/g, " ")) : "";
      var note = expl && expl.note && expl.note !== "value-function best move" && kind !== "play" ? " <span class='muted'>· " + expl.note + "</span>" : "";
      log.appendChild(el("div", "logentry", "<span class='who " + who + "'>" + whoName + "</span> <span class='act'>" + act + note + "</span>"));
    }
    log.scrollTop = log.scrollHeight;
  }

  // ---------------- boot ----------------
  function boot(defaults) {
    $("conn").innerHTML = "engine ready"; $("conn").style.color = "#7fe0a0";
    buildSliders($("metric-sliders"), METRIC, cfg.weights, defaults.weights);
    buildSliders($("strategy-sliders"), STRATEGY, cfg.weights, defaults.weights);
    buildSliders($("trade-sliders"), TRADE, cfg.trade, defaults.trade);
    var opp = $("opp");
    defaults.opponents.forEach(function (o) { var op = el("option"); op.value = o; op.textContent = o; opp.appendChild(op); });
    opp.value = defaults.opponents.indexOf("VALUE") >= 0 ? "VALUE" : defaults.opponents[0];
    var bb = $("baseBot");
    (defaults.base_bots || ["VALUE"]).forEach(function (o) { var op = el("option"); op.value = o; op.textContent = o; bb.appendChild(op); });
    // Optional URL presets: ?opp=TRADER&seed=5&n=60
    var qs = new URLSearchParams(location.search);
    if (qs.get("opp") && defaults.opponents.indexOf(qs.get("opp").toUpperCase()) >= 0) opp.value = qs.get("opp").toUpperCase();
    if (qs.get("seed") !== null) $("seed").value = qs.get("seed");
    if (qs.get("n") !== null) $("nGames").value = qs.get("n");
    initExplorer();
    drawCurve();
    drawField();
    $("runSim").addEventListener("click", function () { runSim(); });
    $("newGame").addEventListener("click", newGame);
    $("step").addEventListener("click", step);
    $("auto").addEventListener("click", toggleAuto);
    $("reset").addEventListener("click", function () { stopAuto(); game = null; $("log").innerHTML = "<div class='empty'>Start a new game to watch the policy play.</div>"; $("players").innerHTML = ""; $("board").innerHTML = ""; ["step", "auto", "reset"].forEach(function (b) { $(b).disabled = true; }); });

    // Deep-link: open #play to auto-start a game already running.
    if (location.hash === "#play") newGame().then(function () { toggleAuto(); });
  }

  api("/api/defaults").then(boot).catch(function () {
    $("conn").innerHTML = "server offline — run <code>uv run python server/app.py</code>";
    $("conn").style.color = "var(--avoid)";
  });
})();
