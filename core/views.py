import json
import re
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import Corridor, SupplierHub, PartnerRestaurant, DemandSignal
from .ml_engine import evaluate_all_corridors, match_suppliers_and_recipe, match_customer_restaurants


# ==================== HELPERS ====================
def _body(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return {}

def _num(data, key, default, lo=None, hi=None, cast=float):
    """Read a number from the payload; fall back to default if missing/invalid; clamp to [lo, hi]."""
    try:
        v = cast(data.get(key, default))
    except (TypeError, ValueError):
        v = default
    if lo is not None: v = max(lo, v)
    if hi is not None: v = min(hi, v)
    return v

def _text(data, key, default):
    v = str(data.get(key) or '').strip()
    return v or default


# ==================== PAGE VIEWS ====================
def get_global_context():
    return {'total_signals': DemandSignal.objects.count()}

def page_opportunities(request):
    return render(request, 'opportunity.html', get_global_context())

def page_restaurant(request):
    return render(request, 'restaurant.html', get_global_context())

def page_customer(request):
    return render(request, 'customer.html', get_global_context())


# ==================== API ENDPOINTS ====================
@require_http_methods(["POST"])
@csrf_exempt
def api_opportunities(request):
    p = _body(request)
    counts = {r['city_or_lga'].lower().strip(): r['total']
              for r in DemandSignal.objects.values('city_or_lga').annotate(total=Count('id'))}
    res = evaluate_all_corridors(
        Corridor.objects.all(), counts,
        dry_sku_cost_ngn=_num(p, 'sku_cost_ngn', 2400.0, 500, 20000),
        hydration_ratio=_num(p, 'hydration_ratio', 3.0, 1.0, 6.0),
        beef_shock_pct=_num(p, 'beef_price_shock_pct', 0.0, -50, 150),
        substitution_pct=_num(p, 'substitution_pct', 50.0, 5, 100) / 100.0,
        pilot_budget_ngn=_num(p, 'pilot_budget_ngn', 10_000_000.0, 0),
        monthly_capacity_tons=_num(p, 'monthly_capacity_tons', 12.0, 0),
        min_margin_pct=_num(p, 'min_margin_pct', 22.0, 0, 95),
        channel=_text(p, 'channel', 'all'),
    )
    res['total_demand_signals'] = DemandSignal.objects.count()
    res['channels'] = sorted(set(Corridor.objects.values_list('channel', flat=True)))
    return JsonResponse(res)


@require_http_methods(["POST"])
@csrf_exempt
def api_match_supplier(request):
    d = _body(request)
    city = _text(d, 'corridor_or_city', 'Surulere, Lagos')
    corridor = Corridor.objects.filter(lga__icontains=city.split(',')[0].strip()).first()
    market_beef = corridor.local_beef_price_ngn if corridor else 7400.0
    beef = _num(d, 'beef_price_ngn', market_beef, 1000, 30000) or market_beef
    res = match_suppliers_and_recipe(
        SupplierHub.objects.all(), city,
        _num(d, 'weekly_demand_kg', 200.0, 1, 100000),
        _text(d, 'menu_type', 'Buka'),
        bool(d.get('has_cold_chain', False)),
        _text(d, 'customer_demographic', '45+'),
        beef,
        _num(d, 'hydration_ratio', 3.0, 1.0, 6.0),
        _num(d, 'substitution_pct', 50.0, 5, 100) / 100.0,
    )
    res['beef_price_used_ngn'] = beef
    res['beef_price_is_market_default'] = 'beef_price_ngn' not in d or not d.get('beef_price_ngn')
    return JsonResponse(res)


@require_http_methods(["POST"])
@csrf_exempt
def api_match_customer(request):
    d = _body(request)
    city = _text(d, 'corridor_or_city', 'Ikeja')
    age = _num(d, 'age', 52, 10, 110, cast=int)
    goal = _text(d, 'health_goal', 'hypertension')
    budget = _num(d, 'max_budget_ngn', 3500.0, 300, 50000)
    max_cal = _num(d, 'max_calories', 0, 0, 3000, cast=int) or None

    if d.get('log_signal', True):
        DemandSignal.objects.create(
            city_or_lga=city.split(',')[0].strip(),
            age_group="45+" if age >= 45 else "Under 45",
            health_goal=goal, max_budget_ngn=budget, raw_query=_text(d, 'raw_query', ''),
        )
    matches = match_customer_restaurants(PartnerRestaurant.objects.all(), city, age, goal, budget, max_cal)
    recent = list(DemandSignal.objects.values('city_or_lga', 'health_goal', 'max_budget_ngn', 'created_at')[:6])
    for r in recent:
        r['created_at'] = r['created_at'].strftime('%H:%M')
    return JsonResponse({'matches': matches, 'recent_signals': recent,
                         'total_demand_signals': DemandSignal.objects.count()})


# ---------- Intent router ----------
KNOWN_PLACES = ["Surulere", "Ikeja", "Lekki", "Yaba", "Alimosho", "Ibadan", "Abeokuta", "Ota", "Abuja", "Wuse",
                "Port Harcourt", "Kaduna", "Kano", "Mushin", "Oshodi", "Ajah", "Ikorodu", "Victoria Island"]
MENU_WORDS = {"Buka": ["buka", "mama put", "canteen"], "QSR": ["qsr", "fast food", "burger", "pie"],
              "Suya / Shawarma": ["suya", "shawarma"], "Catering": ["catering", "caterer", "event"],
              "Canteen": ["staff canteen", "cafeteria"]}
GOAL_WORDS = {"hypertension": ["blood pressure", "hypertension", "bp"], "cholesterol": ["cholesterol"],
              "diabetes": ["diabet", "sugar"], "weight": ["weight", "slim", "lose fat"], "budget": ["cheap", "afford"]}

def _money(t):
    """Find a naira amount: '10m', '₦3,500', '3500 naira', '2k'."""
    m = re.search(r'(\d+(?:\.\d+)?)\s*(m|million)\b', t)
    if m: return float(m.group(1)) * 1_000_000, 'm'
    m = re.search(r'(?:₦|ngn|n)\s*(\d[\d,]*(?:\.\d+)?)\s*(k)?', t)
    if m: return float(m.group(1).replace(',', '')) * (1000 if m.group(2) else 1), 'n'
    m = re.search(r'(\d[\d,]*(?:\.\d+)?)\s*(k|naira)\b', t)
    if m: return float(m.group(1).replace(',', '')) * (1000 if m.group(2) == 'k' else 1), 'n'
    return None, None

@require_http_methods(["POST"])
@csrf_exempt
def api_parse_intent(request):
    """Rule-based parser for Nigerian-English prompts. Returns parsed values and which fields were actually heard."""
    raw = _text(_body(request), 'prompt', '')
    t = raw.lower()
    parsed, found = {}, []

    def put(k, v):
        parsed[k] = v
        if k not in found: found.append(k)

    # Who is speaking
    role = None
    if any(w in t for w in ["blood pressure", "hypertension", "cholesterol", "diabet", "my heart", "i want to eat", "where can i eat", "meal near"]):
        role = "customer"
    elif any(w in t for w in ["pilot", "corridor", "launch", "invest", "rollout", "tons", "wholesale", "distributor"]):
        role = "strategist"
    elif any(w in t for w in ["canteen", "buka", "restaurant", "chef", "shawarma", "suya", "kitchen", "i run", "my customers", "supplier"]):
        role = "restaurant"
    if role: put("role", role)

    for loc in KNOWN_PLACES:
        if loc.lower() in t: put("corridor_or_city", loc); break

    if re.search(r"no (fridge|freezer|cold)|ambient|without (a )?(fridge|freezer)", t): put("has_cold_chain", False)
    elif re.search(r"(have|with|got) (a )?(fridge|freezer|cold)|cold chain", t): put("has_cold_chain", True)

    m = re.search(r"\b(?:i'?m|i am|am|age|aged)\s*(\d{2})\b", t) or re.search(r"\b(\d{2})\s*(?:years|yrs|yr)\b", t)
    if m: put("age", int(m.group(1)))

    m = re.search(r'(\d[\d,]*(?:\.\d+)?)\s*(?:kg|kilo)', t)
    if m: put("weekly_demand_kg", float(m.group(1).replace(',', '')))

    amt, kind = _money(t)
    if amt is not None:
        if role == "customer" or (role is None and amt < 100000): put("max_budget_ngn", amt)
        elif kind == 'm' or amt >= 100000: put("pilot_budget_ngn", amt)

    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:tons?|tonnes?)\b', t)
    if m: put("monthly_capacity_tons", float(m.group(1)))

    m = re.search(r'beef.{0,25}?(?:up|rise|rises|jump\w*|increase\w*)\D{0,12}(\d{1,3})\s*%', t)
    if m: put("beef_price_shock_pct", float(m.group(1)))

    m = re.search(r'(\d{1,3})\s*%\s*(?:blend|substitut|replace|mix)', t) or re.search(r'(?:blend|substitut|replace)\w*\D{0,12}(\d{1,3})\s*%', t)
    if m: put("substitution_pct", float(m.group(1)))

    for name, words in MENU_WORDS.items():
        if any(w in t for w in words): put("menu_type", name); break
    for goal, words in GOAL_WORDS.items():
        if role in ('strategist', 'restaurant'): break
        if any(re.search(r'\b' + re.escape(w), t) for w in words): put("health_goal", goal); break

    m = re.search(r'(?:under|below|less than|max)\s*(\d{3,4})\s*(?:kcal|cal)', t)
    if m: put("max_calories", int(m.group(1)))

    return JsonResponse({"parsed": parsed, "found": found, "engine": "Rule-based router"})