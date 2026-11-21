import json
import logging
import os
import re
import urllib.error
import urllib.request
from django.conf import settings
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

def _rule_parse(raw):
    """Rule-based parser for Nigerian-English prompts. Returns (parsed, found)."""
    t = (raw or '').lower()
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

    return parsed, found
@require_http_methods(["POST"])
@csrf_exempt
def api_parse_intent(request):
    parsed, found = _rule_parse(_text(_body(request), 'prompt', ''))
    return JsonResponse({"parsed": parsed, "found": found, "engine": "rules"})



# Default provider is Amazon Bedrock (Converse API). boto3 finds credentials by itself from the environment:
#   AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN   (temporary CLI credentials)
#   or AWS_BEARER_TOKEN_BEDROCK                                      (Bedrock short-term API key)
#   AWS_REGION=us-east-1   BEDROCK_MODEL_ID=us.amazon.nova-lite-v1:0   (use any model your account can invoke)
# Other providers still work: AI_PROVIDER=anthropic|openai with AI_API_KEY (and optional AI_MODEL, AI_BASE_URL).
logger = logging.getLogger(__name__)
DEFAULT_BEDROCK_MODEL = "us.amazon.nova-lite-v1:0"
def _f(kind, desc, lo=None, hi=None, options=None):
    return {"kind": kind, "desc": desc, "lo": lo, "hi": hi, "options": options}

MENU_OPTIONS = ["Buka", "QSR", "Canteen", "Suya / Shawarma", "Catering"]
AI_SPECS = {
    "customer": {
        "corridor_or_city": _f("text", "Area, LGA or city where they want to eat, e.g. Ikeja"),
        "age": _f("int", "Age in years", 10, 110),
        "health_goal": _f("enum", "Main health goal", options=["hypertension", "cholesterol", "diabetes", "weight", "budget"]),
        "max_budget_ngn": _f("num", "Most they will pay for ONE meal, in naira", 300, 50000),
        "max_calories": _f("int", "Calorie limit per meal in kcal", 100, 3000),
    },
    "restaurant": {
        "corridor_or_city": _f("text", "Area or city of the kitchen, e.g. Surulere, Lagos"),
        "menu_type": _f("enum", "Type of kitchen", options=MENU_OPTIONS),
        "weekly_demand_kg": _f("num", "Kilograms of beef or meat used per WEEK", 1, 100000),
        "has_cold_chain": _f("bool", "true if they have a freezer or fridge, false if ambient storage only"),
        "customer_demographic": _f("enum", "Age of most guests", options=["45+", "Under 45"]),
        "beef_price_ngn": _f("num", "What they pay for beef, naira per kg", 1000, 30000),
        "substitution_pct": _f("num", "Percent of beef they want to replace", 10, 80),
        "hydration_ratio": _f("enum", "Total weight of mince made per 1 kg dry: 2.5 firm, 3 standard, 3.5 soft", options=[2.5, 3.0, 3.5]),
    },
    "opportunity": {
        "sku_cost_ngn": _f("num", "Wholesale price of dry ProExtend-50, naira per kg", 500, 20000),
        "hydration_ratio": _f("enum", "Total weight of mince made per 1 kg dry: 2.5 firm, 3 standard, 3.5 soft", options=[2.5, 3.0, 3.5]),
        "substitution_pct": _f("num", "Percent of beef replaced in a dish", 10, 80),
        "beef_price_shock_pct": _f("num", "Beef price change in percent, negative if it falls", -20, 60),
        "channel": _f("enum", "Channel to focus on", options=["all"] + MENU_OPTIONS),
        "pilot_budget_ngn": _f("num", "Budget for winning new outlets, naira", 0, 10_000_000_000),
        "monthly_capacity_tons": _f("num", "Tons of dry product they can supply per month", 0, 100000),
        "min_margin_pct": _f("num", "Lowest margin they will accept, percent", 0, 95),
    },
}

def _ai_prompt(page):
    lines = []
    for k, f in AI_SPECS[page].items():
        extra = f" One of: {f['options']}." if f["options"] else (f" Range {f['lo']} to {f['hi']}." if f["lo"] is not None else "")
        lines.append(f'- "{k}" ({f["kind"]}): {f["desc"]}.{extra}')
    return (
        "You fill in a web form for a Nigerian food-tech tool. The user spoke freely, possibly for a long time, in Nigerian English or pidgin, "
        "and the transcript may contain speech-recognition mistakes, filler, corrections and numbers spelled out. "
        "If they correct themselves, use the final value. Extract ONLY what they stated or clearly implied. Never guess or invent.\n\n"
        "Return ONE JSON object, nothing else, with exactly these keys. Use null for anything not mentioned:\n" + "\n".join(lines) + "\n\n"
        "Conversions: money is in naira (3k = 3000, 2.5m = 2500000, N3,500 = 3500). 'kilos' = kg. 'half' = 50 percent. "
        "Spelled-out numbers become digits (fifty six = 56)."
    )

