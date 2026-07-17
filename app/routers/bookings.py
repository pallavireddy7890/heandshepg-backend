"""Bookings router."""
from typing import List, Optional
from uuid import UUID
from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Booking, Property, Room, Profile, RoomBed
from app.schemas import (
    BookingCreate,
    BookingStatusUpdate,
    BookingCancelRequest,
    BookingResponse,
    BookingDetailResponse,
    BookingExtend,
)
from app.utils.security import get_current_user, require_role
from app.utils.notifications import (
    notify_booking_created,
    notify_booking_accepted,
    notify_booking_rejected,
    notify_booking_cancelled,
)
from app.services.vacancy import get_bed_vacancy, is_bed_available_for_extension, sync_room_vacancy

require_admin = require_role("admin")

router = APIRouter(prefix="/bookings", tags=["Bookings"])


@router.get("/all", dependencies=[Depends(require_admin)])
async def list_all_bookings(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=100),
):
    """List all bookings on the platform (admin only)."""
    # On-demand cleanup of expired bookings
    from app.scheduler import cleanup_expired_bookings
    cleanup_expired_bookings(db=db, background_tasks=background_tasks)

    from sqlalchemy.orm import joinedload
    
    query = db.query(Booking).options(
        joinedload(Booking.property),
        joinedload(Booking.customer),
        joinedload(Booking.owner),
    )
    
    if status_filter:
        query = query.filter(Booking.status == status_filter)
    
    bookings = query.order_by(Booking.created_at.desc()).offset(skip).limit(limit).all()
    
    # Pre-aggregate transaction sums to avoid N+1 queries (Copilot review)
    from sqlalchemy import func
    from app.models.wallet import WalletTransaction, TransactionStatus, TransactionType
    
    booking_ids = [b.id for b in bookings]
    
    debit_sums = {}
    credit_sums = {}
    
    if booking_ids:
        debit_rows = db.query(
            WalletTransaction.booking_id,
            func.sum(WalletTransaction.amount)
        ).filter(
            WalletTransaction.booking_id.in_(booking_ids),
            WalletTransaction.transaction_type == TransactionType.debit,
            WalletTransaction.status == TransactionStatus.completed
        ).group_by(WalletTransaction.booking_id).all()
        debit_sums = {b_id: amount for b_id, amount in debit_rows if b_id}

        credit_rows = db.query(
            WalletTransaction.booking_id,
            func.sum(WalletTransaction.amount)
        ).filter(
            WalletTransaction.booking_id.in_(booking_ids),
            WalletTransaction.transaction_type == TransactionType.credit,
            WalletTransaction.status == TransactionStatus.completed
        ).group_by(WalletTransaction.booking_id).all()
        credit_sums = {b_id: amount for b_id, amount in credit_rows if b_id}
    
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
        
        # Debits on booking_id are referral/wallet usage
        referral_paid_paise = debit_sums.get(booking.id, 0) or 0
        referral_amount_used = int(referral_paid_paise / 100)

        # Credits on booking_id are the payments received from customer (online/offline)
        actual_paid_paise = credit_sums.get(booking.id, 0) or 0
        actual_paid = int(actual_paid_paise / 100)

        # Total amount is the sum of both transactions, or fallback to booking total if no transactions exist
        if (referral_amount_used + actual_paid) > 0:
            total_amt = referral_amount_used + actual_paid
        else:
            # Fallback to booking expected amount if no transactions recorded
            if booking.status in ["paid", "checked_in", "active", "completed", "vacate_requested", "vacated"]:
                total_amt = (booking.amount or 0) + (booking.security_deposit or 0) + (booking.maintenance_charge or 0)
            else:
                total_amt = 0
                if booking.rent_paid:
                    total_amt += booking.amount or 0
                if booking.deposit_paid:
                    total_amt += booking.security_deposit or 0
                if booking.maintenance_paid:
                    total_amt += booking.maintenance_charge or 0
                
                # If no flags are set, fallback to the total expected booking value (rent + deposit + maintenance)
                if not booking.rent_paid and not booking.deposit_paid and not booking.maintenance_paid:
                    total_amt = (booking.amount or 0) + (booking.security_deposit or 0) + (booking.maintenance_charge or 0)
            
            # For fallback, if status is paid-like, actual_paid equals total_amt
            if booking.status in ["paid", "checked_in", "active", "completed", "vacate_requested", "vacated"]:
                actual_paid = total_amt

        result.append({
            "id": str(booking.id),
            "property_id": str(booking.property_id),
            "property_title": property_title,
            "customer_name": customer_name,
            "owner_name": owner_name,
            "status": booking.status,
            "start_date": booking.start_date.isoformat() if booking.start_date else None,
            "end_date": booking.end_date.isoformat() if booking.end_date else None,
            "total_amount": total_amt,
            "amount": booking.amount or 0,
            "security_deposit": booking.security_deposit or 0,
            "maintenance_charge": booking.maintenance_charge or 0,
            "referral_amount_used": referral_amount_used,
            "actual_paid": actual_paid,
            "created_at": booking.created_at.isoformat() if booking.created_at else None,
        })
    
    return result


