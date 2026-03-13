# companies/views.py
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError, NotFound
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.core.mail import get_connection, EmailMessage
from rest_framework import generics, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from .models import (
    SMTPConfiguration, 
    Company,
    CompanyPerson,
)
from .serializers import (
    CompanySerializer,
    SMTPConfigurationSerializer, 
    SMTPTestSerializer, SMTPPresetSerializer,
    CompanyPersonSerializer,
)

from notifications.utils import (
    notify_interviewer_added,
    notify_avatar_updated
)

class CompanyCreateView(generics.CreateAPIView):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        if self.request.user.company:
            raise ValidationError("You have already created a company.")
        # Extract logo from validated data
        logo_file = serializer.validated_data.pop('logo', None)
        # Create company and link to user
        company = serializer.save()

        if logo_file:
            company.logo = logo_file
            company.save()
            print(f"Logo uploaded for company {company.id}: {company.logo.name}")
        
        # Send Synchronous Acknowledge Email
        try:
            user = self.request.user
            subject = f"Welcome to OrbitOne - {company.name}"
            
            # Use Django settings and utilities
            from django.conf import settings
            from django.core.mail import EmailMultiAlternatives
            from django.utils.html import strip_tags

            # Custom branding
            sender_name = "OrbitOne"
            # Attempt to set a custom From name, falling back to default email if needed
            from_email = f"{sender_name} <{settings.DEFAULT_FROM_EMAIL}>"

            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; background-color: #f4f4f4; margin: 0; padding: 0; }}
                    .container {{ max-width: 600px; margin: 20px auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
                    .header {{ background-color: #ffffff; padding: 30px; text-align: center; border-bottom: 3px solid #6c5ce7; }}
                    .logo {{ max-width: 180px; height: auto; }}
                    .content {{ padding: 30px; }}
                    .status-box {{ background-color: #e8f0fe; border-left: 4px solid #4285f4; padding: 15px; margin: 20px 0; border-radius: 4px; }}
                    .footer {{ background-color: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #888; border-top: 1px solid #eee; }}
                    h2 {{ color: #2d3436; margin-top: 0; }}
                    p {{ margin-bottom: 15px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <img src="https://pub-dc64bbbe864b4f79b3fdd114bf9d76b3.r2.dev/landing/web-s-logo.webp" alt="OrbitOne Logo" class="logo">
                    </div>
                    <div class="content">
                        <h2>Welcome to OrbitOne!</h2>
                        <p>Dear {user.first_name},</p>
                        <p>We are thrilled to acknowledge your request to register <strong>"{company.name}"</strong> with OrbitOne.</p>
                        
                        <div class="status-box">
                            <strong>Status: PENDING APPROVAL</strong><br>
                            Your application is currently under review by our team.
                        </div>

                        <p>We will notify you immediately once the verification process is complete.</p>
                        
                        <p>Best regards,<br>The OrbitOne Team</p>
                    </div>
                    <div class="footer">
                        <p>&copy; {timezone.now().year} OrbitOne. All rights reserved.</p>
                        <p>This is an automated message, please do not reply directly to this email.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            text_content = strip_tags(html_content)
            
            print(f"Sending acknowledgement email to {user.email}...")
            msg = EmailMultiAlternatives(
                subject,
                text_content,
                from_email,
                [user.email]
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send()
            
            print("Acknowledgement email sent successfully.")
            
        except Exception as e:
            print(f"Failed to send acknowledgement email: {str(e)}")

        self.request.user.company = company
        self.request.user.save()

class CompanyDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CompanySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        # return self.request.user.company
        company = self.request.user.company
        if company is None:
            raise NotFound("You have not eligble to access it. Pleas Creat a company first.")
        return company
    
    def perform_update(self, serializer):
        """Handle logo updates properly"""
        # If no logo in request but logo exists, keep existing logo
        if 'logo' not in self.request.data and serializer.instance.logo:
            serializer.validated_data['logo'] = serializer.instance.logo
        instance = serializer.save()
        
        return instance
    


# # Create View
# class InterviewerCreateView(generics.CreateAPIView):
#     serializer_class = InterviewerSerializer
#     permission_classes = [permissions.IsAuthenticated]

#     def perform_create(self, serializer):
#         serializer.save(company=self.request.user.company)

# # List View
# class InterviewerListView(generics.ListAPIView):
#     serializer_class = InterviewerSerializer
#     permission_classes = [permissions.IsAuthenticated]

#     def get_queryset(self):
#         return Interviewer.objects.filter(company=self.request.user.company)

# # Update/Delete/Retrieve View
# class InterviewerDetailView(generics.RetrieveUpdateDestroyAPIView):
#     serializer_class = InterviewerSerializer
#     permission_classes = [permissions.IsAuthenticated]

#     def get_queryset(self):
#         # Ensure users can only access interviewers from their company
#         return Interviewer.objects.filter(company=self.request.user.company)
    
# 🔹 Create View
class CompanyPersonCreateView(generics.CreateAPIView):
    serializer_class = CompanyPersonSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        person = serializer.save(company=self.request.user.company)
        # Notification handled by post_save signal in signals.py


# 🔹 List View (with filtering, search, and ordering)
class CompanyPersonListView(generics.ListAPIView):
    serializer_class = CompanyPersonSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    # Fields that can be filtered exactly
    filterset_fields = ['role']

    # Fields that can be searched (partial match)
    search_fields = ['name', 'email']

    # Fields that can be used for ordering
    ordering_fields = ['created_at', 'name', 'role']

    def get_queryset(self):
        # Restrict results to people from the user's company only
        return CompanyPerson.objects.filter(company=self.request.user.company)


# 🔹 Detail View
class CompanyPersonDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CompanyPersonSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CompanyPerson.objects.filter(company=self.request.user.company)

    def perform_update(self, serializer):
        person = serializer.save()
        # Notification handled by post_save signal in signals.py

# ==================== SMTP Configuration Views ====================

class SMTPConfigurationCreateView(generics.CreateAPIView):
    """Create SMTP configuration for company"""
    serializer_class = SMTPConfigurationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        company = self.request.user.company
        if not company:
            raise ValidationError("You must have a company to configure SMTP.")
        
        if hasattr(company, 'smtp_config'):
            raise ValidationError("SMTP configuration already exists. Use update endpoint.")
        
        serializer.save(company=company)


class SMTPConfigurationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete SMTP configuration"""
    serializer_class = SMTPConfigurationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        company = self.request.user.company
        if not company:
            raise NotFound("You must have a company to access SMTP configuration.")
        
        if not hasattr(company, 'smtp_config'):
            raise NotFound("SMTP configuration not found. Create one first.")
        
        return company.smtp_config


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def test_smtp_configuration(request):
    """Test SMTP configuration by sending a test email"""
    
    company = request.user.company
    if not company:
        return Response({
            'error': 'You must have a company to test SMTP configuration.'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if not hasattr(company, 'smtp_config'):
        return Response({
            'error': 'No SMTP configuration found. Create one first.'
        }, status=status.HTTP_404_NOT_FOUND)
    
    smtp_config = company.smtp_config
    
    # Validate request data
    serializer = SMTPTestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # Get test email (use provided email or company admin email)
    test_email = serializer.validated_data.get('test_email')
    if not test_email:
        if hasattr(company, 'admin_user') and company.admin_user:
            test_email = company.admin_user.email
        else:
            test_email = request.user.email
    
    try:
        # Create email connection with company SMTP settings
        connection = get_connection(**smtp_config.get_connection_params())
        
        # Create test email
        subject = f"SMTP Test from {company.name}"
        message = f"""
        This is a test email from {company.name}.
        
        If you received this email, your SMTP configuration is working correctly.
        
        Configuration Details:
        - Provider: {smtp_config.get_provider_display()}
        - Host: {smtp_config.smtp_host}
        - Port: {smtp_config.smtp_port}
        - Security: {'TLS' if smtp_config.use_tls else 'SSL' if smtp_config.use_ssl else 'None'}
        
        Test sent at: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}
        
        Best regards,
        {company.name} Team
        """
        
        email = EmailMessage(
            subject=subject,
            body=message,
            from_email=smtp_config.get_from_email(),
            to=[test_email],
            connection=connection
        )
        
        # Send the email
        email.send()
        
        # Update SMTP config status
        smtp_config.is_verified = True
        smtp_config.last_tested = timezone.now()
        smtp_config.test_error = ""
        smtp_config.save()
        
        return Response({
            'success': True,
            'message': f'Test email sent successfully to {test_email}',
            'tested_at': smtp_config.last_tested,
            'configuration': {
                'provider': smtp_config.get_provider_display(),
                'host': smtp_config.smtp_host,
                'port': smtp_config.smtp_port,
                'security': 'TLS' if smtp_config.use_tls else 'SSL' if smtp_config.use_ssl else 'None'
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        # Update SMTP config with error
        smtp_config.is_verified = False
        smtp_config.last_tested = timezone.now()
        smtp_config.test_error = str(e)
        smtp_config.save()
        
        return Response({
            'success': False,
            'error': f'SMTP test failed: {str(e)}',
            'tested_at': smtp_config.last_tested,
            'suggestions': [
                'Check your email and password',
                'Verify SMTP host and port settings',
                'Ensure SSL/TLS settings are correct',
                'For Gmail, use App Password instead of regular password',
                'Check if your email provider requires "Less secure app access"'
            ]
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_smtp_presets(request):
    """Get SMTP presets for different providers"""
    
    provider = request.query_params.get('provider')
    if provider:
        serializer = SMTPPresetSerializer(data={'provider': provider})
        if serializer.is_valid():
            return Response(serializer.to_representation({}))
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # Return all presets
    presets = {}
    for provider_code, provider_name in SMTPConfiguration.SMTP_PROVIDERS:
        serializer = SMTPPresetSerializer(data={'provider': provider_code})
        if serializer.is_valid():
            presets[provider_code] = {
                'name': provider_name,
                'settings': serializer.to_representation({})
            }
    
    return Response(presets)

class CompanyAdminActionView(generics.UpdateAPIView):
    """
    Admin View to Approve or Reject a Company.
    Sends synchronous email notification.
    """
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    # Adjust permission to IsAdminUser for real production security
    permission_classes = [permissions.IsAdminUser] 

    def patch(self, request, *args, **kwargs):
        company = self.get_object()
        new_status = request.data.get('status')
        remarks = request.data.get('rejection_remarks', '')

        if new_status not in ['approved', 'rejected']:
             return Response(
                {"error": "Invalid status. Must be 'approved' or 'rejected'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        company.status = new_status
        if new_status == 'rejected':
            company.rejection_remarks = remarks
        else:
            company.rejection_remarks = "" # Clear remarks if approved
        
        company.save()

        # Email Notification is now handled by signals.py

        return Response(CompanySerializer(company).data)
