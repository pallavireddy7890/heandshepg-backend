"""Host profile router - public endpoints for viewing host profiles and their properties."""
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import User, Property, Room, Review, Profile, Booking
from app.models.message import Message, Conversation


router = APIRouter(prefix="/host", tags=["Host"])


@router.get("/{host_id}")
async def get_host_profile(
    host_id: UUID,
    db: Session = Depends(get_db),
):
    """Get public host profile with stats."""
    # Get user and profile
    user = db.query(User).filter(User.id == host_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Host not found")
    
    profile = db.query(Profile).filter(Profile.user_id == host_id).first()
    
    # Get host properties count
    properties_count = db.query(Property).filter(
        Property.owner_id == host_id,
        Property.status == "active",
        Property.inactive_at.is_(None)
    ).count()
    
    # Calculate stats
    # Years hosting - from profile.hosting_since if set, else from first property creation date
    years_hosting = 0
    
    # Get first property for fallback calculations
    first_property = db.query(Property).filter(
        Property.owner_id == host_id,
        Property.inactive_at.is_(None)
    ).order_by(Property.created_at.asc()).first()
    
    # First check if profile has hosting_since date set
    if profile and hasattr(profile, 'hosting_since') and profile.hosting_since:
        try:
            from datetime import date
            hosting_date = profile.hosting_since
            if isinstance(hosting_date, date):
                years_hosting = (datetime.utcnow().date() - hosting_date).days // 365
        except Exception:
            years_hosting = 0
    
    # Fallback to first property creation date
    if years_hosting == 0 and first_property and first_property.created_at:
        try:
            created_date = first_property.created_at
            # Handle offset-aware datetime by converting to naive
            if hasattr(created_date, 'replace') and created_date.tzinfo is not None:
                created_date = created_date.replace(tzinfo=None)
            years_hosting = (datetime.utcnow() - created_date).days // 365
        except Exception:
            years_hosting = 0
    
    # Average rating from reviews
    avg_rating = db.query(func.avg(Review.rating)).join(Property).filter(
        Property.owner_id == host_id
    ).scalar() or 0
    
    total_reviews = db.query(Review).join(Property).filter(
        Property.owner_id == host_id
    ).count()
    
    # Occupancy rate (active bookings / total beds)
    total_beds = db.query(func.sum(Room.bed_count)).join(Property).filter(
        Property.owner_id == host_id,
        Property.status == "active"
    ).scalar() or 0
    
    active_bookings = db.query(Booking).join(Property).filter(
        Property.owner_id == host_id,
        Booking.status.in_(['active', 'paid', 'checked_in'])
    ).count()
    
    occupancy_rate = round((active_bookings / total_beds * 100) if total_beds > 0 else 0, 1)
    
    # Response rate - calculate from messages
    # Count messages sent TO the host and messages host REPLIED to
    from datetime import timedelta
    from sqlalchemy import and_, or_
    
    # Get conversations where host is the owner
    host_conversations = db.query(Conversation).filter(
        Conversation.owner_id == host_id
    ).all()
    
    conversation_ids = [c.id for c in host_conversations]
    
    # Messages sent to host (from customers)
    messages_to_host = db.query(Message).filter(
        Message.conversation_id.in_(conversation_ids),
        Message.to_user == host_id
    ).count() if conversation_ids else 0
    
    # Messages sent by host (replies)
    messages_from_host = db.query(Message).filter(
        Message.conversation_id.in_(conversation_ids),
        Message.from_user == host_id
    ).count() if conversation_ids else 0
    
    response_rate = round((messages_from_host / messages_to_host * 100) if messages_to_host > 0 else 100, 0)
    response_rate = min(response_rate, 100)  # Cap at 100%
    
    # Calculate average response time
    avg_response_time = "< 1 hour"
    if messages_to_host > 0 and messages_from_host > 0:
        # Get a sample of customer messages and find next host reply
        sample_messages = db.query(Message).filter(
            Message.conversation_id.in_(conversation_ids),
            Message.to_user == host_id
        ).order_by(Message.created_at.desc()).limit(20).all() if conversation_ids else []
        
        response_times = []
        for msg in sample_messages:
            # Find next message from host after this customer message
            next_reply = db.query(Message).filter(
                Message.conversation_id == msg.conversation_id,
                Message.from_user == host_id,
                Message.created_at > msg.created_at
            ).order_by(Message.created_at.asc()).first()
            
            if next_reply and msg.created_at and next_reply.created_at:
                try:
                    reply_time = next_reply.created_at.replace(tzinfo=None)
                    msg_time = msg.created_at.replace(tzinfo=None)
                    diff = (reply_time - msg_time).total_seconds() / 3600  # hours
                    if diff > 0:
                        response_times.append(diff)
                except:
                    pass
        
        if response_times:
            avg_hours = sum(response_times) / len(response_times)
            if avg_hours < 1:
                avg_response_time = "< 1 hour"
            elif avg_hours < 24:
                avg_response_time = f"{int(avg_hours)} hours"
            else:
                avg_response_time = f"{int(avg_hours / 24)} days"
    
    # Determine if host is active (has properties, recent activity)
    from datetime import datetime as dt
    thirty_days_ago = dt.utcnow() - timedelta(days=30)
    
    recent_bookings = db.query(Booking).join(Property).filter(
        Property.owner_id == host_id,
        Booking.created_at >= thirty_days_ago
    ).count()
    
    recent_messages = db.query(Message).filter(
        Message.from_user == host_id,
        Message.created_at >= thirty_days_ago
    ).count() if conversation_ids else 0
    
    is_active_host = properties_count > 0 and (recent_bookings > 0 or recent_messages > 0 or user.is_verified)
    
    # Repeat guests
    repeat_guests = db.query(Booking.customer_id).join(Property).filter(
        Property.owner_id == host_id
    ).group_by(Booking.customer_id).having(func.count(Booking.id) > 1).count()
    
    total_guests = db.query(Booking.customer_id).join(Property).filter(
        Property.owner_id == host_id
    ).distinct().count()
    
    repeat_guest_rate = round((repeat_guests / total_guests * 100) if total_guests > 0 else 0, 1)
    
    # Get member since date (from first property or profile creation)
    member_since_date = None
    if first_property and first_property.created_at:
        try:
            member_since_date = first_property.created_at.strftime("%b %Y")
        except:
            pass
    if not member_since_date and profile and profile.created_at:
        try:
            member_since_date = profile.created_at.strftime("%b %Y")
        except:
            pass
    
    return {
        "id": str(host_id),
        "name": profile.name if profile else user.email.split('@')[0],
        "email": user.email,
        "phone": profile.phone if profile else None,
        "profile_photo": profile.profile_photo if profile else None,
        "about": profile.about if profile else None,
        "city": profile.city if profile else None,
        "languages_known": profile.languages_known if profile else [],
        "is_verified": user.is_verified,
        "years_hosting": years_hosting,
        "member_since_date": member_since_date,
        "properties_count": properties_count,
        "avg_rating": round(avg_rating, 1),
        "total_reviews": total_reviews,
        "stats": {
            "response_rate": response_rate,
            "occupancy_rate": occupancy_rate,
            "repeat_guest_rate": repeat_guest_rate,
            "response_time": avg_response_time,
        },
        "is_active_host": is_active_host,
        # Owner availability (using defaults until migration is run)
        "availability": {
            "is_available": True,
            "available_from": "09:00",
            "available_to": "21:00",
            "available_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        }
    }


@router.get("/{host_id}/properties")
async def get_host_properties(
    host_id: UUID,
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    """Get all properties by a host."""
    from sqlalchemy.orm import joinedload
    
    # Verify host exists
    user = db.query(User).filter(User.id == host_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Host not found")
    
    # Get host properties
    properties = db.query(Property).options(
        joinedload(Property.rooms)
    ).filter(
        Property.owner_id == host_id,
        Property.status == "active",
        Property.inactive_at.is_(None)
    ).offset(skip).limit(limit).all()
    
    result = []
    for prop in properties:
        # Get min rent from rooms
        min_rent = min([r.price for r in prop.rooms], default=prop.monthly_rent) if prop.rooms else prop.monthly_rent
        
        # Get vacancy
        total_vacancy = sum([r.vacancy_count for r in prop.rooms], 0) if prop.rooms else 0
        
        # Get reviews count
        reviews_count = db.query(Review).filter(Review.property_id == prop.id).count()
        avg_rating = db.query(func.avg(Review.rating)).filter(Review.property_id == prop.id).scalar() or 0
        
        result.append({
            "id": str(prop.id),
            "title": prop.title,
            "address": prop.address,
            "locality": prop.locality,
            "city": prop.city,
            "gender_preference": prop.gender_preference,
            "monthly_rent": min_rent or prop.monthly_rent,
            "photos": prop.photos or [],
            "amenities": prop.amenities or [],
            "vacancy_count": total_vacancy,
            "avg_rating": round(avg_rating, 1),
            "reviews_count": reviews_count,
        })
    
    return result


@router.get("/{host_id}/reviews")
async def get_host_reviews(
    host_id: UUID,
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    """Get all reviews for a host's properties, sorted by rating (highest first)."""
    # Verify host exists
    user = db.query(User).filter(User.id == host_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Host not found")
    
    # Get all reviews for host's properties, sorted by rating DESC
    reviews = db.query(Review).join(Property).filter(
        Property.owner_id == host_id
    ).order_by(Review.rating.desc(), Review.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for review in reviews:
        # Get reviewer profile
        reviewer_profile = db.query(Profile).filter(Profile.user_id == review.user_id).first()
        reviewer_user = db.query(User).filter(User.id == review.user_id).first()
        
        # Get property info
        property_obj = db.query(Property).filter(Property.id == review.property_id).first()
        
        result.append({
            "id": str(review.id),
            "rating": review.rating,
            "comment": review.comment,
            "cleanliness_rating": review.cleanliness_rating,
            "food_rating": review.food_rating,
            "safety_rating": review.safety_rating,
            "created_at": review.created_at.isoformat() if review.created_at else None,
            "reviewer": {
                "name": reviewer_profile.name if reviewer_profile else (reviewer_user.email.split('@')[0] if reviewer_user else "Anonymous"),
                "profile_photo": reviewer_profile.profile_photo if reviewer_profile else None,
            },
            "property": {
                "id": str(property_obj.id) if property_obj else None,
                "title": property_obj.title if property_obj else None,
            }
        })
    
    return result
