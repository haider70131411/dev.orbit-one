from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone
from django.core.exceptions import ValidationError
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.files.storage import default_storage
import base64
import uuid
from avatars.models import Avatar

def company_logo_upload_path(instance, filename):
    """Generate upload path for company logos"""
    # file extension
    ext = filename.split('.')[-1].lower()

    # Use company ID if exists, otherwise use UUID
    if instance.pk:
        company_id = instance.pk
    else:
        # For new companies, use a UUID
        company_id = str(uuid.uuid4())[:8]
    
    # Create new filename: company_id + timestamp + extension
    timestamp = int(timezone.now().timestamp())
    new_filename = f"company_{company_id}_{timestamp}.{ext}"
    return f"company_logos/{new_filename}"

class Company(models.Model):
    COMPANY_TYPES = (
        ('startup', 'Startup'),
        ('sme', 'SME'),
        ('enterprise', 'Enterprise'),
        ('non_profit', 'Non-Profit'),
        ('government', 'Government'),
        ('educational', 'Educational'),
        ('freelancer', 'Freelancer'),
        ('ngo', 'NGO'),
        ('cooperative', 'Cooperative'),
    )

    INDUSTRIES = (
        ('tech', 'Technology'),
        ('finance', 'Finance'),
        ('healthcare', 'Healthcare'),
        ('education', 'Education'),
        ('manufacturing', 'Manufacturing'),
        ('retail', 'Retail / E-Commerce'),
        ('media', 'Media & Entertainment'),
        ('agriculture', 'Agriculture'),
        ('real_estate', 'Real Estate'),
        ('transport', 'Transportation & Logistics'),
        ('energy', 'Energy & Utilities'),
        ('consulting', 'Consulting & Professional Services'),
        ('hospitality', 'Hospitality & Tourism'),
        ('construction', 'Construction & Infrastructure'),
        ('telecom', 'Telecommunications'),
        ('other', 'Other'),
    )

    # Core Information
    name = models.CharField(max_length=100)
    company_type = models.CharField(max_length=20, choices=COMPANY_TYPES,default='startup', blank=True )
    industry = models.CharField(max_length=20, choices=INDUSTRIES, default='tech', blank=True)
    website = models.URLField(blank=True)
    logo = models.ImageField(upload_to=company_logo_upload_path, blank=True, null=True)
    description = models.TextField(blank=True)

    # Status Fields
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    rejection_remarks = models.TextField(blank=True)
    
    # Contact Information
    address_country = models.CharField(max_length=50 , blank=True, null=True)
    address_city = models.CharField(max_length=50,  blank=True, null=True)
    address_street = models.CharField(max_length=100 , blank=True, null=True)
    address_postal = models.CharField(max_length=20, blank=True, null=True)
    contact_number  = models.CharField(max_length=20, blank=True)
    support_email = models.EmailField(default="support@example.com")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def admin_email(self):
        return self.admin_user.email if hasattr(self, 'admin_user') else None
    admin_email.short_description = 'Admin Email'

   
    def has_smtp_config(self):
        """Check if company has SMTP configuration"""
        return hasattr(self, 'smtp_config') and self.smtp_config.is_active
    

    def delete_old_logo(self):
        """Delete old logo file - works with both local and cloud storage"""
        if self.logo:
            try:
                if default_storage.exists(self.logo.name):
                    default_storage.delete(self.logo.name)
            except Exception as e:
                print(f"Error deleting old logo: {str(e)}")
    

    def save(self, *args, **kwargs):
        """Override save to handle logo updates"""
        if self.pk:
            try:
                old_company = Company.objects.get(pk=self.pk)
                # Compare file names instead of file objects
                old_logo_name = old_company.logo.name if old_company.logo else None
                new_logo_name = self.logo.name if self.logo else None
                
                # Delete old logo if changed
                if old_logo_name and old_logo_name != new_logo_name:
                    old_company.delete_old_logo()
            except Company.DoesNotExist:
                pass
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        # Delete logo file when deleting company
        self.delete_old_logo()
        super().delete(*args, **kwargs)

    def __str__(self):
        return self.name
    

# Signal handler - OUTSIDE the Company class
@receiver(pre_delete, sender='accounts.User')  # Use string reference
def delete_related_company(sender, instance, **kwargs):
    """Delete company when user is deleted"""
    if hasattr(instance, 'company') and instance.company:
        instance.company.delete()


# class Interviewer(models.Model):
#     company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='interviewers')
#     name = models.CharField(max_length=100)
#     email = models.EmailField()
#     phone = models.CharField(max_length=20, blank=True)
#     avatar = models.ForeignKey(Avatar, on_delete=models.SET_NULL, null=True, blank=True, related_name='interviewers')

#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"{self.name} ({self.email})"
class CompanyPerson(models.Model):
    ROLE_CHOICES = [
        ('ceo', 'CEO'),
        ('cfo', 'CFO'),
        ('coo', 'COO'),
        ('cto', 'CTO'),
        ('cio', 'CIO'),
        ('cmo', 'CMO'),
        ('cmc', 'Chief Marketing Officer'),
        ('manager', 'Manager'),
        ('team_lead', 'Team Lead'),
        ('developer', 'Developer / Engineer'),
        ('designer', 'Designer'),
        ('qa', 'QA / Tester'),
        ('product_owner', 'Product Owner'),
        ('project_manager', 'Project Manager'),
        ('hr', 'HR'),
        ('recruiter', 'Recruiter'),
        ('intern', 'Intern'),
        ('interviewer', 'Interviewer'),
        ('consultant', 'Consultant'),
        ('advisor', 'Advisor'),
        ('board_member', 'Board Member'),
        ('other', 'Other'),
    ]


    company = models.ForeignKey(
        'Company',
        on_delete=models.CASCADE,
        related_name='people'
    )
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='interviewer')
    avatar = models.ForeignKey(
        Avatar, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='company_people'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_role_display()}) - {self.company.name}"


