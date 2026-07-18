/* Doppelkopf web client. Talks to the Flask API in web.py.
   ASCII source; suit glyphs come from unicode escapes. */

"use strict";

const SUITS = ["♣", "♠", "♥", "♦"]; // C S H D
const RED_SUITS = [2, 3];
const BOT_DELAY_MS = 650;
const TRICK_LINGER_MS = 1100;

let gameId = null;
let view = null;
let busy = false;        // A request or animation is in flight.
let adviceBest = null;   // Card id the advisor likes best right now.
let stepTimer = null;

// --- Helpers ---------------------------------------------------------

const $ = (sel) => document.querySelector(sel);

async function api(path, body) {
  const opts = body === undefined
      ? {}
      : {method: "POST", headers: {"Content-Type": "application/json"},
         body: JSON.stringify(body)};
  const resp = await fetch(path, opts);
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || resp.statusText);
  return data;
}

function cardLabel(card) {
  return card.rank + SUITS[card.suit];
}

function isRed(card) {
  return RED_SUITS.includes(card.suit);
}

function cardNode(card, extraClass) {
  const div = document.createElement("div");
  div.className = "card" + (isRed(card) ? " red" : "")
      + (card.trump ? " trump" : "") + (extraClass ? " " + extraClass : "");
  const corner = document.createElement("div");
  corner.className = "corner";
  corner.innerHTML = card.rank + "<br>" + SUITS[card.suit];
  const pip = document.createElement("div");
  pip.className = "pip";
  pip.textContent = SUITS[card.suit];
  const pts = document.createElement("div");
  pts.className = "pts";
  pts.textContent = card.points > 0 ? card.points : "";
  div.append(corner, pip, pts);
  return div;
}

function setStatus(html) {
  $("#status-line").innerHTML = html;
}

// --- Rendering -------------------------------------------------------

function render() {
  renderSeats();
  renderTrick(view.current_trick, null);
  renderHand();
  renderScoreboard();
  renderLog();
  renderBanner();
}

function renderSeats() {
  for (let seat = 0; seat < 4; seat++) {
    const el = $("#seat-" + seat);
    el.classList.toggle("to-act", !view.terminal && view.to_act === seat);
    const badges = el.querySelector(".seat-badges");
    badges.innerHTML = "";
    if (view.known_re.includes(seat)) {
      const star = document.createElement("span");
      star.className = "badge-re";
      star.textContent = "★";
      star.title = "played a club queen: publicly Re";
      badges.appendChild(star);
    }
    const backs = el.querySelector(".cardbacks");
    if (backs) {
      backs.innerHTML = "";
      for (let i = 0; i < view.hand_sizes[seat]; i++) {
        const b = document.createElement("div");
        b.className = "cardback";
        backs.appendChild(b);
      }
    }
  }
}

function renderTrick(cards_, winnerSeat) {
  for (let seat = 0; seat < 4; seat++) {
    $(".trick-slot.slot-" + seat).innerHTML = "";
  }
  for (const play of cards_) {
    const node = cardNode(play.card,
        winnerSeat !== null && play.seat === winnerSeat ? "winner" : "");
    $(".trick-slot.slot-" + play.seat).appendChild(node);
  }
  const info = $("#trick-info");
  if (cards_.length === 0 && !view.terminal) {
    info.innerHTML = "Trick " + view.trick_no + "/12<br>"
        + "<span class='big'>" + view.names[view.trick_leader]
        + (view.trick_leader === 0 ? " lead" : " leads") + "</span>";
  } else {
    info.innerHTML = "";
  }
}

function renderHand() {
  const hand = $("#hand");
  hand.innerHTML = "";
  hand.classList.toggle("inactive", !view.your_turn || view.terminal);
  let hinted = false;
  for (const card of view.hand) {
    const legal = card.legal === true;
    const node = cardNode(card, legal ? "playable" : (view.your_turn ? "illegal" : ""));
    if (view.your_turn && legal && !hinted && card.id === adviceBest) {
      node.classList.add("hint");
      hinted = true;
    }
    if (legal && view.your_turn) {
      node.addEventListener("click", () => playCard(card.id));
    }
    hand.appendChild(node);
  }
}

function renderScoreboard() {
  const board = $("#scoreboard");
  board.innerHTML = "";
  for (let seat = 0; seat < 4; seat++) {
    const cell = document.createElement("div");
    cell.className = "score-cell" + (view.known_re.includes(seat) ? " re-known" : "");
    const name = document.createElement("span");
    name.textContent = view.names[seat]
        + (view.known_re.includes(seat) ? " ★" : "");
    const pts = document.createElement("span");
    pts.className = "pts";
    pts.textContent = view.points_taken[seat];
    cell.append(name, pts);
    board.appendChild(cell);
  }
}

