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

require_admin = require_role("admin")

router = APIRouter(prefix="/bookings", tags=["Bookings"])


@router.get("/all", response_model=List[BookingResponse], dependencies=[Depends(require_admin)])
async def list_all_bookings(
    db: Session = Depends(get_db),
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=100),
):
    """List all bookings on the platform (admin only)."""
    query = db.query(Booking)
    
    if status_filter:
        query = query.filter(Booking.status == status_filter)
    
    bookings = query.order_by(Booking.created_at.desc()).offset(skip).limit(limit).all()
    return bookings


@router.get("", response_model=List[BookingResponse])
async def list_bookings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status_filter: str = None,
):
    """List current user's bookings (as customer or owner)."""
    query = db.query(Booking).filter(
        (Booking.customer_id == current_user.id) | (Booking.owner_id == current_user.id)
    )
    
    if status_filter:
        query = query.filter(Booking.status == status_filter)
    
    bookings = query.order_by(Booking.created_at.desc()).all()
    return bookings


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
