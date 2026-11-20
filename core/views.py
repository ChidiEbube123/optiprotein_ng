import json
import re
import boto3
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import Corridor, SupplierHub, PartnerRestaurant, DemandSignal
from .ml_engine import evaluate_all_corridors, match_suppliers_and_recipe, match_customer_restaurants

# ==================== PAGE VIEWS ====================
def get_global_context():
    return {'total_signals': DemandSignal.objects.count()}

def page_opportunities(request):
    """Page 1: Market Opportunity & Knapsack Optimizer"""
    return render(request, 'opportunity.html', get_global_context())

def page_restaurant(request):
    """Page 2: Restaurant Matcher & Recipe Card"""
    return render(request, 'restaurant.html', get_global_context())

def page_customer(request):
    """Page 3: Customer Finder"""
    return render(request, 'customer.html', get_global_context())

# ==================== API ENDPOINTS ====================
@require_http_methods(["POST"])
@csrf_exempt
def api_opportunities(request):
    params = json.loads(request.body.decode('utf-8') or '{}')
    qs = Corridor.objects.all()
    counts = {r['city_or_lga'].lower().strip(): r['total'] for r in DemandSignal.objects.values('city_or_lga').annotate(total=Count('id'))}
    res = evaluate_all_corridors(
        qs, counts,
        dry_sku_cost_ngn=float(params.get('sku_cost_ngn', 2400.0)),
        hydration_ratio=float(params.get('hydration_ratio', 3.0)),
        beef_shock_pct=float(params.get('beef_price_shock_pct', 0.0)),
        substitution_pct=float(params.get('substitution_pct', 50.0)) / 100.0,
        pilot_budget_ngn=float(params.get('pilot_budget_ngn', 10000000.0)),
        monthly_capacity_tons=float(params.get('monthly_capacity_tons', 12.0)),
        min_margin_pct=float(params.get('min_margin_pct', 22.0))
    )
    res['total_demand_signals'] = DemandSignal.objects.count()
    return JsonResponse(res)

@require_http_methods(["POST"])
@csrf_exempt
def api_match_supplier(request):
    data = json.loads(request.body.decode('utf-8') or '{}')
    city = data.get('corridor_or_city', 'Surulere, Lagos')
    qs = SupplierHub.objects.all()
    c_qs = Corridor.objects.filter(lga__icontains=city.split(',')[0].strip()).first()
    beef = c_qs.local_beef_price_ngn if c_qs else 7400.0
    res = match_suppliers_and_recipe(
        qs, city, float(data.get('weekly_demand_kg', 200.0)), data.get('menu_type', 'Buka'),
        bool(data.get('has_cold_chain', False)), data.get('customer_demographic', '45+'), beef, 3.0
    )
    return JsonResponse(res)

@require_http_methods(["POST"])
@csrf_exempt
def api_match_customer(request):
    data = json.loads(request.body.decode('utf-8') or '{}')
    if data.get('log_signal', True):
        DemandSignal.objects.create(
            city_or_lga=data.get('corridor_or_city', 'Ikeja').split(',')[0].strip(),
            age_group="45+" if int(data.get('age', 52)) >= 45 else "Youth",
            health_goal=data.get('health_goal', 'hypertension'),
            max_budget_ngn=float(data.get('max_budget_ngn', 3500.0)),
            raw_query=data.get('raw_query', '')
        )
    qs = PartnerRestaurant.objects.all()
    matches = match_customer_restaurants(qs, data.get('corridor_or_city', 'Ikeja'), int(data.get('age', 52)), data.get('health_goal', 'hypertension'), float(data.get('max_budget_ngn', 3500.0)))
    recent = list(DemandSignal.objects.values('city_or_lga', 'health_goal', 'max_budget_ngn', 'created_at')[:8])
    for r in recent: r['created_at'] = r['created_at'].strftime('%H:%M:%S')
    return JsonResponse({'matches': matches, 'recent_signals': recent, 'total_demand_signals': DemandSignal.objects.count()})

@require_http_methods(["POST"])
@csrf_exempt
def api_parse_intent(request):
    """Deterministic Nigerian-English Regex Fallback Parser for UI Routing"""
    t = json.loads(request.body.decode('utf-8') or '{}').get('prompt', '').lower()
    parsed = {"role": "strategist", "corridor_or_city": "Ikeja", "sku_cost_ngn": 2400.0, "beef_price_shock_pct": 0.0, "pilot_budget_ngn": 10000000.0, "monthly_capacity_tons": 12.0, "health_goal": "hypertension", "weekly_demand_kg": 200.0, "age": 52, "has_cold_chain": False, "max_budget_ngn": 3500.0}
    
    if any(w in t for w in ["canteen", "buka", "restaurant", "chef", "shawarma", "supplier"]):
        parsed["role"] = "strategist" if any(w in t for w in ["budget", "tons", "beef up", "corridor"]) else "restaurant"
    elif any(w in t for w in ["blood pressure", "hypertension", "cholesterol", "heart", "eat", "meal"]):
        parsed["role"] = "customer"

    for loc in ["Surulere", "Ikeja", "Lekki", "Yaba", "Alimosho", "Ibadan", "Abeokuta", "Ota", "Abuja", "Wuse", "Port Harcourt", "Kaduna", "Kano"]:
        if loc.lower() in t: parsed["corridor_or_city"] = loc; break
    
    if "no fridge" in t or "ambient" in t: parsed["has_cold_chain"] = False
    elif "have fridge" in t or "cold chain" in t: parsed["has_cold_chain"] = True

    age_m = re.search(r"\b(?:i'?m|am|age|aged)\s*(\d{2})\b", t)
    if age_m: parsed["age"] = int(age_m.group(1))

    kg_m = re.search(r'(\d+(?:\.\d+)?)\s*kg', t)
    if kg_m: parsed["weekly_demand_kg"] = float(kg_m.group(1))

    bud_m = re.search(r'[₦n]?\s*(\d+(?:\.\d+)?)\s*(?:m|million)\b', t)
    if bud_m: parsed["pilot_budget_ngn"] = float(bud_m.group(1)) * 1000000.0

    return JsonResponse({"parsed": parsed, "engine": "Offline Regex Router"})
