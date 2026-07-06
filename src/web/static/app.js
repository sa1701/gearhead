"use strict";

/* ---------- tiny helpers ---------- */
const $ = (id) => document.getElementById(id);
const api = async (path, body) => {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const detail = (await r.json().catch(() => ({}))).detail;
    throw new Error(typeof detail === "string" ? detail : r.statusText);
  }
  return r.json();
};
const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

let SESSION_ID = null;

/* ---------- tachometer gauge (SVG) ---------- */
const GA_START = 135, GA_SPAN = 270;
const NS = "http://www.w3.org/2000/svg";

function polar(cx, cy, r, deg) {
  const a = (deg * Math.PI) / 180;
  return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
}
function arc(cx, cy, r, a0, a1) {
  const p0 = polar(cx, cy, r, a0), p1 = polar(cx, cy, r, a1);
  const large = a1 - a0 > 180 ? 1 : 0;
  return `M ${p0.x} ${p0.y} A ${r} ${r} 0 ${large} 1 ${p1.x} ${p1.y}`;
}
function el(tag, attrs) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}

function buildGauge(host, size = 240) {
  host.innerHTML = "";
  const cx = 110, cy = 110, r = 86;
  const svg = el("svg", { viewBox: "0 0 220 220", width: size, height: size });

  // track
  svg.appendChild(el("path", { d: arc(cx, cy, r, GA_START, GA_START + GA_SPAN), fill: "none", stroke: "#2a323d", "stroke-width": 12, "stroke-linecap": "round" }));
  // redline zone on the low-confidence end of the dial
  svg.appendChild(el("path", { d: arc(cx, cy, r + 13, GA_START, GA_START + GA_SPAN * 0.3), fill: "none", stroke: "rgba(255,59,48,.5)", "stroke-width": 3 }));
  // major + minor ticks
  for (let i = 0; i <= 20; i++) {
    const a = GA_START + (i / 20) * GA_SPAN;
    const major = i % 2 === 0;
    const o = polar(cx, cy, r + 10, a), inn = polar(cx, cy, r + (major ? -2 : 4), a);
    const v = i * 5;
    svg.appendChild(el("line", {
      x1: o.x, y1: o.y, x2: inn.x, y2: inn.y,
      stroke: v >= 70 ? "#34d058" : (v <= 40 ? "#ff3b30" : "#ffb01f"),
      "stroke-width": major ? (i % 10 === 0 ? 3 : 2) : 1, opacity: major ? .7 : .35,
    }));
    if (i % 10 === 0) {
      const t = polar(cx, cy, r - 16, a);
      const num = el("text", { x: t.x, y: t.y + 3, "text-anchor": "middle", fill: "#5e6b7a", "font-size": 10, "font-family": "JetBrains Mono, monospace" });
      num.textContent = v;
      svg.appendChild(num);
    }
  }
  // progress arc (set later)
  const prog = el("path", { fill: "none", "stroke-width": 12, "stroke-linecap": "round", d: "" });
  svg.appendChild(prog);
  // needle with a slight spring overshoot
  const needle = el("line", { x1: cx, y1: cy, x2: cx + r - 16, y2: cy, stroke: "#fff", "stroke-width": 4, "stroke-linecap": "round" });
  needle.style.transformOrigin = "110px 110px";
  needle.style.transition = "transform 1s cubic-bezier(.34,1.4,.4,1), stroke .6s";
  svg.appendChild(needle);
  svg.appendChild(el("circle", { cx, cy, r: 9, fill: "#11151b", stroke: "#2a323d", "stroke-width": 2 }));
  // readout
  const num = el("text", { x: cx, y: cy + 44, "text-anchor": "middle", fill: "#fff", "font-size": 30, class: "gauge-readout" });
  const lab = el("text", { x: cx, y: cy + 62, "text-anchor": "middle", fill: "#8b97a6", "font-size": 11, "font-family": "JetBrains Mono, monospace", "letter-spacing": "2" });
  svg.appendChild(num); svg.appendChild(lab);

  host.appendChild(svg);
  return { cx, cy, r, prog, needle, num, lab };
}

function colorFor(v) { return v < 45 ? "#ff3b30" : v < 70 ? "#ffb01f" : "#34d058"; }

