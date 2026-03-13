from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model
from .models import Company, CompanyPerson
from notifications.utils import (
    notify_company_approved, 
    notify_company_rejected,
    notify_interviewer_added,
    notify_avatar_updated
)

@receiver(pre_save, sender=Company)
def send_company_status_email(sender, instance, **kwargs):
    # Only check if it's an existing company (update)
    if not instance.pk:
        return

    try:
        old_company = Company.objects.get(pk=instance.pk)
    except Company.DoesNotExist:
        return

    # Check if status has changed
    if old_company.status == instance.status:
        return

    # Status has changed, prepare to send email
    new_status = instance.status
    User = get_user_model()
    
    # Find the company admin
    # User model has a OneToOneField to Company with related_name='admin_user'
    if hasattr(instance, 'admin_user'):
        company_admin = instance.admin_user
    else:
        # Fallback or try query if strict reverse relation is not working (though OneToOne should)
        company_admin = User.objects.filter(company=instance).first()
    
    if not company_admin:
        print(f"Signal: No admin found for company {instance.name}")
        return

    # Use Django settings and utilities
    from django.conf import settings
    from django.core.mail import EmailMultiAlternatives
    from django.utils.html import strip_tags
    from django.utils import timezone

    # Custom branding
    sender_name = "OrbitOne"
    # Attempt to set a custom From name, falling back to default email if needed
    from_email = f"{sender_name} <{settings.DEFAULT_FROM_EMAIL}>"

    subject = f"Company Application Update - {instance.name}"
    
    status_content = ""

    if new_status == 'approved':
        status_content = f"""
        <div class="status-box" style="background-color: #e6fffa; border-left: 4px solid #00b894; padding: 15px; margin: 20px 0; border-radius: 4px;">
            <strong>Status: APPROVED</strong><br>
            Congratulations! Your company "{instance.name}" has been approved. You can now log in and access your dashboard.
        </div>
        """
    elif new_status == 'rejected':
        remarks = instance.rejection_remarks
        status_content = f"""
        <div class="status-box" style="background-color: #fff5f5; border-left: 4px solid #ff7675; padding: 15px; margin: 20px 0; border-radius: 4px;">
            <strong>Status: REJECTED</strong><br>
            We regret to inform you that your request for company "{instance.name}" has been rejected.<br><br>
            <strong>Remarks:</strong><br>
            {remarks}
        </div>
        <p>Please contact support for further assistance if you believe this is an error.</p>
        """
    else:
        # Pending or other status change we don't notify for?
        return

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
                <h2>Company Application Update</h2>
                <p>Dear {company_admin.first_name},</p>
                
                {status_content}
                
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

    try:
        print(f"Signal: Sending status ({new_status}) email to {company_admin.email}...")
        msg = EmailMultiAlternatives(
            subject,
            text_content,
            from_email,
            [company_admin.email]
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send()
        
        print("Signal: Email sent successfully.")
        
        # Trigger Dashboard Notification
        try:
            if new_status == 'approved':
                notify_company_approved(instance)
            elif new_status == 'rejected':
                notify_company_rejected(instance, remarks)
        except Exception as e:
            print(f"Signal: Failed to create notification: {str(e)}")
    except Exception as e:
        print(f"Signal: Failed to send email: {str(e)}")


@receiver(post_save, sender=CompanyPerson)
def notify_company_person_changes(sender, instance, created, **kwargs):
    """Trigger notifications when a company person (interviewer) is added or updated"""
    try:
        if created:
            notify_interviewer_added(instance.company, instance.name)
        else:
            # This covers avatar updates as well since avatar is a field on CompanyPerson
            notify_avatar_updated(instance.company, instance.name)
    except Exception as e:
        print(f"Signal Error (CompanyPerson): {str(e)}")