class SMTPConfiguration(models.Model):
    """SMTP Configuration for each company"""    
    SMTP_PROVIDERS = (
        ('gmail', 'Gmail'),
        ('outlook', 'Outlook/Office365'),
        ('yahoo', 'Yahoo Mail'),
        ('zoho', 'Zoho Mail'),
        ('custom', 'Custom Domain'),
    )
    
    company = models.OneToOneField('Company', on_delete=models.CASCADE, related_name='smtp_config')
    provider = models.CharField(max_length=20, choices=SMTP_PROVIDERS, default='gmail')
    
    # SMTP Settings
    smtp_host = models.CharField(max_length=255, help_text="e.g., smtp.gmail.com")
    smtp_port = models.IntegerField(help_text="587 for TLS, 465 for SSL")
    smtp_username = models.EmailField(help_text="Your email address")
    smtp_password = models.TextField(help_text="Encrypted password")  # Will be encrypted
    
    # Security Settings
    use_tls = models.BooleanField(default=True, help_text="Use TLS (recommended for port 587)")
    use_ssl = models.BooleanField(default=False, help_text="Use SSL (for port 465)")
    
    # Email Settings
    from_email = models.EmailField(help_text="Display email address")
    from_name = models.CharField(max_length=100, blank=True, help_text="Display name")
    
    # Status
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    last_tested = models.DateTimeField(null=True, blank=True)
    test_error = models.TextField(blank=True, help_text="Last test error message")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "SMTP Configuration"
        verbose_name_plural = "SMTP Configurations"
    
    def clean(self):
        """Validate SMTP configuration"""
        # Rule 1: Cannot use both SSL and TLS
        if self.use_ssl and self.use_tls:
            raise ValidationError("Cannot use both SSL and TLS. Choose one.")
        
        # Rule 2: Must use either SSL or TLS
        if not self.use_ssl and not self.use_tls:
            raise ValidationError("Must use either SSL or TLS for secure connection.")
        
        # Rule 3: Port validation
        if self.use_tls and self.smtp_port not in [587, 25]:
            raise ValidationError("TLS typically uses port 587 or 25.")
        
        if self.use_ssl and self.smtp_port != 465:
            raise ValidationError("SSL typically uses port 465.")
        
        # Rule 4: Provider-specific validation
        if self.provider == 'gmail' and 'gmail.com' not in self.smtp_host:
            raise ValidationError("Gmail provider should use smtp.gmail.com")
        
        if self.provider == 'outlook' and 'office365.com' not in self.smtp_host:
            raise ValidationError("Outlook provider should use smtp.office365.com")
    
    def encrypt_password(self, password):
        """Encrypt password before saving"""
        if not hasattr(settings, 'SMTP_ENCRYPTION_KEY'):
            raise ValueError("SMTP_ENCRYPTION_KEY not found in settings")
        
        fernet = Fernet(settings.SMTP_ENCRYPTION_KEY.encode())
        encrypted_password = fernet.encrypt(password.encode())
        return base64.urlsafe_b64encode(encrypted_password).decode()
    
    def decrypt_password(self):
        """Decrypt password for use"""
        if not self.smtp_password:
            return ""
        
        fernet = Fernet(settings.SMTP_ENCRYPTION_KEY.encode())
        decoded_password = base64.urlsafe_b64decode(self.smtp_password.encode())
        return fernet.decrypt(decoded_password).decode()
    
    def save(self, *args, **kwargs):
        # Auto-fill common settings based on provider
        if self.provider == 'gmail' and not self.smtp_host:
            self.smtp_host = 'smtp.gmail.com'
            self.smtp_port = 587
            self.use_tls = True
            self.use_ssl = False
        
        elif self.provider == 'outlook' and not self.smtp_host:
            self.smtp_host = 'smtp.office365.com'
            self.smtp_port = 587
            self.use_tls = True
            self.use_ssl = False
        
        elif self.provider == 'yahoo' and not self.smtp_host:
            self.smtp_host = 'smtp.mail.yahoo.com'
            self.smtp_port = 587
            self.use_tls = True
            self.use_ssl = False
        
        elif self.provider == 'zoho' and not self.smtp_host:
            self.smtp_host = 'smtp.zoho.com'
            self.smtp_port = 587
            self.use_tls = True
            self.use_ssl = False
        
        # Set default from_name if not provided
        if not self.from_name and hasattr(self, 'company'):
            self.from_name = self.company.name
        
        super().save(*args, **kwargs)
    
    def get_connection_params(self):
        """Get connection parameters for Django email"""
        return {
            'host': self.smtp_host,
            'port': self.smtp_port,
            'username': self.smtp_username,
            'password': self.decrypt_password(),
            'use_tls': self.use_tls,
            'use_ssl': self.use_ssl,
            'fail_silently': False,
        }
    
    def get_from_email(self):
        """Get formatted from email"""
        if self.from_name:
            return f"{self.from_name} <{self.from_email}>"
        return self.from_email
    
    def __str__(self):
        return f"{self.company.name} - {self.provider} ({self.smtp_host})"