@router.get("")
async def list_bookings(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status_filter: str = None,
    property_id: Optional[UUID] = None,
):
    """List current user's bookings (as customer or owner)."""
    # On-demand cleanup of expired bookings
    from app.scheduler import cleanup_expired_bookings
    cleanup_expired_bookings(db=db, property_id=property_id, background_tasks=background_tasks)

    try:
        query = db.query(Booking).filter(
            (Booking.customer_id == current_user.id) | (Booking.owner_id == current_user.id)
        )
        
        if property_id:
            query = query.filter(Booking.property_id == property_id)
        
        if status_filter:
            query = query.filter(Booking.status == status_filter)
        
        bookings = query.order_by(Booking.created_at.desc()).all()
        
        result = []
        for booking in bookings:
            # Get property details
            property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
            
            # Get room details
            room_obj = None
            if booking.room_id:
                room_obj = db.query(Room).filter(Room.id == booking.room_id).first()
            
            # Get customer name and phone
            customer_name = None
            customer_phone = None
            if booking.customer_id:
                customer_profile = db.query(Profile).filter(Profile.user_id == booking.customer_id).first()
                if customer_profile:
                    customer_name = customer_profile.name
                    customer_phone = customer_profile.phone
            
            # Fallback to customer snapshot if profile not found/deleted
            if not customer_name and booking.customer_snapshot:
                customer_name = booking.customer_snapshot.get("name")
            if not customer_phone and booking.customer_snapshot:
                customer_phone = booking.customer_snapshot.get("phone")

            # Calculate security deposit and maintenance paid from transactions (lifetime)
            from app.models.wallet import WalletTransaction, TransactionStatus
            dep_txns = db.query(WalletTransaction).filter(
                WalletTransaction.booking_id == booking.id,
                WalletTransaction.status == TransactionStatus.completed,
                WalletTransaction.payment_type.in_(['deposit', 'total'])
            ).all()
            total_deposit_txns_amount = 0
            for p in dep_txns:
                if p.payment_type == 'deposit':
                    total_deposit_txns_amount += p.amount / 100
                elif p.payment_type == 'total':
                    total_deposit_txns_amount += (booking.security_deposit or 0)

            maint_txns = db.query(WalletTransaction).filter(
                WalletTransaction.booking_id == booking.id,
                WalletTransaction.status == TransactionStatus.completed,
                WalletTransaction.payment_type.in_(['maintenance', 'total'])
            ).all()
            total_maint_txns_amount = 0
            for p in maint_txns:
                if p.payment_type == 'maintenance':
                    total_maint_txns_amount += p.amount / 100
                elif p.payment_type == 'total':
                    total_maint_txns_amount += (booking.maintenance_charge or 0)

            # Allocate deposit to security deposit and maintenance charges
            security_cap = float(booking.security_deposit or 0)
            deposit_paid_amt = min(total_deposit_txns_amount, security_cap)
            leftover_deposit = max(0.0, total_deposit_txns_amount - security_cap)
            maintenance_paid_amt = total_maint_txns_amount + leftover_deposit

            # Calculate vacate details if vacate request is pending
            vacate_details = None
            if booking.status == "vacate_requested":
                from app.models import Invoice

                deposit_amount = booking.security_deposit or 0
                maintenance_total = booking.maintenance_charge or 0
                maintenance_unpaid = max(0, maintenance_total - maintenance_paid_amt)

                unpaid_invoices = db.query(Invoice).filter(
                    Invoice.booking_id == booking.id,
                    Invoice.status.in_(["pending", "overdue"])
                ).all()
                deductions = sum(inv.amount for inv in unpaid_invoices)

                final_refund = deposit_paid_amt - maintenance_unpaid - deductions

                vacate_details = {
                    "deposit_amount": deposit_amount,
                    "deposit_paid_amount": int(deposit_paid_amt),
                    "maintenance_charges": maintenance_total,
                    "maintenance_paid_amount": int(maintenance_paid_amt),
                    "unpaid_invoices": deductions,
                    "final_refund": int(final_refund)
                }
            
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
                "rent_paid": booking.rent_paid or False,
                "deposit_paid": booking.deposit_paid or False,
                "maintenance_paid": booking.maintenance_paid or False,
                "maintenance_charge": booking.maintenance_charge or 0,
                "security_paid": int(deposit_paid_amt),
                "maintenance_paid_amount": int(maintenance_paid_amt),
                "stay_type": booking.stay_type,
                "duration_days": booking.duration_days,
                "created_at": booking.created_at.isoformat() if booking.created_at else None,
                "updated_at": booking.updated_at.isoformat() if booking.updated_at else None,
                "cancelled_at": booking.cancelled_at.isoformat() if booking.cancelled_at else None,
                "property": {
                    "title": property_obj.title if property_obj else None,
                    "city": property_obj.city if property_obj else None,
                    "locality": property_obj.locality if property_obj else None,
                    "photos": property_obj.photos if property_obj else None,
                    "grace_period": property_obj.grace_period if property_obj else 0,
                    "payment_expiry_hours": property_obj.payment_expiry_hours if property_obj else 24,
                } if property_obj else None,
                "room": {
                    "room_type": room_obj.room_type,
                    "room_number": room_obj.room_number,
                    "floor_number": room_obj.floor_number,
                    "bed_count": room_obj.bed_count,
                    "room_description": room_obj.room_description,
                    "price": room_obj.price,
                } if room_obj else None,
                "customer_name": customer_name,
                "customer_phone": customer_phone,
                "vacate_details": vacate_details,
            })
        
        return result
    except Exception as e:
        import traceback
        print(f"ERROR in list_bookings: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{booking_id}", response_model=BookingDetailResponse)
