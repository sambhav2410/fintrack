from django.contrib import admin
from .models import Transaction, Category, BankAccount


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "icon", "color", "is_default"]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ["user", "amount", "transaction_type", "merchant_name", "category", "date", "source"]
    list_filter = ["transaction_type", "source", "category"]
    search_fields = ["user__phone_number", "merchant_name", "narration"]
    ordering = ["-date"]


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ["user", "bank_name", "account_last4"]
