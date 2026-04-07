from django.db import models
from django.conf import settings


class Category(models.Model):
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, default="receipt")
    color = models.CharField(max_length=7, default="#6B7280")
    is_default = models.BooleanField(default=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="custom_categories",
    )

    class Meta:
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class BankAccount(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bank_accounts")
    bank_name = models.CharField(max_length=100)
    account_last4 = models.CharField(max_length=4, blank=True)
    account_type = models.CharField(max_length=50, default="savings")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.bank_name} **{self.account_last4}"


class Transaction(models.Model):
    SOURCE_SMS = "sms"
    SOURCE_PDF = "pdf"
    SOURCE_MANUAL = "manual"
    SOURCE_CHOICES = [
        (SOURCE_SMS, "SMS"),
        (SOURCE_PDF, "PDF"),
        (SOURCE_MANUAL, "Manual"),
    ]

    TYPE_DEBIT = "debit"
    TYPE_CREDIT = "credit"
    TYPE_CHOICES = [
        (TYPE_DEBIT, "Debit"),
        (TYPE_CREDIT, "Credit"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions")
    bank_account = models.ForeignKey(BankAccount, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateTimeField()
    narration = models.TextField(blank=True)
    merchant_name = models.CharField(max_length=200, blank=True)
    reference_number = models.CharField(max_length=100, blank=True)
    account_last4 = models.CharField(max_length=4, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    raw_text = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["user", "transaction_type"]),
            models.Index(fields=["reference_number"]),
        ]

    def __str__(self):
        return f"{self.transaction_type} {self.amount} - {self.merchant_name or self.narration[:30]}"
