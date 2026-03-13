from rest_framework import serializers
from .models import Company, CompanyPerson, SMTPConfiguration
from shared.phonenumberValidator import validate_phone_number


class SMTPConfigurationSerializer(serializers.ModelSerializer):
    """SMTP Configuration Serializer"""    
    # Write-only password field
    smtp_password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    # Read-only status fields
    is_verified = serializers.BooleanField(read_only=True)
    last_tested = serializers.DateTimeField(read_only=True)
    test_error = serializers.CharField(read_only=True)    
    # Helper fields
    password_is_set = serializers.SerializerMethodField()
    provider_display = serializers.CharField(source='get_provider_display', read_only=True)
    
    class Meta:
        model = SMTPConfiguration
        fields = [
            'id', 'provider', 'provider_display',
            'smtp_host', 'smtp_port', 'smtp_username', 'smtp_password',
            'use_tls', 'use_ssl',
            'from_email', 'from_name',
            'is_active', 'is_verified', 'last_tested', 'test_error',
            'password_is_set', 'created_at', 'updated_at'
        ]
        read_only_fields = ('created_at', 'updated_at')
    
    def get_password_is_set(self, obj):
        """Check if password is set (without revealing it)"""
        return bool(obj.smtp_password)
    
    def validate(self, data):
        """Custom validation"""
        # Check SSL/TLS conflict
        if data.get('use_ssl') and data.get('use_tls'):
            raise serializers.ValidationError("Cannot use both SSL and TLS. Choose one.")
        
        if not data.get('use_ssl') and not data.get('use_tls'):
            raise serializers.ValidationError("Must use either SSL or TLS for secure connection.")
        
        # Port validation
        port = data.get('smtp_port')
        use_tls = data.get('use_tls')
        use_ssl = data.get('use_ssl')
        
        if use_tls and port not in [587, 25]:
            raise serializers.ValidationError("TLS typically uses port 587 or 25.")
        
        if use_ssl and port != 465:
            raise serializers.ValidationError("SSL typically uses port 465.")
        
        return data
    
    def create(self, validated_data):
        """Create SMTP config with encrypted password"""
        password = validated_data.pop('smtp_password')
        smtp_config = SMTPConfiguration(**validated_data)
        smtp_config.smtp_password = smtp_config.encrypt_password(password)
        smtp_config.save()
        return smtp_config
    
    def update(self, instance, validated_data):
        """Update SMTP config, encrypt password if provided"""
        password = validated_data.pop('smtp_password', None)
        
        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Encrypt and set password if provided
        if password:
            instance.smtp_password = instance.encrypt_password(password)
            instance.is_verified = False  # Reset verification status
        
        instance.save()
        return instance


class SMTPTestSerializer(serializers.Serializer):
    """Serializer for testing SMTP configuration"""
    test_email = serializers.EmailField(
        required=False,
        help_text="Email to send test message to (defaults to company admin email)"
    )
    
    def validate_test_email(self, value):
        # If no test email provided, we'll use the company admin email
        return value
    
    

class CompanySerializer(serializers.ModelSerializer):
    admin_details = serializers.SerializerMethodField()
    smtp_config = SMTPConfigurationSerializer(read_only=True)
    has_smtp_config = serializers.BooleanField(read_only=True)

    logo = serializers.ImageField(required=False, allow_null=True)
    
    class Meta:
        model = Company
        fields = [
            'id', 'name', 'company_type', 'industry', 
            'website', 'logo', 'description',
            'status', 'rejection_remarks', # Status fields
            'address_country', 'address_city', 
            'address_street', 'address_postal',
            'contact_number', 'support_email',
            'has_smtp_config', 'smtp_config', # Include Smtp details
            'created_at', 'updated_at',
            'admin_details'  # Include admin details
        ]
        read_only_fields = ('created_at', 'updated_at')
    
    def get_admin_details(self, obj):
        from accounts.serializers import UserRegistrationSerializer
        """Custom method to get admin user details"""
        if hasattr(obj, 'admin_user'):
            return {
                'id': obj.admin_user.id,
                'email': obj.admin_user.email,
                'first_name': obj.admin_user.first_name,
                'last_name': obj.admin_user.last_name,
                'phone': obj.admin_user.phone
            }
        return None
    
    def validate_logo(self, value):
        """Validate logo file"""
        if value:
            # Check file size (max 5MB)
            if value.size > 1 * 1024 * 1024:
                raise serializers.ValidationError("Logo file size cannot exceed 1MB.")
            # Check file type
            valid_extensions = ['jpg', 'jpeg', 'png', 'gif', 'webp']
            ext = value.name.split('.')[-1].lower()
            if ext not in valid_extensions:
                raise serializers.ValidationError(
                    f"Invalid file type. Allowed types: {', '.join(valid_extensions.upper())}"
                )
        return value
    
    def validate_contact_number(self, value):
        return validate_phone_number(value)
    

# class InterviewerSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Interviewer
#         fields = ['id', 'name', 'email', 'phone', 'avatar', 'created_at']

#     def validate_phone(self, value):
#         return validate_phone_number(value)

class CompanyPersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyPerson
        fields = ['id', 'name', 'email', 'phone', 'role', 'avatar', 'created_at']

    def validate_phone(self, value):
        return validate_phone_number(value)


# Serializer for bulk operations
class SMTPPresetSerializer(serializers.Serializer):
    """Serializer for getting SMTP presets based on provider"""
    provider = serializers.ChoiceField(choices=SMTPConfiguration.SMTP_PROVIDERS)
    def to_representation(self, instance):
        provider = self.validated_data['provider']
        
        presets = {
            'gmail': {
                'smtp_host': 'smtp.gmail.com',
                'smtp_port': 587,
                'use_tls': True,
                'use_ssl': False,
                'help_text': 'Use App Password instead of regular password for Gmail'
            },
            'outlook': {
                'smtp_host': 'smtp.office365.com',
                'smtp_port': 587,
                'use_tls': True,
                'use_ssl': False,
                'help_text': 'Works with Office365 and Outlook.com accounts'
            },
            'yahoo': {
                'smtp_host': 'smtp.mail.yahoo.com',
                'smtp_port': 587,
                'use_tls': True,
                'use_ssl': False,
                'help_text': 'Enable "Less secure app access" in Yahoo settings'
            },
            'zoho': {
                'smtp_host': 'smtp.zoho.com',
                'smtp_port': 587,
                'use_tls': True,
                'use_ssl': False,
                'help_text': 'Works with Zoho Mail accounts'
            },
            'custom': {
                'smtp_host': '',
                'smtp_port': 587,
                'use_tls': True,
                'use_ssl': False,
                'help_text': 'Enter your custom SMTP server details'
            }
        }
        
        return presets.get(provider, presets['custom'])