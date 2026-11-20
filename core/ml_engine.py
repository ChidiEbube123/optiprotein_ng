import math
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

BASELINE = {
    "protein_spread": 5600.0, "outlet_density": 18.0, "margin_squeeze": 0.42,
    "age_45_plus": 24.0, "cold_chain_deficit": 55.0, "hub_distance": 120.0, "live_signals": 2.0
}
FEATURE_WEIGHTS = {
    "protein_spread": 22.0, "outlet_density": 18.0, "margin_squeeze": 16.0,
    "age_45_plus": 15.0, "cold_chain_advantage": 13.0, "hub_proximity": 9.0, "live_demand_boost": 7.0
}
CLUSTER_LABELS = {0: "Margin-Squeezed QSRs", 1: "Cold-Chain Mass Caterers", 2: "Health & Institutional"}

def compute_protein_and_carbon_metrics(local_beef_price_ngn, avg_menu_price_ngn, dry_sku_cost_ngn=2400.0, hydration_ratio=3.0, beef_shock_pct=0.0, substitution_pct=0.50, weekly_volume_kg=100.0):
    shocked_beef = local_beef_price_ngn * (1.0 + beef_shock_pct / 100.0)
    hydrated_cost = dry_sku_cost_ngn / max(hydration_ratio, 1.0)
    spread = max(0.0, shocked_beef - hydrated_cost)
    squeeze = shocked_beef / max(avg_menu_price_ngn, 500.0)
    co2e_avoided = (27.0 - 2.1) * substitution_pct
    return {
        "shocked_beef_price_ngn": shocked_beef, "hydrated_cost_per_kg_ngn": hydrated_cost,
        "protein_spread_ngn": spread, "pre_adoption_margin_squeeze": squeeze,
        "weekly_savings_ngn": weekly_volume_kg * (shocked_beef - (substitution_pct*hydrated_cost + (1-substitution_pct)*shocked_beef)),
        "annual_savings_ngn": weekly_volume_kg * (shocked_beef - (substitution_pct*hydrated_cost + (1-substitution_pct)*shocked_beef)) * 52,
        "weekly_co2e_avoided_kg": weekly_volume_kg * co2e_avoided,
        "annual_co2e_avoided_tons": (weekly_volume_kg * co2e_avoided * 52) / 1000.0
    }

def _run_monte_carlo(base_score, profit, conf, seed=42):
    rng = np.random.default_rng(seed)
    mult = 1.0 if conf == "High" else 2.2
    comp = np.clip(0.45*rng.normal(1.0, 0.08*mult, 500) + 0.35*rng.normal(1.0, 0.10*mult, 500) + 0.20*rng.normal(1.0, 0.06*mult, 500), 0.35, 1.75)
    scores = np.clip(base_score * comp, 5.0, 99.5)
    profits = np.maximum(0.0, (profit * 3.0) * comp)
    return {
        "score_ci_low": round(float(np.percentile(scores, 5)), 1),
        "score_ci_high": round(float(np.percentile(scores, 95)), 1),
        "ci_width": round(float(np.percentile(scores, 95) - np.percentile(scores, 5)), 1),
        "risk_adjusted_90d_profit_ngn": round(float(np.percentile(profits, 50)) * (1.0 - min(0.35, max(1.0, float(np.percentile(scores, 95) - np.percentile(scores, 5)))/100*0.85)), 0)
    }