async def get_booking(
    booking_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get booking details."""
    # On-demand cleanup of expired bookings
    from app.scheduler import cleanup_expired_bookings
    cleanup_expired_bookings(db=db, background_tasks=background_tasks)

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
    
    # Get customer name and phone
    customer_name = None
    customer_phone = None
    if booking.customer_id:
        customer_profile = db.query(Profile).filter(Profile.user_id == booking.customer_id).first()
        if customer_profile:
            customer_name = customer_profile.name
            customer_phone = customer_profile.phone
            
    if not customer_name and booking.customer_snapshot:
        customer_name = booking.customer_snapshot.get("name")
    if not customer_phone and booking.customer_snapshot:
        customer_phone = booking.customer_snapshot.get("phone")

    # Calculate security deposit and maintenance paid from transactions (lifetime)
    from app.models.wallet import WalletTransaction, TransactionStatus
    dep_txns = db.query(WalletTransaction).filter(
        WalletTransaction.booking_id == booking.id,
        WalletTransaction.status == TransactionStatus.completed,
        WalletTransaction.payment_type.in_(['deposit', 'total'])
    ).all()
    total_deposit_txns_amount = 0
    for p in dep_txns:
        if p.payment_type == 'deposit':
            total_deposit_txns_amount += p.amount / 100
        elif p.payment_type == 'total':
            total_deposit_txns_amount += (booking.security_deposit or 0)

    maint_txns = db.query(WalletTransaction).filter(
        WalletTransaction.booking_id == booking.id,
        WalletTransaction.status == TransactionStatus.completed,
        WalletTransaction.payment_type.in_(['maintenance', 'total'])
    ).all()
    total_maint_txns_amount = 0
    for p in maint_txns:
        if p.payment_type == 'maintenance':
            total_maint_txns_amount += p.amount / 100
        elif p.payment_type == 'total':
            total_maint_txns_amount += (booking.maintenance_charge or 0)

    # Allocate deposit to security deposit and maintenance charges
    security_cap = float(booking.security_deposit or 0)
    deposit_paid_amt = min(total_deposit_txns_amount, security_cap)
    leftover_deposit = max(0.0, total_deposit_txns_amount - security_cap)
    maintenance_paid_amt = total_maint_txns_amount + leftover_deposit

    # Calculate vacate details if vacate request is pending
    vacate_details = None
    if booking.status == "vacate_requested":
        from app.models import Invoice

        deposit_amount = booking.security_deposit or 0
        maintenance_total = booking.maintenance_charge or 0
        maintenance_unpaid = max(0, maintenance_total - maintenance_paid_amt)

        unpaid_invoices = db.query(Invoice).filter(
            Invoice.booking_id == booking.id,
            Invoice.status.in_(["pending", "overdue"])
        ).all()
        deductions = sum(inv.amount for inv in unpaid_invoices)

        final_refund = deposit_paid_amt - maintenance_unpaid - deductions

        vacate_details = {
            "deposit_amount": deposit_amount,
            "deposit_paid_amount": int(deposit_paid_amt),
            "maintenance_charges": maintenance_total,
            "maintenance_paid_amount": int(maintenance_paid_amt),
            "unpaid_invoices": deductions,
            "final_refund": int(final_refund)
        }

    response.customer_name = customer_name
    response.customer_phone = customer_phone
    response.vacate_details = vacate_details
    response.security_paid = int(deposit_paid_amt)
    response.maintenance_paid_amount = int(maintenance_paid_amt)
    response.property = {
        "id": str(property.id),
        "title": property.title,
        "city": property.city,
        "locality": property.locality,
        "photos": property.photos,
        "payment_expiry_hours": property.payment_expiry_hours,
    } if property else None
    response.room = {
        "id": str(room.id),
        "room_type": room.room_type,
        "room_number": room.room_number,
        "floor_number": room.floor_number,
        "bed_count": room.bed_count,
        "room_description": room.room_description,
        "price": room.price,
    } if room else None
    
    return response


@router.post("", response_model=BookingResponse)
async def create_booking(
    booking_data: BookingCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new booking request."""
    # On-demand cleanup of expired bookings
    from app.scheduler import cleanup_expired_bookings
    cleanup_expired_bookings(db=db, property_id=booking_data.property_id, background_tasks=background_tasks)

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
        Booking.status.in_(['requested', 'accepted', 'paid', 'active', 'checked_in'])
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
        
        # Calculate booking dates for vacancy check
        booking_start = booking_data.start_date
        if booking_data.stay_type == "daily":
            if booking_data.duration_days:
                duration_for_check = booking_data.duration_days
            elif booking_data.end_date:
                duration_for_check = (booking_data.end_date - booking_data.start_date).days
                if duration_for_check <= 0:
                    duration_for_check = 1
            else:
                duration_for_check = 1
            booking_end = booking_start + timedelta(days=duration_for_check)
        else:
            # For monthly stays, check 30 days ahead
            booking_end = booking_start + timedelta(days=30)
        
        # Dynamic vacancy check using date overlap
        available_beds = get_bed_vacancy(db, room.id, booking_start, booking_end)
        if available_beds <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No beds available in {room.room_type} for the selected dates"
            )
    
    # Calculate amount and deposit based on stay_type
    is_daily = booking_data.stay_type == "daily"
    amount = 0
    security_deposit = 0
    duration = None
    
    if is_daily:
        if not room:
            raise HTTPException(status_code=400, detail="Room selection is required for daily stay")
        
        if room.daily_price is None and room.daily_price_with_food is None and room.daily_price_without_food is None:
             raise HTTPException(status_code=400, detail="Daily stay is not available for this room")

        # Calculate duration
        if booking_data.duration_days:
            duration = booking_data.duration_days
        elif booking_data.end_date:
            duration = (booking_data.end_date - booking_data.start_date).days
            if duration <= 0: duration = 1
        else:
            duration = 1
        
        # Select price based on food preference
        if booking_data.food_included is True and room.daily_price_with_food:
            daily_rate = room.daily_price_with_food
        elif booking_data.food_included is False and room.daily_price_without_food:
            daily_rate = room.daily_price_without_food
        else:
            daily_rate = room.daily_price or room.price
            
        amount = daily_rate * duration
        security_deposit = 0
    else:
        if room.monthly_price is None and room.price is None:
             raise HTTPException(status_code=400, detail="Monthly stay is not available for this room")
             
        # For monthly, use room price if available, else property default
        amount = (room.monthly_price if room and room.monthly_price else (room.price if room else property.monthly_rent)) or 0
        security_deposit = (room.security_deposit if room and room.security_deposit else (room.deposit if room else property.deposit)) or 0

    # Pick a bed (Rule 16)
    bed_id = booking_data.bed_id
    if not bed_id and room:
        # Simple auto-allocation: find first bed with status available
        # Note: In a production system with date-based daily stays, we'd check bed-specific availability across dates.
        # For now, we use the room-level vacancy check and just link to a physical bed.
        available_bed = db.query(RoomBed).filter(
            RoomBed.room_id == room.id,
            RoomBed.status == "available"
        ).first()
        if available_bed:
            bed_id = available_bed.id

    # Get customer profile for snapshot
    customer_profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    customer_name = customer_profile.name if customer_profile else current_user.email
    customer_phone = customer_profile.phone if customer_profile else None
    
    # Create booking with customer snapshot for data retention
    new_booking = Booking(
        property_id=property.id,
        room_id=booking_data.room_id,
        bed_id=bed_id,
        customer_id=current_user.id,
        owner_id=property.owner_id,
        start_date=booking_data.start_date,
        end_date=booking_data.end_date,
        stay_type=booking_data.stay_type or "monthly",
        duration_days=duration,
        amount=amount,
        security_deposit=security_deposit,
        maintenance_charge=0 if is_daily else ((room.maintenance_charge if room else property.maintenance_charge) or 0),
        food_included=booking_data.food_included if is_daily else None,
        status="requested",
        # Snapshot of customer info - preserved even if customer deletes account
        customer_snapshot={
            "name": customer_name,
            "email": current_user.email,
            "phone": customer_phone,
            "rent_history": [{"amount": float(amount), "start_date": booking_data.start_date.isoformat()}]
        }
    )
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)
    
    # Notify owner about new booking request
    try:
        await notify_booking_created(db, property.owner_id, customer_name, property.title, new_booking.id)
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
        if new_status not in ["accepted", "cancelled", "rejected"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status transition"
            )
        if new_status in ["cancelled", "rejected"] and status_data.rejection_reason:
            booking.rejection_reason = status_data.rejection_reason
    
    if new_status == "completed" and booking.status != "completed" and booking.room_id:
        # Sync vacancy using centralized service
        sync_room_vacancy(db, booking.room_id)

    booking.status = new_status
    db.commit()
    db.refresh(booking)
    
    # Send notification to customer based on status change
    try:
        property = db.query(Property).filter(Property.id == booking.property_id).first()
        property_title = property.title if property else "Property"
        
        if new_status == "accepted":
            await notify_booking_accepted(db, booking.customer_id, property_title, booking.id)
        elif new_status in ["cancelled", "rejected"]:
            await notify_booking_rejected(db, booking.customer_id, property_title, rejection_reason=booking.rejection_reason)
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
    
    # If the booking was confirmed/paid/checked-in, we should restore the vacancy
    if booking.status in ["paid", "checked_in", "active", "vacate_requested"] and booking.room_id:
        # Sync vacancy using centralized service
        sync_room_vacancy(db, booking.room_id)

    booking.status = "cancelled"
    booking.cancelled_at = datetime.utcnow()
    booking.cancel_reason = cancel_data.cancel_reason
    
    db.commit()
    db.refresh(booking)

    # Notify the other party about the cancellation
    try:
        property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
        property_title = property_obj.title if property_obj else "Property"

        if current_user.id == booking.customer_id:
            # Tenant cancelled -> Notify Owner
            customer_profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
            customer_name = customer_profile.name if customer_profile else current_user.email
            await notify_booking_cancelled(
                db=db,
                user_id=booking.owner_id,
                property_title=property_title,
                initiator_name=customer_name,
                link="/owner/bookings?tab=cancelled",
                cancel_reason=booking.cancel_reason
            )
        else:
            # Owner cancelled -> Notify Tenant
            owner_profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
            owner_name = owner_profile.name if owner_profile else "Property Owner"
            await notify_booking_cancelled(
                db=db,
                user_id=booking.customer_id,
                property_title=property_title,
                initiator_name=owner_name,
                link="/bookings",
                cancel_reason=booking.cancel_reason
            )
    except Exception as e:
        import logging
        logging.warning(f"Failed to send cancellation notification: {e}")

    return booking


