from django.contrib import admin
from .models import Budget


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ["user", "category", "monthly_limit", "month"]
    list_filter = ["month"]
    search_fields = ["user__phone_number"]
