from django.urls import path
from .views import SendOTPView, VerifyOTPView, RefreshTokenView, ProfileView

urlpatterns = [
    path("send-otp/", SendOTPView.as_view(), name="send-otp"),
    path("verify-otp/", VerifyOTPView.as_view(), name="verify-otp"),
    path("refresh/", RefreshTokenView.as_view(), name="refresh"),
    path("profile/", ProfileView.as_view(), name="profile"),
]
