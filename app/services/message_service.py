import logging
from typing import List, Dict, Any
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import User, Message, Profile
from app.repositories import MessageRepository, PropertyRepository, ProfileRepository
from app.schemas import MessageCreate

logger = logging.getLogger(__name__)

class MessageService:
    @staticmethod
    def list_conversations(db: Session, current_user: User) -> List[Dict[str, Any]]:
        """List all conversations for the current user with details."""
        logger.info("Listing conversations for user: %s", current_user.id)
        try:
            conversations = MessageRepository.get_conversations_by_user(db, current_user.id)
            
            result = []
            for conv in conversations:
                # Get property title
                property_obj = PropertyRepository.get_property_by_id(db, conv.property_id)
                
                # Get other user's info
                other_user_id = conv.owner_id if conv.customer_id == current_user.id else conv.customer_id
                other_profile = ProfileRepository.get_profile_by_user_id(db, other_user_id)
                
                # Get last message
                last_message = db.query(Message).filter(Message.conversation_id == conv.id).order_by(Message.created_at.desc()).first()
                
                other_user = db.query(User).filter(User.id == other_user_id).first()
                
                conv_dict = {
                    "id": conv.id,
                    "property_id": conv.property_id,
                    "customer_id": conv.customer_id,
                    "owner_id": conv.owner_id,
                    "last_message_at": conv.last_message_at,
                    "created_at": conv.created_at,
                    "property_title": property_obj.title if property_obj else None,
                    "other_user_name": other_profile.name if other_profile else "User",
                    "other_user_photo": other_profile.profile_photo if other_profile else None,
                    "messages": [last_message] if last_message else [],
                    "is_online": other_user.is_online if other_user else False,
                    "last_seen_at": other_user.last_seen_at if other_user else None,
                }
                
                result.append(conv_dict)
                
            logger.info("Successfully fetched %d conversations for user %s", len(result), current_user.id)
            return result
        except Exception as e:
            logger.error("Failed to list conversations for user %s: %s", current_user.id, str(e), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error while retrieving conversations"
            )

    @staticmethod
    def get_conversation(db: Session, conversation_id: UUID, current_user: User) -> Dict[str, Any]:
        """Get a conversation with all messages and mark incoming messages as read."""
        logger.info("Fetching conversation %s for user %s", conversation_id, current_user.id)
        try:
            conversation = MessageRepository.get_conversation_by_id_and_user(db, conversation_id, current_user.id)
            if not conversation:
                logger.warning("Conversation %s not found for user %s", conversation_id, current_user.id)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation not found"
                )
                
            # Get all messages
            messages = MessageRepository.get_messages_by_conversation_id(db, conversation_id)
            
            # Mark as read
            MessageRepository.mark_messages_as_read(db, conversation_id, current_user.id)
            db.commit()
            
            # Get property and other user info
            property_obj = PropertyRepository.get_property_by_id(db, conversation.property_id)
            other_user_id = conversation.owner_id if conversation.customer_id == current_user.id else conversation.customer_id
            other_profile = ProfileRepository.get_profile_by_user_id(db, other_user_id)
            
            logger.info("Successfully fetched conversation %s with %d messages", conversation_id, len(messages))
            other_user = db.query(User).filter(User.id == other_user_id).first()
            
            return {
                "id": conversation.id,
                "property_id": conversation.property_id,
                "customer_id": conversation.customer_id,
                "owner_id": conversation.owner_id,
                "last_message_at": conversation.last_message_at,
                "created_at": conversation.created_at,
                "property_title": property_obj.title if property_obj else None,
                "other_user_name": other_profile.name if other_profile else "User",
                "other_user_photo": other_profile.profile_photo if other_profile else None,
                "messages": messages,
                "is_online": other_user.is_online if other_user else False,
                "last_seen_at": other_user.last_seen_at if other_user else None,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to retrieve conversation %s: %s", conversation_id, str(e), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error while retrieving conversation"
            )

    @staticmethod
    def send_message(db: Session, message_data: MessageCreate, current_user: User) -> Message:
        """Send a message, creating the conversation if it doesn't exist."""
        logger.info("User %s sending message in property %s", current_user.id, message_data.property_id)
        try:
            property_obj = PropertyRepository.get_property_by_id(db, message_data.property_id)
            if not property_obj:
                logger.warning("Property %s not found. Cannot send message.", message_data.property_id)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Property not found"
                )
                
            # Determine customer and owner
            if current_user.id == property_obj.owner_id:
                customer_id = message_data.to_user
                owner_id = current_user.id
            else:
                customer_id = current_user.id
                owner_id = property_obj.owner_id
                
            # Find or create conversation
            conversation = MessageRepository.get_conversation_by_property_customer_owner(
                db, message_data.property_id, customer_id, owner_id
            )
            
            if not conversation:
                logger.info("No conversation found. Creating new conversation for property %s", message_data.property_id)
                conversation = MessageRepository.create_conversation(db, message_data.property_id, customer_id, owner_id)
                
            # Create message
            message = MessageRepository.create_message(
                db=db,
                conversation_id=conversation.id,
                from_user=current_user.id,
                to_user=message_data.to_user if current_user.id == property_obj.owner_id else owner_id,
                content=message_data.content
            )
            
            # Update conversation timestamp
            MessageRepository.update_conversation_timestamp(db, conversation)
            db.commit()
            db.refresh(message)
            
            logger.info("Message %s successfully sent in conversation %s", message.id, conversation.id)
            return message
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to send message: %s", str(e), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error while sending message"
            )

    @staticmethod
    def mark_message_read(db: Session, message_id: UUID, current_user: User) -> Dict[str, str]:
        """Mark a specific message as read."""
        logger.info("Marking message %s as read by user %s", message_id, current_user.id)
        try:
            message = MessageRepository.get_message_by_id_and_to_user(db, message_id, current_user.id)
            if not message:
                logger.warning("Message %s not found or recipient mismatch for user %s", message_id, current_user.id)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Message not found"
                )
                
            message.read = True
            db.commit()
            logger.info("Message %s successfully marked as read", message_id)
            return {"message": "Message marked as read"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to mark message %s as read: %s", message_id, str(e), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error"
            )

    @staticmethod
    def get_unread_count(db: Session, current_user: User) -> Dict[str, int]:
        """Get the count of unread messages for the user."""
        logger.info("Getting unread message count for user %s", current_user.id)
        try:
            count = MessageRepository.get_unread_messages_count(db, current_user.id)
            logger.info("User %s has %d unread messages", current_user.id, count)
            return {"unread_count": count}
        except Exception as e:
            logger.error("Failed to get unread count for user %s: %s", current_user.id, str(e), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error"
            )
