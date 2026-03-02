"""Owner router for financial tracking and tenant management."""
from typing import List, Optional
from uuid import UUID
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from pydantic import BaseModel

from app.database import get_db
from app.models import User, Profile, Property, Booking, Payment, Invoice, Room, PaymentStatus, BookingStatus
from app.utils.security import get_current_user, require_role, get_user_role

require_owner = require_role("owner")

router = APIRouter(prefix="/owner", tags=["Owner"])


# ========== Pydantic Schemas ==========

class PaymentResponse(BaseModel):
    id: UUID
    booking_id: UUID
    amount: float
    payment_type: str
    status: str
    payment_date: Optional[datetime]
    created_at: datetime
    tenant_name: Optional[str] = None
    property_title: Optional[str] = None

    class Config:
        from_attributes = True


class InvoiceResponse(BaseModel):
    id: UUID
    booking_id: UUID
    amount: float
    due_date: Optional[datetime]
    status: str
    created_at: datetime
    tenant_name: Optional[str] = None
    property_title: Optional[str] = None

    class Config:
        from_attributes = True


class TenantResponse(BaseModel):
    id: UUID
    name: Optional[str]
    email: str
    phone: Optional[str]
    property_title: Optional[str]
    room_type: Optional[str]
    booking_status: str
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    monthly_rent: Optional[float]

    class Config:
        from_attributes = True


class FinancialSummary(BaseModel):
    total_revenue: float
    pending_payments: float
    total_properties: int
    total_tenants: int
    monthly_revenue: float


# ========== Owner Properties ==========

@router.get("/properties", dependencies=[Depends(require_owner)])
async def get_owner_properties(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all properties owned by the current user."""
    try:
        properties = db.query(Property).filter(
            Property.owner_id == current_user.id
        ).order_by(Property.created_at.desc()).all()
        
        result = []
        for prop in properties:
            result.append({
                "id": str(prop.id),
                "title": prop.title,
                "description": prop.description,
                "address": prop.address,
                "city": prop.city,
                "locality": prop.locality,
                "monthly_rent": prop.monthly_rent,
                "deposit": prop.deposit,
                "grace_period": prop.grace_period,
                "gender_preference": prop.gender_preference,
                "amenities": prop.amenities or [],
                "photos": prop.photos or [],
                "status": prop.status,
                "available_from": prop.available_from.isoformat() if prop.available_from else None,
                "created_at": prop.created_at.isoformat() if prop.created_at else None,
                "rooms": [{
                    "id": str(r.id),
                    "room_type": r.room_type,
                    "room_number": r.room_number,
                    "floor_number": r.floor_number or 1,
                    "bed_count": r.bed_count,
                    "price": r.price,
                    "monthly_price": r.monthly_price,
                    "daily_price": r.daily_price,
                    "deposit": r.deposit,
                    "security_deposit": r.security_deposit,
                    "maintenance_charge": r.maintenance_charge,
                    "vacancy_count": r.bed_count - len([
                        b for b in db.query(Booking).filter(
                            Booking.room_id == r.id,
                            Booking.status.in_([BookingStatus.active, BookingStatus.paid, BookingStatus.checked_in, BookingStatus.vacate_requested])
                        ).all()
                    ]),
                    "is_available": (r.bed_count - len([
                        b for b in db.query(Booking).filter(
                            Booking.room_id == r.id,
                            Booking.status.in_([BookingStatus.active, BookingStatus.paid, BookingStatus.checked_in, BookingStatus.vacate_requested])
                        ).all()
                    ])) > 0,
                    "stay_type": r.stay_type,
                    "room_photos": r.room_photos or [],
                    "room_description": r.room_description,
                    "area_sqft": r.area_sqft,
                    "width_ft": r.width_ft,
                    "has_ventilation": r.has_ventilation,
                    "tenants": [{
                        "booking_id": str(b.id),
                        "name": (db.query(Profile).filter(Profile.user_id == b.customer_id).first().name if db.query(Profile).filter(Profile.user_id == b.customer_id).first() else None) or (db.query(User).filter(User.id == b.customer_id).first().email if db.query(User).filter(User.id == b.customer_id).first() else "Tenant"),
                        "email": db.query(User).filter(User.id == b.customer_id).first().email if db.query(User).filter(User.id == b.customer_id).first() else "",
                        "phone": db.query(Profile).filter(Profile.user_id == b.customer_id).first().phone if db.query(Profile).filter(Profile.user_id == b.customer_id).first() else None,
                        "start_date": b.start_date.isoformat() if b.start_date else None,
                        "room_id": str(r.id),
                    } for b in db.query(Booking).filter(
                        Booking.room_id == r.id,
                        # Filter by business logic - active or soon-to-be active tenants
                        Booking.status.in_([
                            BookingStatus.active, 
                            BookingStatus.paid, 
                            BookingStatus.checked_in, 
                            BookingStatus.vacate_requested,
                            BookingStatus.accepted,
                            BookingStatus.requested
                        ])
                    ).all()],
                } for r in prop.rooms]
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Financial Tracking ==========

@router.delete("/properties/{property_id}", dependencies=[Depends(require_owner)])
async def delete_owner_property(
    property_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a property owned by the current user."""
    try:
        # Get the property
        property_obj = db.query(Property).filter(Property.id == property_id).first()
        
        if not property_obj:
            raise HTTPException(status_code=404, detail="Property not found")
        
        # Verify ownership
        if property_obj.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="You don't have permission to delete this property")
        
        # Check for active bookings
        active_bookings = db.query(Booking).filter(
            Booking.property_id == property_id,
            Booking.status.in_([BookingStatus.active, BookingStatus.accepted, BookingStatus.paid])
        ).count()
        
        if active_bookings > 0:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot delete property with {active_bookings} active booking(s). Please cancel or complete all bookings first."
            )
        
        # Delete the property (CASCADE will handle rooms)
        db.delete(property_obj)
        db.commit()
        
        return {"message": "Property deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/payments", dependencies=[Depends(require_owner)])
