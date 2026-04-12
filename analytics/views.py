from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.conf import settings
from datetime import datetime, date
import calendar
import json

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


class FinBotChatView(APIView):
    """Gemini-powered FinBot: answers questions using the user's real transaction data."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        question = (request.data.get("question") or "").strip()
        if not question:
            return Response({"error": "question required"}, status=400)

        # Build financial context from last 90 days of transactions
        today = timezone.now().date()
        start_90 = today.replace(day=1)  # current month start
        # Get last 3 months
        months_data = []
        for i in range(3):
            m = today.month - i
            y = today.year
            while m <= 0:
                m += 12
                y -= 1
            s = date(y, m, 1)
            e = date(y, m, calendar.monthrange(y, m)[1])
            txns = Transaction.objects.filter(
                user=request.user, date__date__gte=s, date__date__lte=e
            )
            spent = txns.filter(transaction_type="debit").aggregate(t=Sum("amount"))["t"] or 0
            income = txns.filter(transaction_type="credit").aggregate(t=Sum("amount"))["t"] or 0
            # Category breakdown
            cats = txns.filter(transaction_type="debit").values("category__name").annotate(
                total=Sum("amount"), cnt=Count("id")
            ).order_by("-total")[:8]
            months_data.append({
                "month": f"{y}-{m:02d}",
                "spent": float(spent),
                "income": float(income),
                "savings": float(income) - float(spent),
                "categories": [
                    {"name": c["category__name"] or "Other", "amount": float(c["total"] or 0), "count": c["cnt"]}
                    for c in cats
                ],
            })

        # Recent individual transactions (last 30)
        recent_txns = Transaction.objects.filter(
            user=request.user
        ).select_related("category").order_by("-date")[:30]
        txn_lines = []
        for t in recent_txns:
            txn_lines.append(
                f"{t.date.strftime('%d %b %Y')} | {'OUT' if t.transaction_type=='debit' else 'IN'} | "
                f"₹{float(t.amount):.0f} | {t.merchant_name or t.narration[:40] or 'Unknown'} | "
                f"{t.category.name if t.category else 'Other'}"
            )

        context = f"""You are FinBot, a personal finance AI for an Indian user.

USER'S FINANCIAL DATA:

Monthly Summary (last 3 months):
{json.dumps(months_data, indent=2)}

Recent Transactions (last 30):
{chr(10).join(txn_lines) if txn_lines else 'No transactions found.'}

INSTRUCTIONS:
- Answer in 2-4 short paragraphs max. Be specific with rupee amounts from the data.
- Give actionable advice based on their actual spending patterns.
- Use Indian context (₹, UPI, SIP, FD etc.)
- If asked where they spend most, name the actual top categories with amounts.
- If no data available, tell them to import transactions first.
- Do NOT make up numbers not in the data.
- Keep response concise and friendly."""

        try:
            import google.genai as genai
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            resp = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=f"{context}\n\nUSER QUESTION: {question}",
            )
            answer = resp.text.strip()
        except Exception as e:
            answer = f"Sorry, I couldn't process your question right now. Please try again. (Error: {str(e)[:100]})"

        return Response({"answer": answer})
