from django.urls import path
from .views import SummaryView, ByCategoryView, TrendView, TopMerchantsView, CategoryBreakdownView

urlpatterns = [
    path("summary/", SummaryView.as_view(), name="analytics-summary"),
    path("by-category/", ByCategoryView.as_view(), name="analytics-category"),
    path("breakdown/", CategoryBreakdownView.as_view(), name="analytics-breakdown"),
    path("trend/", TrendView.as_view(), name="analytics-trend"),
    path("merchants/", TopMerchantsView.as_view(), name="analytics-merchants"),
]
