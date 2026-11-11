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

let SESSION_ID = null;

/* ---------- the 3D showroom (showroom.js) ---------- */
/* showroom.js loads as a module, after this file. Calls made before it is ready are
   replayed once it says so. */
const showroomQueue = [];
function showroom(method, ...args) {
  const sr = window.Showroom;
  if (sr && sr.views) sr[method](...args);
  else showroomQueue.push([method, args]);
}
window.addEventListener("showroom-ready", () => {
  for (const [method, args] of showroomQueue.splice(0)) window.Showroom[method](...args);
});

/* Which part of the car a sentence is about. First match wins, so order matters. */
const ZONES = [
  ["cooling", /overheat|coolant|radiator|temperature|thermostat|water pump|fan belt/i],
  ["driveline", /clutch|\bgears?\b|transmission|gearbox|\bdiff\b|differential|transfer case|4wd|driveshaft|\baxles?\b|\bcv\b/i],
  ["chassis", /brak|\babs\b|pedal|shudder|rotor|\bpads?\b|steering|suspension|clunk|tyre|tire|wheel bearing|shock/i],
  ["electrical", /battery|alternator|headlight|\blights?\b|fuse|starter|gauge|window|wiper|horn|dash|wiring|relay/i],
  ["engine", /engine|misfire|idle|crank|stall|smoke|\boil\b|injector|turbo|timing|fuel|glow plug|exhaust/i],
];
const ZONE_LABELS = { engine: "Engine", cooling: "Cooling", chassis: "Brakes and steering", driveline: "Driveline", electrical: "Electrics" };
function zoneOf(text) {
  const hit = ZONES.find(([, pattern]) => pattern.test(text || ""));
  return hit ? hit[0] : null;
}
let ZONE = null;
function setZone(zone, seconds) {
  if (!zone || zone === ZONE) return;
  ZONE = zone;
  $("zoneTag").textContent = ZONE_LABELS[zone] || "";
  showroom("focus", zone, seconds);
}

/* ---------- confidence meter: a thin numeral over a hairline bar ---------- */
function buildGauge(host) {
  host.innerHTML =
    '<div class="meter"><div class="meter-num"><span></span><small>%</small></div>' +
    '<div class="meter-label"></div><span class="meter-bar"><i></i></span></div>';
  const root = host.firstChild;
  return {
    root, num: root.querySelector(".meter-num span"), unit: root.querySelector("small"),
    lab: root.querySelector(".meter-label"), bar: root.querySelector(".meter-bar i"),
  };
}

function setGauge(g, value, label) {
  const v = Math.max(0, Math.min(100, value));
  g.root.classList.remove("scanning");
  g.num.textContent = Math.round(v);
  g.unit.hidden = false;
  g.lab.textContent = label || "";
  g.bar.style.width = v + "%";
}
function setScanning(g) {
  g.root.classList.add("scanning");
  g.num.textContent = "—";
  g.unit.hidden = true;
  g.lab.textContent = "Reading the manual";
  g.bar.style.width = "";
}
let gaugeMain, gaugeFix;

/* ---------- screen switching ---------- */
function show(id) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
  $(id).classList.add("active");
  document.body.dataset.screen = id.replace("screen-", "");
  showroom("setIdle", id === "screen-start");   // the car only turns on the start screen
  window.scrollTo(0, 0);
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
function thinking() { return bubble("bot thinking", "Reading the manual", "GEARHEAD"); }

/* ---------- cluster readouts ---------- */
function setMinis(questions, sources) {
  if (questions !== null) $("miniQuestions").textContent = questions;
  if (sources !== null) $("miniSources").textContent = sources;
}

