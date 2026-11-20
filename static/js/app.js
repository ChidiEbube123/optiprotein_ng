/* OptiProtein NG front end. One form per page; every input carries data-key = API field name. */
const PAGE = document.body.dataset.page;
const REQUIRED = (document.body.dataset.required || "").split(",").filter(Boolean);
const form = document.getElementById("main-form");

const naira = v => "₦" + Math.round(Number(v || 0)).toLocaleString("en-NG");
const nairaShort = v => {
  v = Number(v || 0);
  if (Math.abs(v) >= 1e9) return "₦" + (v / 1e9).toFixed(2) + "bn";
  if (Math.abs(v) >= 1e6) return "₦" + (v / 1e6).toFixed(1) + "m";
  if (Math.abs(v) >= 1e3) return "₦" + Math.round(v / 1e3) + "k";
  return naira(v);
};
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const $ = id => document.getElementById(id);

async function post(url, payload) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (!res.ok) throw new Error("Request failed (" + res.status + ")");
  return res.json();
}

/* ---------- Form helpers ---------- */
function inputsFor(key) { return form ? [...form.querySelectorAll(`[data-key="${key}"]`)] : []; }
function fieldOf(el) { return el.closest(".field") || el.closest(".check"); }

function readForm() {
  const out = {};
  form.querySelectorAll("[data-key]").forEach(el => {
    const k = el.dataset.key, t = el.dataset.type;
    if (el.type === "radio") { if (el.checked) out[k] = el.value; return; }
    if (el.type === "checkbox") { out[k] = el.checked; return; }
    let v = el.value.trim();
    if (v === "") return;
    if (t === "int") v = parseInt(v, 10);
    else if (t === "float") v = parseFloat(v);
    else if (t === "bool") v = v === "true";
    out[k] = v;
  });
  return out;
}

