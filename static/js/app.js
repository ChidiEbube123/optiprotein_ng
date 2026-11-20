let shapChartInstance = null;

function formatNaira(val) { return "₦" + Math.round(Number(val||0)).toLocaleString("en-NG"); }

// Global Router logic
async function executeGlobalIntent(promptText) {
  if (!promptText.trim()) return;
  const btn = document.getElementById("command-submit-btn");
  btn.textContent = "Routing..."; btn.disabled = true;
  try {
    const res = await fetch("/api/parse-intent/", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: promptText })
    });
    const data = await res.json();
    sessionStorage.setItem('aiIntent', JSON.stringify(data.parsed));
    
    if (data.parsed.role === "restaurant" && window.location.pathname !== "/restaurant/") {
      window.location.href = "/restaurant/";
    } else if (data.parsed.role === "customer" && window.location.pathname !== "/customer/") {
      window.location.href = "/customer/";
    } else if (data.parsed.role === "strategist" && window.location.pathname !== "/") {
      window.location.href = "/";
    } else {
      applyIntentData(); // Same page, just apply
    }
  } finally {
    btn.textContent = "Run Router →"; btn.disabled = false;
  }
}

document.getElementById("command-submit-btn")?.addEventListener("click", () => {
  executeGlobalIntent(document.getElementById("command-input").value);
});

// Apply session intent data if present
function applyIntentData() {
  const intentStr = sessionStorage.getItem('aiIntent');
  if (!intentStr) return;
  const p = JSON.parse(intentStr);
  sessionStorage.removeItem('aiIntent');

  if (document.getElementById("ctrl-sku-cost") && p.sku_cost_ngn) {
    document.getElementById("ctrl-sku-cost").value = p.sku_cost_ngn;
    document.getElementById("ctrl-budget").value = p.pilot_budget_ngn || 10000000;
    if (typeof loadOpportunities === "function") loadOpportunities();
  }
  if (document.getElementById("rest-city") && p.corridor_or_city) {
    document.getElementById("rest-city").value = p.corridor_or_city;
    document.getElementById("rest-volume").value = p.weekly_demand_kg || 200;
    if (typeof runRestaurantMatch === "function") runRestaurantMatch();
  }
  if (document.getElementById("cust-city") && p.corridor_or_city) {
    document.getElementById("cust-city").value = p.corridor_or_city;
    document.getElementById("cust-age").value = p.age || 52;
    if (typeof runCustomerMatch === "function") runCustomerMatch();
  }
}

// ---------------- Page 1: Opportunities ----------------
async function loadOpportunities() {
  if (!document.getElementById("recalc-opp-btn")) return;
  const payload = {
    sku_cost_ngn: parseFloat(document.getElementById("ctrl-sku-cost").value),
    pilot_budget_ngn: parseFloat(document.getElementById("ctrl-budget").value),
    monthly_capacity_tons: parseFloat(document.getElementById("ctrl-capacity").value),
  };
  const res = await fetch("/api/opportunities/", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
  });
  const data = await res.json();
  
  // Table
  document.getElementById("corridors-tbody").innerHTML = data.corridors.map(c => `
    <tr>
      <td><strong>#${c.rank} ${c.lga}</strong><br><small>${c.state}</small></td>
      <td><span class="tag-pill">${c.cluster_label}</span></td>
      <td><strong>${c.opportunity_score}</strong> <small>(${c.score_ci_low}-${c.score_ci_high})</small></td>
    </tr>
  `).join("");

  // Knapsack
  const port = data.portfolio;
  document.getElementById("kpi-knapsack-profit").textContent = formatNaira(port.total_risk_adjusted_90d_profit_ngn);
  document.getElementById("knapsack-list").innerHTML = port.selected_corridors.map(c => `
    <div style="border:1px solid #A7F3D0; padding:10px; margin-bottom:8px; border-radius:6px; background:#ECFDF5;">
      <strong>${c.lga}</strong> - Profit: ${formatNaira(c.risk_adjusted_90d_profit_ngn)}
    </div>
  `).join("");

  // Chart (using top corridor)
  if (data.corridors.length > 0) {
    const c = data.corridors[0];
    const ctx = document.getElementById("shapChart").getContext("2d");
    if (shapChartInstance) shapChartInstance.destroy();
    shapChartInstance = new Chart(ctx, {
      type: "bar",
      data: {
        labels: Object.keys(c.shap_breakdown),
        datasets: [{ label: "SHAP pts", data: Object.values(c.shap_breakdown), backgroundColor: "#10B981" }]
      },
      options: { indexAxis: "y", responsive: true, maintainAspectRatio: false }
    });
  }
}
document.getElementById("recalc-opp-btn")?.addEventListener("click", loadOpportunities);