@router.post("/{booking_id}/vacate")
async def request_vacate(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Request to vacate a paid/active booking.
    Only the tenant (customer) can request to vacate.
    This notifies the owner about the vacate request.
    """
    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.customer_id == current_user.id
    ).first()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found"
        )
    
    # Can only vacate a paid or active booking
    if booking.status not in ["paid", "active", "checked_in"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot request vacate for booking with status: {booking.status}. Only paid/active bookings can be vacated."
        )
    
    # Update booking status
    booking.status = "vacate_requested"
    db.commit()
    db.refresh(booking)
    
    # Fetch property, room, and customer details for notification
    property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
    room_obj = db.query(Room).filter(Room.id == booking.room_id).first() if booking.room_id else None
    customer_profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    
    property_title = property_obj.title if property_obj else "Property"
    customer_name = customer_profile.name if customer_profile else current_user.email
    room_details = f" (Floor {room_obj.floor_number}, Room {room_obj.room_number})" if room_obj else ""

    # Calculate deposit, maintenance, and unpaid invoices (deductions)
    deposit_amount = booking.security_deposit or 0
    maintenance_charges = 0 if booking.maintenance_paid else (booking.maintenance_charge or 0)
    
    from app.models import Invoice
    unpaid_invoices = db.query(Invoice).filter(
        Invoice.booking_id == booking.id,
        Invoice.status.in_(["pending", "overdue"])
    ).all()
    deductions = sum(inv.amount for inv in unpaid_invoices)
    
    final_refund = deposit_amount - maintenance_charges - deductions
    
    owner_message = (
        f"{customer_name} has requested to vacate from {property_title}{room_details}.\n\n"
        f"Refund & Dues Details:\n"
        f"• Deposit Amount: ₹{deposit_amount}\n"
        f"• Maintenance Charges (Unpaid): ₹{maintenance_charges}\n"
        f"• Other Deductions (Unpaid Invoices): ₹{deductions}\n"
        f"• Final Refund Amount: ₹{final_refund}\n\n"
        f"Please review and process their checkout."
    )
    
    tenant_message = (
        f"Your request to vacate from {property_title}{room_details} has been submitted.\n\n"
        f"Estimated Refund Breakdown:\n"
        f"• Deposit Amount: ₹{deposit_amount}\n"
        f"• Maintenance Charges (Unpaid): ₹{maintenance_charges}\n"
        f"• Other Deductions (Unpaid Invoices): ₹{deductions}\n"
        f"• Estimated Refund Amount: ₹{final_refund}\n\n"
        f"The property owner has been notified to process your checkout."
    )
    
    # Notify owner and tenant about vacate request
    try:
        from app.utils.notifications import create_notification
        
        # 1. Notify Owner
        await create_notification(
            db=db,
            user_id=booking.owner_id,
            title="Vacate Request",
            message=owner_message,
            notification_type="vacate_request",
            link=f"/owner/bookings?tab=vacate&bookingId={booking.id}",
            reference_id=str(booking.id),
            reference_type="booking"
        )
        
        # 2. Notify Tenant
        await create_notification(
            db=db,
            user_id=booking.customer_id,
            title="Vacate Request Submitted",
            message=tenant_message,
            notification_type="info",
            reference_id=str(booking.id),
            reference_type="booking",
            link="/bookings"
        )
    except Exception as e:
        # Log but don't fail the vacate request
        import logging
        logging.warning(f"Failed to send vacate notifications: {e}")
    
    return {
        "success": True,
        "message": "Vacate request submitted successfully. The property owner has been notified.",
        "booking_id": str(booking.id),
        "status": "vacate_requested"
    }


@router.post("/{booking_id}/force-vacate")
async def force_vacate(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Force vacate a tenant (Owner only).
    Marks booking as 'vacated' and releases the bed.
    """
    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.owner_id == current_user.id
    ).first()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or not authorized")
    
    today_dt = date.today()
    
    # Release the bed immediately
    if booking.bed_id:
        bed = db.query(RoomBed).filter(RoomBed.id == booking.bed_id).first()
        if bed:
            bed.status = "available"
            bed.current_tenant_id = None
            
    # Update booking status
    booking.status = "vacated"
    booking.end_date = today_dt
    
    if booking.room_id:
        sync_room_vacancy(db, booking.room_id)
        
    db.commit()
    db.refresh(booking)
    
    # Notify tenant about force vacate (Omnichannel: Web, Email, SMS)
    try:
        from app.utils.notifications import create_notification
        property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
        property_title = property_obj.title if property_obj else "Property"
        
        await create_notification(
            db=db,
            user_id=booking.customer_id,
            title="Checkout Processed",
            message=f"Your stay at {property_title} has been marked as completed (vacated) by the owner.",
            notification_type="info",
            link="/bookings",
            send_external=True
        )
    except Exception as e:
        import logging
        logging.warning(f"Failed to send force-vacate notification: {e}")
        
    return {"success": True, "message": "Tenant vacated successfully", "status": "vacated"}


