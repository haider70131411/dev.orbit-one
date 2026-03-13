import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import logging

logger = logging.getLogger(__name__)

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print("DEBUG: NotificationConsumer.connect called")
        self.user = self.scope["user"]
        print(f"DEBUG: Consumer User: {self.user}")
        
        if self.user.is_anonymous:
            print("DEBUG: User is anonymous. Closing connection.")
            await self.close()
            return

        # Check if user has a company
        self.company = await self.get_user_company(self.user)
        print(f"DEBUG: User Company: {self.company}")
        if not self.company:
            print("DEBUG: No company found. Closing connection.")
            await self.close()
            return

        self.group_name = f"company_notifications_{self.company.id}"
        print(f"DEBUG: Joining group {self.group_name}")

        # Join room group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        print("DEBUG: Accepting connection...")
        await self.accept()
        print("DEBUG: Connection accepted")
        logger.info(f"User {self.user.email} connected to notification group {self.group_name}")

    async def disconnect(self, close_code):
        # Leave room group
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
            logger.info(f"User {self.user.email} disconnected from notification group {self.group_name}")

    @database_sync_to_async
    def get_user_company(self, user):
        return user.company if hasattr(user, 'company') else None

    # Receive message from room group
    async def notification_message(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps(event["message"]))
