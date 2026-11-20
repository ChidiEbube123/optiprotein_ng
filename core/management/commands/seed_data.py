from django.core.management.base import BaseCommand
from core.models import Corridor, SupplierHub, PartnerRestaurant, DemandSignal

class Command(BaseCommand):
    def handle(self, *args, **options):
        Corridor.objects.all().delete()
        SupplierHub.objects.all().delete()
        PartnerRestaurant.objects.all().delete()
        DemandSignal.objects.all().delete()

        Corridor.objects.create(name="Surulere Buka", lga="Surulere", state="Lagos", channel="Buka", local_beef_price_ngn=7600, avg_menu_price_ngn=2600, outlet_density_per_km2=34.5, estimated_outlets=420, cold_chain_deficit_pct=68.0, age_45_plus_share_pct=31.0, nearest_hub_km=42.0, base_weekly_demand_tons=2.4, cac_per_outlet_ngn=42000, data_confidence="High", data_source_tag="NBS")
        Corridor.objects.create(name="Ikeja QSR", lga="Ikeja", state="Lagos", channel="QSR", local_beef_price_ngn=7800, avg_menu_price_ngn=3200, outlet_density_per_km2=38.0, estimated_outlets=510, cold_chain_deficit_pct=52.0, age_45_plus_share_pct=34.0, nearest_hub_km=28.0, base_weekly_demand_tons=2.9, cac_per_outlet_ngn=48000, data_confidence="High", data_source_tag="NBS")
        
        SupplierHub.objects.create(name="Ota Agro", city="Ota", state="Ogun", specialty="ProExtend-50", wholesale_price_dry_ngn_kg=2380.0, monthly_capacity_tons=28.0, transport_rate_ngn_per_ton_km=135.0)
        
        PartnerRestaurant.objects.create(name="Mama Put Wellness", lga="Surulere", city="Lagos", state="Lagos", channel="Buka", signature_dish="Heart Stew", dish_price_ngn=2200, proextend_blend_pct=55, health_tags="hypertension,cholesterol", calories_per_serving=410, cholesterol_reduction_pct=52, rating=4.8, address="Surulere")
        
        DemandSignal.objects.create(city_or_lga="Surulere", age_group="45+", health_goal="hypertension", max_budget_ngn=2500)
        self.stdout.write("Seeded minimal set for multi-page demo.")
