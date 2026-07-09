"""Properties router."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta

from app.database import get_db
from app.models import User, Property, Room, Review, Profile, SystemSettings
from app.schemas import (
    PropertyCreate,
    PropertyUpdate,
    PropertyResponse,
    PropertyListResponse,
    PropertyDetailResponse,
    RoomCreate,
    RoomUpdate,
    RoomResponse,
    PropertyFilter,
    GenderPreferenceEnum,
    PropertyDeletionResponse,
)
from app.utils.security import get_current_user, require_owner
from app.services.vacancy import get_room_availability, get_property_availability

router = APIRouter(prefix="/properties", tags=["Properties"])


def sync_property_rent_and_deposit(db: Session, property_id: UUID):
    """Sync property monthly_rent and deposit columns with its cheapest room."""
    rooms = db.query(Room).filter(Room.property_id == property_id).all()
    if rooms:
        # Prioritize monthly rooms if available
        monthly_rooms = [r for r in rooms if not r.stay_type or r.stay_type == "monthly"]
        lead_rooms = monthly_rooms if monthly_rooms else rooms
        lead_room = min(lead_rooms, key=lambda r: r.price if r.price is not None else float('inf'))
        prop = db.query(Property).filter(Property.id == property_id).first()
        if prop and lead_room.price is not None:
            prop.monthly_rent = lead_room.price
            prop.deposit = lead_room.deposit
            db.commit()


@router.get("", response_model=List[PropertyListResponse])
async def list_properties(
    db: Session = Depends(get_db),
    city: Optional[str] = None,
    locality: Optional[str] = None,
    gender_preference: Optional[str] = None,
    min_rent: Optional[int] = None,
    max_rent: Optional[int] = None,
    amenities: Optional[str] = None,  # Comma-separated
    sort_by: Optional[str] = "newest",
    skip: int = 0,
    limit: int = 50,
):
    """List properties with optional filters."""
    from sqlalchemy.orm import joinedload
    query = db.query(Property).options(joinedload(Property.rooms)).filter(
        Property.status == "active",
        Property.inactive_at.is_(None)
    )
    
    if city:
        query = query.filter(Property.city.ilike(f"%{city}%"))
    if locality:
        query = query.filter(Property.locality.ilike(f"%{locality}%"))
    if gender_preference:
        query = query.filter(Property.gender_preference == gender_preference)
    if min_rent:
        query = query.filter(Property.monthly_rent >= min_rent)
    if max_rent:
        query = query.filter(Property.monthly_rent <= max_rent)
    if amenities:
        amenity_list = [a.strip() for a in amenities.split(",")]
        for amenity in amenity_list:
            query = query.filter(Property.amenities.contains([amenity]))
    
    # Sorting
    if sort_by == "price_low":
        query = query.order_by(Property.monthly_rent.asc())
    elif sort_by == "price_high":
        query = query.order_by(Property.monthly_rent.desc())
    else:  # newest
        query = query.order_by(Property.created_at.desc())
    
    properties = query.offset(skip).limit(limit).all()
    return properties


@router.get("/search", response_model=List[PropertyListResponse])
async def search_properties(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    limit: int = 10
):
    """Global search for properties (customer-facing)."""
    from sqlalchemy.orm import joinedload
    import re
    
    # Check if user query implies a specific bed configuration
    t = q.lower().strip()
    beds = None
    if "single" in t or t == "1" or "1 sharing" in t or "1-sharing" in t:
        beds = 1
    elif "double" in t or t == "2" or "2 sharing" in t or "2-sharing" in t:
        beds = 2
    elif "triple" in t or t == "3" or "3 sharing" in t or "3-sharing" in t:
        beds = 3
    elif "four" in t or t == "4" or "4 sharing" in t or "4-sharing" in t:
        beds = 4
    else:
        match = re.search(r"(\d+)\s*sharing", t)
        if match:
            beds = int(match.group(1))

    # Construct room filters
    room_filter = Room.room_type.ilike(f"%{q}%")
    if beds is not None:
        room_filter = room_filter | (Room.bed_count == beds)

    query = db.query(Property).options(joinedload(Property.rooms)).filter(
        Property.status == "active",
        Property.inactive_at.is_(None),
        (Property.title.ilike(f"%{q}%") | 
         Property.city.ilike(f"%{q}%") | 
         Property.locality.ilike(f"%{q}%") |
         Property.rooms.any(room_filter))
    )
    return query.limit(limit).all()


@router.get("/{property_id}", response_model=PropertyDetailResponse)
async def get_property(
    property_id: UUID,
    db: Session = Depends(get_db)
):
    """Get property details by ID."""
    property = db.query(Property).filter(
        Property.id == property_id,
        Property.inactive_at.is_(None)
    ).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    # Get rooms
    rooms = db.query(Room).filter(Room.property_id == property_id).all()
    
    # Get owner profile
    owner_profile = db.query(Profile).filter(Profile.user_id == property.owner_id).first()
    
    # Get reviews stats
    review_stats = db.query(
        func.avg(Review.rating).label("avg_rating"),
        func.count(Review.id).label("count")
    ).filter(Review.property_id == property_id).first()
    
    response = PropertyDetailResponse.model_validate(property)
    response.rooms = [RoomResponse.model_validate(r) for r in rooms]
    
    # Calculate response rate
    from app.routers.host import calculate_host_response_rate
    host_id = property.owner_id
    response_rate = calculate_host_response_rate(db, host_id)

    # Mask bank account number
    masked_account = "********" + owner_profile.bank_account_number[-4:] if owner_profile and owner_profile.bank_account_number and len(owner_profile.bank_account_number) > 4 else owner_profile.bank_account_number if owner_profile else None

    response.owner_profile = {
        "name": owner_profile.name if owner_profile else "Owner",
        "phone": owner_profile.phone if owner_profile else None,
        "profile_photo": owner_profile.profile_photo if owner_profile else None,
        "languages_known": owner_profile.languages_known if owner_profile else None,
        "bank_name": owner_profile.bank_name if owner_profile else None,
        "bank_account_masked": masked_account,
        "bank_ifsc_code": owner_profile.bank_ifsc_code if owner_profile else None,
        "response_rate": response_rate,
    }
    response.average_rating = float(review_stats.avg_rating) if review_stats.avg_rating else None
    response.review_count = review_stats.count or 0
    
    return response


@router.post("", response_model=PropertyResponse, dependencies=[Depends(require_owner)])
async def create_property(
    property_data: PropertyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new property (owner only)."""
    # Check max properties limit
    limit_setting = db.query(SystemSettings).filter(SystemSettings.key == "max_properties_per_owner").first()
    max_limit = 10  # Default fallback
    if limit_setting and limit_setting.value:
        try:
            max_limit = int(limit_setting.value)
        except ValueError:
            pass

    existing_count = db.query(Property).filter(
        Property.owner_id == current_user.id,
        Property.inactive_at.is_(None)
    ).count()
    if existing_count >= max_limit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Property limit reached. You can only list up to {max_limit} properties."
        )

    # Extract rooms if provided
    rooms_data = property_data.rooms
    property_dict = property_data.model_dump(exclude={"rooms"})
    
    new_property = Property(
        owner_id=current_user.id,
        **property_dict
    )
    db.add(new_property)
    db.flush()  # To get the property ID
    
    # Create rooms if provided
    if rooms_data:
        for room_data in rooms_data:
            new_room = Room(
                property_id=new_property.id,
                **room_data.model_dump()
            )
            db.add(new_room)
    
    db.commit()
    db.refresh(new_property)
    sync_property_rent_and_deposit(db, new_property.id)
    return new_property


