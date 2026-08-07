from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from pydantic import BaseModel

from app.database import get_db
from app.models import User, Profile, RoommateProfile, RoommateMatch, RoommateMessage, BlockedUser, Notification
from app.utils.security import get_current_user

router = APIRouter(prefix="/roommates", tags=["Roommate Matching"])


class ConnectionRequestPayload(BaseModel):
    senderId: UUID
    receiverId: UUID
    status: str = "pending"

class RoommateProfileCreate(BaseModel):
    age: Optional[int] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    preferred_location: Optional[str] = None
    preferred_city: Optional[str] = None
    move_in_date: Optional[datetime] = None
    preferences: Optional[List[str]] = []
    languages: Optional[List[str]] = []
    hobbies: Optional[List[str]] = []
    bio: Optional[str] = None
    # Additional fields for frontend compatibility
    dietary_preference: Optional[str] = None
    smoking: Optional[bool] = False
    drinking: Optional[bool] = False
    pets_allowed: Optional[bool] = False
    cleanliness_level: Optional[int] = 3
    is_active: Optional[bool] = True


class RoommateProfileResponse(BaseModel):
    id: UUID
    user_id: UUID
    age: Optional[int]
    gender: Optional[str]
    occupation: Optional[str]
    budget_min: Optional[int]
    budget_max: Optional[int]
    preferred_location: Optional[str]
    preferred_city: Optional[str]
    move_in_date: Optional[datetime]
    preferences: Optional[List[str]]
    languages: Optional[List[str]]
    hobbies: Optional[List[str]]
    bio: Optional[str]
    is_active: bool
    # Additional fields
    dietary_preference: Optional[str] = None
    smoking: Optional[bool] = False
    drinking: Optional[bool] = False
    pets_allowed: Optional[bool] = False
    cleanliness_level: Optional[int] = 3
    user_name: Optional[str] = None
    user_photo: Optional[str] = None

    class Config:
        from_attributes = True


class RoommateMatchResponse(BaseModel):
    id: UUID  # Profile ID
    matched_user_id: UUID
    match_score: Optional[float]
    status: str
    user_name: Optional[str] = None
    user_photo: Optional[str] = None
    age: Optional[int] = None
    occupation: Optional[str] = None
    bio: Optional[str] = None
    preferences: Optional[List[str]] = None
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    match_id: Optional[UUID] = None

    class Config:
        from_attributes = True


class ConnectionRespond(BaseModel):
    status: str  # accepted or rejected


class RoommateMessageCreate(BaseModel):
    content: str
    reply_to: Optional[dict] = None


class BlockUserPayload(BaseModel):
    blockedUserId: UUID


class BlockStatusResponse(BaseModel):
    is_blocked: bool = False
    blocked_by_me: bool = False
    blocked_by_them: bool = False


class UserSummary(BaseModel):
    id: UUID
    name: str
    profile_photo: Optional[str] = None

class RoommateMessageResponse(BaseModel):
    id: UUID
    sender_id: UUID
    receiver_id: UUID
    content: str
    created_at: datetime
    read: bool
    reply_to: Optional[dict] = None
    is_deleted: bool = False
    sender_info: Optional[UserSummary] = None
    receiver_info: Optional[UserSummary] = None

    class Config:
        from_attributes = True


class ChatListResponse(BaseModel):
    user_id: UUID
    user_name: Optional[str]
    user_photo: Optional[str]
    last_message: Optional[str]
    last_message_at: Optional[datetime]
    unread_count: int
    is_blocked: bool = False
    blocked_by_me: bool = False
    blocked_by_them: bool = False
    is_online: bool = False
    last_seen_at: Optional[datetime] = None


# ========== Helpers ==========

def check_block_status(db: Session, user_a_id: UUID, user_b_id: UUID) -> dict:
    """Check block status between two users. Returns dict with is_blocked, blocked_by_me, blocked_by_them."""
    blocked_by_me = db.query(BlockedUser).filter(
        BlockedUser.blocker_id == user_a_id,
        BlockedUser.blocked_id == user_b_id
    ).first() is not None

    blocked_by_them = db.query(BlockedUser).filter(
        BlockedUser.blocker_id == user_b_id,
        BlockedUser.blocked_id == user_a_id
    ).first() is not None

    return {
        "is_blocked": blocked_by_me or blocked_by_them,
        "blocked_by_me": blocked_by_me,
        "blocked_by_them": blocked_by_them,
    }


