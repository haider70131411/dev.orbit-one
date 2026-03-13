# views.py
from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.core.mail import send_mail
from django.conf import settings
from django.shortcuts import get_object_or_404
from .models import ContactMessage, SupportThread, SupportMessage
from .serializers import (
    ContactMessageSerializer,
    SupportThreadSerializer,
    SupportThreadListSerializer,
    SupportMessageSerializer,
)

class ContactMessageCreateView(generics.CreateAPIView):
    """API view for creating contact messages"""
    queryset = ContactMessage.objects.all()
    serializer_class = ContactMessageSerializer
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        # ALWAYS send confirmation email to user (automatic thank you message)
        try:
            send_mail(
                subject='Thank You for Contacting Us',
                message=f"Hi {serializer.validated_data['full_name']},\n\nThank you for reaching out to us. We have received your message and will get back to you as soon as possible.\n\nYour message:\n{serializer.validated_data['message']}\n\nBest regards,\nYour Team",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[serializer.validated_data['email']],
                fail_silently=False,  # Changed to False to see errors
            )
            print(f"Confirmation email sent successfully to {serializer.validated_data['email']}")
        except Exception as e:
            # Log the error but don't stop the request
            print(f"Error sending confirmation email: {e}")
        
        headers = self.get_success_headers(serializer.data)
        return Response(
            {
                'success': True,
                'message': 'Your message has been sent successfully! A confirmation email has been sent to your inbox.',
                'data': serializer.data
            },
            status=status.HTTP_201_CREATED,
            headers=headers
        )


@api_view(['POST'])
def contact_message_create(request):
    """Function-based view alternative"""
    serializer = ContactMessageSerializer(data=request.data)
    
    if serializer.is_valid():
        serializer.save()
        
        # ALWAYS send confirmation email to user (automatic thank you message)
        try:
            send_mail(
                subject='Thank You for Contacting Us',
                message=f"Hi {serializer.validated_data['full_name']},\n\nThank you for reaching out to us. We have received your message and will get back to you as soon as possible.\n\nYour message:\n{serializer.validated_data['message']}\n\nBest regards,\nYour Team",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[serializer.validated_data['email']],
                fail_silently=False,
            )
            print(f"Confirmation email sent successfully to {serializer.validated_data['email']}")
        except Exception as e:
            print(f"Error sending confirmation email: {e}")
        
        return Response({
            'success': True,
            'message': 'Your message has been sent successfully! A confirmation email has been sent to your inbox.',
            'data': serializer.data
        }, status=status.HTTP_201_CREATED)
    
    return Response({
        'success': False,
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


# --- Support Chat (company owners only) ---

class SupportThreadListView(generics.ListAPIView):
    """GET /api/shared/support/threads/ - List my threads (company owner)"""
    permission_classes = [IsAuthenticated]
    serializer_class = SupportThreadListSerializer

    def get_queryset(self):
        return SupportThread.objects.filter(user=self.request.user).prefetch_related('messages').order_by('-updated_at')


class SupportThreadCreateView(APIView):
    """POST /api/shared/support/threads/ - Create thread (company owner)"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if not getattr(user, 'company', None):
            return Response(
                {'error': 'Only company owners can use live support.'},
                status=status.HTTP_403_FORBIDDEN
            )
        subject = (request.data.get('subject') or 'Support request').strip()[:200]
        # Reuse open thread if exists
        thread = SupportThread.objects.filter(
            user=user,
            status='open'
        ).order_by('-updated_at').first()
        if not thread:
            thread = SupportThread.objects.create(
                user=user,
                company=user.company,
                subject=subject
            )
        serializer = SupportThreadSerializer(thread)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SupportThreadDetailView(generics.RetrieveAPIView):
    """GET /api/shared/support/threads/<id>/ - Get thread with messages"""
    permission_classes = [IsAuthenticated]
    serializer_class = SupportThreadSerializer
    lookup_url_kwarg = 'thread_id'
    lookup_field = 'id'

    def get_queryset(self):
        return SupportThread.objects.filter(user=self.request.user).prefetch_related('messages')


class SupportMessageCreateView(APIView):
    """POST /api/shared/support/threads/<id>/messages/ - Send message (company owner)"""
    permission_classes = [IsAuthenticated]

    def post(self, request, thread_id):
        thread = get_object_or_404(SupportThread, id=thread_id, user=request.user)
        msg_text = (request.data.get('message') or '').strip()
        if not msg_text:
            return Response({'error': 'message is required'}, status=status.HTTP_400_BAD_REQUEST)
        SupportMessage.objects.create(thread=thread, sender_type='user', message=msg_text)
        thread.save()  # touch updated_at
        serializer = SupportThreadSerializer(thread)
        return Response(serializer.data, status=status.HTTP_200_OK)