function setValue(key, value) {
  const els = inputsFor(key);
  if (!els.length) return false;
  els.forEach(el => {
    if (el.type === "radio") el.checked = String(el.value) === String(value);
    else if (el.type === "checkbox") el.checked = !!value;
    else if (el.tagName === "SELECT") {
      const want = String(value).toLowerCase();
      const opt = [...el.options].find(o => o.value.toLowerCase() === want || o.text.toLowerCase() === want);
      if (opt) el.value = opt.value;
      else if (key === "channel" || key === "menu_type") return;
    } else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  return true;
}

function mark(key, cls) {
  inputsFor(key).forEach(el => { const f = fieldOf(el); if (f) { f.classList.remove("heard", "needed", "invalid"); if (cls) f.classList.add(cls); } });
}

function clearErrors() {
  form.querySelectorAll(".field-error").forEach(e => e.remove());
  form.querySelectorAll(".invalid").forEach(f => f.classList.remove("invalid"));
}

function validate() {
  clearErrors();
  const data = readForm();
  let first = null;
  const fail = (key, msg) => {
    const el = inputsFor(key)[0]; const f = el && fieldOf(el); if (!f) return;
    f.classList.remove("needed"); f.classList.add("invalid");
    const p = document.createElement("p"); p.className = "field-error"; p.textContent = msg; f.appendChild(p);
    first = first || el;
  };
  REQUIRED.forEach(k => { if (data[k] === undefined || data[k] === "") fail(k, "Add this to continue."); });
  form.querySelectorAll("input[type=number]").forEach(el => {
    if (!el.value || el.closest(".invalid")) return;
    const v = parseFloat(el.value);
    if (el.min !== "" && v < +el.min) fail(el.dataset.key, `Must be at least ${el.min}.`);
    else if (el.max !== "" && v > +el.max) fail(el.dataset.key, `Must be ${el.max} or less.`);
  });
  if (first) first.focus();
  return !first;
}

/* sliders show their value */
document.querySelectorAll('input[type=range]').forEach(r => {
  const out = document.querySelector(`output[for="${r.id}"]`);
  const show = () => { if (out) out.textContent = (r.dataset.key === "beef_price_shock_pct" && +r.value > 0 ? "+" : "") + r.value + "%"; };
  r.addEventListener("input", show); show();
});
/* editing a field removes its "from your text" mark */
form?.addEventListener("input", e => { const f = e.target.closest?.(".field"); if (f && e.isTrusted) f.classList.remove("heard", "needed"); });

/* ---------- Brief (intent router) ---------- */
const FIELD_LABELS = { corridor_or_city: "area", age: "age", health_goal: "health goal", max_budget_ngn: "budget per meal", menu_type: "kitchen type",
  weekly_demand_kg: "weekly volume", has_cold_chain: "storage", pilot_budget_ngn: "pilot budget", monthly_capacity_tons: "monthly supply",
  beef_price_shock_pct: "beef price change", substitution_pct: "beef replaced", max_calories: "calorie limit" ,max_calories: "calorie limit", customer_demographic: "guest age", beef_price_ngn: "beef price", sku_cost_ngn: "dry product price", hydration_ratio: "water ratio", min_margin_pct: "minimum margin", channel: "channel" };
const ROUTES = { restaurant: "/restaurant/", customer: "/customer/", strategist: "/" };
const PAGE_ROLE = { restaurant: "restaurant", customer: "customer", opportunity: "strategist" };

function applyBrief(parsed, found) {
  if (!form) return [];
  const applied = [];
  found.forEach(k => { if (k !== "role" && setValue(k, parsed[k])) { mark(k, "heard"); applied.push(k); } });
  const missing = REQUIRED.filter(k => readForm()[k] === undefined || readForm()[k] === "");
  missing.forEach(k => mark(k, "needed"));
  const box = $("brief-result");
  box.hidden = false;
  const heard = applied.map(k => FIELD_LABELS[k] || k);
  if (!applied.length) {
    box.className = "brief-result warn";
    box.textContent = "We couldn't pick anything out of that. Try adding a place, a number, or what you want to do.";
  } else if (missing.length) {
    box.className = "brief-result warn";
    box.textContent = `Filled in: ${heard.join(", ")}. Still needed: ${missing.map(k => FIELD_LABELS[k] || k).join(", ")}.`;
    inputsFor(missing[0])[0]?.focus();
  } else {
    box.className = "brief-result";
    box.textContent = `Filled in: ${heard.join(", ")}. Running it now.`;
    form.requestSubmit();
  }
  return applied;
}

async function runBrief(text) {
  text = text.trim();
  if (!text) { $("brief-input").focus(); return; }
  const btn = $("brief-submit"); btn.disabled = true; btn.textContent = "Reading…";
  try {
    const data = await post("/api/parse-intent/", { prompt: text });
    const role = data.parsed.role;
    if (role && PAGE_ROLE[PAGE] !== role) {
      try { sessionStorage.setItem("brief", JSON.stringify({ text, parsed: data.parsed, found: data.found })); } catch (e) {}
      window.location.href = ROUTES[role];
      return;
    }
    applyBrief(data.parsed, data.found);
  } catch (err) {
    const box = $("brief-result"); box.hidden = false; box.className = "brief-result warn"; box.textContent = "Couldn't read that right now. Fill in the form directly.";
  } finally { btn.disabled = false; btn.textContent = "Fill the form"; }
}
$("brief-form").addEventListener("submit", e => { e.preventDefault(); runBrief($("brief-input").value); });
document.querySelectorAll("[data-example]").forEach(b => b.addEventListener("click", () => { $("brief-input").value = b.dataset.example; runBrief(b.dataset.example); }));
/* ---------- Voice sheet: long-form dictation, then an AI model fills the form ---------- */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const VOICE_HINTS = {
  customer: "Say where you are, your age, what you're managing (blood pressure, sugar, cholesterol, weight) and the most you'll pay for a meal.",
  restaurant: "Describe your kitchen: the area, what kind of place it is, how much beef you use a week, your storage, and what you pay for beef.",
  opportunity: "Tell us your launch budget, how much you can supply each month, what you expect beef prices to do, and which channel you care about.",
};
const V = { rec: null, state: "idle", opener: null, secs: 0, tick: null };
const vEl = id => document.getElementById(id);

function vSetState(state, label) {
  V.state = state;
  vEl("v-meter").dataset.state = state;
  vEl("v-status").textContent = label || ({ listening: "Listening", paused: "Paused", busy: "Reading what you said", idle: SR ? "Ready" : "Type or paste" }[state]);
  vEl("v-toggle").textContent = state === "listening" ? "Pause" : "Resume";
  vEl("v-toggle").hidden = !SR;
  clearInterval(V.tick);
  if (state === "listening") V.tick = setInterval(() => { V.secs++; vEl("v-time").textContent = Math.floor(V.secs / 60) + ":" + String(V.secs % 60).padStart(2, "0"); }, 1000);
}
function vError(msg) { const e = vEl("v-error"); e.hidden = !msg; e.textContent = msg || ""; }

function vStart() {
  if (!SR) return;
  vError("");
  const rec = new SR(); V.rec = rec;
  rec.lang = "en-NG"; rec.continuous = true; rec.interimResults = true;
  rec.onresult = e => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const t = e.results[i][0].transcript;
      if (e.results[i].isFinal) vEl("v-text").value = (vEl("v-text").value.trim() + " " + t.trim()).trim() + " ";
      else interim += t;
    }
    vEl("v-interim").textContent = interim;
    vEl("v-text").scrollTop = vEl("v-text").scrollHeight;
  };
  rec.onerror = e => {
    if (e.error === "no-speech" || e.error === "aborted") return;
    V.state = "paused";
    vError(e.error === "not-allowed" || e.error === "service-not-allowed"
      ? "Microphone is blocked. Allow it in your browser's address bar, or type below instead."
      : e.error === "network" ? "Speech service unreachable. Check your connection, or type below instead."
      : "Voice stopped unexpectedly. Tap Resume or type below.");
    vSetState("paused");
  };
  rec.onend = () => { if (V.state === "listening" && V.rec === rec) { try { vStart(); } catch (err) { vSetState("paused"); } } };  // browsers end after silence; keep going
  try { rec.start(); vSetState("listening"); } catch (err) { vSetState("paused"); }
}
function vStop() { const r = V.rec; V.rec = null; if (r) { try { r.stop(); } catch (e) {} } vEl("v-interim").textContent = ""; }

