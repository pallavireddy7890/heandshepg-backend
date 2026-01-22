"""Bookings router."""
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Booking, Property, Room, Profile
from app.schemas import (
    BookingCreate,
    BookingStatusUpdate,
    BookingCancelRequest,
    BookingResponse,
    BookingDetailResponse,
)
from app.utils.security import get_current_user, require_role
from app.utils.notifications import notify_booking_created, notify_booking_accepted, notify_booking_rejected

require_admin = require_role("admin")

router = APIRouter(prefix="/bookings", tags=["Bookings"])


@router.get("/all", dependencies=[Depends(require_admin)])
async def list_all_bookings(
    db: Session = Depends(get_db),
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=100),
):
    """List all bookings on the platform (admin only)."""
    from sqlalchemy.orm import joinedload
    
    query = db.query(Booking).options(
        joinedload(Booking.property),
        joinedload(Booking.customer),
        joinedload(Booking.owner),
    )
    
    if status_filter:
        query = query.filter(Booking.status == status_filter)
    
    bookings = query.order_by(Booking.created_at.desc()).offset(skip).limit(limit).all()
    
    # Enrich with property and user details
    result = []
    for booking in bookings:
        # Get customer name from profile or user email
        customer_name = "Unknown Customer"
        if booking.customer_id:
            customer_profile = db.query(Profile).filter(Profile.user_id == booking.customer_id).first()
            if customer_profile:
                customer_name = customer_profile.name
            elif booking.customer:
                customer_name = booking.customer.email
        
        # Get owner name from profile or user email
        owner_name = "Unknown Owner"
        if booking.owner_id:
            owner_profile = db.query(Profile).filter(Profile.user_id == booking.owner_id).first()
            if owner_profile:
                owner_name = owner_profile.name
            elif booking.owner:
                owner_name = booking.owner.email
        
        # Get property title
        property_title = "Unknown Property"
        if booking.property:
            property_title = booking.property.title
        
        result.append({
            "id": str(booking.id),
            "property_id": str(booking.property_id),
            "property_title": property_title,
            "customer_name": customer_name,
            "owner_name": owner_name,
            "status": booking.status,
            "start_date": booking.start_date.isoformat() if booking.start_date else None,
            "end_date": booking.end_date.isoformat() if booking.end_date else None,
            "total_amount": booking.amount or 0,
            "created_at": booking.created_at.isoformat() if booking.created_at else None,
        })
    
    return result