// ---------------- Page 2: Restaurant ----------------
async function runRestaurantMatch(e) {
  if (e) e.preventDefault();
  if (!document.getElementById("restaurant-form")) return;
  const payload = {
    corridor_or_city: document.getElementById("rest-city").value,
    weekly_demand_kg: parseFloat(document.getElementById("rest-volume").value),
    has_cold_chain: document.getElementById("rest-cold-chain").value === "true"
  };
  const res = await fetch("/api/match-supplier/", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
  });
  const data = await res.json();
  const rc = data.recipe_card;
  
  document.getElementById("recipe-body").innerHTML = `
    <h3>${rc.title}</h3>
    <p><strong>Supplier:</strong> ${rc.selected_supplier}</p>
    <p><strong>Landed Cost:</strong> ₦${Math.round(rc.landed_hydrated_cost_ngn_kg)}/kg vs Beef ₦${rc.local_beef_cost_ngn_kg}</p>
    <p><strong>Protocol:</strong> ${rc.hydration_protocol}</p>
    <p><strong>Save per 100 meals:</strong> ${formatNaira(rc.naira_saved_per_100_portions)}</p>
  `;
  document.getElementById("supplier-hubs-list").innerHTML = data.ranked_hubs.map(h => `
    <div class="rest-card"><strong>${h.name} (${h.city})</strong><br><small>Hydrated: ₦${Math.round(h.landed_hydrated_ngn_kg)}/kg</small></div>
  `).join("");
}
document.getElementById("restaurant-form")?.addEventListener("submit", runRestaurantMatch);

// ---------------- Page 3: Customer ----------------
async function runCustomerMatch(e) {
  if (e) e.preventDefault();
  if (!document.getElementById("customer-form")) return;
  const payload = {
    corridor_or_city: document.getElementById("cust-city").value,
    age: parseInt(document.getElementById("cust-age").value),
    health_goal: document.getElementById("cust-goal").value,
    log_signal: !!e // only log if user clicked submit explicitly
  };
  const res = await fetch("/api/match-customer/", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
  });
  const data = await res.json();
  
  document.getElementById("customer-restaurants-list").innerHTML = data.matches.map(r => `
    <div class="rest-card">
      <strong>${r.name}</strong> <span class="tag-pill">${r.match_pct}% Match</span><br>
      <small>${r.signature_dish} - ₦${r.dish_price_ngn}</small><br>
      <small class="text-emerald">Tags: ${r.health_tags.join(", ")}</small>
    </div>
  `).join("");

  document.getElementById("signal-feed-list").innerHTML = data.recent_signals.map(s => `
    <li><strong>${s.city_or_lga}</strong> <span>${s.health_goal}</span></li>
  `).join("");
}
document.getElementById("customer-form")?.addEventListener("submit", runCustomerMatch);

window.addEventListener("DOMContentLoaded", () => {
  applyIntentData();
  if (document.getElementById("recalc-opp-btn")) loadOpportunities();
  if (document.getElementById("restaurant-form")) runRestaurantMatch();
  if (document.getElementById("customer-form")) runCustomerMatch();
});
