from django.urls import path
from .views import SummaryView, ByCategoryView, TrendView, TopMerchantsView, CategoryBreakdownView, FinBotChatView

urlpatterns = [
    path("summary/", SummaryView.as_view(), name="analytics-summary"),
    path("by-category/", ByCategoryView.as_view(), name="analytics-category"),
    path("breakdown/", CategoryBreakdownView.as_view(), name="analytics-breakdown"),
    path("trend/", TrendView.as_view(), name="analytics-trend"),
    path("merchants/", TopMerchantsView.as_view(), name="analytics-merchants"),
    path("chat/", FinBotChatView.as_view(), name="finbot-chat"),
]
