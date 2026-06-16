from typing import List
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models import Conversation, Message

class MessageRepository:
    @staticmethod
    def get_conversations_by_user(db: Session, user_id: UUID) -> List[Conversation]:
        """List all conversations for a user, ordered by last message timestamp."""
        return db.query(Conversation).filter(
            or_(
                Conversation.customer_id == user_id,
                Conversation.owner_id == user_id
            )
        ).order_by(Conversation.last_message_at.desc()).all()

    @staticmethod
    def get_conversation_by_id_and_user(db: Session, conversation_id: UUID, user_id: UUID) -> Conversation | None:
        """Retrieve a specific conversation if the user is a participant."""
        return db.query(Conversation).filter(
            Conversation.id == conversation_id,
            or_(
                Conversation.customer_id == user_id,
                Conversation.owner_id == user_id
            )
        ).first()

    @staticmethod
    def get_conversation_by_property_customer_owner(
        db: Session, property_id: UUID, customer_id: UUID, owner_id: UUID
    ) -> Conversation | None:
        """Find an existing conversation between a customer and owner for a property."""
        return db.query(Conversation).filter(
            Conversation.property_id == property_id,
            Conversation.customer_id == customer_id,
            Conversation.owner_id == owner_id
        ).first()

    @staticmethod
    def create_conversation(db: Session, property_id: UUID, customer_id: UUID, owner_id: UUID) -> Conversation:
        """Create a new conversation record."""
        conversation = Conversation(
            property_id=property_id,
            customer_id=customer_id,
            owner_id=owner_id
        )
        db.add(conversation)
        db.flush()
        return conversation

    @staticmethod
    def get_messages_by_conversation_id(db: Session, conversation_id: UUID) -> List[Message]:
        """Retrieve all messages for a conversation, ordered by creation time."""
        return db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at.asc()).all()

    @staticmethod
    def mark_messages_as_read(db: Session, conversation_id: UUID, to_user: UUID) -> None:
        """Mark all messages sent to the user in a conversation as read."""
        db.query(Message).filter(
            Message.conversation_id == conversation_id,
            Message.to_user == to_user,
            Message.read == False
        ).update({"read": True})

    @staticmethod
    def create_message(db: Session, conversation_id: UUID, from_user: UUID, to_user: UUID, content: str) -> Message:
        """Create and add a new message to the database."""
        message = Message(
            conversation_id=conversation_id,
            from_user=from_user,
            to_user=to_user,
            content=content
        )
        db.add(message)
        return message

    @staticmethod
    def update_conversation_timestamp(db: Session, conversation: Conversation) -> None:
        """Update last_message_at timestamp for a conversation."""
        conversation.last_message_at = datetime.now(timezone.utc)

    @staticmethod
    def get_message_by_id_and_to_user(db: Session, message_id: UUID, to_user: UUID) -> Message | None:
        """Get a message by ID and verify recipient."""
        return db.query(Message).filter(
            Message.id == message_id,
            Message.to_user == to_user
        ).first()

    @staticmethod
    def get_unread_messages_count(db: Session, user_id: UUID) -> int:
        """Count unread messages for a user."""
        return db.query(Message).filter(
            Message.to_user == user_id,
            Message.read == False
        ).count()
