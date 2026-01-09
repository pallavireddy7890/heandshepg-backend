"""WebSocket for real-time messaging."""
from typing import Dict, List
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.orm import Session
import json

from app.database import get_db
from app.models import User, Message, Conversation

router = APIRouter(tags=["WebSocket"])


class ConnectionManager:
    """Manages WebSocket connections for real-time messaging."""
    
    def __init__(self):
        # user_id -> list of WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept and store a new WebSocket connection."""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
    
    def disconnect(self, websocket: WebSocket, user_id: str):
        """Remove a disconnected WebSocket."""
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
    
    async def send_personal_message(self, message: dict, user_id: str):
        """Send a message to a specific user."""
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except:
                    pass
    
    async def broadcast_to_users(self, message: dict, user_ids: List[str]):
        """Send a message to multiple users."""
        for user_id in user_ids:
            await self.send_personal_message(message, user_id)


manager = ConnectionManager()


@router.websocket("/ws/chat/{user_id}")
async def websocket_chat(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(...),
):
    """WebSocket endpoint for real-time chat."""
    from app.utils.security import decode_access_token
    
    # Verify token
    try:
        payload = decode_access_token(token)
        if not payload or payload.get("sub") != user_id:
            await websocket.close(code=4001, reason="Invalid token")
            return
    except Exception:
        await websocket.close(code=4001, reason="Authentication failed")
        return
    
    await manager.connect(websocket, user_id)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            action = message_data.get("action")
            
            if action == "send_message":
                # Save message to database and broadcast
                db = next(get_db())
                try:
                    await handle_send_message(db, user_id, message_data, manager)
                finally:
                    db.close()
            
            elif action == "typing":
                # Broadcast typing indicator
                to_user = message_data.get("to_user")
                if to_user:
                    await manager.send_personal_message({
                        "type": "typing",
                        "from_user": user_id,
                        "is_typing": message_data.get("is_typing", True)
                    }, to_user)
            
            elif action == "read":
                # Mark messages as read
                conversation_id = message_data.get("conversation_id")
                # Update read status (simplified)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket, user_id)


async def handle_send_message(db: Session, from_user_id: str, message_data: dict, manager: ConnectionManager):
    """Handle sending a message via WebSocket."""
    to_user = message_data.get("to_user")
    content = message_data.get("content")
    property_id = message_data.get("property_id")
    
    if not to_user or not content:
        return
    
    # Find or create conversation
    conversation = db.query(Conversation).filter(
        ((Conversation.user1_id == UUID(from_user_id)) & (Conversation.user2_id == UUID(to_user))) |
        ((Conversation.user1_id == UUID(to_user)) & (Conversation.user2_id == UUID(from_user_id)))
    ).first()
    
    if not conversation:
        conversation = Conversation(
            user1_id=UUID(from_user_id),
            user2_id=UUID(to_user),
            property_id=UUID(property_id) if property_id else None
        )
        db.add(conversation)
        db.flush()
    
    # Create message
    message = Message(
        conversation_id=conversation.id,
        sender_id=UUID(from_user_id),
        content=content
    )
    db.add(message)
    db.commit()
    
    # Broadcast to both users
    message_response = {
        "type": "new_message",
        "id": str(message.id),
        "conversation_id": str(conversation.id),
        "sender_id": from_user_id,
        "content": content,
        "created_at": datetime.utcnow().isoformat(),
    }
    
    await manager.broadcast_to_users(
        message_response,
        [from_user_id, to_user]
    )