@router.put("/{property_id}", response_model=PropertyResponse, dependencies=[Depends(require_owner)])
async def update_property(
    property_id: UUID,
    property_data: PropertyUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a property (owner only)."""
    property = db.query(Property).filter(
        Property.id == property_id,
        Property.owner_id == current_user.id,
        Property.inactive_at.is_(None)
    ).first()
    
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found or you don't have permission to edit it"
        )
    
    # Extract rooms if provided
    rooms_data = property_data.rooms
    update_data = property_data.model_dump(exclude_unset=True, exclude={"rooms"})
    
    for field, value in update_data.items():
        setattr(property, field, value)
    
    # Nested room updates are no longer handled here to prevent accidental data deletion.
    # Rooms should be managed through their dedicated endpoints (/properties/{property_id}/rooms).
    
    db.commit()
    db.refresh(property)
    return property


@router.delete("/{property_id}", response_model=PropertyDeletionResponse, dependencies=[Depends(require_owner)])
async def delete_property(
    property_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a property (owner only)."""
    from app.services.property_service import PropertyService
    return await PropertyService.delete_property(
        db=db,
        property_id=property_id,
        current_user_id=current_user.id,
        is_admin=False
    )


# Room endpoints
@router.get("/{property_id}/rooms", response_model=List[RoomResponse])
async def get_property_rooms(
    property_id: UUID,
    db: Session = Depends(get_db)
):
    """Get rooms for a property."""
    rooms = db.query(Room).filter(Room.property_id == property_id).all()
    return rooms


@router.get("/{property_id}/availability")
async def property_availability(
    property_id: UUID,
    background_tasks: BackgroundTasks,
    start_date: date = Query(..., description="Start date for availability check"),
    end_date: date = Query(..., description="End date for availability check"),
    db: Session = Depends(get_db)
):
    """Get bed availability for all rooms in a property over a date range."""
    # On-demand cleanup of expired bookings
    from app.scheduler import cleanup_expired_bookings
    cleanup_expired_bookings(db=db, property_id=property_id, background_tasks=background_tasks)

    property_obj = db.query(Property).filter(Property.id == property_id).first()
    if not property_obj:
        raise HTTPException(status_code=404, detail="Property not found")
    
    return get_property_availability(db, property_id, start_date, end_date)


@router.get("/{property_id}/rooms/{room_id}/availability")
async def room_availability(
    property_id: UUID,
    room_id: UUID,
    background_tasks: BackgroundTasks,
    start_date: date = Query(..., description="Start date for availability check"),
    end_date: date = Query(..., description="End date for availability check"),
    db: Session = Depends(get_db)
):
    """Get bed availability for a specific room over a date range."""
    # On-demand cleanup of expired bookings
    from app.scheduler import cleanup_expired_bookings
    cleanup_expired_bookings(db=db, property_id=property_id, background_tasks=background_tasks)

    room = db.query(Room).filter(
        Room.id == room_id,
        Room.property_id == property_id
    ).first()
    
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    availability = get_room_availability(db, room_id, start_date, end_date)
    availability["price"] = room.price
    availability["stay_type"] = room.stay_type or "monthly"
    
    return availability


@router.post("/{property_id}/rooms", response_model=RoomResponse, dependencies=[Depends(require_owner)])
async def create_room(
    property_id: UUID,
    room_data: RoomCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a room to a property (owner only)."""
    property = db.query(Property).filter(
        Property.id == property_id,
        Property.owner_id == current_user.id,
        Property.inactive_at.is_(None)
    ).first()
    
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found or you don't have permission"
        )
    
    new_room = Room(
        property_id=property_id,
        **room_data.model_dump()
    )
    db.add(new_room)
    db.commit()
    db.refresh(new_room)
    sync_property_rent_and_deposit(db, property_id)
    return new_room


@router.post("/{property_id}/rooms/bulk", response_model=List[RoomResponse], dependencies=[Depends(require_owner)])
async def create_rooms_bulk(
    property_id: UUID,
    rooms_data: List[RoomCreate],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add multiple rooms to a property in a single transaction (owner only)."""
    property = db.query(Property).filter(
        Property.id == property_id,
        Property.owner_id == current_user.id,
        Property.inactive_at.is_(None)
    ).first()
    
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found or you don't have permission"
        )
    
    new_rooms = []
    for room_data in rooms_data:
        new_room = Room(
            property_id=property_id,
            **room_data.model_dump()
        )
        db.add(new_room)
        new_rooms.append(new_room)
        
    db.commit()
    for new_room in new_rooms:
        db.refresh(new_room)
        
    sync_property_rent_and_deposit(db, property_id)
    return new_rooms


@router.put("/{property_id}/rooms/{room_id}", response_model=RoomResponse, dependencies=[Depends(require_owner)])
async def update_room(
    property_id: UUID,
    room_id: UUID,
    room_data: RoomUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a room (owner only)."""
    # Verify ownership
    property = db.query(Property).filter(
        Property.id == property_id,
        Property.owner_id == current_user.id,
        Property.inactive_at.is_(None)
    ).first()
    
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found or you don't have permission"
        )
    
    room = db.query(Room).filter(
        Room.id == room_id,
        Room.property_id == property_id
    ).first()
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )
    
    update_data = room_data.model_dump(exclude_unset=True)
    # Never allow room edits to overwrite vacancy_count or is_available —
    # these are managed exclusively by the booking system (add/remove tenant).
    update_data.pop("vacancy_count", None)
    update_data.pop("is_available", None)

    # Track which financial fields changed so we can sync active bookings
    price_changed = "price" in update_data and update_data["price"] != room.price
    deposit_changed = "security_deposit" in update_data and update_data["security_deposit"] != room.security_deposit
    maintenance_changed = "maintenance_charge" in update_data and update_data["maintenance_charge"] != room.maintenance_charge

    for field, value in update_data.items():
        setattr(room, field, value)

    # Sync active bookings in this room when financial fields change,
    # so rent management and payment collection use the updated values.
    if price_changed or deposit_changed or maintenance_changed:
        from app.models.booking import Booking, BookingStatus
        from app.services.booking_service import BookingService
        active_bookings = db.query(Booking).filter(
            Booking.room_id == room_id,
            Booking.status.in_([
                BookingStatus.active,
                BookingStatus.paid,
                BookingStatus.checked_in,
                BookingStatus.vacate_requested,
            ])
        ).all()
        for bk in active_bookings:
            if price_changed:
                # Update rent history in customer_snapshot for mid-month changes
                from datetime import date
                import calendar
                today = date.today()
                
                # Helper to calculate start day of a cycle
                def get_date_for_month(base_date: date, month_offset: int) -> date:
                    m = (base_date.month + month_offset - 1) % 12 + 1
                    y = base_date.year + (base_date.month + month_offset - 1) // 12
                    last_day_of_m = calendar.monthrange(y, m)[1]
                    return date(y, m, min(base_date.day, last_day_of_m))

                # Find the earliest cycle start date >= today
                effective_date = bk.start_date
                if today > bk.start_date:
                    i = 0
                    while True:
                        period_start = get_date_for_month(bk.start_date, i)
                        if period_start >= today:
                            effective_date = period_start
                            break
                        i += 1
                
                import copy
                from sqlalchemy.orm.attributes import flag_modified

                snapshot = copy.deepcopy(bk.customer_snapshot or {})
                if not isinstance(snapshot, dict):
                    snapshot = {}
                
                rent_history = snapshot.get("rent_history")
                if not rent_history or not isinstance(rent_history, list):
                    # Fallback initialize with the old bk.amount
                    rent_history = [{"amount": float(bk.amount), "start_date": bk.start_date.isoformat()}]
                
                # Update or append
                replaced = False
                for entry in rent_history:
                    if entry.get("start_date") == effective_date.isoformat():
                        entry["amount"] = float(room.price)
                        replaced = True
                        break
                
                if not replaced:
                    rent_history.append({
                        "amount": float(room.price),
                        "start_date": effective_date.isoformat()
                    })
                
                rent_history.sort(key=lambda x: x.get("start_date", ""))
                snapshot["rent_history"] = rent_history
                bk.customer_snapshot = snapshot
                flag_modified(bk, "customer_snapshot")
                bk.amount = room.price

            if deposit_changed and not bk.deposit_paid:
                bk.security_deposit = room.security_deposit or 0
            if maintenance_changed and not bk.maintenance_paid:
                bk.maintenance_charge = room.maintenance_charge or 0
            
            # Flush changes to booking so handle_payment_completion sees the updated amount/deposit/charge
            db.flush()
            
            # Recalculate rent_paid, deposit_paid, maintenance_paid flags and booking status
            BookingService.handle_payment_completion(db, bk.id, commit=False)

    db.commit()
    db.refresh(room)
    sync_property_rent_and_deposit(db, property_id)
    return room


@router.delete("/{property_id}/rooms/{room_id}", dependencies=[Depends(require_owner)])
async def delete_room(
    property_id: UUID,
    room_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a room (owner only)."""
    # Verify ownership
    property = db.query(Property).filter(
        Property.id == property_id,
        Property.owner_id == current_user.id,
        Property.inactive_at.is_(None)
    ).first()
    
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found or you don't have permission"
        )
    
    room = db.query(Room).filter(
        Room.id == room_id,
        Room.property_id == property_id
    ).first()
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )
    
    db.delete(room)
    db.commit()
    sync_property_rent_and_deposit(db, property_id)
    return {"message": "Room deleted successfully"}