def evaluate_all_corridors(corridors_qs, demand_counts_by_area, dry_sku_cost_ngn=2400.0, hydration_ratio=3.0, beef_shock_pct=0.0, substitution_pct=0.50, pilot_budget_ngn=10_000_000.0, monthly_capacity_tons=12.0, min_margin_pct=22.0):
    evaluated = []
    dry_cogs = 1580.0
    margin_pct = max(0.0, ((dry_sku_cost_ngn - dry_cogs) / max(dry_sku_cost_ngn, 1.0)) * 100.0)
    for idx, c in enumerate(corridors_qs):
        econ = compute_protein_and_carbon_metrics(c.local_beef_price_ngn, c.avg_menu_price_ngn, dry_sku_cost_ngn, hydration_ratio, beef_shock_pct, substitution_pct, c.base_weekly_demand_tons * 1000)
        live = demand_counts_by_area.get(c.lga.lower().strip(), 0)
        shap = {
            "Protein Spread": round(float(np.clip(((econ["protein_spread_ngn"] - BASELINE["protein_spread"])/2800)*FEATURE_WEIGHTS["protein_spread"], -14, 22)), 1),
            "Outlet Density": round(float(np.clip(((c.outlet_density_per_km2 - BASELINE["outlet_density"])/16)*FEATURE_WEIGHTS["outlet_density"], -12, 18)), 1),
            "Margin Squeeze": round(float(np.clip(((econ["pre_adoption_margin_squeeze"] - BASELINE["margin_squeeze"])/0.18)*FEATURE_WEIGHTS["margin_squeeze"], -10, 16)), 1),
            "45+ Health": round(float(np.clip(((c.age_45_plus_share_pct - BASELINE["age_45_plus"])/12)*FEATURE_WEIGHTS["age_45_plus"], -10, 15)), 1),
            "Cold Chain": round(float(np.clip(((c.cold_chain_deficit_pct - BASELINE["cold_chain_deficit"])/28)*FEATURE_WEIGHTS["cold_chain_advantage"], -9, 13)), 1),
            "Hub Prox": round(float(np.clip(((BASELINE["hub_distance"] - c.nearest_hub_km)/140)*FEATURE_WEIGHTS["hub_proximity"], -8, 9)), 1),
            "Live Demand": round(float(np.clip((math.log1p(live)/math.log1p(8))*FEATURE_WEIGHTS["live_demand_boost"] - 1.5, -2, 12)), 1)
        }
        score = round(float(np.clip(52.0 + sum(shap.values()), 12.0, 98.5)), 1)
        tons = round(c.base_weekly_demand_tons * 4.33 * (1.0 + 0.03 * live), 2)
        profit = max(0.0, (tons*1000*dry_sku_cost_ngn) - (tons*1000*dry_cogs))
        mc = _run_monte_carlo(score, profit, c.data_confidence, seed=100+idx)
        evaluated.append({
            "id": c.id, "name": c.name, "lga": c.lga, "state": c.state, "channel": c.channel,
            "shocked_beef_price_ngn": econ["shocked_beef_price_ngn"], "hydrated_cost_ngn": econ["hydrated_cost_per_kg_ngn"],
            "protein_spread_ngn": econ["protein_spread_ngn"], "estimated_outlets": c.estimated_outlets,
            "target_pilot_outlets": max(8, int(round(c.estimated_outlets * 0.18))), "live_signals": live,
            "opportunity_score": score, "shap_breakdown": shap, "monthly_dry_tons": tons,
            "cac_total_ngn": max(8, int(round(c.estimated_outlets * 0.18))) * c.cac_per_outlet_ngn,
            "wholesale_margin_pct": round(margin_pct, 1), "annual_co2e_avoided_tons": econ["annual_co2e_avoided_tons"],
            "data_confidence": c.data_confidence, "data_source_tag": c.data_source_tag, **mc
        })

    if len(evaluated) >= 3:
        X = StandardScaler().fit_transform(np.array([[c["protein_spread_ngn"], c["opportunity_score"]] for c in evaluated]))
        labels = KMeans(n_clusters=3, random_state=42, n_init=10).fit_predict(X)
        for i, c in enumerate(evaluated): c["cluster_label"] = CLUSTER_LABELS[labels[i]]
    else:
        for c in evaluated: c["cluster_label"] = "Cluster 1"

    evaluated.sort(key=lambda x: x["opportunity_score"], reverse=True)
    for i, c in enumerate(evaluated): c["rank"] = i + 1

    eligible = [c for c in evaluated if c["wholesale_margin_pct"] >= min_margin_pct and c["cac_total_ngn"] <= pilot_budget_ngn and c["monthly_dry_tons"] <= monthly_capacity_tons]
    best_combo, best_prof = [], -1.0
    for i in range(len(eligible)):
        if eligible[i]["risk_adjusted_90d_profit_ngn"] > best_prof: best_prof, best_combo = eligible[i]["risk_adjusted_90d_profit_ngn"], [eligible[i]]
        for j in range(i+1, len(eligible)):
            if eligible[i]["cac_total_ngn"]+eligible[j]["cac_total_ngn"] <= pilot_budget_ngn and eligible[i]["monthly_dry_tons"]+eligible[j]["monthly_dry_tons"] <= monthly_capacity_tons:
                if eligible[i]["risk_adjusted_90d_profit_ngn"]+eligible[j]["risk_adjusted_90d_profit_ngn"] > best_prof:
                    best_prof, best_combo = eligible[i]["risk_adjusted_90d_profit_ngn"]+eligible[j]["risk_adjusted_90d_profit_ngn"], [eligible[i], eligible[j]]
    
    return {
        "corridors": evaluated,
        "portfolio": {
            "selected_corridors": best_combo, "total_cac_ngn": sum(c["cac_total_ngn"] for c in best_combo),
            "budget_utilization_pct": round(sum(c["cac_total_ngn"] for c in best_combo)/max(pilot_budget_ngn, 1)*100, 1),
            "total_monthly_tons": sum(c["monthly_dry_tons"] for c in best_combo),
            "total_risk_adjusted_90d_profit_ngn": sum(c["risk_adjusted_90d_profit_ngn"] for c in best_combo),
            "total_target_outlets": sum(c["target_pilot_outlets"] for c in best_combo),
            "total_annual_co2_avoided_tons": sum(c["annual_co2e_avoided_tons"] for c in best_combo),
            "feasible": len(best_combo) > 0
        }
    }

