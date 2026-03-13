from django.contrib import admin
from django.utils.html import format_html
from .models import Avatar


@admin.register(Avatar)
class AvatarAdmin(admin.ModelAdmin):
    """Admin interface for Avatar management"""
    
    list_display = [
        'name',
        'preview_thumbnail',
        'vrm_file_info',
        'is_active',
        'created_at',
    ]
    
    list_filter = [
        'is_active',
        'created_at',
    ]
    
    search_fields = [
        'name',
        'slug',
        'description'
    ]
    
    readonly_fields = [
        'slug',
        'created_at',
        'updated_at',
        'preview_display',
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description', 'is_active')
        }),
        ('Files', {
            'fields': ('vrm_file', 'preview_image', 'preview_display')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    list_per_page = 20
    
    actions = ['activate_avatars', 'deactivate_avatars']
    
    def preview_thumbnail(self, obj):
        """Display small thumbnail in list view"""
        if obj.preview_image:
            try:
                # Use cached URL with fallback
                url = obj.preview_image_url or obj.preview_image.url
                return format_html(
                    '<img src="{}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 5px;" />',
                    url
                )
            except Exception:
                return "❌ Image Error"
        return "No Image"
    preview_thumbnail.short_description = 'Preview'
    
    def preview_display(self, obj):
        """Display larger preview in detail view"""
        if obj.preview_image:
            try:
                # Use cached URL with fallback
                url = obj.preview_image_url or obj.preview_image.url
                return format_html(
                    '<img src="{}" style="max-width: 300px; max-height: 300px; border-radius: 10px;" />',
                    url
                )
            except Exception:
                return "❌ Image Error"
        return "No Image"
    preview_display.short_description = 'Preview Image'
    
    def vrm_file_info(self, obj):
        """Display VRM file information - handles missing files gracefully"""
        if obj.vrm_file:
            try:
                # Use cached size and URL with fallback
                file_size = obj.vrm_file_size
                file_url = obj.vrm_file_url or obj.vrm_file.url
                
                if file_size == 0:
                    # File might be missing
                    return format_html(
                        '<span style="color: orange;">⚠️ File Missing (0 MB)</span><br>'
                        '<small>{}</small>',
                        obj.vrm_file.name
                    )
                
                return format_html(
                    '<strong>Size:</strong> {} MB<br><a href="{}" target="_blank">Download</a>',
                    file_size,
                    file_url
                )
            except FileNotFoundError:
                # File doesn't exist in R2 storage
                return format_html(
                    '<span style="color: red;">❌ File Not Found in R2</span><br>'
                    '<small>Path: {}</small>',
                    obj.vrm_file.name
                )
            except Exception as e:
                # Other errors (permissions, network, etc.)
                return format_html(
                    '<span style="color: red;">❌ Error: {}</span><br>'
                    '<small>Path: {}</small>',
                    str(e)[:50],
                    obj.vrm_file.name
                )
        return "No File"
    vrm_file_info.short_description = 'VRM File'
    
    def activate_avatars(self, request, queryset):
        """Bulk action to activate avatars"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} avatar(s) activated successfully.')
    activate_avatars.short_description = 'Activate selected avatars'
    
    def deactivate_avatars(self, request, queryset):
        """Bulk action to deactivate avatars"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} avatar(s) deactivated successfully.')
    deactivate_avatars.short_description = 'Deactivate selected avatars'