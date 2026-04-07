from django.urls import path
from .views import (
    TransactionListCreateView, TransactionDetailView,
    CategoryListView, BankAccountListCreateView,
    BankAccountDeleteView, DeleteAllDataView,
)

urlpatterns = [
    path("", TransactionListCreateView.as_view(), name="transaction-list"),
    path("<int:pk>/", TransactionDetailView.as_view(), name="transaction-detail"),
    path("categories/", CategoryListView.as_view(), name="category-list"),
    path("accounts/", BankAccountListCreateView.as_view(), name="bank-accounts"),
    path("accounts/<int:pk>/", BankAccountDeleteView.as_view(), name="bank-account-delete"),
    path("delete-all/", DeleteAllDataView.as_view(), name="delete-all"),
]
