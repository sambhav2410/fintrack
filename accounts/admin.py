from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, OTPToken


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["phone_number", "name", "created_at", "is_active"]
    search_fields = ["phone_number", "name"]
    ordering = ["-created_at"]
    fieldsets = (
        (None, {"fields": ("phone_number", "name", "password")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser")}),
    )
    add_fieldsets = (
        (None, {"fields": ("phone_number",)}),
    )


@admin.register(OTPToken)
class OTPTokenAdmin(admin.ModelAdmin):
    list_display = ["phone_number", "otp_code", "created_at", "expires_at", "is_used"]
    list_filter = ["is_used"]
    search_fields = ["phone_number"]
