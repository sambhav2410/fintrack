from rest_framework import serializers
from .models import Transaction, Category, BankAccount


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "icon", "color", "is_default"]


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = ["id", "bank_name", "account_last4", "account_type", "created_at"]
        read_only_fields = ["id", "created_at"]


class TransactionSerializer(serializers.ModelSerializer):
    category_detail = CategorySerializer(source="category", read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id", "amount", "transaction_type", "category", "category_detail",
            "date", "narration", "merchant_name", "reference_number",
            "account_last4", "bank_name", "source", "notes", "created_at",
        ]
        read_only_fields = ["id", "source", "created_at"]


class TransactionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            "amount", "transaction_type", "category", "date",
            "narration", "merchant_name", "notes",
        ]
