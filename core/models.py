from django.db import models

class Corridor(models.Model):
    name = models.CharField(max_length=120)
    lga = models.CharField(max_length=80)
    state = models.CharField(max_length=50)
    channel = models.CharField(max_length=80)
    local_beef_price_ngn = models.FloatField()
    avg_menu_price_ngn = models.FloatField()
    outlet_density_per_km2 = models.FloatField()
    estimated_outlets = models.IntegerField()
    cold_chain_deficit_pct = models.FloatField()
    age_45_plus_share_pct = models.FloatField()
    nearest_hub_km = models.FloatField()
    base_weekly_demand_tons = models.FloatField()
    cac_per_outlet_ngn = models.FloatField()
    data_confidence = models.CharField(max_length=20, default='Medium')
    data_source_tag = models.CharField(max_length=100)

class SupplierHub(models.Model):
    name = models.CharField(max_length=120)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=50)
    specialty = models.CharField(max_length=150)
    wholesale_price_dry_ngn_kg = models.FloatField(default=2400.0)
    monthly_capacity_tons = models.FloatField()
    transport_rate_ngn_per_ton_km = models.FloatField(default=145.0)
    nafdac_certified = models.BooleanField(default=True)
    shelf_life_months = models.IntegerField(default=12)
    protein_pct_dry = models.FloatField(default=54.0)
    lead_time_days = models.IntegerField(default=2)
    contact_phone = models.CharField(max_length=30)

class PartnerRestaurant(models.Model):
    name = models.CharField(max_length=120)
    lga = models.CharField(max_length=80)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=50)
    channel = models.CharField(max_length=80)
    signature_dish = models.CharField(max_length=140)
    dish_price_ngn = models.FloatField()
    proextend_blend_pct = models.IntegerField(default=50)
    health_tags = models.CharField(max_length=200)
    calories_per_serving = models.IntegerField(default=420)
    cholesterol_reduction_pct = models.IntegerField(default=48)
    rating = models.FloatField(default=4.6)
    address = models.CharField(max_length=200)

class DemandSignal(models.Model):
    city_or_lga = models.CharField(max_length=80)
    age_group = models.CharField(max_length=30)
    health_goal = models.CharField(max_length=60)
    max_budget_ngn = models.FloatField()
    raw_query = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