function renderLog() {
  const log = $("#trick-log");
  if (!view.tricks.length) {
    log.innerHTML = "<p class='muted'>No tricks yet.</p>";
    return;
  }
  log.innerHTML = "";
  view.tricks.forEach((trick, i) => {
    const row = document.createElement("div");
    row.className = "log-row";
    const cards_ = document.createElement("span");
    cards_.className = "cards";
    cards_.append(...trick.cards.map((play, j) => {
      const s = document.createElement("span");
      s.className = (isRed(play.card) ? "red" : "")
          + (play.seat === trick.winner ? " tw" : "");
      s.textContent = (j ? " " : "") + cardLabel(play.card);
      return s;
    }));
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = (i + 1) + ". " + view.names[trick.winner]
        + " +" + trick.points;
    row.append(cards_, who);
    log.appendChild(row);
  });
  log.scrollTop = log.scrollHeight;
}

function renderBanner() {
  const banner = $("#team-banner");
  banner.classList.remove("hidden");
  if (view.silent_wedding) {
    banner.innerHTML = "You hold <b>both club queens</b> &mdash; a silent "
        + "wedding! You play <b>Re</b> alone against all three, for triple "
        + "the score.";
  } else if (view.you_re) {
    banner.innerHTML = "You hold a club queen: you play for <b>Re</b>. "
        + "Your partner holds the other one&hellip;";
  } else {
    banner.innerHTML = "No club queen: you play for <b>Kontra</b>. "
        + "Who your partner is will emerge&hellip;";
  }
}

// --- Advice ----------------------------------------------------------

async function refreshAdvice() {
  const panel = $("#advice-body");
  adviceBest = null;
  if (!$("#advice-toggle").checked) {
    panel.innerHTML = "<p class='muted'>Advice is switched off.</p>";
    return;
  }
  if (!view || view.terminal || !view.your_turn) {
    panel.innerHTML = "<p class='muted'>Advice appears here on your turn.</p>";
    return;
  }
  panel.innerHTML = "<p class='muted'>Thinking&hellip;</p>";
  let data;
  try {
    data = await api("/api/advice?game=" + gameId);
  } catch (err) {
    panel.innerHTML = "<p class='muted'>" + err.message + "</p>";
    return;
  }
  if (!view.your_turn) return;  // The world moved on while we thought.

  const advice = data.advice;
  adviceBest = advice[0].card.id;
  panel.innerHTML = "";
  const head = document.createElement("p");
  head.className = "advice-head";
  head.innerHTML = "Bot would play <b>" + cardLabel(advice[0].card)
      + "</b> (expected " + fmtScore(advice[0].score) + " game points)";
  panel.appendChild(head);

  const maxAbs = Math.max(1, ...advice.map((a) => Math.abs(a.score)));
  advice.forEach((entry, i) => {
    const row = document.createElement("div");
    row.className = "advice-row" + (i === 0 ? " best" : "");
    const tag = document.createElement("span");
    tag.className = "tag" + (isRed(entry.card) ? " red" : "")
        + (entry.card.trump ? " trump" : "");
    tag.textContent = cardLabel(entry.card);
    const bar = document.createElement("div");
    bar.className = "advice-bar";
    bar.title = cardLabel(entry.card) + ": " + fmtScore(entry.score);
    const zero = document.createElement("div");
    zero.className = "zero";
    const fill = document.createElement("div");
    fill.className = "fill " + (entry.score >= 0 ? "pos" : "neg");
    fill.style.width = (Math.abs(entry.score) / maxAbs * 46) + "%";
    bar.append(zero, fill);
    const val = document.createElement("span");
    val.className = "val";
    val.textContent = fmtScore(entry.score);
    row.append(tag, bar, val);
    panel.appendChild(row);
  });
  const note = document.createElement("p");
  note.className = "panel-note";
  note.textContent = "Expected game points for you, averaged over "
      + "sampled worlds (" + data.source + " rollouts).";
  panel.appendChild(note);
  renderHand();  // Outline the recommended card.
}

function fmtScore(x) {
  return (x >= 0 ? "+" : "") + x.toFixed(2);
}

// --- Game flow -------------------------------------------------------

async function newGame() {
  clearTimeout(stepTimer);
  busy = true;
  $("#new-game").disabled = true;
  $("#result-overlay").classList.add("hidden");
  try {
    const seedRaw = $("#seed").value.trim();
    const data = await api("/api/new", {
      seed: seedRaw === "" ? null : Number(seedRaw),
      opponents: $("#opponents").value,
    });
    gameId = data.game;
    view = data.view;
    $("#advice-source").textContent = "(" + view.advice_source + ")";
    render();
    setStatus(view.your_turn ? "Your lead. Pick a card."
                             : view.names[view.to_act] + " starts.");
    refreshAdvice();
  } finally {
    busy = false;
    $("#new-game").disabled = false;
  }
  tick();
}

async function playCard(cardId) {
  if (busy || !view.your_turn) return;
  busy = true;
  try {
    const data = await api("/api/play", {game: gameId, card: cardId});
    await advance(data.view);
  } catch (err) {
    setStatus("<span class='warn'>" + err.message + "</span>");
  } finally {
    busy = false;
  }
  tick();
}

