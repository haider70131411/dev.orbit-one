# meetings/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from .models import Meeting, MeetingParticipant
import logging

logger = logging.getLogger(__name__)


class MeetingConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time meeting communication.
    Handles WebRTC signaling (offer/answer/ICE candidates).
    """
    
    async def connect(self):
        """Handle WebSocket connection"""
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'meeting_{self.room_id}'
        self.user_id = None
        
        # Verify meeting exists
        meeting = await self.get_meeting(self.room_id)
        if not meeting:
            await self.close(code=4004)
            return
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        logger.info(f"WebSocket connected to room: {self.room_id}")
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        
        # Notify others that user left
        if self.user_id:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_left',
                    'user_id': self.user_id
                }
            )
        
        logger.info(f"WebSocket disconnected from room: {self.room_id}, code: {close_code}")
    
    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            # Route message based on type
            if message_type == 'join':
                await self.handle_join(data)
            elif message_type == 'offer':
                await self.handle_offer(data)
            elif message_type == 'answer':
                await self.handle_answer(data)
            elif message_type == 'ice-candidate':
                await self.handle_ice_candidate(data)
            elif message_type == 'leave':
                await self.handle_leave(data)
            elif message_type == 'set-recording-status':
                await self.handle_set_recording_status(data)
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))
    
    async def handle_join(self, data):
        """Handle user joining the room"""
        frontend_user_id = data.get('user_id')  # Frontend-generated ID (for reference only)
        participant_type = data.get('participant_type')
        name = data.get('name')
        email = data.get('email')
        
        # Validate participant
        is_valid = await self.validate_participant(
            self.room_id,
            email,
            participant_type
        )
        
        if not is_valid:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Unauthorized participant'
            }))
            await self.close(code=4003)
            return
        
        # Get or create participant record and use database ID
        participant = await self.get_or_create_participant(
            self.room_id,
            email,
            name,
            participant_type
        )
        
        if not participant:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to create participant record'
            }))
            await self.close(code=4004)
            return
        
        # Use database participant ID consistently
        self.user_id = str(participant.id)  # Use database ID, not frontend ID
        
        # Get participant's avatar (for interviewers)
        avatar_data = None
        if participant_type == 'interviewer':
            avatar_data = await self.get_interviewer_avatar(email)
        
        # Notify others about new participant - USE DATABASE ID
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_joined',
                'user_id': self.user_id,  # Database ID
                'participant_type': participant_type,
                'name': name,
                'email': email,
                'avatar': avatar_data,
                'sender_channel': self.channel_name
            }
        )
        
        # Get list of existing participants
        participants = await self.get_active_participants(self.room_id)
        
        # Send current room state to new participant
        await self.send(text_data=json.dumps({
            'type': 'room-state',
            'participants': participants
        }))
        
        logger.info(f"User {name} ({participant_type}) joined room {self.room_id} with participant_id: {self.user_id}")
    
    async def handle_offer(self, data):
        """Forward WebRTC offer to target peer"""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'webrtc_offer',
                'offer': data.get('offer'),
                'from_user': data.get('from_user'),
                'to_user': data.get('to_user')
            }
        )
    
    async def handle_answer(self, data):
        """Forward WebRTC answer to target peer"""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'webrtc_answer',
                'answer': data.get('answer'),
                'from_user': data.get('from_user'),
                'to_user': data.get('to_user')
            }
        )
    
    async def handle_ice_candidate(self, data):
        """Forward ICE candidate to target peer"""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'webrtc_ice_candidate',
                'candidate': data.get('candidate'),
                'from_user': data.get('from_user'),
                'to_user': data.get('to_user')
            }
        )
    
    async def handle_leave(self, data):
        """Handle user leaving"""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_left',
                'user_id': self.user_id
            }
        )
        # If this was the recorder, reset recording status
        await self.handle_recorder_disconnect(self.user_id)

    async def handle_set_recording_status(self, data):
        """Handle recording status update from a participant"""
        is_recording = data.get('is_recording', False)
        recording_by = data.get('recording_by')
        
        # Update meeting model
        await self.update_meeting_recording_status(
            self.room_id, 
            'recording' if is_recording else 'pending',
            recording_by if is_recording else None
        )
        
        # Get recorder name
        recorder_name = None
        if is_recording and recording_by:
            participant = await self.get_participant_by_id(recording_by)
            if participant:
                recorder_name = participant.name
        
        # Broadcast to room
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'recording_status_update',
                'is_recording': is_recording,
                'recording_by': recording_by,
                'recorder_name': recorder_name
            }
        )

    async def handle_recorder_disconnect(self, user_id):
        """Check if disconnected user was the recorder and reset if so"""
        meeting = await self.get_meeting(self.room_id)
        if meeting and meeting.recording_by == user_id:
            await self.update_meeting_recording_status(self.room_id, 'pending', None)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'recording_status_update',
                    'is_recording': False,
                    'recording_by': None,
                    'recorder_name': None
                }
            )
    
    # Event handlers (called by channel layer)
    
    async def user_joined(self, event):
        """Send user_joined event to WebSocket"""
        # Don't send to the user who joined
        if event.get('sender_channel') != self.channel_name:
            await self.send(text_data=json.dumps({
                'type': 'user-joined',
                'user_id': event['user_id'],
                'participant_type': event['participant_type'],
                'name': event['name'],
                'email': event['email'],
                'avatar': event['avatar']
            }))
    
    async def user_left(self, event):
        """Send user_left event to WebSocket"""
        # Check if connection is still open before sending
        if hasattr(self, 'scope') and self.scope.get('type') == 'websocket':
            try:
                await self.send(text_data=json.dumps({
                    'type': 'user-left',
                    'user_id': event['user_id']
                }))
            except Exception as e:
                # Connection already closed, silently ignore
                pass
    
    async def webrtc_offer(self, event):
        """Send WebRTC offer to target user"""
        if event['to_user'] == self.user_id:
            await self.send(text_data=json.dumps({
                'type': 'offer',
                'offer': event['offer'],
                'from_user': event['from_user']
            }))
    
    async def webrtc_answer(self, event):
        """Send WebRTC answer to target user"""
        if event['to_user'] == self.user_id:
            await self.send(text_data=json.dumps({
                'type': 'answer',
                'answer': event['answer'],
                'from_user': event['from_user']
            }))
    
    async def webrtc_ice_candidate(self, event):
        """Send ICE candidate to target user"""
        if event['to_user'] == self.user_id:
            await self.send(text_data=json.dumps({
                'type': 'ice-candidate',
                'candidate': event['candidate'],
                'from_user': event['from_user']
            }))
    
    async def meeting_end_warning(self, event):
        """Send meeting end warning to all connected participants"""
        await self.send(text_data=json.dumps({
            'type': 'meeting-end-warning',
            'message': event.get('message', 'Meeting will end soon'),
            'minutes_remaining': event.get('minutes_remaining', 5),
            'meeting_id': event.get('meeting_id'),
            'meeting_title': event.get('meeting_title')
        }))
    
    async def meeting_ended(self, event):
        """Send meeting ended notification to all connected participants"""
        await self.send(text_data=json.dumps({
            'type': 'meeting-ended',
            'message': event.get('message', 'Meeting has ended'),
            'meeting_id': event.get('meeting_id'),
            'meeting_title': event.get('meeting_title'),
            'reason': event.get('reason', 'time_expired')
        }))
        
        # Optionally close the WebSocket connection after sending the message
        # This ensures participants are disconnected when meeting ends
        logger.info(f"Sending meeting ended notification and closing connection for room: {self.room_id}")
        await self.close(code=4000)  # 4000 is a normal closure code
    
    async def recording_status_update(self, event):
        """Send recording-status event to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'recording-status',
            'is_recording': event['is_recording'],
            'recording_by': event['recording_by'],
            'recorder_name': event['recorder_name']
        }))
    
    # Database helper methods
    
    @database_sync_to_async
    def get_meeting(self, room_id):
        """Get meeting by room_id"""
        try:
            return Meeting.objects.get(meeting_room_id=room_id)
        except Meeting.DoesNotExist:
            return None
    
    @database_sync_to_async
    def validate_participant(self, room_id, email, participant_type):
        """Validate if user can join this meeting"""
        try:
            meeting = Meeting.objects.get(meeting_room_id=room_id)
            
            if participant_type == 'interviewer':
                return meeting.interviewers.filter(email=email).exists()
            elif participant_type == 'interviewee':
                return meeting.interviewee_email == email
            
            return False
        except Meeting.DoesNotExist:
            return False
    
    @database_sync_to_async
    def get_or_create_participant(self, room_id, email, name, participant_type):
        """Get or create MeetingParticipant record"""
        try:
            meeting = Meeting.objects.get(meeting_room_id=room_id)
            participant, created = MeetingParticipant.objects.get_or_create(
                meeting=meeting,
                email=email,
                defaults={
                    'name': name,
                    'participant_type': participant_type,
                    'joined_at': timezone.now()
                }
            )
            if not created and not participant.joined_at:
                # Update joined_at if not set (user rejoining)
                participant.joined_at = timezone.now()
                participant.left_at = None  # Reset left_at if rejoining
                participant.save()
            elif not created and participant.left_at:
                # User is rejoining after leaving
                participant.joined_at = timezone.now()
                participant.left_at = None
                participant.save()
            return participant
        except Meeting.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error creating participant: {e}")
            return None
    
    @database_sync_to_async
    def get_interviewer_avatar(self, email):
        """Get interviewer's avatar data"""
        try:
            from companies.models import CompanyPerson
            person = CompanyPerson.objects.select_related('avatar').get(email=email)
            
            if person.avatar:
                # Use cached URLs with fallback
                vrm_url = person.avatar.vrm_file_url or (
                    person.avatar.vrm_file.url if person.avatar.vrm_file else None
                )
                preview_url = person.avatar.preview_image_url or (
                    person.avatar.preview_image.url if person.avatar.preview_image else None
                )
                
                return {
                    'id': person.avatar.id,
                    'name': person.avatar.name,
                    'vrm_url': vrm_url,
                    'preview_url': preview_url
                }
            return None
        except:
            return None
    
    @database_sync_to_async
    def get_active_participants(self, room_id):
        """Get list of currently active participants"""
        try:
            meeting = Meeting.objects.get(meeting_room_id=room_id)
            participants = MeetingParticipant.objects.filter(
                meeting=meeting,
                joined_at__isnull=False,
                left_at__isnull=True
            ).select_related('meeting')
            
            result = []
            for p in participants:
                participant_data = {
                    'user_id': str(p.id),
                    'name': p.name,
                    'email': p.email,
                    'participant_type': p.participant_type,
                    'joined_at': p.joined_at.isoformat()
                }
                
                # Add avatar for interviewers
                if p.participant_type == 'interviewer':
                    from companies.models import CompanyPerson
                    try:
                        person = CompanyPerson.objects.select_related('avatar').get(email=p.email)
                        if person.avatar:
                            # Use cached URLs with fallback
                            vrm_url = person.avatar.vrm_file_url or (
                                person.avatar.vrm_file.url if person.avatar.vrm_file else None
                            )
                            preview_url = person.avatar.preview_image_url or (
                                person.avatar.preview_image.url if person.avatar.preview_image else None
                            )
                            
                            participant_data['avatar'] = {
                                'id': person.avatar.id,
                                'name': person.avatar.name,
                                'vrm_url': vrm_url,
                                'preview_url': preview_url
                            }
                    except:
                        pass
                
                result.append(participant_data)
            
            return result
        except Meeting.DoesNotExist:
            return []

    @database_sync_to_async
    def update_meeting_recording_status(self, room_id, status, recorder_id):
        """Update recording status in the database"""
        try:
            Meeting.objects.filter(meeting_room_id=room_id).update(
                recording_status=status,
                recording_by=recorder_id
            )
        except Exception as e:
            logger.error(f"Error updating recording status: {e}")

    @database_sync_to_async
    def get_participant_by_id(self, participant_id):
        """Get participant record by ID"""
        try:
            return MeetingParticipant.objects.get(id=participant_id)
        except MeetingParticipant.DoesNotExist:
            return None