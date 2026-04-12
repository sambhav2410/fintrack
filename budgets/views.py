from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from django.utils import timezone
import calendar
from datetime import date

from transactions.models import Transaction, Category
from .models import Budget
from .serializers import BudgetSerializer


def current_month():
    return timezone.now().strftime("%Y-%m")


class BudgetListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BudgetSerializer
    pagination_class = None

    def get_queryset(self):
        month = self.request.query_params.get("month", current_month())
        return Budget.objects.filter(user=self.request.user, month=month).select_related("category")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        month = serializer.validated_data.get("month", current_month())
        category = serializer.validated_data["category"]
        monthly_limit = serializer.validated_data["monthly_limit"]
        # Upsert: update if same category+month already exists
        budget, _ = Budget.objects.update_or_create(
            user=request.user,
            category=category,
            month=month,
            defaults={"monthly_limit": monthly_limit},
        )
        out = BudgetSerializer(budget)
        return Response(out.data, status=status.HTTP_200_OK)


class BudgetStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        month = request.query_params.get("month", current_month())
        try:
            year, m = map(int, month.split("-"))
        except ValueError:
            return Response({"error": "Invalid month format. Use YYYY-MM"}, status=400)

        start = date(year, m, 1)
        end = date(year, m, calendar.monthrange(year, m)[1])
        budgets = Budget.objects.filter(user=request.user, month=month).select_related("category")

        result = []
        for budget in budgets:
            spent = Transaction.objects.filter(
                user=request.user,
                category=budget.category,
                transaction_type="debit",
                date__date__gte=start,
                date__date__lte=end,
            ).aggregate(t=Sum("amount"))["t"] or 0

            limit = float(budget.monthly_limit)
            spent_float = float(spent)
            remaining = limit - spent_float
            pct = round(spent_float / limit * 100, 1) if limit > 0 else 0

            result.append({
                "id": budget.id,
                "category": {"id": budget.category.id, "name": budget.category.name, "color": budget.category.color},
                "monthly_limit": limit,
                "spent": spent_float,
                "remaining": remaining,
                "percentage": pct,
                "status": "over" if pct > 100 else "warning" if pct > 80 else "ok",
            })

        return Response({"budgets": result, "month": month})


class BudgetUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BudgetSerializer

    def get_queryset(self):
        return Budget.objects.filter(user=self.request.user)
