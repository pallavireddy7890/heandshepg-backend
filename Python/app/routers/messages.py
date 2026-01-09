"""Messages router."""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models import User, Message, Conversation, Property, Profile
from app.schemas import MessageCreate, MessageResponse, ConversationResponse, ConversationWithMessages
from app.utils.security import get_current_user

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.get("/conversations", response_model=List[ConversationWithMessages])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List user's conversations."""
    conversations = db.query(Conversation).filter(
        or_(
            Conversation.customer_id == current_user.id,
            Conversation.owner_id == current_user.id
        )
    ).order_by(Conversation.last_message_at.desc()).all()
    
    result = []
    for conv in conversations:
        # Get property title
        property = db.query(Property).filter(Property.id == conv.property_id).first()
        
        # Get other user's info
        other_user_id = conv.owner_id if conv.customer_id == current_user.id else conv.customer_id
        other_profile = db.query(Profile).filter(Profile.user_id == other_user_id).first()
        
        # Get last message
        last_message = db.query(Message).filter(
            Message.conversation_id == conv.id
        ).order_by(Message.created_at.desc()).first()
        
        conv_response = ConversationWithMessages.model_validate(conv)
        conv_response.property_title = property.title if property else None
        conv_response.other_user_name = other_profile.name if other_profile else "User"
        conv_response.other_user_photo = other_profile.profile_photo if other_profile else None
        conv_response.messages = [MessageResponse.model_validate(last_message)] if last_message else []
        
        result.append(conv_response)
    
    return result


@router.get("/conversations/{conversation_id}", response_model=ConversationWithMessages)
async def get_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get conversation with all messages."""
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        or_(
            Conversation.customer_id == current_user.id,
            Conversation.owner_id == current_user.id
        )
    ).first()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Get all messages
    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all()
    
    # Mark as read
    db.query(Message).filter(
        Message.conversation_id == conversation_id,
        Message.to_user == current_user.id,
        Message.read == False
    ).update({"read": True})
    db.commit()
    
    # Get property and other user info
    property = db.query(Property).filter(Property.id == conversation.property_id).first()
    other_user_id = conversation.owner_id if conversation.customer_id == current_user.id else conversation.customer_id
    other_profile = db.query(Profile).filter(Profile.user_id == other_user_id).first()
    
    response = ConversationWithMessages.model_validate(conversation)
    response.messages = [MessageResponse.model_validate(m) for m in messages]
    response.property_title = property.title if property else None
    response.other_user_name = other_profile.name if other_profile else "User"
    response.other_user_photo = other_profile.profile_photo if other_profile else None
    
    return response


@router.post("/send", response_model=MessageResponse)
async def send_message(
    message_data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a message."""
    # Get or create conversation
    property = db.query(Property).filter(Property.id == message_data.property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    # Determine customer and owner
    if current_user.id == property.owner_id:
        customer_id = message_data.to_user
        owner_id = current_user.id
    else:
        customer_id = current_user.id
        owner_id = property.owner_id
    
    # Find existing conversation
    conversation = db.query(Conversation).filter(
        Conversation.property_id == message_data.property_id,
        Conversation.customer_id == customer_id,
        Conversation.owner_id == owner_id
    ).first()
    
    if not conversation:
        conversation = Conversation(
            property_id=message_data.property_id,
            customer_id=customer_id,
            owner_id=owner_id
        )
        db.add(conversation)
        db.flush()
    
    # Create message
    message = Message(
        conversation_id=conversation.id,
        from_user=current_user.id,
        to_user=message_data.to_user,
        content=message_data.content
    )
    db.add(message)
    
    # Update conversation last_message_at
    from datetime import datetime
    conversation.last_message_at = datetime.utcnow()
    
    db.commit()
    db.refresh(message)
    return message


@router.put("/{message_id}/read")
async def mark_message_read(
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark a message as read."""
    message = db.query(Message).filter(
        Message.id == message_id,
        Message.to_user == current_user.id
    ).first()
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    message.read = True
    db.commit()
    return {"message": "Message marked as read"}


@router.get("/unread-count")
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get count of unread messages."""
    count = db.query(Message).filter(
        Message.to_user == current_user.id,
        Message.read == False
    ).count()
    return {"unread_count": count}
