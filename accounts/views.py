import requests
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, OTPToken
from .serializers import SendOTPSerializer, VerifyOTPSerializer, UserSerializer


def send_otp_via_communication_service(phone_number, otp_code):
    data = {
        "payload": {
            "mobile": phone_number,
            "template_id": getattr(settings, "OTP_TEMPLATE_ID", "66d5e5b8d6fc05264b2bfab4"),
            "message": f"Your FinTrack OTP is {otp_code}. Valid for 10 minutes. Do not share.",
            "variable_list": [otp_code, "q4sPmhmf9K5"],
        },
        "communication_channel": "msg",
    }
    try:
        response = requests.post(
            settings.COMMUNICATION_FUNCTION_URL,
            json=data,
            timeout=10,
        )
        return response.status_code == 200
    except Exception:
        return False


class SendOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SendOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        phone_number = serializer.validated_data["phone_number"]
        otp_token = OTPToken.generate_otp(phone_number)
        sent = send_otp_via_communication_service(phone_number, otp_token.otp_code)

        if not sent:
            # For beta: log the OTP if SMS fails (remove in production)
            print(f"[BETA OTP] {phone_number}: {otp_token.otp_code}")

        return Response(
            {"message": "OTP sent successfully", "phone_number": phone_number},
            status=status.HTTP_200_OK,
        )


class VerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        phone_number = serializer.validated_data["phone_number"]
        otp_code = serializer.validated_data["otp_code"]

        # Master OTP for testing
        MASTER_OTP = "119191"
        if otp_code == MASTER_OTP:
            user, created = User.objects.get_or_create(phone_number=phone_number)
            refresh = RefreshToken.for_user(user)
            return Response(
                {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "user": UserSerializer(user).data,
                    "is_new_user": created,
                },
                status=status.HTTP_200_OK,
            )

        try:
            otp_token = OTPToken.objects.filter(
                phone_number=phone_number,
                otp_code=otp_code,
                is_used=False,
            ).latest("created_at")
        except OTPToken.DoesNotExist:
            return Response(
                {"error": "Invalid OTP"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not otp_token.is_valid():
            return Response(
                {"error": "OTP has expired"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        otp_token.is_used = True
        otp_token.save()

        user, created = User.objects.get_or_create(phone_number=phone_number)
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
                "is_new_user": created,
            },
            status=status.HTTP_200_OK,
        )


class RefreshTokenView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"error": "Refresh token required"}, status=400)
        try:
            refresh = RefreshToken(refresh_token)
            return Response({"access": str(refresh.access_token)})
        except Exception:
            return Response({"error": "Invalid or expired refresh token"}, status=401)


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)
