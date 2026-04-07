from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import datetime, date
import calendar

from transactions.models import Transaction, Category


def current_month_range():
    today = timezone.now().date()
    start = today.replace(day=1)
    end = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    return start, end


class SummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        month_str = request.query_params.get("month")
        if month_str:
            try:
                year, month = map(int, month_str.split("-"))
                start = date(year, month, 1)
                end = date(year, month, calendar.monthrange(year, month)[1])
            except (ValueError, AttributeError):
                start, end = current_month_range()
        else:
            start, end = current_month_range()

        qs = Transaction.objects.filter(user=request.user, date__date__gte=start, date__date__lte=end)

        # If no transactions this month, fall back to most recent month with data
        if not qs.exists() and not month_str:
            latest = Transaction.objects.filter(user=request.user).order_by('-date').first()
            if latest:
                d = latest.date.date()
                start = d.replace(day=1)
                end = d.replace(day=calendar.monthrange(d.year, d.month)[1])
                qs = Transaction.objects.filter(user=request.user, date__date__gte=start, date__date__lte=end)

        total_spent = qs.filter(transaction_type="debit").aggregate(t=Sum("amount"))["t"] or 0
        total_income = qs.filter(transaction_type="credit").aggregate(t=Sum("amount"))["t"] or 0
        txn_count = qs.count()
        savings = float(total_income) - float(total_spent)
        savings_rate = round((savings / float(total_income) * 100), 1) if total_income > 0 else 0

        return Response({
            "month": start.strftime("%Y-%m"),
            "total_spent": float(total_spent),
            "total_income": float(total_income),
            "savings": savings,
            "savings_rate": savings_rate,
            "transaction_count": txn_count,
            "period": {"from": str(start), "to": str(end)},
        })


class ByCategoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        month_str = request.query_params.get("month")
        if month_str:
            try:
                year, month = map(int, month_str.split("-"))
                start = date(year, month, 1)
                end = date(year, month, calendar.monthrange(year, month)[1])
            except (ValueError, AttributeError):
                start, end = current_month_range()
        else:
            start, end = current_month_range()

        # Fall back to most recent month if no data this month
        if not Transaction.objects.filter(user=request.user, date__date__gte=start, date__date__lte=end).exists() and not month_str:
            latest = Transaction.objects.filter(user=request.user).order_by('-date').first()
            if latest:
                d = latest.date.date()
                start = d.replace(day=1)
                end = d.replace(day=calendar.monthrange(d.year, d.month)[1])

        qs = Transaction.objects.filter(
            user=request.user,
            transaction_type="debit",
            date__date__gte=start,
            date__date__lte=end,
        ).values("category__name", "category__color", "category__icon").annotate(
            total=Sum("amount"),
            count=Count("id"),
        ).order_by("-total")

        total_spent = sum(float(item["total"] or 0) for item in qs)

        result = []
        for item in qs:
            amount = float(item["total"] or 0)
            result.append({
                "category": item["category__name"] or "Uncategorized",
                "color": item["category__color"] or "#6B7280",
                "icon": item["category__icon"] or "receipt",
                "amount": amount,
                "count": item["count"],
                "percentage": round(amount / total_spent * 100, 1) if total_spent > 0 else 0,
            })

        return Response({"categories": result, "total_spent": total_spent})


class TrendView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()
        months = []
        for i in range(5, -1, -1):
            month = today.month - i
            year = today.year
            while month <= 0:
                month += 12
                year -= 1
            months.append((year, month))

        result = []
        for year, month in months:
            start = date(year, month, 1)
            end = date(year, month, calendar.monthrange(year, month)[1])
            qs = Transaction.objects.filter(user=request.user, date__date__gte=start, date__date__lte=end)
            spent = qs.filter(transaction_type="debit").aggregate(t=Sum("amount"))["t"] or 0
            income = qs.filter(transaction_type="credit").aggregate(t=Sum("amount"))["t"] or 0
            result.append({
                "month": f"{year}-{month:02d}",
                "label": date(year, month, 1).strftime("%b %Y"),
                "spent": float(spent),
                "income": float(income),
            })

        return Response({"trend": result})


class TopMerchantsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start, end = current_month_range()
        qs = Transaction.objects.filter(
            user=request.user,
            transaction_type="debit",
            date__date__gte=start,
            date__date__lte=end,
        ).exclude(merchant_name="").values("merchant_name").annotate(
            total=Sum("amount"),
            count=Count("id"),
        ).order_by("-total")[:10]

        return Response({
            "merchants": [
                {"merchant": item["merchant_name"], "amount": float(item["total"]), "count": item["count"]}
                for item in qs
            ]
        })


class CategoryBreakdownView(APIView):
    """Returns categories with their top merchants as drilldown data."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        month_str = request.query_params.get("month")
        if month_str:
            try:
                year, month = map(int, month_str.split("-"))
                start = date(year, month, 1)
                end = date(year, month, calendar.monthrange(year, month)[1])
            except (ValueError, AttributeError):
                start, end = current_month_range()
        else:
            start, end = current_month_range()

        # Fall back to most recent month if no data this month
        if not Transaction.objects.filter(user=request.user, date__date__gte=start, date__date__lte=end).exists() and not month_str:
            latest = Transaction.objects.filter(user=request.user).order_by('-date').first()
            if latest:
                d = latest.date.date()
                start = d.replace(day=1)
                end = d.replace(day=calendar.monthrange(d.year, d.month)[1])

        # Get all debit transactions for the period
        txns = Transaction.objects.filter(
            user=request.user,
            transaction_type="debit",
            date__date__gte=start,
            date__date__lte=end,
        ).select_related("category")

        # Group by category
        from collections import defaultdict
        cat_map = defaultdict(lambda: {"amount": 0, "count": 0, "merchants": defaultdict(lambda: {"amount": 0, "count": 0})})

        for txn in txns:
            cat_name = txn.category.name if txn.category else "Other"
            cat_map[cat_name]["amount"] += float(txn.amount)
            cat_map[cat_name]["count"] += 1
            merchant = txn.merchant_name or txn.narration[:30] or "Unknown"
            cat_map[cat_name]["merchants"][merchant]["amount"] += float(txn.amount)
            cat_map[cat_name]["merchants"][merchant]["count"] += 1

        total_spent = sum(v["amount"] for v in cat_map.values())

        result = []
        for cat_name, data in sorted(cat_map.items(), key=lambda x: -x[1]["amount"]):
            top_merchants = sorted(
                [{"name": m, "amount": round(v["amount"], 2), "count": v["count"]} for m, v in data["merchants"].items()],
                key=lambda x: -x["amount"]
            )[:5]
            result.append({
                "category": cat_name,
                "amount": round(data["amount"], 2),
                "count": data["count"],
                "percentage": round(data["amount"] / total_spent * 100, 1) if total_spent > 0 else 0,
                "top_merchants": top_merchants,
            })

        return Response({"categories": result, "total_spent": round(total_spent, 2)})