function setGauge(g, value, label) {
  const v = Math.max(0, Math.min(100, value));
  const a = GA_START + (v / 100) * GA_SPAN;
  const c = colorFor(v);
  g.prog.setAttribute("d", v > 0 ? arc(g.cx, g.cy, g.r, GA_START, a) : "");
  g.prog.setAttribute("stroke", c);
  g.needle.style.transform = `rotate(${a - 0}deg)`;
  g.needle.setAttribute("stroke", c);
  g.num.textContent = Math.round(v);
  g.num.setAttribute("fill", c);
  g.lab.textContent = label || "%";
}
function setScanning(g) {
  g.prog.setAttribute("d", arc(g.cx, g.cy, g.r, GA_START, GA_START + GA_SPAN * 0.42));
  g.prog.setAttribute("stroke", "#ffb01f");
  g.needle.style.transform = `rotate(${GA_START + GA_SPAN * 0.42}deg)`;
  g.needle.setAttribute("stroke", "#ffb01f");
  g.num.textContent = "—"; g.num.setAttribute("fill", "#ffb01f");
  g.lab.textContent = "SCANNING";
}

/* the classic key-on cluster sweep: needle flies to max, falls back, then scans */
function ignitionSweep(g, after) {
  if (REDUCED) { after(); return; }
  setGauge(g, 100, "SELF-TEST");
  setTimeout(() => setGauge(g, 0, "SELF-TEST"), 650);
  setTimeout(after, 1350);
}

let gaugeMain, gaugeFix;

/* ---------- screen switching ---------- */
function show(id) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
  $(id).classList.add("active");
}

/* ---------- chat ---------- */
function bubble(kind, html, who) {
  const b = document.createElement("div");
  b.className = "bubble " + kind;
  b.innerHTML = (who ? `<span class="who">${who}</span>` : "") + html;
  $("chatLog").appendChild(b);
  $("chatLog").scrollTop = $("chatLog").scrollHeight;
  return b;
}
function thinking() { return bubble("bot thinking", "SCANNING", "GEARHEAD"); }

/* ---------- cluster readouts ---------- */
function setMinis(questions, sources) {
  if (questions !== null) $("miniQuestions").textContent = questions;
  if (sources !== null) $("miniSources").textContent = sources;
}

