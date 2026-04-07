from rest_framework import serializers
from .models import User


class SendOTPSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15)

    def validate_phone_number(self, value):
        value = value.strip().replace(" ", "").replace("-", "")
        if not value.startswith("+"):
            if len(value) == 10:
                value = "+91" + value
        return value


class VerifyOTPSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15)
    otp_code = serializers.CharField(max_length=6, min_length=6)

    def validate_phone_number(self, value):
        value = value.strip().replace(" ", "").replace("-", "")
        if not value.startswith("+"):
            if len(value) == 10:
                value = "+91" + value
        return value


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "phone_number", "name", "created_at"]
        read_only_fields = ["id", "phone_number", "created_at"]