/* ---------- diagnosis formatting ---------- */
function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
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
  showroom("focus", "report", 2.2);
  const wo = String(Math.floor(1000 + Math.random() * 9000));
  const d = new Date();
  const local = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  $("woMeta").textContent = `Report ${wo}  ·  ${local}`;
  let body = step.text.replace(/⚠️[^\n]*/g, "").trim(); // safety line shown separately
  $("fixBody").innerHTML = formatFix(body);
  $("sources").innerHTML = step.sources
    .map((s) => `<span class="chip">${esc(s.section)} · p.${esc(s.page)}</span>`).join("");
  setGauge(gaugeFix, step.confidence, "");
  $("diagram").innerHTML = '<div class="loading">rendering manual page…</div>';
  $("diagramCaption").textContent = "";
  try {
    const ill = await api("/api/illustrate", { session_id: SESSION_ID });
    $("diagram").innerHTML = ill.images.map((u) => `<img src="${esc(u)}" alt="manual diagram" />`).join("");
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
    setZone(zoneOf(step.text));   // the camera follows the part being asked about
    $("answerInput").disabled = false;
    $("answerInput").focus();
  } else {
    $("ledScan").classList.remove("blink");
    $("fixTitle").textContent = step.sources && step.sources.length ? "Diagnosis" : "Not in the manual";
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
  $("startError").textContent = "";
  const startZone = zoneOf(full) || document.querySelector(".zone.active")?.dataset.zone || "engine";
  try {
    // Kick the request off, run the cluster self-test sweep while it's in flight.
    const pending = api("/api/start", { problem: full, car: $("carSelect").value });
    show("screen-interview");
    $("answerInput").disabled = true; // no session yet — enabled when the first question lands
    $("chatLog").innerHTML = "";
    setMinis(0, "—");
    $("ledScan").classList.add("blink");
    bubble("user", esc(full));
    ZONE = null;
    setZone(startZone, 2.2);
    const t = thinking();
    setScanning(gaugeMain);
    const step = await pending;
    t.remove();
    SESSION_ID = step.session_id;
    handleStep(step);
  } catch (e) {
    show("screen-start");
    showroom("focus", "hero");
    $("startError").textContent = "Couldn't start: " + e.message;
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
  setGauge(gaugeMain, 0, "");
  ZONE = null;
  $("zoneTag").textContent = "";
  document.querySelectorAll(".zone.active").forEach((z) => z.classList.remove("active"));
  show("screen-start");
  showroom("focus", "hero", 2);
}

/* ---------- the car on the stage ---------- */
let CAR_INFO = {};
function selectCar(id) {
  const info = CAR_INFO[id] || {};
  const name = $("carSelect").selectedOptions[0]?.textContent || id;
  $("carMake").textContent = info.make || name.split(" ")[0];
  $("carModel").textContent = info.model_name || name.split(" ")[1] || "car";
  $("carCode").textContent = info.code || "";
  showroom("loadCar", id);
  // paint swatches for this car
  const paints = info.paints || [];
  $("paintRow").innerHTML = paints.map((p) => {
    const chosen = p.colour === info.paint;
    return `<button class="paint${chosen ? " active" : ""}" data-colour="${esc(p.colour)}" style="background:${esc(p.colour)}" title="${esc(p.name)}" aria-label="${esc(p.name)} paint" aria-pressed="${chosen}"></button>`;
  }).join("");
}

/* ---------- picture quality ---------- */
/* Full quality is the default. Light mode is the person's choice and is remembered.
   The 3D scene reads the choice when it starts, so changing it reloads the page. */
function quality() {
  try { return localStorage.getItem("gearhead-quality") === "lite" ? "lite" : "full"; } catch (e) { return "full"; }
}
function setQuality(value) {
  try { localStorage.setItem("gearhead-quality", value); } catch (e) { return; }
  location.reload();
}
function initQuality() {
  const lite = quality() === "lite";
  $("qualityBtn").textContent = lite ? "Light mode" : "Full quality";
  $("qualityBtn").setAttribute("aria-label", lite
    ? "Picture quality: light mode. Switch to full quality (reloads the page)"
    : "Picture quality: full. Switch to light mode, which is faster but less sharp (reloads the page)");
  $("qualityBtn").addEventListener("click", () => setQuality(quality() === "lite" ? "full" : "lite"));
  window.addEventListener("showroom-slow", () => {
    const software = document.body.dataset.slow === "software";
    $("slowNote").innerHTML = (software
      ? "This browser is drawing 3D without the graphics card, so it is slow. Turn on graphics acceleration in the browser settings, or"
      : "The 3D view is running slowly on this machine. You can")
      + '<button type="button" id="slowLite">switch to light mode</button>';
    $("slowLite").addEventListener("click", () => setQuality("lite"));
  });
}

/* ---------- init ---------- */
(async function init() {
  initQuality();
  gaugeMain = buildGauge($("gauge"));
  gaugeFix = buildGauge($("gaugeFix"));
  setGauge(gaugeMain, 0, "");
  setGauge(gaugeFix, 0, "");

  try {
    const cars = await (await fetch("/api/cars")).json();
    $("carSelect").innerHTML = cars.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join("");
  } catch (e) { /* ignore */ }
  try { CAR_INFO = await (await fetch("/static/cars/cars.json", { cache: "no-store" })).json(); } catch (e) { /* stand-in car */ }
  selectCar($("carSelect").value || "nissan-patrol-y61");
  $("carSelect").addEventListener("change", (e) => selectCar(e.target.value));

  // engine badge: which brain is under the hood (local Ollama vs Claude API)
  try {
    const st = await (await fetch("/api/status")).json();
    $("engineText").innerHTML = st.local
      ? `<span class="hot">${esc(st.model)}</span> · runs on this machine`
      : `<span class="hot">${esc(st.model)}</span>`;
  } catch (e) { $("engineText").textContent = "Ready"; }

  // zone buttons: the camera flies to that part of the car, and an example symptom is filled in
  $("zoneRow").addEventListener("click", (e) => {
    const z = e.target.closest(".zone");
    if (!z) return;
    const wasActive = z.classList.contains("active");
    document.querySelectorAll(".zone").forEach((o) => { o.classList.remove("active"); o.setAttribute("aria-pressed", "false"); });
    if (wasActive) { showroom("focus", "hero"); return; }
    z.classList.add("active");
    z.setAttribute("aria-pressed", "true");
    showroom("focus", z.dataset.zone);
    if (!$("problemInput").value.trim() || $("problemInput").dataset.example) {
      $("problemInput").value = z.dataset.fill;
      $("problemInput").dataset.example = "1";
    }
  });
  $("problemInput").addEventListener("input", () => { delete $("problemInput").dataset.example; });

  $("paintRow").addEventListener("click", (e) => {
    const swatch = e.target.closest(".paint");
    if (!swatch) return;
    document.querySelectorAll(".paint").forEach((o) => { o.classList.remove("active"); o.setAttribute("aria-pressed", "false"); });
    swatch.classList.add("active");
    swatch.setAttribute("aria-pressed", "true");
    showroom("setPaint", swatch.dataset.colour);
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
  // Enter starts; Shift+Enter makes a new line. The box grows with the text.
  $("problemInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); startDiagnosis(); }
  });
  const grow = () => { const box = $("problemInput"); box.style.height = "auto"; box.style.height = box.scrollHeight + "px"; };
  $("problemInput").addEventListener("input", grow);
  $("zoneRow").addEventListener("click", () => setTimeout(grow, 0));
  $("resetBtn").addEventListener("click", reset);
})();
