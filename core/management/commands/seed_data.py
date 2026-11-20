from django.core.management.base import BaseCommand
from core.models import Corridor, SupplierHub, PartnerRestaurant, DemandSignal

# name, lga, state, channel, beef, menu, density, outlets, cold_deficit, age45, hub_km, tons/wk, cac, confidence, source
CORRIDORS = [
    ("Surulere Buka Belt", "Surulere", "Lagos", "Buka", 7600, 2600, 34.5, 420, 68, 31, 42, 2.4, 42000, "High", "NBS"),
    ("Ikeja QSR Strip", "Ikeja", "Lagos", "QSR", 7800, 3200, 38.0, 510, 52, 34, 28, 2.9, 48000, "High", "NBS"),
    ("Alimosho Mass Canteens", "Alimosho", "Lagos", "Canteen", 7300, 2200, 29.0, 640, 74, 26, 55, 3.4, 36000, "Medium", "Field survey"),
    ("Yaba Campus Suya", "Yaba", "Lagos", "Suya / Shawarma", 7900, 2800, 41.0, 360, 49, 22, 30, 1.8, 51000, "Medium", "Field survey"),
    ("Ibadan Bodija Caterers", "Ibadan", "Oyo", "Catering", 7100, 3000, 21.0, 280, 71, 33, 130, 1.5, 39000, "Low", "Desk estimate"),
    ("Wuse Office Lunch", "Wuse", "FCT", "Canteen", 8400, 3600, 26.0, 330, 58, 37, 700, 1.9, 58000, "Low", "Desk estimate"),
    ("Ota Factory Canteens", "Ota", "Ogun", "Canteen", 7200, 2100, 17.0, 240, 77, 29, 12, 2.2, 31000, "Medium", "Field survey"),
]
# name, city, state, specialty, price, cap_t, rate, nafdac, shelf, protein, lead, phone
HUBS = [
    ("Ota Agro Processing", "Ota", "Ogun", "ProExtend-50", 2380, 28, 135, True, 12, 54, 2, "+234 803 000 1101"),
    ("Abeokuta Soy Mills", "Abeokuta", "Ogun", "ProExtend-50 coarse", 2310, 18, 140, True, 10, 52, 3, "+234 803 000 1102"),
    ("Ibadan Plant Proteins", "Ibadan", "Oyo", "ProExtend-50 fine", 2450, 12, 150, True, 12, 54, 3, "+234 803 000 1103"),
    ("Kano Grain Hub", "Kano", "Kano", "Bulk dry mince", 2200, 40, 120, False, 6, 50, 6, "+234 803 000 1104"),
]
# name, lga, city, state, channel, dish, price, blend, tags, kcal, chol, rating, address
RESTAURANTS = [
    ("Mama Put Wellness", "Surulere", "Lagos", "Lagos", "Buka", "Heart Stew with Brown Rice", 2200, 55, "hypertension,cholesterol", 410, 52, 4.8, "14 Adeniran Ogunsanya St, Surulere"),
    ("Ikeja Green Plate", "Ikeja", "Lagos", "Lagos", "QSR", "Grilled Blend Burger", 3400, 40, "cholesterol,weight", 480, 44, 4.5, "Allen Avenue, Ikeja"),
    ("Iya Basira Kitchen", "Ikeja", "Lagos", "Lagos", "Buka", "Low-salt Ofada Stew", 2600, 50, "hypertension", 430, 48, 4.7, "Obafemi Awolowo Way, Ikeja"),
    ("Yaba Suya Spot", "Yaba", "Lagos", "Lagos", "Suya / Shawarma", "Suya Mince Wrap", 2800, 60, "weight,budget", 390, 40, 4.4, "Herbert Macaulay Way, Yaba"),
    ("Alimosho Staff Canteen", "Alimosho", "Lagos", "Lagos", "Canteen", "Jollof and Mince Plate", 1800, 60, "budget,diabetes", 450, 41, 4.2, "Egbeda Road, Alimosho"),
    ("Surulere Fit Buka", "Surulere", "Lagos", "Lagos", "Buka", "Egusi with Blend Mince", 2400, 50, "diabetes,hypertension", 420, 46, 4.6, "Bode Thomas St, Surulere"),
    ("Lekki Lean Kitchen", "Lekki", "Lagos", "Lagos", "QSR", "Light Beef Pie Bowl", 4200, 45, "weight,cholesterol", 360, 50, 4.7, "Admiralty Way, Lekki"),
    ("Bodija Heart Eatery", "Ibadan", "Ibadan", "Oyo", "Buka", "Heart Stew and Amala", 1900, 55, "hypertension,budget", 440, 49, 4.5, "Bodija Market Rd, Ibadan"),
]
SIGNALS = [("Surulere", "45+", "hypertension", 2500), ("Surulere", "45+", "cholesterol", 2800), ("Ikeja", "45+", "hypertension", 3000),
           ("Alimosho", "Under 45", "budget", 1800), ("Yaba", "Under 45", "weight", 3000), ("Surulere", "45+", "diabetes", 2600)]

class Command(BaseCommand):
    help = "Load demo corridors, supplier hubs, partner restaurants and demand signals."

    def handle(self, *args, **options):
        for m in (Corridor, SupplierHub, PartnerRestaurant, DemandSignal): m.objects.all().delete()
        for r in CORRIDORS:
            Corridor.objects.create(name=r[0], lga=r[1], state=r[2], channel=r[3], local_beef_price_ngn=r[4], avg_menu_price_ngn=r[5],
                outlet_density_per_km2=r[6], estimated_outlets=r[7], cold_chain_deficit_pct=r[8], age_45_plus_share_pct=r[9],
                nearest_hub_km=r[10], base_weekly_demand_tons=r[11], cac_per_outlet_ngn=r[12], data_confidence=r[13], data_source_tag=r[14])
        for r in HUBS:
            SupplierHub.objects.create(name=r[0], city=r[1], state=r[2], specialty=r[3], wholesale_price_dry_ngn_kg=r[4], monthly_capacity_tons=r[5],
                transport_rate_ngn_per_ton_km=r[6], nafdac_certified=r[7], shelf_life_months=r[8], protein_pct_dry=r[9], lead_time_days=r[10], contact_phone=r[11])
        for r in RESTAURANTS:
            PartnerRestaurant.objects.create(name=r[0], lga=r[1], city=r[2], state=r[3], channel=r[4], signature_dish=r[5], dish_price_ngn=r[6],
                proextend_blend_pct=r[7], health_tags=r[8], calories_per_serving=r[9], cholesterol_reduction_pct=r[10], rating=r[11], address=r[12])
        for c, a, g, b in SIGNALS:
            DemandSignal.objects.create(city_or_lga=c, age_group=a, health_goal=g, max_budget_ngn=b)
        self.stdout.write(self.style.SUCCESS("Seeded %d corridors, %d hubs, %d restaurants, %d signals." % (len(CORRIDORS), len(HUBS), len(RESTAURANTS), len(SIGNALS))))