from django.core.mail import send_mail
from django.conf import settings
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from .models import PasswordResetOTP
from .serializers import(
    User, UserRegistrationSerializer, CustomTokenObtainPairSerializer,
    RequestPasswordResetSerializer, VerifyOTPSerializer, SetNewPasswordSerializer,
    ChangePasswordSerializer, UserProfileSerializer, UserSettingsSerializer,
)
from .models import UserSettings
# This thing need to be implemented Before Production 
# It prevent the multiple Request on the Server of Otp Or Brut Force Attack
#                           from django.utils.decorators import method_decorator
#                           from django_ratelimit.decorators import ratelimit


# Register Company Admin
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "User registered successfully!"},
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Login (JWT Token)
class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


# LogOut Functionality 
class LogoutView(APIView):
    def post(self, request):
        try:
            refresh_token = request.data["refresh_token"]
            token = RefreshToken(refresh_token)
            token.blacklist()  # Add token to blacklist
            return Response({"message": "Logged out successfully!"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# this Methode is requird As i Notify at the top comment in this page

# @method_decorator(
#     ratelimit(key='ip', rate='5/h', method='POST', block=True), 
#     name='dispatch'
# )

# Create OTP Functionality 
class RequestPasswordResetView(generics.GenericAPIView):
    serializer_class = RequestPasswordResetSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        user = User.objects.get(email=email)

        # Delete old OTPs
        PasswordResetOTP.objects.filter(user=user).delete()

        # Create and send new OTP
        otp_obj = PasswordResetOTP.objects.create(user=user)
        html_message = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Your OTP from TechSecure</title>
            <style type="text/css">
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}

                body {{
                    background-color: #f7f9fc;
                    color: #333333;
                    line-height: 1.6;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                }}

                .email-wrapper {{
                    width: 100%;
                    padding: 20px;
                }}

                .email-container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background-color: #ffffff;
                    border-radius: 20px;
                    overflow: hidden;
                }}

                .header {{
                    background: linear-gradient(135deg, #6a11cb 0%, #2575fc 100%);
                    padding: 40px 30px;
                    text-align: center;
                    color: #ffffff;
                }}

                .logo-container {{
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin-bottom: 20px;
                }}

                .logo {{
                    width: 60px;
                    height: 60px;
                    background-color: #ffffff;
                    border-radius: 12px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin-right: 15px;
                }}

                .logo-symbol {{
                    font-size: 28px;
                    font-weight: 800;
                    background: linear-gradient(135deg, #6a11cb 0%, #2575fc 100%);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                }}

                .company-name {{
                    font-size: 28px;
                    font-weight: 700;
                    letter-spacing: -0.5px;
                }}

                .header h1 {{
                    font-size: 28px;
                    font-weight: 600;
                    margin-top: 10px;
                }}

                .content {{
                    padding: 40px 35px;
                }}

                .welcome-text {{
                    font-size: 18px;
                    color: #444444;
                    margin-bottom: 25px;
                    line-height: 1.7;
                }}

                .otp-container {{
                    background: linear-gradient(135deg, #f6f9ff 0%, #f0f5ff 100%);
                    border-radius: 16px;
                    padding: 30px;
                    text-align: center;
                    margin: 30px 0;
                    border: 1px solid #e6eeff;
                }}

                .otp-label {{
                    font-size: 16px;
                    color: #666666;
                    margin-bottom: 15px;
                    display: block;
                }}

                .otp-code {{
                    font-size: 52px;
                    font-weight: 700;
                    letter-spacing: 8px;
                    color: #2d5bff;
                    margin: 15px 0;
                    padding: 5px;
                    background-color: #ffffff;
                    border-radius: 12px;
                    font-family: 'Courier New', Courier, monospace;
                }}

                .validity-note {{
                    color: #666666;
                    font-size: 15px;
                    margin-top: 20px;
                    padding: 12px 20px;
                    background-color: #fff9e6;
                    border-radius: 10px;
                    display: inline-block;
                    border-left: 4px solid #ffcc00;
                }}

                .instruction-box {{
                    background-color: #f8fafc;
                    border-radius: 12px;
                    padding: 25px;
                    margin-top: 35px;
                    border-left: 4px solid #2d5bff;
                }}

                .instruction-box h3 {{
                    color: #2d5bff;
                    margin-bottom: 15px;
                    font-size: 18px;
                }}

                .instruction-box ul {{
                    padding-left: 20px;
                }}

                .instruction-box li {{
                    margin-bottom: 10px;
                    color: #555555;
                }}

                .footer {{
                    background-color: #f8fafc;
                    padding: 30px;
                    text-align: center;
                    border-top: 1px solid #eef2f7;
                }}

                .footer-text {{
                    color: #777777;
                    font-size: 14px;
                    line-height: 1.6;
                    margin-bottom: 20px;
                }}

                .social-icons {{
                    display: flex;
                    justify-content: center;
                    margin: 25px 0;
                }}

                .social-icon {{
                    width: 40px;
                    height: 40px;
                    border-radius: 50%;
                    background-color: #eef2f7;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: #666666;
                    text-decoration: none;
                    margin: 0 10px;
                }}

                .copyright {{
                    color: #999999;
                    font-size: 13px;
                    margin-top: 20px;
                    padding-top: 20px;
                    border-top: 1px solid #eef2f7;
                }}

                @media only screen and (max-width: 600px) {{
                    .email-container {{
                        border-radius: 0;
                    }}

                    .header {{
                        padding: 30px 20px;
                    }}

                    .header h1 {{
                        font-size: 24px;
                    }}

                    .content {{
                        padding: 30px 25px;
                    }}

                    .otp-code {{
                        font-size: 42px;
                        letter-spacing: 6px;
                    }}

                    .footer {{
                        padding: 25px 20px;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="email-wrapper">
                <div class="email-container">
                    <div class="header">
                        <div class="logo-container">
                            <div class="logo">
                                <div class="logo-symbol"
                                <img src="https://pub-dc64bbbe864b4f79b3fdd114bf9d76b3.r2.dev/landing/web-s-logo.webp" >
                                </div>
                            </div>
                            <div class="company-name">OrbitOne</div>
                        </div>
                        <h1>One-Time Password Verification</h1>
                    </div>

                    <div class="content">
                        <p class="welcome-text">
                            Hello,<br><br>
                            You've requested to access your OrbitOne account.
                        </p>

                        <div class="otp-container">
                            <span class="otp-label">Your verification code is:</span>
                            <div class="otp-code">{otp_obj.otp}</div>
                            <div class="validity-note">
                                ⏳ This OTP is valid for <strong>10 minutes</strong>.
                            </div>
                        </div>
                    </div>

                    <div class="footer">
                        <p class="footer-text">
                            Need help? Contact support@OrbitOne.com
                        </p>
                        <p class="copyright">
                            © 2026 OrbitOne Inc. All rights reserved.
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """

        send_mail(
            "Your Password Reset OTP",
            f"Your OTP is: {otp_obj.otp} (valid for 10 minutes)",
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
            html_message=html_message,
        )
        return Response(
            {"message": "OTP sent to email!"},
            status=status.HTTP_200_OK,
        )

# OTP Verifivcation Functionality 
class VerifyOTPView(generics.GenericAPIView):
    serializer_class = VerifyOTPSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        otp = serializer.validated_data['otp']

        try:
            otp_obj = PasswordResetOTP.objects.get(user__email=email, otp=otp)
            if not otp_obj.is_valid():
                return Response(
                    {"error": "OTP expired"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            return Response(
                {"message": "OTP verified!"},
                status=status.HTTP_200_OK,
            )
        except PasswordResetOTP.DoesNotExist:
            return Response(
                {"error": "Invalid OTP"},
                status=status.HTTP_400_BAD_REQUEST,
            )


# Setup New Password Functionality 
class SetNewPasswordView(generics.GenericAPIView):
    serializer_class = SetNewPasswordSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        otp = serializer.validated_data['otp']
        new_password = serializer.validated_data['new_password']

        try:
            otp_obj = PasswordResetOTP.objects.get(user__email=email, otp=otp)
            if not otp_obj.is_valid():
                return Response(
                    {"error": "OTP expired"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Update password and delete OTP
            user = otp_obj.user
            user.set_password(new_password)
            user.save()
            otp_obj.delete()

            return Response(
                {"message": "Password updated successfully!"},
                status=status.HTTP_200_OK,
            )
        except PasswordResetOTP.DoesNotExist:
            return Response(
                {"error": "Invalid OTP"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
# Deactivate Functionality 
class DeactivateAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        user.is_active = False
        user.save()
        return Response(
            {"message": "Account deactivated successfully!"},
            status=status.HTTP_200_OK,
        )

# User Profile & Settings Views
class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get current user profile"""
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        """Update user profile"""
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Change user password"""
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            old_password = serializer.validated_data['old_password']
            new_password = serializer.validated_data['new_password']

            # Verify old password
            if not user.check_password(old_password):
                return Response(
                    {"error": "Current password is incorrect"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Set new password
            user.set_password(new_password)
            user.save()

            return Response(
                {"message": "Password changed successfully"},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get user settings"""
        user = request.user
        
        # Get or create user settings
        settings, created = UserSettings.objects.get_or_create(
            user=user,
            defaults={
                'notifications_email': True,
                'notifications_meetings': True,
                'notifications_campaigns': True,
                'security_session_timeout': 30,
                'security_password_expiry': 90,
            }
        )
        
        serializer = UserSettingsSerializer(settings)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        """Save user settings"""
        user = request.user
        
        # Get or create user settings
        settings, created = UserSettings.objects.get_or_create(user=user)
        
        serializer = UserSettingsSerializer(settings, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Settings saved successfully", "settings": serializer.data},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)