/* Applies a new view; if it completed a trick, linger on the full trick
   with the winner highlighted before sweeping it away. */
async function advance(newView) {
  const before = view;
  view = newView;
  const finished = view.last_trick && before
      && view.tricks.length === before.tricks.length + 1;
  if (finished) {
    const t = view.last_trick;
    renderSeats();
    renderTrick(t.cards, t.winner);
    $("#trick-info").innerHTML = "";
    setStatus("<b>" + view.names[t.winner] + "</b> "
        + (t.winner === 0 ? "take" : "takes") + " the trick (+"
        + t.points + " points).");
    renderScoreboard();
    renderLog();
    await new Promise((resolve) => setTimeout(resolve, TRICK_LINGER_MS));
  }
  render();
  if (view.terminal) {
    showResult();
  } else if (view.your_turn) {
    setStatus("Your turn.");
    refreshAdvice();
  } else {
    setStatus(view.names[view.to_act] + " is thinking…");
    refreshAdvice();
  }
}

/* Drives bot moves whenever it is not the human's turn. */
function tick() {
  clearTimeout(stepTimer);
  if (!view || view.terminal || view.your_turn || busy) return;
  stepTimer = setTimeout(async () => {
    if (!view || view.terminal || view.your_turn || busy) return;
    busy = true;
    try {
      const data = await api("/api/step", {game: gameId});
      await advance(data.view);
    } catch (err) {
      setStatus("<span class='warn'>" + err.message + "</span>");
    } finally {
      busy = false;
    }
    tick();
  }, BOT_DELAY_MS);
}

// --- Result ----------------------------------------------------------

function showResult() {
  const res = view.result;
  const youRe = view.you_re;
  const youWin = (res.re_wins && youRe) || (!res.re_wins && !youRe);
  const headline = $("#result-headline");
  headline.innerHTML = (res.re_wins ? "Re wins" : "Kontra wins")
      + " &mdash; <span class='" + (youWin ? "win'>you win " : "lose'>you lose ")
      + fmtScore(res.returns[0]).replace(".00", "") + "</span>";

  const names = view.names;
  const teamList = (seats) => seats.map((s) => names[s]).join(", ");
  let html = "";
  html += "<div class='result-section'>Card points</div>";
  html += "<table class='result-table'>";
  html += "<tr><td>Re (" + teamList(res.re_seats)
      + (res.re_seats.length === 1 ? ", silent wedding" : "") + ")</td>"
      + "<td class='num'>" + res.re_points + "</td></tr>";
  html += "<tr><td>Kontra (" + teamList(res.kontra_seats) + ")</td>"
      + "<td class='num'>" + res.kontra_points + "</td></tr></table>";

  html += "<div class='result-section'>Game points</div>";
  html += "<table class='result-table'>";
  const winnerTeam = res.re_wins ? "Re" : "Kontra";
  for (const [label] of res.base) {
    html += "<tr><td>" + winnerTeam + ": " + label + "</td><td class='num'>+1</td></tr>";
  }
  for (const [label, sign] of res.specials) {
    html += "<tr><td>" + (sign > 0 ? "Re" : "Kontra") + ": " + label
        + "</td><td class='num'>+1</td></tr>";
  }
  html += "<tr><td><b>Value (from Re's side)</b></td><td class='num'><b>"
      + (res.value >= 0 ? "+" : "") + res.value + "</b></td></tr></table>";

  html += "<div class='result-section'>Score</div>";
  html += "<table class='result-table'>";
  for (let seat = 0; seat < 4; seat++) {
    html += "<tr><td>" + names[seat] + "</td><td class='num'>"
        + fmtScore(res.returns[seat]).replace(".00", "") + "</td></tr>";
  }
  html += "</table>";

  $("#result-body").innerHTML = html;
  $("#result-overlay").classList.remove("hidden");
}

// --- Wiring ----------------------------------------------------------

$("#new-game").addEventListener("click", newGame);
$("#again").addEventListener("click", newGame);
$("#advice-toggle").addEventListener("change", refreshAdvice);

setStatus("Press <b>New game</b> to be dealt in.");

/* Attaches to a game that already exists server-side. */
async function attach(id) {
  gameId = id;
  try {
    const data = await api("/api/state?game=" + id);
    view = data.view;
    $("#advice-source").textContent = "(" + view.advice_source + ")";
    render();
    if (view.terminal) {
      showResult();
    } else {
      setStatus(view.your_turn ? "Your turn."
                               : view.names[view.to_act] + " is thinking…");
      refreshAdvice();
      tick();
    }
  } catch (err) {
    setStatus("<span class='warn'>" + err.message + "</span>");
  }
}

// Quick start via URL: /?new, /?seed=42&opponents=master, /?game=<id>
const params = new URLSearchParams(location.search);
if (params.get("game")) {
  attach(params.get("game"));
} else if (params.has("new") || params.has("seed")
           || params.has("opponents")) {
  if (params.get("seed")) $("#seed").value = params.get("seed");
  if (params.get("opponents")) $("#opponents").value = params.get("opponents");
  newGame();
}
