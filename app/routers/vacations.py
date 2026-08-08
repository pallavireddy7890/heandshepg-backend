"""Vacations router."""
from typing import List, Optional
from uuid import UUID
from datetime import date, datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Property, Booking, Room, Vacation, VacationStatus, Profile
from app.schemas.vacation import VacationCreate, VacationUpdate, VacationResponse, VacationOwnerView
from app.utils.security import get_current_user
from app.utils.notifications import create_notification

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vacations", tags=["Vacations"])

@router.post("/", response_model=VacationResponse)
async def create_vacation(
    vacation_data: VacationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a vacation (Tenant only)."""
    # Verify the tenant has an active booking for this property
    booking = db.query(Booking).filter(
        Booking.customer_id == current_user.id,
        Booking.property_id == vacation_data.property_id,
        Booking.status.in_(["active", "checked_in", "paid"])
    ).first()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active booking found for this property"
        )
    
    # Calculate total days
    if vacation_data.end_date < vacation_data.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End date cannot be before start date"
        )
    
    total_days = (vacation_data.end_date - vacation_data.start_date).days + 1
    
    # Check for overlapping vacations
    overlap = db.query(Vacation).filter(
        Vacation.tenant_id == current_user.id,
        Vacation.status != VacationStatus.cancelled,
        (
            ((Vacation.start_date <= vacation_data.start_date) & (Vacation.end_date >= vacation_data.start_date)) |
            ((Vacation.start_date <= vacation_data.end_date) & (Vacation.end_date >= vacation_data.end_date)) |
            ((Vacation.start_date >= vacation_data.start_date) & (Vacation.end_date <= vacation_data.end_date))
        )
    ).first()
    
    if overlap:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have a vacation planned during this period"
        )

    new_vacation = Vacation(
        tenant_id=current_user.id,
        property_id=vacation_data.property_id,
        start_date=vacation_data.start_date,
        end_date=vacation_data.end_date,
        total_days=total_days,
        reason=vacation_data.reason,
        status=VacationStatus.upcoming if vacation_data.start_date > date.today() else VacationStatus.active
    )
    db.add(new_vacation)
    db.commit()
    db.refresh(new_vacation)
    
   # Notify owner via WebSocket (no emails as requested)
    try:
        property_obj = db.query(Property).filter(
            Property.id == new_vacation.property_id
        ).first()

        tenant_profile = db.query(Profile).filter(
            Profile.user_id == current_user.id
        ).first()

        tenant_name = tenant_profile.name if tenant_profile else "A tenant"

        room = None
        if booking.room_id:
            room = db.query(Room).filter(Room.id == booking.room_id).first()

        room_info = (
            f" from Room {room.room_number}, Floor {room.floor_number}"
            if room
            else ""
        )

        if property_obj:
            await create_notification(
                db=db,
                user_id=property_obj.owner_id,
                property_id=property_obj.id,
                title="🧳 New Vacation Planned",
                message=(
                    f"{tenant_name} is going on vacation{room_info} "
                    f"at {property_obj.title} from "
                    f"{new_vacation.start_date} to {new_vacation.end_date} "
                    f"({new_vacation.total_days} days)."
                ),
                notification_type="vacation",
                link="/owner/dashboard?tab=vacations",
                send_external=False
            )

    except Exception as e:
        logger.warning(f"Failed to send vacation notification: {e}")

    return new_vacation
@router.get("/my", response_model=List[VacationResponse])
async def get_my_vacations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get tenant's vacations."""
    return db.query(Vacation).filter(Vacation.tenant_id == current_user.id).order_by(Vacation.start_date.desc()).all()

@router.get("/owner", response_model=List[VacationOwnerView])
async def get_owner_vacations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get vacations for properties owned by the current user."""
    vacations = db.query(Vacation).join(Property, Vacation.property_id == Property.id).filter(Property.owner_id == current_user.id).order_by(Vacation.start_date.desc()).all()
    
    results = []
    for v in vacations:
        tenant_profile = db.query(Profile).filter(Profile.user_id == v.tenant_id).first()
        property_obj = db.query(Property).filter(Property.id == v.property_id).first()
        # Look for any booking with a room for this tenant and property, prioritizing the latest
        booking = db.query(Booking).filter(
            Booking.customer_id == v.tenant_id, 
            Booking.property_id == v.property_id,
            Booking.room_id.isnot(None)
        ).order_by(Booking.created_at.desc()).first()
        
        # If no booking with a room ID is found, fallback to the latest booking regardless of room ID
        if not booking:
            booking = db.query(Booking).filter(
                Booking.customer_id == v.tenant_id, 
                Booking.property_id == v.property_id
            ).order_by(Booking.created_at.desc()).first()
            
        room = db.query(Room).filter(Room.id == booking.room_id).first() if booking and booking.room_id else None
        
        results.append(VacationOwnerView(
            id=v.id,
            tenant_id=v.tenant_id,
            property_id=v.property_id,
            start_date=v.start_date,
            end_date=v.end_date,
            total_days=v.total_days,
            reason=v.reason,
            status=v.status,
            created_at=v.created_at,
            updated_at=v.updated_at,
            tenant_name=tenant_profile.name if tenant_profile else "Unknown",
            property_title=property_obj.title if property_obj else "Unknown",
            room_number=room.room_number if room else "N/A",
            floor_number=room.floor_number if room else None
        ))
    return results

@router.put("/{vacation_id}", response_model=VacationResponse)
async def update_vacation(
    vacation_id: UUID,
    vacation_data: VacationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a vacation."""
    vacation = db.query(Vacation).filter(Vacation.id == vacation_id).first()
    if not vacation:
        raise HTTPException(status_code=404, detail="Vacation not found")
    
    if vacation.tenant_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this vacation")
    
    if vacation_data.start_date:
        vacation.start_date = vacation_data.start_date
    if vacation_data.end_date:
        vacation.end_date = vacation_data.end_date
    if vacation_data.reason is not None:
        vacation.reason = vacation_data.reason
    if vacation_data.status:
        vacation.status = vacation_data.status
        
    # Recalculate total_days
    vacation.total_days = (vacation.end_date - vacation.start_date).days + 1
    
    db.commit()
    db.refresh(vacation)
    
    # Notify owner about update
    try:
        property_obj = db.query(Property).filter(Property.id == vacation.property_id).first()
        tenant_profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
        tenant_name = tenant_profile.name if tenant_profile else "A tenant"
        
        if property_obj:
            await create_notification(
                db=db,
                user_id=property_obj.owner_id,
                property_id=property_obj.id,
                title="🧳 Vacation Updated",
                message=f"{tenant_name} has updated their vacation dates: {vacation.start_date} to {vacation.end_date}.",
                notification_type="info",
                link="/owner/dashboard?tab=vacations",
                send_external=False
            )
    except Exception as e:
        logger.warning(f"Failed to send vacation update notification: {e}")

    return vacation

@router.delete("/{vacation_id}")
async def cancel_vacation(
    vacation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel a vacation."""
    vacation = db.query(Vacation).filter(Vacation.id == vacation_id).first()
    if not vacation:
        raise HTTPException(status_code=404, detail="Vacation not found")
    
    if vacation.tenant_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this vacation")
    
    vacation.status = VacationStatus.cancelled
    db.commit()
    
    # Notify owner
    try:
        property_obj = db.query(Property).filter(Property.id == vacation.property_id).first()
        tenant_profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
        tenant_name = tenant_profile.name if tenant_profile else "A tenant"
        
        if property_obj:
            await create_notification(
                db=db,
                user_id=property_obj.owner_id,
                property_id=property_obj.id,
                title="🧳 Vacation Cancelled",
                message=f"{tenant_name} has cancelled their vacation.",
                notification_type="warning",
                link="/owner/dashboard?tab=vacations",
                send_external=False
            )
    except Exception as e:
        logger.warning(f"Failed to send vacation cancellation notification: {e}")

    return {"message": "Vacation cancelled successfully"}
