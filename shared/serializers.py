# serializers.py
from rest_framework import serializers
from .models import ContactMessage, SupportThread, SupportMessage


class ContactMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = [
            'id',
            'full_name',
            'company_name',
            'email',
            'message',
            'created_at',
            'is_replied',
        ]
        read_only_fields = ['id', 'created_at', 'is_replied']
    
    def validate_email(self, value):
        """Validate email format"""
        if not value:
            raise serializers.ValidationError("Email is required")
        return value.lower()
    
    def validate_full_name(self, value):
        """Validate full name"""
        if not value or len(value.strip()) < 2:
            raise serializers.ValidationError("Please provide a valid full name")
        return value.strip()


class ContactMessageDetailSerializer(serializers.ModelSerializer):
    """Serializer for admin view with reply information"""
    class Meta:
        model = ContactMessage
        fields = '__all__'


class SupportMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportMessage
        fields = ['id', 'sender_type', 'message', 'is_read', 'created_at']
        read_only_fields = ['id', 'created_at']


class SupportThreadSerializer(serializers.ModelSerializer):
    messages = SupportMessageSerializer(many=True, read_only=True)
    company_name = serializers.SerializerMethodField()
    user_email = serializers.CharField(source='user.email', read_only=True)

    def get_company_name(self, obj):
        return obj.company.name if obj.company else None

    class Meta:
        model = SupportThread
        fields = [
            'id', 'subject', 'status', 'company', 'company_name',
            'user', 'user_email', 'messages', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SupportThreadListSerializer(serializers.ModelSerializer):
    company_name = serializers.SerializerMethodField()
    user_email = serializers.CharField(source='user.email', read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = SupportThread
        fields = [
            'id', 'subject', 'status', 'company_name', 'user_email',
            'last_message', 'unread_count', 'created_at', 'updated_at'
        ]

    def get_last_message(self, obj):
        last = obj.messages.order_by('-created_at').first()
        if not last:
            return ''
        return last.message[:80] + '...' if len(last.message) > 80 else last.message

    def get_company_name(self, obj):
        return obj.company.name if obj.company else None

    def get_unread_count(self, obj):
        return obj.messages.filter(sender_type='user', is_read=False).count()