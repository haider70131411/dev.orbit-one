
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

        # Send Synchronous Email Notification
        try:
            # Find the admin user for this company to send email
            # Assuming the user who created it is linked via OneToOne or stored logic.
            # In current logic: user.company = company. 
            # So we query User where company = this company.
            from django.contrib.auth import get_user_model
            User = get_user_model()
            # Since OneToOne or ForeignKey relation might differ, let's find the user.
            # Based on User model analysis (not fully shown but implied OneToOne/Foreign), 
            # let's try reverse relation if User has company field.
            
            company_admin = User.objects.filter(company=company).first()
            
            if company_admin:
                subject = f"Company Application Update - {company.name}"
                if new_status == 'approved':
                    message = f"""
                    Dear {company_admin.first_name},

                    Congratulations! Your company "{company.name}" has been APPROVED.
                    
                    You can now log in and access your dashboard.

                    Best regards,
                    Avatar Interview Platform Team
                    """
                else:
                    message = f"""
                    Dear {company_admin.first_name},

                    We regret to inform you that your request for company "{company.name}" has been REJECTED.

                    Remarks:
                    {remarks}

                    Please contact support for further assistance.

                    Best regards,
                    Avatar Interview Platform Team
                    """
                
                from django.core.mail import send_mail
                from django.conf import settings
                
                print(f"Sending status update email to {company_admin.email}...")
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [company_admin.email],
                    fail_silently=False,
                )
                print("Status update email sent.")
            else:
                 print("No company admin user found to send email.")

        except Exception as e:
            print(f"Failed to send status email: {str(e)}")

        return Response(CompanySerializer(company).data)