def match_suppliers_and_recipe(suppliers_qs, city_or_lga, weekly_demand_kg, menu_type, has_cold_chain, customer_demographic, local_beef_price_ngn, hydration_ratio):
    ranked = []
    for s in suppliers_qs:
        dist = 120.0
        if "lagos" in city_or_lga.lower() and s.city.lower() in ["ota", "abeokuta"]: dist = 40.0 if s.city.lower() == "ota" else 80.0
        freight = (dist * s.transport_rate_ngn_per_ton_km) / 1000.0
        landed = (s.wholesale_price_dry_ngn_kg + freight) / max(hydration_ratio, 1.0)
        ranked.append({
            "id": s.id, "name": s.name, "city": s.city, "state": s.state, "distance_km": dist,
            "wholesale_dry_ngn_kg": s.wholesale_price_dry_ngn_kg, "freight_ngn_kg": freight, "landed_hydrated_ngn_kg": landed,
            "savings_vs_beef_pct": round(((local_beef_price_ngn - landed) / local_beef_price_ngn) * 100, 1),
            "monthly_capacity_tons": s.monthly_capacity_tons, "contact_phone": s.contact_phone,
            "match_score": 100 - (dist/5)
        })
    ranked.sort(key=lambda x: x["match_score"], reverse=True)
    return {
        "ranked_hubs": ranked,
        "top_dishes": [
            {"dish_name": "Heart-Healthy Beef Stew", "blend_ratio": "50/50", "spices": "Locust beans, ginger, garlic", "naira_saved_per_100_portions": (local_beef_price_ngn - ranked[0]["landed_hydrated_ngn_kg"])*6.5, "texture_note": "Umami rich"},
            {"dish_name": "Suya Mince Wrap", "blend_ratio": "60/40", "spices": "Yaji spice, white pepper", "naira_saved_per_100_portions": (local_beef_price_ngn - ranked[0]["landed_hydrated_ngn_kg"])*7.8, "texture_note": "High moisture retention"}
        ],
        "recipe_card": {
            "title": "B2B Chef Conversion Protocol", "selected_supplier": ranked[0]["name"],
            "landed_hydrated_cost_ngn_kg": ranked[0]["landed_hydrated_ngn_kg"], "local_beef_cost_ngn_kg": local_beef_price_ngn,
            "naira_saved_per_100_portions": (local_beef_price_ngn - ranked[0]["landed_hydrated_ngn_kg"])*6.5,
            "annual_naira_saved": weekly_demand_kg * (local_beef_price_ngn - ranked[0]["landed_hydrated_ngn_kg"]) * 52,
            "weekly_co2e_avoided_kg": weekly_demand_kg * (27.0 - 2.1) * 0.5,
            "hydration_protocol": "1kg Dry + 2L Hot Water = 3kg Mince", "recommended_spices": "Locust beans, ginger, paprika",
            "cold_chain_advantage": "Ambient storage approved" if not has_cold_chain else "Hybrid mode available"
        }
    }

def match_customer_restaurants(restaurants_qs, city_or_lga, age, health_goal, max_budget_ngn):
    res = []
    for r in restaurants_qs:
        score = 50.0
        if city_or_lga.lower() in r.lga.lower() or city_or_lga.lower() in r.city.lower(): score += 30.0
        if r.dish_price_ngn <= max_budget_ngn: score += 20.0
        res.append({
            "id": r.id, "name": r.name, "lga": r.lga, "city": r.city, "state": r.state,
            "signature_dish": r.signature_dish, "dish_price_ngn": r.dish_price_ngn,
            "health_tags": r.health_tags.split(","), "rating": r.rating, "address": r.address,
            "match_pct": min(99, int(score))
        })
    res.sort(key=lambda x: x["match_pct"], reverse=True)
    return res[:6]