# ========== Endpoints ==========

@router.get("/profile", response_model=Optional[RoommateProfileResponse])
async def get_my_roommate_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's roommate profile. Returns null if no profile exists."""
    profile = db.query(RoommateProfile).filter(RoommateProfile.user_id == current_user.id).first()
    
    if not profile:
        return None
    
    response = RoommateProfileResponse.model_validate(profile)
    user_profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    response.user_name = user_profile.name if user_profile else None
    response.user_photo = user_profile.profile_photo if user_profile else None
    
    return response



@router.get("/profile/{user_id}", response_model=RoommateProfileResponse)
async def get_roommate_profile_by_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get any user's roommate profile."""

    profile = (
        db.query(RoommateProfile)
        .filter(RoommateProfile.user_id == user_id)
        .first()
    )

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    response = RoommateProfileResponse.model_validate(profile)

    user_profile = (
        db.query(Profile)
        .filter(Profile.user_id == user_id)
        .first()
    )

    response.user_name = user_profile.name if user_profile else None
    response.user_photo = user_profile.profile_photo if user_profile else None

    return response

@router.post("/profile", response_model=RoommateProfileResponse)
async def create_or_update_roommate_profile(
    profile_data: RoommateProfileCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create or update roommate profile."""
    profile = db.query(RoommateProfile).filter(RoommateProfile.user_id == current_user.id).first()
    
    if profile:
        # Update existing
        for field, value in profile_data.model_dump(exclude_unset=True).items():
            setattr(profile, field, value)
    else:
        # Create new
        profile = RoommateProfile(
            user_id=current_user.id,
            **profile_data.model_dump()
        )
        db.add(profile)
    
    db.commit()
    db.refresh(profile)
    
    response = RoommateProfileResponse.model_validate(profile)
    user_profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    response.user_name = user_profile.name if user_profile else None
    response.user_photo = user_profile.profile_photo if user_profile else None
    
    return response


@router.delete("/profile")
async def delete_roommate_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete roommate profile."""
    profile = db.query(RoommateProfile).filter(RoommateProfile.user_id == current_user.id).first()
    
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    
    db.delete(profile)
    db.commit()
    return {"message": "Roommate profile deleted"}


@router.get("/matches", response_model=List[RoommateMatchResponse])
async def get_roommate_matches(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get potential roommate matches based on compatibility."""
    my_profile = db.query(RoommateProfile).filter(RoommateProfile.user_id == current_user.id).first()
    
    if not my_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please create a roommate profile first"
        )
    
    # Find compatible profiles (show all active profiles from other users)
    query = db.query(RoommateProfile).filter(
        RoommateProfile.user_id != current_user.id,
        RoommateProfile.is_active == True
    )
    
    potential_matches = query.limit(20).all()
    
    # Pre-fetch existing connection requests
    existing_matches = db.query(RoommateMatch).filter(
        or_(
            RoommateMatch.user_id == current_user.id,
            RoommateMatch.matched_user_id == current_user.id
        )
    ).all()
    
    match_map = {} # {other_user_id: (status, match_id)}
    for m in existing_matches:
        if m.status == "accepted":
            other_id = m.matched_user_id if m.user_id == current_user.id else m.user_id
            match_map[other_id] = ("accepted", m.id)
        elif m.status == "pending":
            if m.user_id == current_user.id:
                match_map[m.matched_user_id] = ("pending", m.id)
            else:
                match_map[m.user_id] = ("incoming", m.id)
        elif m.status == "cancelled":
            continue # Ignore cancelled requests
        else:
            other_id = m.matched_user_id if m.user_id == current_user.id else m.user_id
            match_map[other_id] = (m.status, m.id)

    result = []
    for match_profile in potential_matches:
        # Calculate match score
        score = calculate_match_score(my_profile, match_profile)
        
        user_profile = db.query(Profile).filter(Profile.user_id == match_profile.user_id).first()
        
        # Determine status
        match_info = match_map.get(match_profile.user_id, ("suggested", None))
        match_status, match_id = match_info
        
        result.append(RoommateMatchResponse(
            id=match_profile.id,
            matched_user_id=match_profile.user_id,
            match_score=score,
            status=match_status,
            user_name=user_profile.name if user_profile else None,
            user_photo=user_profile.profile_photo if user_profile else None,
            age=match_profile.age,
            occupation=match_profile.occupation,
            bio=match_profile.bio,
            preferences=match_profile.preferences,
            budget_min=match_profile.budget_min,
            budget_max=match_profile.budget_max,
            match_id=match_id,
        ))
    
    # Sort by match score
    result.sort(key=lambda x: x.match_score or 0, reverse=True)
    return result


def calculate_match_score(profile1: RoommateProfile, profile2: RoommateProfile) -> float:
    """Calculate compatibility score between two profiles (0-100)."""
    score = 50.0  # Base score
    
    # Preference matching
    if profile1.preferences and profile2.preferences:
        common_prefs = set(profile1.preferences) & set(profile2.preferences)
        pref_score = (len(common_prefs) / max(len(profile1.preferences), 1)) * 20
        score += pref_score
    
    # Language matching
    if profile1.languages and profile2.languages:
        common_langs = set(profile1.languages) & set(profile2.languages)
        if common_langs:
            score += 10
    
    # Hobby matching
    if profile1.hobbies and profile2.hobbies:
        common_hobbies = set(profile1.hobbies) & set(profile2.hobbies)
        hobby_score = (len(common_hobbies) / max(len(profile1.hobbies), 1)) * 10
        score += hobby_score
    
    # Budget compatibility
    if profile1.budget_max and profile2.budget_min:
        if profile1.budget_max >= profile2.budget_min:
            score += 10
    
    return min(score, 100.0)


@router.post("/matches/{profile_id}/connect")
async def connect_with_roommate(
    profile_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Express interest in connecting with a potential roommate."""
    target_profile = db.query(RoommateProfile).filter(RoommateProfile.id == profile_id).first()
    
    if not target_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    
    if target_profile.user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot connect with yourself")
    
    # Check if already connected (in either direction)
    existing = db.query(RoommateMatch).filter(
        or_(
            and_(RoommateMatch.user_id == current_user.id, RoommateMatch.matched_user_id == target_profile.user_id),
            and_(RoommateMatch.user_id == target_profile.user_id, RoommateMatch.matched_user_id == current_user.id)
        )
    ).first()
    
    if existing:
        return {"message": "Already connected", "status": existing.status, "match_id": str(existing.id)}
    
    # Create match request
    my_profile = db.query(RoommateProfile).filter(RoommateProfile.user_id == current_user.id).first()
    score = calculate_match_score(my_profile, target_profile) if my_profile else 50.0
    
    match = RoommateMatch(
        user_id=current_user.id,
        matched_user_id=target_profile.user_id,
        match_score=score,
        status="pending"
    )
    db.add(match)
    db.commit()
    
    return {"message": "Connection request sent", "match_id": str(match.id), "status": "pending"}


@router.post("/requests")
async def send_connection_request(
    payload: ConnectionRequestPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Alias for connecting with a roommate using a JSON payload."""
    target_user_id = payload.receiverId
    # Security: Use current_user.id as sender regardless of payload.senderId
    # (unless admin, but let's stick to current user for now)
    sender_id = current_user.id
    
    # Check if already connected (in either direction)
    existing = db.query(RoommateMatch).filter(
        or_(
            and_(RoommateMatch.user_id == sender_id, RoommateMatch.matched_user_id == target_user_id),
            and_(RoommateMatch.user_id == target_user_id, RoommateMatch.matched_user_id == sender_id)
        ),
        RoommateMatch.status != "cancelled"
    ).first()
    
    if existing:
        if existing.status == "cancelled":
            existing.status = "pending"
            existing.user_id = sender_id
            existing.matched_user_id = target_user_id
            db.commit()
            return existing
        return existing
    
    # Create match request
    match = RoommateMatch(
        user_id=sender_id,
        matched_user_id=target_user_id,
        match_score=50.0,
        status="pending"
    )
    db.add(match)
    db.commit()
    db.refresh(match)
    sender_profile = db.query(Profile).filter(
        Profile.user_id == sender_id
    ).first()

    db.add(
        Notification(
            user_id=target_user_id,
            title="🤝 New Roommate Request",
            message=f"{sender_profile.name if sender_profile else 'Someone'} wants to connect with you.",
            type="roommate_request",
            link="/roommates?tab=requests"
        )
    )

    db.commit()
    return match


@router.delete("/requests/{match_id}")
async def delete_connection_request(
    match_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete or cancel a connection request."""
    match = db.query(RoommateMatch).filter(RoommateMatch.id == match_id).first()
    
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
        
    # Only allow the sender to cancel 'pending'
    if match.status == "pending" and match.user_id == current_user.id:

        # Get sender profile
        sender_profile = db.query(Profile).filter(
            Profile.user_id == current_user.id
        ).first()

        # Delete notification
        if sender_profile:
            db.query(Notification).filter(
                Notification.user_id == match.matched_user_id,
                Notification.type == "roommate_request",
                Notification.link == "/roommates?tab=requests",
                Notification.message == f"{sender_profile.name} wants to connect with you."
            ).delete(synchronize_session=False)

        # Delete request
        db.delete(match)
        db.commit()

        return {"message": "Request deleted"}
        
    # Generic delete if authorized (e.g. either party can delete an accepted/rejected match to disconnect)
    if match.user_id == current_user.id or match.matched_user_id == current_user.id:
        db.delete(match)
        db.commit()
        return {"message": "Match deleted"}
        
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")


@router.get("/requests")
async def get_connection_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List incoming connection requests."""
    requests = db.query(RoommateMatch).filter(
        RoommateMatch.matched_user_id == current_user.id,
        RoommateMatch.user_id != current_user.id,
        RoommateMatch.status == "pending"
    ).all()
    
    result = []
    for req in requests:
        sender_profile = db.query(Profile).filter(Profile.user_id == req.user_id).first()
        result.append({
            "id": req.id,
            "sender_id": req.user_id,
            "sender_name": sender_profile.name if sender_profile else "Unknown",
            "sender_photo": sender_profile.profile_photo if sender_profile else None,
            "created_at": req.created_at,
            "status": req.status
        })
    return result


@router.post("/requests/{match_id}/respond")
async def respond_to_request(
    match_id: UUID,
    response: ConnectionRespond,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Accept or reject a connection request."""
    match = db.query(RoommateMatch).filter(
        RoommateMatch.id == match_id,
        RoommateMatch.matched_user_id == current_user.id
    ).first()
    
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    
    if response.status not in ["accepted", "rejected"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
    

    match.status = response.status

    receiver_profile = db.query(Profile).filter(
        Profile.user_id == current_user.id
    ).first()

    if response.status == "accepted":
        db.add(
            Notification(
                user_id=match.user_id,
                title="🎉 Request Accepted",
                message=f"{receiver_profile.name if receiver_profile else 'User'} accepted your roommate request.",
                type="roommate_request",
                link="/roommates?tab=matches"
            )
        )

    elif response.status == "rejected":
        db.add(
            Notification(
                user_id=match.user_id,
                title="Roommate Request",
                message=f"{receiver_profile.name if receiver_profile else 'User'} declined your roommate request.",
                type="roommate_request",
                link="/roommates?tab=matches"
            )
        )

    db.commit()

    return {
        "message": f"Connection {response.status}",
        "status": response.status
    }


@router.get("/chats", response_model=List[ChatListResponse])
async def get_chat_list(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all users with whom current user has an accepted match."""
    matches = db.query(RoommateMatch).filter(
        and_(
            or_(RoommateMatch.user_id == current_user.id, RoommateMatch.matched_user_id == current_user.id),
            RoommateMatch.status == "accepted"
        )
    ).all()
    
    result = []
    for match in matches:
        other_user_id = match.matched_user_id if match.user_id == current_user.id else match.user_id
        other_profile = db.query(Profile).filter(Profile.user_id == other_user_id).first()
        
        # Get last message
        last_msg = db.query(RoommateMessage).filter(
            or_(
                and_(RoommateMessage.sender_id == current_user.id, RoommateMessage.receiver_id == other_user_id),
                and_(RoommateMessage.sender_id == other_user_id, RoommateMessage.receiver_id == current_user.id)
            )
        ).order_by(desc(RoommateMessage.created_at)).first()
        
        # unread count
        unread_count = db.query(RoommateMessage).filter(
            RoommateMessage.sender_id == other_user_id,
            RoommateMessage.receiver_id == current_user.id,
            RoommateMessage.read == False
        ).count()
        
        # Check block status
        block_info = check_block_status(db, current_user.id, other_user_id)

        other_user = db.query(User).filter(User.id == other_user_id).first()

        result.append(ChatListResponse(
            user_id=other_user_id,
            user_name=other_profile.name if other_profile else "Unknown",
            user_photo=other_profile.profile_photo if other_profile else None,
            last_message=last_msg.content if last_msg else None,
            last_message_at=last_msg.created_at if last_msg else None,
            unread_count=unread_count,
            is_blocked=block_info["is_blocked"],
            blocked_by_me=block_info["blocked_by_me"],
            blocked_by_them=block_info["blocked_by_them"],
            is_online=other_user.is_online if other_user else False,
            last_seen_at=other_user.last_seen_at if other_user else None,
        ))
        
    # Sort by last message time
    def get_sort_key(x):
        if not x.last_message_at:
            return datetime.min.replace(tzinfo=timezone.utc)
        if x.last_message_at.tzinfo is not None:
            return x.last_message_at
        return x.last_message_at.replace(tzinfo=timezone.utc)
        
    result.sort(key=get_sort_key, reverse=True)
    return result


@router.get("/unread-count")
async def get_total_unread_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the total number of unread messages for the current user."""
    count = db.query(RoommateMessage).filter(
        RoommateMessage.receiver_id == current_user.id,
        RoommateMessage.read == False
    ).count()
    return {"unread_count": count}


@router.get("/chats/{user_id}/messages", response_model=List[RoommateMessageResponse])
async def get_messages(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get message history between two users."""
    # Check if they are connected
    match = db.query(RoommateMatch).filter(
        and_(
            or_(
                and_(RoommateMatch.user_id == current_user.id, RoommateMatch.matched_user_id == user_id),
                and_(RoommateMatch.user_id == user_id, RoommateMatch.matched_user_id == current_user.id)
            ),
            RoommateMatch.status == "accepted"
        )
    ).first()
    
    if not match:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not connected with this user")
    
    messages = db.query(RoommateMessage).filter(
        or_(
            and_(RoommateMessage.sender_id == current_user.id, RoommateMessage.receiver_id == user_id),
            and_(RoommateMessage.sender_id == user_id, RoommateMessage.receiver_id == current_user.id)
        )
    ).order_by(RoommateMessage.created_at).all()
    
    # Mark messages as read
    db.query(RoommateMessage).filter(
        RoommateMessage.sender_id == user_id,
        RoommateMessage.receiver_id == current_user.id,
        RoommateMessage.read == False
    ).update({"read": True})
    db.commit()
    
    # Enrich with sender/receiver info
    user_cache = {}
    
    def get_user_summary(uid):
        if uid not in user_cache:
            p = db.query(Profile).filter(Profile.user_id == uid).first()
            user_cache[uid] = UserSummary(
                id=uid,
                name=p.name if p else "Unknown",
                profile_photo=p.profile_photo if p else None
            )
        return user_cache[uid]

    result = []
    for m in messages:
        resp = RoommateMessageResponse.model_validate(m)
        resp.sender_info = get_user_summary(m.sender_id)
        resp.receiver_info = get_user_summary(m.receiver_id)
        result.append(resp)
        
    return result


@router.post("/chats/{user_id}/messages", response_model=RoommateMessageResponse)
async def send_message(
    user_id: UUID,
    message_data: RoommateMessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a new message to a connected user."""
    # ===== BLOCK CHECK (security validation) =====
    block_info = check_block_status(db, current_user.id, user_id)
    if block_info["is_blocked"]:
        if block_info["blocked_by_me"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You have blocked this user. Unblock to send messages."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot send messages to this user."
            )

    # Check if they are connected
    match = db.query(RoommateMatch).filter(
        and_(
            or_(
                and_(RoommateMatch.user_id == current_user.id, RoommateMatch.matched_user_id == user_id),
                and_(RoommateMatch.user_id == user_id, RoommateMatch.matched_user_id == current_user.id)
            ),
            RoommateMatch.status == "accepted"
        )
    ).first()
    
    if not match:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not connected with this user")
    
    new_message = RoommateMessage(
        sender_id=current_user.id,
        receiver_id=user_id,
        content=message_data.content,
        reply_to=message_data.reply_to
    )
    db.add(new_message)
    db.commit()
    db.refresh(new_message)
    
    # Enrich Response
    sender_p = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    receiver_p = db.query(Profile).filter(Profile.user_id == user_id).first()
    
    resp = RoommateMessageResponse.model_validate(new_message)
    resp.sender_info = UserSummary(id=current_user.id, name=sender_p.name if sender_p else "Me", profile_photo=sender_p.profile_photo if sender_p else None)
    resp.receiver_info = UserSummary(id=user_id, name=receiver_p.name if receiver_p else "User", profile_photo=receiver_p.profile_photo if receiver_p else None)
    
    return resp


@router.delete("/chats/{user_id}/messages/{message_id}")
async def delete_message(
    user_id: UUID,
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a message (sender only)."""
    message = db.query(RoommateMessage).filter(
        RoommateMessage.id == message_id,
        or_(RoommateMessage.sender_id == current_user.id, RoommateMessage.receiver_id == current_user.id)
    ).first()

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    if message.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the sender can delete their message")

    # WhatsApp-style: we don't actually REMOVE the row, just flag it and clear content
    message.is_deleted = True
    message.content = "This message was deleted"
    db.commit()
    
    return {"status": "success", "message": "Message deleted"}


# ========== Block User Endpoints ==========

@router.post("/block-user", response_model=BlockStatusResponse)
async def block_user(
    payload: BlockUserPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Block a user. Prevents both users from sending messages to each other."""
    blocked_user_id = payload.blockedUserId

    if blocked_user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot block yourself"
        )

    # Check if target user exists
    target_user = db.query(User).filter(User.id == blocked_user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Check if already blocked
    existing = db.query(BlockedUser).filter(
        BlockedUser.blocker_id == current_user.id,
        BlockedUser.blocked_id == blocked_user_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already blocked"
        )

    # Create block record
    block = BlockedUser(
        blocker_id=current_user.id,
        blocked_id=blocked_user_id
    )
    db.add(block)
    db.commit()

    return BlockStatusResponse(
        is_blocked=True,
        blocked_by_me=True,
        blocked_by_them=False
    )


@router.delete("/block-user/{blocked_user_id}")
async def unblock_user(
    blocked_user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unblock a user."""
    block = db.query(BlockedUser).filter(
        BlockedUser.blocker_id == current_user.id,
        BlockedUser.blocked_id == blocked_user_id
    ).first()

    if not block:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Block record not found. User is not blocked by you."
        )

    db.delete(block)
    db.commit()

    # Return updated block status (the other user may still have blocked current user)
    updated_status = check_block_status(db, current_user.id, blocked_user_id)
    return {
        "message": "User unblocked successfully",
        **updated_status
    }


@router.get("/block-status/{user_id}", response_model=BlockStatusResponse)
async def get_block_status(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check block status between current user and target user."""
    status_info = check_block_status(db, current_user.id, user_id)
    return BlockStatusResponse(**status_info)