@router.post("/{booking_id}/decline-vacate")
async def decline_vacate(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Decline/cancel a vacate request (Owner only).
    Reverts booking status from 'vacate_requested' to 'active'.
    """
    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.owner_id == current_user.id
    ).first()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or not authorized")
        
    if booking.status != "vacate_requested":
        raise HTTPException(status_code=400, detail="Booking is not in vacate requested status")
        
    # Revert booking status
    booking.status = "active"
    db.commit()
    db.refresh(booking)
    
    # Notify tenant about vacate request decline (Omnichannel: Web, Email, SMS)
    try:
        from app.utils.notifications import create_notification
        property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
        property_title = property_obj.title if property_obj else "Property"
        
        await create_notification(
            db=db,
            user_id=booking.customer_id,
            title="Vacate Request Declined",
            message=f"Your request to vacate from {property_title} has been declined by the owner.",
            notification_type="warning",
            link="/bookings",
            send_external=True
        )
    except Exception as e:
        import logging
        logging.warning(f"Failed to send decline-vacate notification: {e}")
        
    return {"success": True, "message": "Vacate request declined successfully", "status": "active"}


@router.post("/{booking_id}/convert-to-monthly")
async def convert_to_monthly(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Convert a daily stay to a monthly stay."""
    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.customer_id == current_user.id,
        Booking.stay_type == "daily"
    ).first()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Active daily booking not found")
        
    room = db.query(Room).filter(Room.id == booking.room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
        
    if room.monthly_price is None and room.price is None:
        raise HTTPException(status_code=400, detail="Monthly stay not available for this room")
        
    booking.stay_type = "monthly"
    booking.amount = room.monthly_price or room.price or 0
    booking.security_deposit = room.security_deposit or room.deposit or 0
    booking.end_date = None # Monthly is open-ended
    
    db.commit()
    db.refresh(booking)
    
    # Notify owner about stay type change (Omnichannel: Web, Email, SMS)
    try:
        from app.utils.notifications import create_notification
        customer_profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
        customer_name = customer_profile.name if customer_profile else current_user.email
        property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
        property_title = property_obj.title if property_obj else "Property"
        
        await create_notification(
            db=db,
            user_id=booking.owner_id,
            title="Stay Type Updated",
            message=f"{customer_name} has converted their stay at {property_title} to Monthly.",
            notification_type="info",
            link="/owner/bookings",
            send_external=True
        )
    except Exception as e:
        import logging
        logging.warning(f"Failed to send stay type change notification: {e}")
        
    return booking


# --- Ticket System Moved to Maintenance Router ---


@router.post("/{booking_id}/extend", response_model=BookingResponse)
async def extend_booking(
    booking_id: UUID,
    extend_data: BookingExtend,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Extend a daily stay booking."""
    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.customer_id == current_user.id,
        Booking.stay_type == "daily"
    ).first()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active daily booking not found"
        )
    
    room = db.query(Room).filter(Room.id == booking.room_id).first()
    if not room:
         raise HTTPException(status_code=404, detail="Room not found")

    # Dynamic vacancy check for extension period
    is_available, available_beds = is_bed_available_for_extension(
        db, booking_id, extend_data.extra_days
    )
    if not is_available:
         raise HTTPException(
             status_code=400, 
             detail="No vacancy available for the extension period"
         )

    # Update booking
    # Use food-based pricing if available
    if booking.food_included is True and room.daily_price_with_food:
        daily_rate = room.daily_price_with_food
    elif booking.food_included is False and room.daily_price_without_food:
        daily_rate = room.daily_price_without_food
    else:
        daily_rate = room.daily_price or room.price
    extra_amount = daily_rate * extend_data.extra_days
    booking.amount += extra_amount
    booking.duration_days += extend_data.extra_days
    if booking.end_date:
        booking.end_date = booking.end_date + timedelta(days=extend_data.extra_days)
    else:
        # If no end date, calculate from start_date + new duration
        booking.end_date = booking.start_date + timedelta(days=booking.duration_days)
    
    db.commit()
    db.refresh(booking)
    
    # Notify owner about booking extension (Omnichannel: Web, Email, SMS)
    try:
        from app.utils.notifications import create_notification
        customer_profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
        customer_name = customer_profile.name if customer_profile else current_user.email
        property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
        property_title = property_obj.title if property_obj else "Property"
        
        await create_notification(
            db=db,
            user_id=booking.owner_id,
            title="Booking Extended",
            message=f"{customer_name} has extended their stay at {property_title} by {extend_data.extra_days} days.",
            notification_type="info",
            link="/owner/bookings",
            send_external=True
        )
    except Exception as e:
        import logging
        logging.warning(f"Failed to send extension notification: {e}")
        
    return booking
