from rest_framework import serializers
from .models import Budget
from transactions.models import Category


class BudgetSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_color = serializers.CharField(source="category.color", read_only=True)

    class Meta:
        model = Budget
        fields = ["id", "category", "category_name", "category_color", "monthly_limit", "month"]
        read_only_fields = ["id"]
        extra_kwargs = {
            "month": {"required": False},
        }
