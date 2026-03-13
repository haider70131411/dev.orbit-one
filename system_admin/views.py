# admin_app/views.py
from rest_framework import generics, status
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from system_admin.permissions import IsSuperAdmin
from system_admin.serializers import AdminUserListSerializer
from accounts.serializers import UserRegistrationSerializer, SetNewPasswordSerializer
from accounts.models import PasswordResetOTP
from django.core.mail import send_mail
from django.conf import settings

User = get_user_model()

# 1. List all users
class AdminUserListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    queryset = User.objects.all().order_by('-id')
    serializer_class = AdminUserListSerializer

# 2. Get single user details
class AdminUserDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    queryset = User.objects.all()
    serializer_class = AdminUserListSerializer
    lookup_field = "id"

# 3. Create new user
class AdminUserCreateView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    serializer_class = UserRegistrationSerializer

# 4. Update user details
class AdminUserUpdateView(generics.UpdateAPIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    lookup_field = "id"

# 5. Deactivate user
class AdminDeactivateUserView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request, id):
        try:
            user = User.objects.get(id=id)
            user.is_active = False
            user.save()
            return Response({"message": "User deactivated successfully"}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

# 6. Reactivate user
class AdminReactivateUserView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request, id):
        try:
            user = User.objects.get(id=id)
            user.is_active = True
            user.save()
            return Response({"message": "User reactivated successfully"}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

# 7. Delete user
class AdminDeleteUserView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def delete(self, request, id):
        try:
            user = User.objects.get(id=id)
            user.delete()
            return Response({"message": "User deleted successfully"}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

# 8. Force password reset (generate and send OTP)
class AdminForcePasswordResetView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request, id):
        try:
            user = User.objects.get(id=id)
            PasswordResetOTP.objects.filter(user=user).delete()
            otp_obj = PasswordResetOTP.objects.create(user=user)
            send_mail(
                "Password Reset OTP (Admin)",
                f"Your OTP is: {otp_obj.otp} (valid for 10 minutes)",
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
            return Response({"message": "OTP sent to user's email"}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

# 9. Admin set new password directly
class AdminSetPasswordView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request, id):
        serializer = SetNewPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = User.objects.get(id=id)
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            return Response({"message": "Password updated successfully"}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