/* ---------- diagnosis formatting ---------- */
function esc(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function inline(s) {
  return esc(s)
    .replace(/\[([^\]]*?p[\.\s]*\d+[^\]]*)\]/gi, '<span class="cite">$1</span>')
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}
function formatFix(text) {
  const lines = text.split("\n");
  let html = "", list = null;
  const closeList = () => { if (list) { html += `</${list}>`; list = null; } };
  for (let raw of lines) {
    const line = raw.trim();
    if (!line) { closeList(); continue; }
    let m;
    if ((m = line.match(/^#{1,3}\s+(.*)/)) || /^\*\*[^*].*\*\*$/.test(line)) {
      closeList();
      html += `<h3>${inline(m ? m[1] : line.replace(/\*\*/g, ""))}</h3>`;
    } else if ((m = line.match(/^\d+[\.\)]\s+(.*)/))) {
      if (list !== "ol") { closeList(); html += "<ol>"; list = "ol"; }
      html += `<li>${inline(m[1])}</li>`;
    } else if ((m = line.match(/^[-*]\s+(.*)/))) {
      if (list !== "ul") { closeList(); html += "<ul>"; list = "ul"; }
      html += `<li>${inline(m[1])}</li>`;
    } else { closeList(); html += `<p>${inline(line)}</p>`; }
  }
  closeList();
  return html;
}

/* ---------- the fix screen ---------- */
async function showFix(step) {
  show("screen-fix");
  const wo = String(Math.floor(1000 + Math.random() * 9000));
  const d = new Date();
  const local = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  $("woMeta").textContent = `WO-${wo} · ${local}`;
  let body = step.text.replace(/⚠️[^\n]*/g, "").trim(); // safety line shown separately
  $("fixBody").innerHTML = formatFix(body);
  $("sources").innerHTML = step.sources
    .map((s) => `<span class="chip">${s.section} · p.${s.page}</span>`).join("");
  setGauge(gaugeFix, step.confidence, "% SURE");
  $("diagram").innerHTML = '<div class="loading">rendering manual page…</div>';
  $("diagramCaption").textContent = "";
  try {
    const ill = await api("/api/illustrate", { session_id: SESSION_ID });
    $("diagram").innerHTML = ill.images.map((u) => `<img src="${u}" alt="manual diagram" />`).join("");
    $("diagramCaption").innerHTML = inline(ill.captions);
  } catch (e) {
    $("diagram").innerHTML = '<div class="loading">diagram unavailable</div>';
  }
}

/* ---------- handle a step from the engine ---------- */
function handleStep(step) {
  if (step.questions_asked !== undefined) setMinis(step.questions_asked, null);
  if (step.sections !== undefined) setMinis(null, step.sections);
  if (step.type === "question") {
    bubble("bot", inline(step.text), "GEARHEAD");
    $("answerInput").disabled = false;
    $("answerInput").focus();
  } else {
    $("ledScan").classList.remove("blink");
    showFix(step);
  }
}

/* ---------- events ---------- */
async function startDiagnosis() {
  const problem = $("problemInput").value.trim();
  const code = $("codeInput").value.trim().toUpperCase();
  if (!problem && !code) { $("problemInput").focus(); return; }
  const full = code ? `OBD fault code ${code}. ${problem}` : problem;

  const btn = $("diagnoseBtn");
  btn.classList.add("busy");
  try {
    // Kick the request off, run the cluster self-test sweep while it's in flight.
    const pending = api("/api/start", { problem: full, car: $("carSelect").value });
    show("screen-interview");
    $("answerInput").disabled = true; // no session yet — enabled when the first question lands
    $("chatLog").innerHTML = "";
    setMinis(0, "—");
    $("ledScan").classList.add("blink");
    bubble("user", esc(full));
    const t = thinking();
    ignitionSweep(gaugeMain, () => setScanning(gaugeMain));
    const step = await pending;
    t.remove();
    SESSION_ID = step.session_id;
    handleStep(step);
  } catch (e) {
    show("screen-start");
    alert("Couldn't start: " + e.message);
  } finally {
    btn.classList.remove("busy");
  }
}

async function sendAnswer() {
  const txt = $("answerInput").value.trim();
  if (!txt || !SESSION_ID || $("answerInput").disabled) return;
  bubble("user", esc(txt));
  $("answerInput").value = "";
  $("answerInput").disabled = true;
  const t = thinking();
  try {
    const step = await api("/api/answer", { session_id: SESSION_ID, answer: txt });
    t.remove();
    handleStep(step);
  } catch (e) {
    t.remove();
    bubble("bot", "Something went wrong: " + esc(e.message), "GEARHEAD");
    $("answerInput").disabled = false;
  }
}

function reset() {
  SESSION_ID = null;
  $("problemInput").value = "";
  $("codeInput").value = "";
  setGauge(gaugeMain, 0, "READY");
  show("screen-start");
}

/* ---------- init ---------- */
(async function init() {
  gaugeMain = buildGauge($("gauge"), 250);
  gaugeFix = buildGauge($("gaugeFix"), 200);
  setGauge(gaugeMain, 0, "READY");
  setGauge(gaugeFix, 0, "READY");

  try {
    const cars = await (await fetch("/api/cars")).json();
    $("carSelect").innerHTML = cars.map((c) => `<option value="${c.id}">${c.name}</option>`).join("");
  } catch (e) { /* ignore */ }

  // engine badge: which brain is under the hood (local Ollama vs Claude API)
  try {
    const st = await (await fetch("/api/status")).json();
    $("engineText").innerHTML = st.local
      ? `ENGINE <span class="hot">${esc(st.model)}</span> · 100% LOCAL`
      : `ENGINE <span class="hot">${esc(st.model)}</span>`;
  } catch (e) { $("engineText").textContent = "ENGINE READY"; }

  // symptom presets — one tap fills the form
  $("presetRow").addEventListener("click", (e) => {
    const p = e.target.closest(".preset");
    if (!p) return;
    if (p.dataset.fill) $("problemInput").value = p.dataset.fill;
    if (p.dataset.code) { $("codeInput").value = p.dataset.code; if (!p.dataset.fill) $("problemInput").value = "Check-engine light on"; }
    $("problemInput").focus();
  });

  // click a manual page to open it full-screen; click anywhere / Esc to close
  $("diagram").addEventListener("click", (e) => {
    if (e.target.tagName === "IMG") {
      $("lbImg").src = e.target.src;
      $("lightbox").classList.add("open");
    }
  });
  $("lightbox").addEventListener("click", () => $("lightbox").classList.remove("open"));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("lightbox").classList.remove("open"); });

  $("diagnoseBtn").addEventListener("click", startDiagnosis);
  $("answerBtn").addEventListener("click", sendAnswer);
  $("answerInput").addEventListener("keydown", (e) => { if (e.key === "Enter") sendAnswer(); });
  $("problemInput").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) startDiagnosis(); });
  $("resetBtn").addEventListener("click", reset);
})();