function openVoice(opener) {
  V.opener = opener || null; V.secs = 0; vEl("v-time").textContent = "0:00";
  vEl("v-text").value = ""; vEl("v-interim").textContent = ""; vError("");
  vEl("v-hint").textContent = VOICE_HINTS[PAGE] || VOICE_HINTS.customer;
  vEl("voice").hidden = false; document.body.classList.add("voice-open");
  if (SR) { vSetState("listening"); vStart(); }
  else { vSetState("idle"); vError("Voice isn't supported in this browser, so type or paste what you want to say."); vEl("v-text").focus(); }
}
function closeVoice() {
  vStop(); vSetState("idle");
  vEl("voice").hidden = true; document.body.classList.remove("voice-open");
  V.opener?.focus();
}
async function fillFromVoice() {
  const text = (vEl("v-text").value + " " + vEl("v-interim").textContent).trim();
  if (text.length < 3) { vError("Say or type something first."); return; }
  vStop(); vError(""); vSetState("busy");
  vEl("v-fill").disabled = true;
  try {
    const d = await post("/api/ai-fill/", { transcript: text, page: PAGE });
    if (!d.found.length) { vSetState("paused", "Nothing to fill yet"); vError("We couldn't find anything for this form in that. Add more detail, then try again."); return; }
    closeVoice();
    $("brief-input").value = text.length > 140 ? text.slice(0, 137) + "…" : text;
    applyBrief(d.parsed, d.found);
    if (d.note) $("brief-result").textContent += " " + d.note;
  } catch (err) {
    vSetState("paused", "Couldn't reach the server"); vError("Something went wrong sending that. Your text is still here, so try again.");
  } finally { vEl("v-fill").disabled = false; }
}

