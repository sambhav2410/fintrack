from rest_framework import generics, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from .models import Transaction, Category, BankAccount
from .serializers import (
    TransactionSerializer, TransactionCreateSerializer,
    CategorySerializer, BankAccountSerializer,
)


class TransactionListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["merchant_name", "narration", "notes"]
    ordering_fields = ["date", "amount"]
    ordering = ["-date"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return TransactionCreateSerializer
        return TransactionSerializer

    def get_queryset(self):
        qs = Transaction.objects.filter(user=self.request.user).select_related("category")
        params = self.request.query_params

        if category := params.get("category"):
            qs = qs.filter(category_id=category)
        if txn_type := params.get("type"):
            qs = qs.filter(transaction_type=txn_type)
        if date_from := params.get("from"):
            qs = qs.filter(date__date__gte=date_from)
        if date_to := params.get("to"):
            qs = qs.filter(date__date__lte=date_to)
        if bank := params.get("bank"):
            qs = qs.filter(bank_name__icontains=bank)

        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, source=Transaction.SOURCE_MANUAL)


class TransactionDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TransactionSerializer

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)


class CategoryListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CategorySerializer
    pagination_class = None

    def get_queryset(self):
        return Category.objects.filter(
            Q(is_default=True, user=None) | Q(user=self.request.user)
        )


class BankAccountListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BankAccountSerializer
    pagination_class = None

    def get_queryset(self):
        return BankAccount.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class BankAccountDeleteView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BankAccountSerializer

    def get_queryset(self):
        return BankAccount.objects.filter(user=self.request.user)


class DeleteAllDataView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        Transaction.objects.filter(user=request.user).delete()
        return Response({"message": "All your transaction data has been deleted."})
