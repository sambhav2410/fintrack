from django.urls import path
from .views import BudgetListCreateView, BudgetStatusView, BudgetUpdateDeleteView

urlpatterns = [
    path("", BudgetListCreateView.as_view(), name="budget-list"),
    path("status/", BudgetStatusView.as_view(), name="budget-status"),
    path("<int:pk>/", BudgetUpdateDeleteView.as_view(), name="budget-detail"),
]
