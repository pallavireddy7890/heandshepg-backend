"""Vacancy calculation service for bed-based availability."""
from datetime import date, timedelta
from typing import Optional, List, Dict
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models import Booking, Room


# Active booking statuses that occupy beds
ACTIVE_BOOKING_STATUSES = ['requested', 'accepted', 'paid', 'checked_in', 'active']


def get_overlapping_bookings_count(
    db: Session,
    room_id: UUID,
    start_date: date,
    end_date: date,
    exclude_booking_id: Optional[UUID] = None
) -> int:
    """
    Count active bookings that overlap with the given date range.
    
    Overlap condition: booking.start_date < end_date AND 
                       (booking.end_date > start_date OR booking.end_date IS NULL)
    
    Args:
        db: Database session
        room_id: Room to check
        start_date: Start of date range
        end_date: End of date range
        exclude_booking_id: Optionally exclude a booking (for extension checks)
    
    Returns:
        Number of overlapping active bookings
    """
    query = db.query(Booking).filter(
        Booking.room_id == room_id,
        Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        Booking.start_date < end_date,
        or_(
            Booking.end_date > start_date,
            Booking.end_date.is_(None)  # Open-ended monthly bookings
        )
    )
    
    if exclude_booking_id:
        query = query.filter(Booking.id != exclude_booking_id)
    
    return query.count()


def get_bed_vacancy(
    db: Session,
    room_id: UUID,
    start_date: date,
    end_date: date,
    exclude_booking_id: Optional[UUID] = None
) -> int:
    """
    Calculate available beds for a room in a date range.
    
    Formula: available_beds = bed_count - overlapping_bookings_count
    
    Args:
        db: Database session
        room_id: Room to check
        start_date: Start of date range
        end_date: End of date range
        exclude_booking_id: Optionally exclude a booking
    
    Returns:
        Number of available beds (minimum 0)
    """
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        return 0
    
    total_beds = room.bed_count or 0
    booked_beds = get_overlapping_bookings_count(
        db, room_id, start_date, end_date, exclude_booking_id
    )
    
    return max(0, total_beds - booked_beds)


def is_bed_available_for_extension(
    db: Session,
    booking_id: UUID,
    extra_days: int
) -> tuple[bool, int]:
    """
    Check if a bed is available for extending a booking.
    
    Args:
        db: Database session
        booking_id: Current booking to extend
        extra_days: Number of days to extend
    
    Returns:
        Tuple of (is_available, available_beds)
    """
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking or not booking.room_id:
        return False, 0
    
    if not booking.end_date:
        # Open-ended booking, extension is handled differently
        return True, 1
    
    # Check vacancy for the extension period
    extension_start = booking.end_date
    extension_end = booking.end_date + timedelta(days=extra_days)
    
    available = get_bed_vacancy(
        db,
        booking.room_id,
        extension_start,
        extension_end,
        exclude_booking_id=booking_id
    )
    
    return available > 0, available


def get_room_availability(
    db: Session,
    room_id: UUID,
    start_date: date,
    end_date: date
) -> Dict:
    """
    Get detailed availability info for a room.
    
    Returns:
        Dict with total_beds, booked_beds, available_beds, is_available
    """
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        return {
            "room_id": str(room_id),
            "room_type": "Unknown",
            "total_beds": 0,
            "booked_beds": 0,
            "available_beds": 0,
            "is_available": False
        }
    
    total_beds = room.bed_count or 0
    booked_beds = get_overlapping_bookings_count(db, room_id, start_date, end_date)
    available_beds = max(0, total_beds - booked_beds)
    
    return {
        "room_id": str(room_id),
        "room_type": room.room_type,
        "total_beds": total_beds,
        "booked_beds": booked_beds,
        "available_beds": available_beds,
        "is_available": available_beds > 0
    }


def sync_room_vacancy(db: Session, room_id: UUID) -> int:
    """
    Recalculate and update the stored vacancy_count for a room.
    Used for long-term consistency and to fix manual update errors.
    
    Occupied if status is: paid, checked_in, active, vacate_requested
    Note: requested/accepted are excluded from the stored count but included 
    in dynamic checks (get_bed_vacancy) to prevent overbooking.
    
    Args:
        db: Database session
        room_id: Room to sync
        
    Returns:
        New vacancy count
    """
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        return 0
        
    # Real occupied beds are those with these persistent statuses
    occupied_statuses = ['paid', 'checked_in', 'active', 'vacate_requested']
    
    occupied_count = db.query(Booking).filter(
        Booking.room_id == room_id,
        Booking.status.in_(occupied_statuses)
    ).count()
    
    total_beds = room.bed_count or 0
    new_vacancy = max(0, total_beds - occupied_count)
    
    # Update room state
    room.vacancy_count = new_vacancy
    room.is_available = new_vacancy > 0
    
    db.commit()
    return new_vacancy


def get_property_availability(
    db: Session,
    property_id: UUID,
    start_date: date,
    end_date: date
) -> List[Dict]:
    """
    Get availability info for all rooms in a property.
    
    Returns:
        List of dicts with room availability info
    """
    rooms = db.query(Room).filter(Room.property_id == property_id).all()
    
    availability_list = []
    for room in rooms:
        availability = get_room_availability(db, room.id, start_date, end_date)
        availability_list.append(availability)
        
    return availability_list
