from django.urls import path
from .views import(
    RegisterView, LoginView, LogoutView,
    RequestPasswordResetView, VerifyOTPView,
    SetNewPasswordView, DeactivateAccountView,
    UserProfileView, ChangePasswordView, UserSettingsView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'), 
    path('login/', LoginView.as_view(), name='login'),          
    path('logout/', LogoutView.as_view(), name='logout'),
    path('password-reset/request/', RequestPasswordResetView.as_view(), name='request-password-reset'),
    path('password-reset/verify/', VerifyOTPView.as_view(), name='verify-otp'),
    path('password-reset/confirm/', SetNewPasswordView.as_view(), name='set-new-password'),
    path('deactivate/', DeactivateAccountView.as_view(), name='deactivate'),
    path('profile/', UserProfileView.as_view(), name='user-profile'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('settings/', UserSettingsView.as_view(), name='user-settings'),
]