@router.get("")
async def list_bookings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status_filter: str = None,
):
    """List current user's bookings (as customer or owner)."""
    try:
        query = db.query(Booking).filter(
            (Booking.customer_id == current_user.id) | (Booking.owner_id == current_user.id)
        )
        
        if status_filter:
            query = query.filter(Booking.status == status_filter)
        
        bookings = query.order_by(Booking.created_at.desc()).all()
        
        result = []
        for booking in bookings:
            # Get property details
            property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
            
            # Get customer name
            customer_name = None
            if booking.customer_id:
                customer_profile = db.query(Profile).filter(Profile.user_id == booking.customer_id).first()
                if customer_profile:
                    customer_name = customer_profile.name
            
            result.append({
                "id": str(booking.id),
                "property_id": str(booking.property_id) if booking.property_id else None,
                "room_id": str(booking.room_id) if booking.room_id else None,
                "customer_id": str(booking.customer_id) if booking.customer_id else None,
                "owner_id": str(booking.owner_id) if booking.owner_id else None,
                "status": booking.status.value if hasattr(booking.status, 'value') else str(booking.status),
                "start_date": booking.start_date.isoformat() if booking.start_date else None,
                "end_date": booking.end_date.isoformat() if booking.end_date else None,
                "amount": booking.amount or 0,
                "security_deposit": booking.security_deposit or 0,
                "created_at": booking.created_at.isoformat() if booking.created_at else None,
                "property": {
                    "title": property_obj.title if property_obj else None,
                    "city": property_obj.city if property_obj else None,
                    "locality": property_obj.locality if property_obj else None,
                } if property_obj else None,
                "customer_name": customer_name,
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{booking_id}", response_model=BookingDetailResponse)
async def get_booking(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get booking details."""
    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        (Booking.customer_id == current_user.id) | (Booking.owner_id == current_user.id)
    ).first()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found"
        )
    
    # Get property details
    property = db.query(Property).filter(Property.id == booking.property_id).first()
    
    # Get room details
    room = None
    if booking.room_id:
        room = db.query(Room).filter(Room.id == booking.room_id).first()
    
    response = BookingDetailResponse.model_validate(booking)
    response.property = {
        "id": str(property.id),
        "title": property.title,
        "city": property.city,
        "locality": property.locality,
        "photos": property.photos,
    } if property else None
    response.room = {
        "id": str(room.id),
        "room_type": room.room_type,
        "bed_count": room.bed_count,
    } if room else None
    
    return response


@router.post("", response_model=BookingResponse)
async def create_booking(
    booking_data: BookingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new booking request."""
    # Get property
    property = db.query(Property).filter(Property.id == booking_data.property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    if property.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Property is not available for booking"
        )
    
    # Can't book own property
    if property.owner_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot book your own property"
        )
    
    # Check for existing active/pending booking for this property by this customer
    existing_booking = db.query(Booking).filter(
        Booking.property_id == booking_data.property_id,
        Booking.customer_id == current_user.id,
        Booking.status.in_(['requested', 'accepted', 'paid', 'active', 'checked-in'])
    ).first()
    
    if existing_booking:
        status_text = existing_booking.status
        if status_text == 'requested':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You already have a pending booking request for this property"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You already have an active booking for this property (status: {status_text})"
            )
    
    # Check room if provided
    room = None
    if booking_data.room_id:
        room = db.query(Room).filter(
            Room.id == booking_data.room_id,
            Room.property_id == property.id
        ).first()
        if not room:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Room not found"
            )
        if not room.is_available:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Room is not available"
            )
    
    # Create booking
    new_booking = Booking(
        property_id=property.id,
        room_id=booking_data.room_id,
        customer_id=current_user.id,
        owner_id=property.owner_id,
        start_date=booking_data.start_date,
        end_date=booking_data.end_date,
        amount=property.monthly_rent,
        security_deposit=property.deposit,
        status="requested",
    )
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)
    
    # Notify owner about new booking request
    try:
        customer_profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
        customer_name = customer_profile.name if customer_profile else current_user.email
        notify_booking_created(db, property.owner_id, customer_name, property.title, new_booking.id)
    except Exception:
        pass  # Don't fail booking if notification fails
    
    return new_booking


@router.put("/{booking_id}/status", response_model=BookingResponse)
async def update_booking_status(
    booking_id: UUID,
    status_data: BookingStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update booking status (owner only for accept/reject)."""
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found"
        )
    
    # Check permissions
    is_owner = booking.owner_id == current_user.id
    is_customer = booking.customer_id == current_user.id
    
    if not is_owner and not is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this booking"
        )
    
    # Status transition rules
    new_status = status_data.status.value
    
    # Owners can accept/reject requested bookings
    if is_owner and booking.status == "requested":
        if new_status not in ["accepted", "cancelled"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status transition"
            )
    
    booking.status = new_status
    db.commit()
    db.refresh(booking)
    
    # Send notification to customer based on status change
    try:
        property = db.query(Property).filter(Property.id == booking.property_id).first()
        property_title = property.title if property else "Property"
        
        if new_status == "accepted":
            notify_booking_accepted(db, booking.customer_id, property_title, booking.id)
        elif new_status in ["cancelled", "rejected"]:
            notify_booking_rejected(db, booking.customer_id, property_title)
    except Exception:
        pass  # Don't fail status update if notification fails
    
    return booking


@router.put("/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(
    booking_id: UUID,
    cancel_data: BookingCancelRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel a booking."""
    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        (Booking.customer_id == current_user.id) | (Booking.owner_id == current_user.id)
    ).first()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found"
        )
    
    if booking.status in ["cancelled", "completed"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Booking cannot be cancelled"
        )
    
    booking.status = "cancelled"
    booking.cancelled_at = datetime.utcnow()
    booking.cancel_reason = cancel_data.cancel_reason
    
    db.commit()
    db.refresh(booking)
    return booking
