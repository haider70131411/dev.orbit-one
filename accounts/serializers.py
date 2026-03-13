from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from companies.serializers import CompanySerializer
from shared.passwordValidator import validate_password_strength
from shared.phonenumberValidator import validate_phone_number

User = get_user_model()

class UserRegistrationSerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['email', 'password', 'first_name', 'last_name', 'phone', 'company']
  
    def validate_password(self, value):
        return validate_password_strength(value)
    
    def validate_phone(self, value):
        return validate_phone_number(value)
    
    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        # Check email exists
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                {"email": "Email does not exist."}
            )

        # Check password
        if not user.check_password(password):
            raise serializers.ValidationError(
                {"password": "Wrong password. Please enter the correct password."}
            )

        # Check active
        if not user.is_active:
            raise serializers.ValidationError(
                {"email": "This account is inactive."}
            )

        return super().validate(attrs)

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["is_company_admin"] = user.is_company_admin
        token["is_staff"] = user.is_staff
        token["is_superuser"] = getattr(user, 'is_superuser', False)
        return token

class RequestPasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("No user found with this email.")
        return value

class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)

class SetNewPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        return validate_password_strength(value)

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True)

    def validate_new_password(self, value):
        return validate_password_strength(value)

class UserProfileSerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'phone', 'company', 'is_active', 'date_joined']
        read_only_fields = ['id', 'email', 'company', 'is_active', 'date_joined']

class UserSettingsSerializer(serializers.ModelSerializer):
    """Serializer for user preferences/settings"""
    
    class Meta:
        from .models import UserSettings
        model = UserSettings
        fields = [
            'notifications_email',
            'notifications_meetings',
            'notifications_campaigns',
            'security_session_timeout',
            'security_password_expiry',
        ]
        extra_kwargs = {
            'security_session_timeout': {'min_value': 5, 'max_value': 120},
            'security_password_expiry': {'min_value': 30, 'max_value': 365},
        }