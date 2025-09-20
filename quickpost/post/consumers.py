import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import Conversation, Message


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Get conversation ID from URL
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f'chat_{self.conversation_id}'
        
        # Get user from scope (requires authentication middleware)
        self.user = self.scope["user"]
        
        # Check if user is authenticated
        if not self.user.is_authenticated:
            await self.close()
            return
        
        # Check if user is participant in this conversation
        is_participant = await self.check_conversation_participant()
        if not is_participant:
            await self.close()
            return

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message_content = text_data_json['message']
            
            # Save message to database
            message = await self.save_message(message_content)
            
            if message:
                # Send message to room group
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'message': message_content,
                        'sender': self.user.username,
                        'sender_id': self.user.id,
                        'timestamp': message.created_at.isoformat(),
                        'message_id': message.id
                    }
                )
        except json.JSONDecodeError:
            # Handle invalid JSON
            await self.send(text_data=json.dumps({
                'error': 'Invalid message format'
            }))
        except Exception as e:
            # Handle other errors
            await self.send(text_data=json.dumps({
                'error': 'Failed to send message'
            }))

    # Receive message from room group
    async def chat_message(self, event):
        message = event['message']
        sender = event['sender']
        sender_id = event['sender_id']
        timestamp = event['timestamp']
        message_id = event['message_id']

        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': message,
            'sender': sender,
            'sender_id': sender_id,
            'timestamp': timestamp,
            'message_id': message_id
        }))

    @database_sync_to_async
    def check_conversation_participant(self):
        """Check if current user is a participant in the conversation"""
        try:
            conversation = Conversation.objects.get(id=self.conversation_id)
            return conversation.participants.filter(id=self.user.id).exists()
        except Conversation.DoesNotExist:
            return False

    @database_sync_to_async
    def save_message(self, message_content):
        """Save message to database"""
        try:
            conversation = Conversation.objects.get(id=self.conversation_id)
            
            # Validate message content
            if not message_content.strip():
                return None
            
            if len(message_content) > 1000:
                return None
            
            # Create and save message
            message = Message.objects.create(
                conversation=conversation,
                sender=self.user,
                content=message_content.strip()
            )
            
            # Update conversation's updated_at timestamp
            conversation.save()
            
            return message
        except Conversation.DoesNotExist:
            return None
        except Exception:
            return None

    @database_sync_to_async
    def mark_messages_as_read(self):
        """Mark all messages in conversation as read for current user"""
        try:
            conversation = Conversation.objects.get(id=self.conversation_id)
            # Mark messages as read (exclude messages from current user)
            conversation.messages.filter(is_read=False).exclude(sender=self.user).update(is_read=True)
        except Conversation.DoesNotExist:
            pass


class NotificationConsumer(AsyncWebsocketConsumer):
    """Consumer for real-time notifications (optional for future use)"""
    
    async def connect(self):
        self.user = self.scope["user"]
        
        if not self.user.is_authenticated:
            await self.close()
            return
        
        # Create a unique group for this user
        self.notification_group_name = f'notifications_{self.user.id}'
        
        # Join notification group
        await self.channel_layer.group_add(
            self.notification_group_name,
            self.channel_name
        )
        
        await self.accept()

    async def disconnect(self, close_code):
        # Leave notification group
        if hasattr(self, 'notification_group_name'):
            await self.channel_layer.group_discard(
                self.notification_group_name,
                self.channel_name
            )

    # Receive notification from group
    async def notification_message(self, event):
        notification_type = event['type']
        message = event['message']
        
        # Send notification to WebSocket
        await self.send(text_data=json.dumps({
            'type': notification_type,
            'message': message
        }))