"""Pydantic schemas for messages and notifications."""
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime


# Message Schemas
class MessageCreate(BaseModel):
    to_user: UUID
    property_id: UUID
    content: str


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: Optional[UUID]
    from_user: UUID
    to_user: UUID
    content: str
    read: bool
    created_at: datetime

    class Config:
        from_attributes = True


# Conversation Schemas
class ConversationResponse(BaseModel):
    id: UUID
    property_id: UUID
    customer_id: UUID
    owner_id: UUID
    last_message_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationWithMessages(ConversationResponse):
    messages: Optional[List[MessageResponse]] = None
    property_title: Optional[str] = None
    other_user_name: Optional[str] = None
    other_user_photo: Optional[str] = None


# Notification Schemas
class NotificationResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    message: str
    type: str
    link: Optional[str]
    read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationMarkRead(BaseModel):
    notification_ids: List[UUID]
