from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.conf import settings
from .models import Meeting
from notifications.tasks import send_recording_ready_notification
import boto3
from botocore.config import Config
import uuid
import logging

logger = logging.getLogger(__name__)

class GetRecordingConfigView(APIView):
    """
    Get configuration for recording a meeting, including a pre-signed URL for direct upload to R2.
    Only accessible to participants of the meeting (logic could be tightened to Interviewers).
    """
    permission_classes = [permissions.AllowAny]  # Publicly accessible via room_id, but we'll validate room_id

    def get(self, request, room_id):
        meeting = get_object_or_404(Meeting, meeting_room_id=room_id)
        
        if not meeting.enable_recording:
            return Response(
                {"error": "Recording is not enabled for this meeting"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if meeting.recording_status == 'completed' and meeting.recording_file:
            return Response(
                {"error": "Recording has already been completed for this meeting"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Generate a unique filename for the recording
        # Storage location: 
        # - If USE_R2=True: Cloudflare R2 bucket at {AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/recordings/{meeting.id}/{uuid}.webm
        # - Public URL: {AWS_S3_CUSTOM_DOMAIN}/recordings/{meeting.id}/{uuid}.webm
        # - If USE_R2=False: Local storage at MEDIA_ROOT/recordings/{meeting.id}/{uuid}.webm
        file_name = f"recordings/{meeting.id}/{uuid.uuid4()}.webm"
        logger.info(f"Recording will be saved to: {file_name} (Bucket: {settings.AWS_STORAGE_BUCKET_NAME if hasattr(settings, 'AWS_STORAGE_BUCKET_NAME') else 'Local'})")
        
        # Configure Boto3 for R2
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            region_name='auto',
            config=Config(signature_version='s3v4')
        )

        try:
            # Generate pre-signed URL for PUT request with CORS headers
            presigned_url = s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                    'Key': file_name,
                    'ContentType': 'video/webm'
                },
                ExpiresIn=3600,  # URL valid for 1 hour
                # Note: CORS headers need to be configured on the R2 bucket itself
                # The presigned URL will work if CORS is properly configured on R2
            )

            # Update meeting status to uploading
            meeting.recording_status = 'uploading'
            meeting.save()

            return Response({
                "presigned_url": presigned_url,
                "file_path": file_name,
                "meeting_id": meeting.id,
                "bucket_name": settings.AWS_STORAGE_BUCKET_NAME
            })
        except Exception as e:
            logger.error(f"Error generating pre-signed URL: {str(e)}")
            return Response(
                {"error": "Could not generate upload URL"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class CompleteRecordingUploadView(APIView):
    """
    Called by the frontend once the recording upload to R2 is complete.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, room_id):
        meeting = get_object_or_404(Meeting, meeting_room_id=room_id)
        file_path = request.data.get('file_path')

        if not file_path:
            return Response({"error": "file_path is required"}, status=status.HTTP_400_BAD_REQUEST)

        meeting.recording_file = file_path
        meeting.recording_status = 'completed'
        meeting.save()

        # Trigger async dashboard notification that recording is ready
        try:
            send_recording_ready_notification.delay(str(meeting.id))
        except Exception as e:
            logger.error(f"Failed to enqueue recording-ready notification: {str(e)}")

        return Response({"message": "Recording upload confirmed"})


class UploadRecordingView(APIView):
    """
    Proxy endpoint to upload recording through backend (avoids CORS issues with R2).
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, room_id):
        meeting = get_object_or_404(Meeting, meeting_room_id=room_id)
        
        if not meeting.enable_recording:
            return Response(
                {"error": "Recording is not enabled for this meeting"},
                status=status.HTTP_400_BAD_REQUEST
            )

        recording_file = request.FILES.get('recording')
        file_path = request.data.get('file_path')

        if not recording_file:
            return Response(
                {"error": "Recording file is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not file_path:
            return Response(
                {"error": "file_path is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Configure Boto3 for R2
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                endpoint_url=settings.AWS_S3_ENDPOINT_URL,
                region_name='auto',
                config=Config(signature_version='s3v4')
            )

            # Upload file to R2
            s3_client.upload_fileobj(
                recording_file,
                settings.AWS_STORAGE_BUCKET_NAME,
                file_path,
                ExtraArgs={'ContentType': 'video/webm'}
            )

            # Log recording storage location
            storage_location = f"R2 Bucket: {settings.AWS_STORAGE_BUCKET_NAME}"
            if hasattr(settings, 'AWS_S3_CUSTOM_DOMAIN'):
                public_url = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{file_path}"
                logger.info(f"Recording saved successfully. Storage: {storage_location}, Public URL: {public_url}")
            else:
                logger.info(f"Recording saved successfully. Storage: {storage_location}, Path: {file_path}")

            # Update meeting status
            meeting.recording_file = file_path
            meeting.recording_status = 'completed'
            meeting.save()

            # Trigger async dashboard notification that recording is ready
            try:
                send_recording_ready_notification.delay(str(meeting.id))
            except Exception as e:
                logger.error(f"Failed to enqueue recording-ready notification: {str(e)}")

            return Response({"message": "Recording uploaded successfully"})

        except Exception as e:
            logger.error(f"Error uploading recording: {str(e)}")
            return Response(
                {"error": "Failed to upload recording"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
