from django.urls import path
from . import views

urlpatterns = [
    # Pages
    path('', views.page_opportunities, name='opportunities'),
    path('restaurant/', views.page_restaurant, name='restaurant'),
    path('customer/', views.page_customer, name='customer'),
    
    # APIs
    path('api/opportunities/', views.api_opportunities, name='api_opportunities'),
    path('api/match-supplier/', views.api_match_supplier, name='api_match_supplier'),
    path('api/match-customer/', views.api_match_customer, name='api_match_customer'),
    path('api/parse-intent/', views.api_parse_intent, name='api_parse_intent'),
]
