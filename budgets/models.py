from django.db import models
from django.conf import settings
from transactions.models import Category


class Budget(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="budgets")
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    monthly_limit = models.DecimalField(max_digits=12, decimal_places=2)
    month = models.CharField(max_length=7)  # YYYY-MM

    class Meta:
        unique_together = [["user", "category", "month"]]
        ordering = ["-month"]

    def __str__(self):
        return f"{self.user} - {self.category} - {self.month}"