async def get_owner_payments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=100),
):
    """Get all payments for owner's properties."""
    try:
        # Get owner's property IDs
        owner_properties = db.query(Property.id).filter(Property.owner_id == current_user.id).all()
        property_ids = [p.id for p in owner_properties]
        
        if not property_ids:
            return []
        
        # Get bookings for owner's properties
        owner_bookings = db.query(Booking.id).filter(Booking.property_id.in_(property_ids)).all()
        booking_ids = [b.id for b in owner_bookings]
        
        if not booking_ids:
            return []
        
        # Get payments
        query = db.query(Payment).filter(Payment.booking_id.in_(booking_ids))
        
        if status_filter:
            query = query.filter(Payment.status == status_filter)
        
        payments = query.order_by(Payment.created_at.desc()).offset(skip).limit(limit).all()
        
        # Enrich with details
        result = []
        for payment in payments:
            booking = db.query(Booking).filter(Booking.id == payment.booking_id).first()
            property_obj = None
            tenant = None
            if booking:
                property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
                tenant = db.query(Profile).filter(Profile.user_id == booking.customer_id).first()
            
            result.append({
                "id": str(payment.id),
                "booking_id": str(payment.booking_id),
                "amount": payment.amount or 0,
                "payment_type": payment.payment_type.value if hasattr(payment.payment_type, 'value') else str(payment.payment_type or "rent"),
                "status": payment.status.value if hasattr(payment.status, 'value') else str(payment.status or "pending"),
                "payment_date": payment.payment_date.isoformat() if payment.payment_date else None,
                "created_at": payment.created_at.isoformat() if payment.created_at else None,
                "tenant_name": tenant.name if tenant else None,
                "property_title": property_obj.title if property_obj else None,
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/invoices", dependencies=[Depends(require_owner)])
async def get_owner_invoices(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=100),
):
    """Get all invoices for owner's properties."""
    try:
        # Get owner's property IDs
        owner_properties = db.query(Property.id).filter(Property.owner_id == current_user.id).all()
        property_ids = [p.id for p in owner_properties]
        
        if not property_ids:
            return []
        
        # Get bookings for owner's properties
        owner_bookings = db.query(Booking.id).filter(Booking.property_id.in_(property_ids)).all()
        booking_ids = [b.id for b in owner_bookings]
        
        if not booking_ids:
            return []
        
        # Get invoices
        query = db.query(Invoice).filter(Invoice.booking_id.in_(booking_ids))
        
        if status_filter:
            query = query.filter(Invoice.status == status_filter)
        
        invoices = query.order_by(Invoice.created_at.desc()).offset(skip).limit(limit).all()
        
        # Enrich with details
        result = []
        for invoice in invoices:
            booking = db.query(Booking).filter(Booking.id == invoice.booking_id).first()
            property_obj = None
            tenant = None
            if booking:
                property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
                tenant = db.query(Profile).filter(Profile.user_id == booking.customer_id).first()
            
            result.append({
                "id": str(invoice.id),
                "booking_id": str(invoice.booking_id),
                "amount": invoice.amount or 0,
                "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
                "status": invoice.status.value if hasattr(invoice.status, 'value') else str(invoice.status or "pending"),
                "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
                "tenant_name": tenant.name if tenant else None,
                "property_title": property_obj.title if property_obj else None,
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/financial-summary", dependencies=[Depends(require_owner)])
async def get_financial_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get financial summary for owner."""
    try:
        # Get owner's properties
        owner_properties = db.query(Property).filter(Property.owner_id == current_user.id).all()
        property_ids = [p.id for p in owner_properties]
        
        total_properties = len(owner_properties)
        
        if not property_ids:
            return {
                "total_revenue": 0,
                "pending_payments": 0,
                "total_properties": 0,
                "total_tenants": 0,
                "monthly_revenue": 0,
            }
        
        # Get active bookings (current tenants)
        active_bookings = db.query(Booking).filter(
            Booking.property_id.in_(property_ids),
            Booking.status.in_([BookingStatus.active, BookingStatus.paid])
        ).all()
        
        total_tenants = len(active_bookings)
        
        # Calculate monthly revenue from active bookings
        monthly_revenue = sum(b.amount or 0 for b in active_bookings)
        
        # Get total revenue from completed payments
        booking_ids = [b.id for b in db.query(Booking.id).filter(Booking.property_id.in_(property_ids)).all()]
        
        if booking_ids:
            total_revenue = db.query(func.sum(Payment.amount)).filter(
                Payment.booking_id.in_(booking_ids),
                Payment.status == PaymentStatus.completed
            ).scalar() or 0
            
            pending_payments = db.query(func.sum(Payment.amount)).filter(
                Payment.booking_id.in_(booking_ids),
                Payment.status == PaymentStatus.pending
            ).scalar() or 0
        else:
            total_revenue = 0
            pending_payments = 0
        
        return {
            "total_revenue": float(total_revenue),
            "pending_payments": float(pending_payments),
            "total_properties": total_properties,
            "total_tenants": total_tenants,
            "monthly_revenue": float(monthly_revenue),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Tenant Management ==========

@router.get("/tenants", dependencies=[Depends(require_owner)])
async def get_owner_tenants(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    property_id: Optional[UUID] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=100),
):
    """Get all tenants for owner's properties."""
    try:
        # Get owner's properties
        properties_query = db.query(Property).filter(Property.owner_id == current_user.id)
        
        if property_id:
            properties_query = properties_query.filter(Property.id == property_id)
        
        owner_properties = properties_query.all()
        property_ids = [p.id for p in owner_properties]
        
        if not property_ids:
            return []
        
        # Get paid/checked_in/active bookings (tenants actually occupying beds)
        active_bookings = db.query(Booking).filter(
            Booking.property_id.in_(property_ids),
            Booking.status.in_([BookingStatus.active, BookingStatus.paid, BookingStatus.checked_in, BookingStatus.vacate_requested])
        ).offset(skip).limit(limit).all()
        
        result = []
        for booking in active_bookings:
            user = db.query(User).filter(User.id == booking.customer_id).first()
            profile = db.query(Profile).filter(Profile.user_id == booking.customer_id).first()
            property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
            room = db.query(Room).filter(Room.id == booking.room_id).first() if booking.room_id else None
            
            result.append({
                "id": str(user.id if user else booking.customer_id),
                "booking_id": str(booking.id),
                "name": profile.name if profile else None,
                "email": user.email if user else "",
                "phone": profile.phone if profile else None,
                "property_title": property_obj.title if property_obj else None,
                "property_id": str(property_obj.id) if property_obj else None,
                "room_id": str(room.id) if room else None,
                "room_number": room.room_number if room else None,
                "room_type": room.room_type if room else None,
                "booking_status": booking.status.value if hasattr(booking.status, 'value') else str(booking.status),
                "start_date": booking.start_date.isoformat() if booking.start_date else None,
                "end_date": booking.end_date.isoformat() if booking.end_date else None,
                "monthly_rent": booking.amount,
                # Profile details
                "profile_photo": profile.profile_photo if profile else None,
                "gender": profile.gender if profile else None,
                "date_of_birth": profile.date_of_birth if profile else None,
                "work_type": profile.work_type if profile else None,
                "work_place": profile.work_place if profile else None,
                "current_address": profile.current_address if profile else None,
                "permanent_address": profile.permanent_address if profile else None,
                "city": profile.city if profile else None,
                # Emergency contact
                "emergency_contact_name": profile.emergency_contact_name if profile else None,
                "emergency_contact_phone": profile.emergency_contact_phone if profile else None,
                # KYC Documents
                "aadhar_front_url": profile.aadhar_front_url if profile else None,
                "aadhar_back_url": profile.aadhar_back_url if profile else None,
                "pan_card_url": profile.pan_card_url if profile else None,
                "dl_front_url": profile.dl_front_url if profile else None,
                "dl_back_url": profile.dl_back_url if profile else None,
                "college_company_id_url": profile.college_company_id_url if profile else None,
                "profile_verification_status": profile.profile_verification_status if profile else "pending",
                "documents_submitted": bool(
                    (profile.aadhar_front_url if profile else None) or 
                    (profile.pan_card_url if profile else None) or
                    (profile.college_company_id_url if profile else None)
                ),
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class VerifyTenantRequest(BaseModel):
    status: str  # "approved" or "rejected"


@router.put("/tenants/{tenant_id}/verify", dependencies=[Depends(require_owner)])
async def verify_tenant_profile(
    tenant_id: UUID,
    request: VerifyTenantRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify or reject a tenant's profile/KYC documents."""
    try:
        if request.status not in ["approved", "rejected", "pending"]:
            raise HTTPException(status_code=400, detail="Invalid status. Must be 'approved', 'rejected', or 'pending'")
        
        # Get owner's properties
        owner_properties = db.query(Property).filter(Property.owner_id == current_user.id).all()
        property_ids = [p.id for p in owner_properties]
        
        if not property_ids:
            raise HTTPException(status_code=403, detail="No properties found for this owner")
        
        # Check if tenant has booking with owner's property
        tenant_booking = db.query(Booking).filter(
            Booking.customer_id == tenant_id,
            Booking.property_id.in_(property_ids),
            Booking.status.in_([BookingStatus.active, BookingStatus.accepted, BookingStatus.paid])
        ).first()
        
        if not tenant_booking:
            raise HTTPException(status_code=403, detail="This tenant does not have a booking with your property")
        
        # Update profile verification status
        profile = db.query(Profile).filter(Profile.user_id == tenant_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Tenant profile not found")
        
        profile.profile_verification_status = request.status
        db.commit()
        
        return {"message": f"Tenant profile verification status updated to {request.status}"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# ========== Manual Tenant Addition ==========

@router.get("/lookup-tenant", dependencies=[Depends(require_owner)])
async def lookup_tenant_by_email(
    email: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Look up a tenant by email to verify they exist and are verified before adding."""
    email_clean = email.strip().lower()
    if not email_clean or "@" not in email_clean:
        raise HTTPException(status_code=400, detail="Valid email is required")

    user = db.query(User).filter(User.email == email_clean).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail="No account found with this email. The tenant must sign up on He&She PG first."
        )
    if not user.is_verified:
        raise HTTPException(
            status_code=400,
            detail="This account is not verified yet. The tenant must complete signup and verify their email first."
        )

    # Role Check: Only customers can be added as tenants
    role = get_user_role(user, db)
    if role in ["owner", "admin"]:
        raise HTTPException(
            status_code=400,
            detail=f"Accounts with '{role}' role cannot be added as tenants. Please use a regular customer account."
        )

    profile = db.query(Profile).filter(Profile.user_id == user.id).first()

    # Check if tenant already has an active booking
    active_booking = db.query(Booking).filter(
        Booking.customer_id == user.id,
        Booking.status.in_([BookingStatus.active, BookingStatus.accepted, BookingStatus.paid])
    ).first()

    return {
        "found": True,
        "tenant_name": profile.name if profile else "Tenant",
        "tenant_phone": profile.phone if profile else "",
        "tenant_email": user.email,
        "has_active_booking": active_booking is not None,
        "active_booking_message": f"This tenant already has an active booking in another property." if active_booking else None,
    }


class AddTenantRequest(BaseModel):
    email: str
    join_date: Optional[date] = None


@router.post("/rooms/{room_id}/add-tenant", dependencies=[Depends(require_owner)])
async def add_tenant_to_room(
    room_id: UUID,
    request: AddTenantRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a verified tenant to a room by their email. Tenant must have signed up first."""
    try:
        if not request.email.strip() or "@" not in request.email:
            raise HTTPException(status_code=400, detail="Valid email is required")

        # Get the room
        room = db.query(Room).filter(Room.id == room_id).first()
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")

        # Verify the room belongs to owner's property
        property_obj = db.query(Property).filter(Property.id == room.property_id).first()
        if not property_obj or property_obj.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="This room does not belong to your property")

        # Check vacancy
        if room.vacancy_count is not None and room.vacancy_count <= 0:
            raise HTTPException(status_code=400, detail="No vacancy available in this room")

        # Look up verified user by email
        tenant_user = db.query(User).filter(User.email == request.email.strip().lower()).first()
        if not tenant_user:
            raise HTTPException(
                status_code=404,
                detail="No account found with this email. The tenant must sign up on He&She PG first."
            )
        if not tenant_user.is_verified:
            raise HTTPException(
                status_code=400,
                detail="This account is not verified yet. The tenant must complete their signup and verify their email first."
            )

        # Role Check: Only customers can be added as tenants
        role = get_user_role(tenant_user, db)
        if role in ["owner", "admin"]:
            raise HTTPException(
                status_code=400,
                detail=f"Accounts with '{role}' role cannot be added as tenants. Please use a regular customer account."
            )

        # Get tenant profile for name/phone
        tenant_profile = db.query(Profile).filter(Profile.user_id == tenant_user.id).first()
        tenant_name = tenant_profile.name if tenant_profile else "Tenant"
        tenant_phone = tenant_profile.phone if tenant_profile else ""
        tenant_email = tenant_user.email

        # Check if this user already has an active booking for this room
        existing_booking = db.query(Booking).filter(
            Booking.customer_id == tenant_user.id,
            Booking.room_id == room_id,
            Booking.status.in_([BookingStatus.active, BookingStatus.accepted, BookingStatus.paid])
        ).first()
        if existing_booking:
            raise HTTPException(status_code=400, detail="This tenant already has an active booking for this room")

        # Check if tenant already has an active booking in ANY room
        any_active_booking = db.query(Booking).filter(
            Booking.customer_id == tenant_user.id,
            Booking.status.in_([BookingStatus.active, BookingStatus.accepted, BookingStatus.paid])
        ).first()
        if any_active_booking:
            raise HTTPException(
                status_code=400,
                detail=f"'{tenant_name}' already has an active booking in another property. They must vacate first."
            )

        # Create active booking
        start_date = request.join_date if request.join_date else date.today()
        booking = Booking(
            property_id=property_obj.id,
            room_id=room.id,
            customer_id=tenant_user.id,
            owner_id=current_user.id,
            start_date=start_date,
            status="active",
            amount=room.price or 0,
            security_deposit=room.deposit or 0,
            maintenance_charge=0,
            stay_type=room.stay_type or "monthly",
            customer_snapshot={
                "name": tenant_name,
                "email": tenant_email,
                "phone": tenant_phone,
            },
        )
        db.add(booking)

        # Decrement vacancy
        if room.vacancy_count is not None and room.vacancy_count > 0:
            room.vacancy_count -= 1
            if room.vacancy_count == 0:
                room.is_available = False

        db.commit()

        return {
            "message": f"Tenant '{tenant_name}' added to room successfully",
            "tenant_id": str(tenant_user.id),
            "booking_id": str(booking.id),
            "tenant_name": tenant_name,
            "tenant_phone": tenant_phone,
            "tenant_email": tenant_email,
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tenants/{booking_id}/remove", dependencies=[Depends(require_owner)])
async def remove_tenant_from_room(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a tenant from a room by cancelling their booking."""
    try:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        # Verify ownership
        property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
        if not property_obj or property_obj.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized")

        # Cancel the booking
        booking.status = "vacated"

        # Restore vacancy
        if booking.room_id:
            room = db.query(Room).filter(Room.id == booking.room_id).first()
            if room:
                if room.vacancy_count is not None:
                    room.vacancy_count += 1
                else:
                    room.vacancy_count = 1
                room.is_available = True

        db.commit()
        return {"message": "Tenant removed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


class UpdateTenantRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    join_date: Optional[date] = None


@router.put("/tenants/{booking_id}/update", dependencies=[Depends(require_owner)])
async def update_tenant_info(
    booking_id: UUID,
    request: UpdateTenantRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a tenant's profile info (name, phone, email)."""
    try:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        # Verify ownership
        property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
        if not property_obj or property_obj.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized")

        # Update profile
        profile = db.query(Profile).filter(Profile.user_id == booking.customer_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Tenant profile not found")

        # Get the associated user
        tenant_user = db.query(User).filter(User.id == booking.customer_id).first()
        if not tenant_user:
            raise HTTPException(status_code=404, detail="Tenant user not found")

        if request.name and request.name.strip():
            profile.name = request.name.strip()

        if request.phone and request.phone.strip():
            new_phone = request.phone.strip()
            # Check if phone number already belongs to another verified user
            existing_profile_by_phone = db.query(Profile).filter(
                Profile.phone == new_phone, 
                Profile.user_id != tenant_user.id
            ).first()
            if existing_profile_by_phone:
                existing_phone_user = db.query(User).filter(User.id == existing_profile_by_phone.user_id).first()
                if existing_phone_user and existing_phone_user.is_verified:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Phone number '{new_phone}' is already registered to another verified account."
                    )
            profile.phone = new_phone

        if request.email and request.email.strip():
            new_email = request.email.strip()
            # If tenant is already verified, owner cannot change their email
            if tenant_user.is_verified and new_email != tenant_user.email:
                raise HTTPException(
                    status_code=400, 
                    detail="Cannot change email for a verified tenant. They must manage it themselves."
                )
            
            # Check if email is already taken by another verified user
            existing_user_by_email = db.query(User).filter(
                User.email == new_email, 
                User.id != tenant_user.id
            ).first()
            if existing_user_by_email and existing_user_by_email.is_verified:
                raise HTTPException(
                    status_code=400,
                    detail=f"Email '{new_email}' is already registered to another verified account."
                )
            
            # Update both profile and user (for unverified claiming)
            profile.email = new_email
            if not tenant_user.is_verified:
                tenant_user.email = new_email
        
        if request.join_date:
            booking.start_date = request.join_date

        db.commit()
        return {"message": "Tenant info updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