$("mic-btn").addEventListener("click", e => openVoice(e.currentTarget));
$("voice-btn")?.addEventListener("click", e => openVoice(e.currentTarget));
$("v-fill").addEventListener("click", fillFromVoice);
$("v-cancel").addEventListener("click", closeVoice);
$("v-close").addEventListener("click", closeVoice);
$("v-clear").addEventListener("click", () => { vEl("v-text").value = ""; vEl("v-interim").textContent = ""; vError(""); vEl("v-text").focus(); });
$("v-toggle").addEventListener("click", () => { if (V.state === "listening") { vStop(); vSetState("paused"); } else vStart(); });
$("voice").addEventListener("mousedown", e => { if (e.target === $("voice")) closeVoice(); });
document.addEventListener("keydown", e => {
  if ($("voice").hidden) return;
  if (e.key === "Escape") { closeVoice(); return; }
  if (e.key === "Tab") {  // keep focus inside the sheet
    const f = [...$("voice").querySelectorAll("button:not([hidden]):not(:disabled), textarea")];
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
});

/* ---------- Shared results plumbing ---------- */
function showResults(on) { const e = $("results-empty"), b = $("results-body"); if (e) e.hidden = on; if (b) b.hidden = !on; }
async function submitWith(btn, fn) {
  const label = btn.textContent; btn.disabled = true; btn.textContent = "Working…";
  try { await fn(); } catch (err) { alert(err.message + ". Check your connection and try again."); }
  finally { btn.disabled = false; btn.textContent = label; }
}
$("reset-btn")?.addEventListener("click", () => {
  form.reset(); clearErrors();
  form.querySelectorAll(".heard,.needed").forEach(f => f.classList.remove("heard", "needed"));
  form.querySelectorAll("input[type=range]").forEach(r => r.dispatchEvent(new Event("input")));
  if (PAGE === "opportunity") loadOpportunities(); else showResults(false);
});

/* ---------- Mode 1: launch planner ---------- */
let plan = null, selectedId = null;

async function loadOpportunities() {
  const data = await post("/api/opportunities/", readForm());
  plan = data;
  const ch = $("f-channel");
  if (ch && ch.options.length === 1) data.channels.forEach(c => ch.add(new Option(c, c)));
  const p = data.portfolio;
  $("plan-summary").innerHTML = `
    <div><b>${nairaShort(p.total_risk_adjusted_90d_profit_ngn)}</b><span>Expected profit in 90 days</span></div>
    <div><b>${p.total_target_outlets}</b><span>Outlets to win</span></div>
    <div><b>${p.total_monthly_tons.toFixed(1)} t</b><span>Dry mince per month</span></div>
    <div><b>${p.budget_utilization_pct}%</b><span>Of launch budget used</span></div>`;
  $("portfolio").innerHTML = p.feasible ? p.selected_corridors.map(c => `
    <div class="pilot"><h3>${esc(c.name)}</h3><p>${esc(c.channel)}, ${esc(c.state)} · ${c.target_pilot_outlets} outlets · ${c.monthly_dry_tons.toFixed(1)} t/month</p><b>${nairaShort(c.risk_adjusted_90d_profit_ngn)} in 90 days</b></div>`).join("")
    : `<p class="no-pilot">No corridor fits these limits. Raise the budget or supply, or lower the minimum margin.</p>`;
  const picked = new Set(p.selected_corridors.map(c => c.id));
  const max = 100;
  $("corridor-body").innerHTML = data.corridors.map(c => `
    <tr tabindex="0" data-id="${c.id}">
      <td class="name"><span class="rank">${c.rank}</span><b>${esc(c.lga)}</b>${picked.has(c.id) ? '<span class="picked">Pilot</span>' : ""}<small>${esc(c.channel)} · ${esc(c.state)}</small></td>
      <td><div class="range"><b>${Math.round(c.opportunity_score)}</b><div class="range-bar" role="img" aria-label="Score ${c.score_ci_low} to ${c.score_ci_high}"><i style="left:${c.score_ci_low / max * 100}%;width:${(c.score_ci_high - c.score_ci_low) / max * 100}%"></i><u style="left:${c.opportunity_score / max * 100}%"></u></div></div></td>
      <td class="num">${naira(c.protein_spread_ngn)}</td>
      <td class="num">${c.monthly_dry_tons.toFixed(1)}</td>
      <td class="num">${nairaShort(c.cac_total_ngn)}</td>
      <td><span class="conf ${esc(c.data_confidence)}">${esc(c.data_confidence)}</span></td>
    </tr>`).join("");
  if (!data.corridors.length) { $("corridor-body").innerHTML = `<tr><td colspan="6">No corridors for this channel.</td></tr>`; $("why").innerHTML = ""; return; }
  if (!data.corridors.some(c => c.id === selectedId)) selectedId = data.corridors[0].id;
  renderWhy();
}

function renderWhy() {
  const c = plan.corridors.find(x => x.id === selectedId); if (!c) return;
  document.querySelectorAll("#corridor-body tr").forEach(r => r.classList.toggle("is-selected", +r.dataset.id === selectedId));
  const rows = Object.entries(c.shap_breakdown).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  const m = Math.max(...rows.map(r => Math.abs(r[1])), 1);
  $("why").innerHTML = `<h3>Why ${esc(c.lga)} scores ${Math.round(c.opportunity_score)}</h3>
    <p class="muted">Points each factor adds to or takes from the base score. Cluster: ${esc(c.cluster_label)}. ${esc(c.data_source_tag)}.</p>
    <div class="drivers">${rows.map(([k, v]) => `<div class="driver"><span>${esc(k)}</span><div class="driver-track"><i class="${v >= 0 ? "pos" : "neg"}" style="width:${Math.abs(v) / m * 50}%"></i></div><output>${v > 0 ? "+" : ""}${v}</output></div>`).join("")}</div>`;
}
$("corridor-body")?.addEventListener("click", e => { const r = e.target.closest("tr[data-id]"); if (r) { selectedId = +r.dataset.id; renderWhy(); } });
$("corridor-body")?.addEventListener("keydown", e => { if (e.key === "Enter") e.target.click(); });

if (PAGE === "opportunity") {
  form.addEventListener("submit", e => { e.preventDefault(); if (validate()) submitWith(form.querySelector("[type=submit]"), loadOpportunities); });
}

/* ---------- Mode 2: kitchen to supplier ---------- */
async function runRestaurant() {
  const d = await post("/api/match-supplier/", readForm());
  const c = d.recipe_card;
  if (!c) { showResults(false); return; }
  showResults(true);
  $("recipe-card").innerHTML = `
    <header><h2>${esc(c.title)}</h2><span>${esc(c.menu_type)} · ${c.blend_pct}% replacement</span></header>
    <div class="saving"><b>${naira(c.monthly_saved_ngn)} a month</b><span>saved by swapping ${c.blend_pct}% of your beef (${naira(c.annual_naira_saved)} a year)</span></div>
    <dl class="facts">
      <div><dt>Supplier</dt><dd>${esc(c.selected_supplier)}, ${esc(c.supplier_city)}</dd></div>
      <div><dt>Hydrated mince cost</dt><dd>${naira(c.landed_hydrated_cost_ngn_kg)}/kg vs beef ${naira(c.local_beef_cost_ngn_kg)}/kg${d.beef_price_is_market_default ? " (market price)" : ""}</dd></div>
      <div><dt>Saved per kg replaced</dt><dd>${naira(c.naira_saved_per_kg)}</dd></div>
      <div><dt>Saved per 100 portions</dt><dd>${naira(c.naira_saved_per_100_portions)}</dd></div>
      <div><dt>Carbon avoided</dt><dd>${Math.round(c.weekly_co2e_avoided_kg).toLocaleString()} kg CO₂e a week</dd></div>
      <div><dt>Storage</dt><dd>${esc(c.cold_chain_advantage)}</dd></div>
    </dl>
    <div class="steps"><p><b>Hydrate:</b> ${esc(c.hydration_protocol)}</p><p><b>Season with:</b> ${esc(c.recommended_spices)}</p></div>`;
  $("hub-list").innerHTML = d.ranked_hubs.map((h, i) => `
    <article class="${i === 0 ? "top" : ""}">
      <div><h3>${esc(h.name)}</h3>
        <p class="meta">${esc(h.city)}, ${esc(h.state)} · ${h.distance_km} km · ${h.lead_time_days} day lead time · ${esc(h.contact_phone)}</p>
        <p class="meta">${h.nafdac ? '<span class="flag ok">NAFDAC registered</span>' : '<span class="flag warn">Not NAFDAC registered</span>'}${h.capacity_ok ? "" : '<span class="flag warn">May not cover your volume</span>'}</p></div>
      <div class="price"><b>${naira(h.landed_hydrated_ngn_kg)}/kg</b><span class="meta">${h.savings_vs_beef_pct}% below beef</span></div>
    </article>`).join("");
  $("dish-list").innerHTML = d.top_dishes.map(x => `
    <article><h3>${esc(x.dish_name)}</h3><p>${esc(x.blend_ratio)} blend · ${esc(x.spices)}</p><p>${esc(x.texture_note)}</p><p class="save">Saves ${naira(x.naira_saved_per_100_portions)} per 100 portions</p></article>`).join("");
}
if (PAGE === "restaurant") {
  form.addEventListener("submit", e => { e.preventDefault(); if (validate()) submitWith(form.querySelector("[type=submit]"), runRestaurant); });
}

/* ---------- Mode 3: diner ---------- */
async function runCustomer() {
  const payload = readForm();
  const d = await post("/api/match-customer/", payload);
  showResults(true);
  $("header-signal-count").textContent = d.total_demand_signals;
  $("results-title").textContent = "Best matches in " + (payload.corridor_or_city || "your area");
  $("results-sub").textContent = d.matches.length + " restaurants ranked for you";
  $("match-list").innerHTML = d.matches.map(r => `
    <li>
      <div class="match-score">${r.match_pct}<small>match</small></div>
      <div class="match-main"><h3>${esc(r.name)}</h3><p class="dish">${esc(r.signature_dish)}</p><p class="where">${esc(r.address)}</p>
        <div class="reasons">${r.reasons.map(x => `<span>${esc(x)}</span>`).join("")}</div></div>
      <div class="match-facts"><b class="${r.within_budget ? "" : "over"}">${naira(r.dish_price_ngn)}</b><span>${r.calories} kcal</span><span>${r.cholesterol_reduction_pct}% less cholesterol</span><span>Rated ${r.rating}</span></div>
    </li>`).join("");
  $("signal-feed").innerHTML = d.recent_signals.map(s => `<li><b>${esc(s.city_or_lga)}</b><span>${esc(s.health_goal)} · up to ${naira(s.max_budget_ngn)}</span><time>${esc(s.created_at)}</time></li>`).join("");
}
if (PAGE === "customer") {
  form.addEventListener("submit", e => { e.preventDefault(); if (validate()) submitWith(form.querySelector("[type=submit]"), runCustomer); });


  /* read the top matches aloud */
  if (window.speechSynthesis) {
    const sp = $("speak-btn"); sp.hidden = false;
    sp.addEventListener("click", () => {
      if (speechSynthesis.speaking) { speechSynthesis.cancel(); sp.textContent = "Read aloud"; return; }
      const top = [...document.querySelectorAll("#match-list li")].slice(0, 3).map((li, i) =>
        `Number ${i + 1}: ${li.querySelector("h3").textContent}. ${li.querySelector(".dish").textContent}, ${li.querySelector(".match-facts b").textContent.replace("₦", "").replace(",", "")} naira.`);
      const u = new SpeechSynthesisUtterance("Your top matches. " + top.join(" "));
      u.lang = "en-NG"; u.onend = u.onerror = () => { sp.textContent = "Read aloud"; };
      sp.textContent = "Stop"; speechSynthesis.speak(u);
    });
  }
}

/* ---------- Boot ---------- */
window.addEventListener("DOMContentLoaded", () => {
  let brief = null;
  try { brief = JSON.parse(sessionStorage.getItem("brief") || "null"); sessionStorage.removeItem("brief"); } catch (e) {}
  if (PAGE === "opportunity") loadOpportunities().then(() => { if (brief) { $("brief-input").value = brief.text; applyBrief(brief.parsed, brief.found); } });
  else if (brief) { $("brief-input").value = brief.text; applyBrief(brief.parsed, brief.found); }
});