from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.core.exceptions import ValidationError
from .models import Avatar
from .serializers import (
    AvatarListSerializer, 
    AvatarDetailSerializer,
    AvatarCreateSerializer,
    AvatarUpdateSerializer
)
import logging

logger = logging.getLogger(__name__)


class AvatarViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Avatar API endpoints
    
    Public endpoints (GET): list, retrieve, count, download_vrm
    Admin endpoints (POST, PUT, PATCH, DELETE): create, update, delete
    """
    
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['-created_at']
    
    def get_permissions(self):
        """
        Public can read, only admins can write
        """
        if self.action in ['list', 'retrieve', 'count', 'download_vrm']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        """
        Return all avatars for admin, only active for public
        """
        if self.request.user and self.request.user.is_staff:
            return Avatar.objects.all()
        return Avatar.objects.filter(is_active=True)
    
    def get_serializer_class(self):
        """
        Use different serializers for different actions
        """
        if self.action == 'create':
            return AvatarCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return AvatarUpdateSerializer
        elif self.action == 'retrieve':
            return AvatarDetailSerializer
        return AvatarListSerializer
    
    @method_decorator(cache_page(60 * 15))
    def list(self, request, *args, **kwargs):
        """List all active avatars with pagination"""
        return super().list(request, *args, **kwargs)
    
    @method_decorator(cache_page(60 * 15))
    def retrieve(self, request, *args, **kwargs):
        """Retrieve single avatar details"""
        return super().retrieve(request, *args, **kwargs)
    
    def create(self, request, *args, **kwargs):
        """Create new avatar (Admin only)"""
        serializer = self.get_serializer(data=request.data)
        
        try:
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            
            avatar = serializer.instance
            
            response_serializer = AvatarDetailSerializer(
                avatar, 
                context={'request': request}
            )
            
            return Response(
                {
                    'message': 'Avatar created successfully',
                    'avatar': response_serializer.data
                },
                status=status.HTTP_201_CREATED
            )
        except ValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'Failed to create avatar: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def update(self, request, *args, **kwargs):
        """Full/Partial update of avatar (Admin only)"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        try:
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            avatar = serializer.instance
            
            response_serializer = AvatarDetailSerializer(
                avatar,
                context={'request': request}
            )
            
            return Response({
                'message': 'Avatar updated successfully',
                'avatar': response_serializer.data
            })
        except ValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'Failed to update avatar: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def partial_update(self, request, *args, **kwargs):
        """Partial update of avatar (Admin only)"""
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Delete avatar (Admin only)"""
        instance = self.get_object()
        avatar_name = instance.name
        avatar_id = instance.id
        
        try:
            self.perform_destroy(instance)
            return Response(
                {
                    'message': f'Avatar "{avatar_name}" deleted successfully',
                    'deleted_id': avatar_id
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {'error': f'Failed to delete avatar: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def count(self, request):
        """Get total count of active avatars"""
        count = self.get_queryset().count()
        return Response({'count': count})
    
    @action(detail=True, methods=['get'])
    def download_vrm(self, request, pk=None):
        """Get VRM file download URL"""
        avatar = self.get_object()
        if avatar.vrm_file:
            # Use cached URL with fallback
            url = avatar.vrm_file_url or avatar.vrm_file.url
            if url and not url.startswith('http'):
                url = request.build_absolute_uri(url)
            
            return Response({
                'url': url,
                'filename': avatar.vrm_file.name.split('/')[-1],
                'size_mb': avatar.vrm_file_size
            })
        return Response(
            {'error': 'VRM file not available'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def toggle_active(self, request, pk=None):
        """Toggle avatar active status (Admin only)"""
        avatar = self.get_object()
        avatar.is_active = not avatar.is_active
        avatar.save()
        
        return Response({
            'message': f'Avatar is now {"active" if avatar.is_active else "inactive"}',
            'is_active': avatar.is_active
        })
    
    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
    def bulk_delete(self, request):
        """Bulk delete avatars (Admin only)"""
        ids = request.data.get('ids', [])
        
        if not ids:
            return Response(
                {'error': 'No IDs provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            avatars = Avatar.objects.filter(id__in=ids)
            count = avatars.count()
            avatars.delete()
            
            return Response({
                'message': f'{count} avatar(s) deleted successfully',
                'deleted_count': count
            })
        except Exception as e:
            return Response(
                {'error': f'Failed to delete avatars: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
    def bulk_toggle_active(self, request):
        """Bulk toggle active status (Admin only)"""
        ids = request.data.get('ids', [])
        is_active = request.data.get('is_active', True)
        
        if not ids:
            return Response(
                {'error': 'No IDs provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            count = Avatar.objects.filter(id__in=ids).update(is_active=is_active)
            
            return Response({
                'message': f'{count} avatar(s) updated successfully',
                'updated_count': count,
                'is_active': is_active
            })
        except Exception as e:
            return Response(
                {'error': f'Failed to update avatars: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )