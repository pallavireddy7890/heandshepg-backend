"""Properties router."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
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
    query = db.query(Property).options(joinedload(Property.rooms)).filter(Property.status == "active")
    
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
    query = db.query(Property).options(joinedload(Property.rooms)).filter(
        (Property.status == "active"),
        (Property.title.ilike(f"%{q}%") | 
         Property.city.ilike(f"%{q}%") | 
         Property.locality.ilike(f"%{q}%"))
    )
    return query.limit(limit).all()


@router.get("/{property_id}", response_model=PropertyDetailResponse)
async def get_property(
    property_id: UUID,
    db: Session = Depends(get_db)
):
    """Get property details by ID."""
    property = db.query(Property).filter(Property.id == property_id).first()
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

    existing_count = db.query(Property).filter(Property.owner_id == current_user.id).count()
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
        Property.owner_id == current_user.id
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
    start_date: date = Query(..., description="Start date for availability check"),
    end_date: date = Query(..., description="End date for availability check"),
    db: Session = Depends(get_db)
):
    """Get bed availability for all rooms in a property over a date range."""
    property_obj = db.query(Property).filter(Property.id == property_id).first()
    if not property_obj:
        raise HTTPException(status_code=404, detail="Property not found")
    
    return get_property_availability(db, property_id, start_date, end_date)


@router.get("/{property_id}/rooms/{room_id}/availability")
async def room_availability(
    property_id: UUID,
    room_id: UUID,
    start_date: date = Query(..., description="Start date for availability check"),
    end_date: date = Query(..., description="End date for availability check"),
    db: Session = Depends(get_db)
):
    """Get bed availability for a specific room over a date range."""
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
        Property.owner_id == current_user.id
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
    return new_room


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
        Property.owner_id == current_user.id
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
    for field, value in update_data.items():
        setattr(room, field, value)
    
    db.commit()
    db.refresh(room)
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
        Property.owner_id == current_user.id
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
    return {"message": "Room deleted successfully"}