import boto3

def _call_bedrock(system, user):
    print("Lie to his nigas ")
    import boto3
    from botocore.config import Config
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    client = boto3.client("bedrock-runtime", region_name=region,
                          config=Config(connect_timeout=8, read_timeout=25, retries={"max_attempts": 1}))
    resp = client.converse(
        modelId=os.environ.get("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL),
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"maxTokens": 700, "temperature": 0},
    )
    return "".join(block.get("text", "") for block in resp["output"]["message"]["content"])

def _call_http_llm(provider, system, user):
    key = os.environ.get("AI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY")
    if not key:
        raise RuntimeError("no API key configured")
    if provider == "openai":
        base = os.environ.get("AI_BASE_URL", "https://api.openai.com").rstrip("/")
        url, headers = base + "/v1/chat/completions", {"Authorization": "Bearer " + key}
        body = {"model": os.environ.get("AI_MODEL", "gpt-4o-mini"), "temperature": 0, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    else:
        base = os.environ.get("AI_BASE_URL", "https://api.anthropic.com").rstrip("/")
        url, headers = base + "/v1/messages", {"x-api-key": key, "anthropic-version": "2023-06-01"}
        body = {"model": os.environ.get("AI_MODEL", "claude-sonnet-5-5"), "max_tokens": 700, "system": system,
                "messages": [{"role": "user", "content": user}]}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={**headers, "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"] if provider == "openai" else "".join(b.get("text", "") for b in data["content"])

def _call_llm(system, user):
    provider = os.environ.get("AI_PROVIDER", "bedrock").lower()
    text = _call_bedrock(system, user) if provider == "bedrock" else _call_http_llm(provider, system, user)
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < a: raise ValueError("model returned no JSON")
    return json.loads(text[a:b + 1])

def _clean_ai(page, raw):
    """Validate whatever the model returned against the form's real limits."""
    parsed = {}
    for k, f in AI_SPECS[page].items():
        v = raw.get(k)
        if v is None or v == "": continue
        try:
            if f["kind"] == "text":
                v = str(v).strip()[:80]
                if not v: continue
            elif f["kind"] in ("int", "num"):
                v = float(str(v).replace(",", ""))
                v = max(f["lo"], min(f["hi"], v))
                v = int(round(v)) if f["kind"] == "int" else v
                if k == "substitution_pct": v = int(round(v / 5) * 5)
            elif f["kind"] == "bool":
                v = v if isinstance(v, bool) else str(v).lower() in ("true", "yes", "1")
            elif f["kind"] == "enum":
                if isinstance(f["options"][0], float):
                    v = min(f["options"], key=lambda o: abs(o - float(v)))
                else:
                    low = str(v).lower().strip()
                    hit = next((o for o in f["options"] if o.lower() == low), None) or \
                          next((o for o in f["options"] if low in o.lower() or o.lower().split(" ")[0] in low), None)
                    if hit is None: continue
                    v = hit
        except (TypeError, ValueError):
            continue
        parsed[k] = v
    print(f"tjhe parsed {parsed}")
    return parsed

@require_http_methods(["POST"])
@csrf_exempt
def api_ai_fill(request):
    d = _body(request)
    page = d.get("page") if d.get("page") in AI_SPECS else "customer"
    transcript = _text(d, "transcript", "")[:6000]
    print(transcript)
    if not transcript:
        return JsonResponse({"parsed": {}, "found": [], "engine": "none", "note": "Nothing to read."})
    try:
        print("sayy")
        parsed = _clean_ai(page, _call_llm(_ai_prompt(page), transcript))
        return JsonResponse({"parsed": parsed, "found": list(parsed), "engine": "ai"})
    except Exception as exc:  # credentials, network, model access, bad JSON: fall back so the user still gets something
        logger.warning("AI fill failed: %s: %s", type(exc).__name__, exc)
        rules, _ = _rule_parse(transcript)
        parsed = {k: v for k, v in rules.items() if k in AI_SPECS[page]}
        resp = getattr(exc, "response", None)
        code = resp.get("Error", {}).get("Code", "") if isinstance(resp, dict) else ""
        name = type(exc).__name__
        if name in ("NoCredentialsError", "PartialCredentialsError") or code in ("ExpiredTokenException", "ExpiredToken", "UnrecognizedClientException", "InvalidSignatureException", "InvalidClientTokenId"):
            why = "AWS credentials are missing or expired. Refresh them, restart the server, and try again."
        elif code in ("AccessDeniedException", "ValidationException", "ResourceNotFoundException"):
            why = "Bedrock refused the request. Check BEDROCK_MODEL_ID and that this account can use that model in this region."
        else:
            why = "The AI service didn't respond."
        out = {"parsed": parsed, "found": list(parsed), "engine": "rules", "note": why + " We used basic matching, so check the form."}
        if settings.DEBUG: out["detail"] = f"{name}: {str(exc)[:300]}"
        return JsonResponse(out)