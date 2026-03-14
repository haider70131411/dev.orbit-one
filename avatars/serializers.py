from rest_framework import serializers
from django.core.validators import FileExtensionValidator
from .models import Avatar


class AvatarListSerializer(serializers.ModelSerializer):
    """Serializer for listing avatars (lighter response)"""
    vrm_file_url = serializers.SerializerMethodField()
    preview_image_url = serializers.SerializerMethodField()
    file_size_mb = serializers.SerializerMethodField()
    
    class Meta:
        model = Avatar
        fields = [
            'id',
            'name',
            'slug',
            'preview_image_url',
            'vrm_file_url',
            'file_size_mb',
            'description',
            'is_active',
            'created_at'
        ]
        read_only_fields = fields
    
    def get_vrm_file_url(self, obj):
        """Return cached URL, with fallback to building absolute URI if needed"""
        request = self.context.get('request')
        
        # Use cached URL if available (already absolute for R2)
        if obj.vrm_file_url:
            # If it's already a full URL (R2), return as-is
            if obj.vrm_file_url.startswith('http'):
                return obj.vrm_file_url
            # Otherwise, make it absolute using request context
            if request:
                return request.build_absolute_uri(obj.vrm_file_url)
            return obj.vrm_file_url
        
        # Fallback: compute on-the-fly (for backward compatibility during migration)
        if obj.vrm_file and request:
            return request.build_absolute_uri(obj.vrm_file.url)
        return None
    
    def get_preview_image_url(self, obj):
        """Return cached URL, with fallback to building absolute URI if needed"""
        request = self.context.get('request')
        
        # Use cached URL if available
        if obj.preview_image_url:
            if obj.preview_image_url.startswith('http'):
                return obj.preview_image_url
            if request:
                return request.build_absolute_uri(obj.preview_image_url)
            return obj.preview_image_url
        
        # Fallback: compute on-the-fly (for backward compatibility during migration)
        if obj.preview_image and request:
            return request.build_absolute_uri(obj.preview_image.url)
        return None
    
    def get_file_size_mb(self, obj):
        """Return file size in MB from cached value"""
        return obj.vrm_file_size


class AvatarDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed avatar information"""
    vrm_file_url = serializers.SerializerMethodField()
    preview_image_url = serializers.SerializerMethodField()
    file_size_mb = serializers.SerializerMethodField()
    
    class Meta:
        model = Avatar
        fields = [
            'id',
            'name',
            'slug',
            'preview_image_url',
            'vrm_file_url',
            'file_size_mb',
            'description',
            'is_active',
            'created_at',
            'updated_at'
        ]
        read_only_fields = fields
    
    def get_vrm_file_url(self, obj):
        """Return cached URL, with fallback to building absolute URI if needed"""
        request = self.context.get('request')
        
        # Use cached URL if available (already absolute for R2)
        if obj.vrm_file_url:
            if obj.vrm_file_url.startswith('http'):
                return obj.vrm_file_url
            if request:
                return request.build_absolute_uri(obj.vrm_file_url)
            return obj.vrm_file_url
        
        # Fallback: compute on-the-fly (for backward compatibility during migration)
        if obj.vrm_file and request:
            return request.build_absolute_uri(obj.vrm_file.url)
        return None
    
    def get_preview_image_url(self, obj):
        """Return cached URL, with fallback to building absolute URI if needed"""
        request = self.context.get('request')
        
        # Use cached URL if available
        if obj.preview_image_url:
            if obj.preview_image_url.startswith('http'):
                return obj.preview_image_url
            if request:
                return request.build_absolute_uri(obj.preview_image_url)
            return obj.preview_image_url
        
        # Fallback: compute on-the-fly (for backward compatibility during migration)
        if obj.preview_image and request:
            return request.build_absolute_uri(obj.preview_image.url)
        return None
    
    def get_file_size_mb(self, obj):
        """Return file size in MB from cached value"""
        return obj.vrm_file_size


class AvatarCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new avatars"""
    vrm_file = serializers.FileField(
        validators=[FileExtensionValidator(allowed_extensions=['vrm'])],
        help_text="VRM file (max 30MB)"
    )
    
    preview_image = serializers.ImageField(
        help_text="Preview image (PNG, JPG, JPEG)"
    )
    
    class Meta:
        model = Avatar
        fields = [
            'name',
            'vrm_file',
            'preview_image',
            'description',
            'is_active'
        ]
    
    def validate_name(self, value):
        """Ensure name is unique"""
        if Avatar.objects.filter(name=value).exists():
            raise serializers.ValidationError(
                f"Avatar with name '{value}' already exists"
            )
        return value
    
    def validate_vrm_file(self, value):
        """Validate VRM file size"""
        # On the Oracle Free Tier VM, very large VRM uploads can exhaust memory.
        # Keep this lower so we reject too-big files with a 400 instead of OOM-killing Daphne.
        max_size = 30 * 1024 * 1024  # 30MB
        if value.size > max_size:
            raise serializers.ValidationError(
                f"VRM file size cannot exceed 100MB. Current size: {value.size / (1024*1024):.2f}MB"
            )
        return value
    
    def validate_preview_image(self, value):
        """Validate preview image size and format"""
        max_size = 10 * 1024 * 1024  # 10MB
        if value.size > max_size:
            raise serializers.ValidationError(
                f"Image size cannot exceed 10MB. Current size: {value.size / (1024*1024):.2f}MB"
            )
        
        valid_formats = ['image/jpeg', 'image/jpg', 'image/png']
        if value.content_type not in valid_formats:
            raise serializers.ValidationError(
                f"Invalid image format. Allowed formats: JPG, PNG"
            )
        
        return value
    
    def create(self, validated_data):
        """Create new avatar instance with metadata caching"""
        avatar = Avatar(**validated_data)
        avatar.save()  # This will trigger _cache_file_metadata()
        return avatar


class AvatarUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating existing avatars"""
    vrm_file = serializers.FileField(
        required=False,
        validators=[FileExtensionValidator(allowed_extensions=['vrm'])],
        help_text="VRM file (max 100MB)"
    )
    
    preview_image = serializers.ImageField(
        required=False,
        help_text="Preview image (PNG, JPG, JPEG)"
    )
    
    name = serializers.CharField(required=False)
    
    class Meta:
        model = Avatar
        fields = [
            'name',
            'vrm_file',
            'preview_image',
            'description',
            'is_active'
        ]
    
    def validate_name(self, value):
        """Ensure name is unique (except for current instance)"""
        instance = self.instance
        if Avatar.objects.filter(name=value).exclude(pk=instance.pk).exists():
            raise serializers.ValidationError(
                f"Avatar with name '{value}' already exists"
            )
        return value
    
    def validate_vrm_file(self, value):
        """Validate VRM file size"""
        max_size = 30 * 1024 * 1024  # 30MB
        if value.size > max_size:
            raise serializers.ValidationError(
                f"VRM file size cannot exceed 100MB. Current size: {value.size / (1024*1024):.2f}MB"
            )
        return value
    
    def validate_preview_image(self, value):
        """Validate preview image size and format"""
        max_size = 10 * 1024 * 1024  # 10MB
        if value.size > max_size:
            raise serializers.ValidationError(
                f"Image size cannot exceed 10MB. Current size: {value.size / (1024*1024):.2f}MB"
            )
        
        valid_formats = ['image/jpeg', 'image/jpg', 'image/png']
        if value.content_type not in valid_formats:
            raise serializers.ValidationError(
                f"Invalid image format. Allowed formats: JPG, PNG"
            )
        
        return value
    
    def update(self, instance, validated_data):
        """Update avatar instance and recache metadata if files changed"""
        # Check if files are being updated
        files_changed = 'vrm_file' in validated_data or 'preview_image' in validated_data
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Save will trigger metadata caching if files changed
        instance.save()
        return instance