"""Messages router."""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import MessageCreate, MessageResponse, ConversationWithMessages
from app.utils.security import get_current_user
from app.services.message_service import MessageService

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.get("/conversations", response_model=List[ConversationWithMessages])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List user's conversations."""
    return MessageService.list_conversations(db, current_user)


@router.get("/conversations/{conversation_id}", response_model=ConversationWithMessages, include_in_schema=False)
@router.get("/conversation/{conversation_id}", response_model=ConversationWithMessages)
async def get_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get conversation with all messages."""
    return MessageService.get_conversation(db, conversation_id, current_user)


@router.post("", response_model=MessageResponse)
async def send_message(
    message_data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a message."""
    return MessageService.send_message(db, message_data, current_user)


@router.put("/{message_id}/read")
async def mark_message_read(
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark a message as read."""
    return MessageService.mark_message_read(db, message_id, current_user)


@router.get("/unread-count")
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get count of unread messages."""
    return MessageService.get_unread_count(db, current_user)
