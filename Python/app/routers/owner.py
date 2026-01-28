"""Owner router for financial tracking and tenant management."""
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from app.database import get_db
from app.models import User, Profile, Property, Booking, Payment, Invoice, Room, PaymentStatus, BookingStatus
from app.utils.security import get_current_user, require_role

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
                "gender_preference": prop.gender_preference,
                "amenities": prop.amenities or [],
                "photos": prop.photos or [],
                "status": prop.status,
                "available_from": prop.available_from.isoformat() if prop.available_from else None,
                "created_at": prop.created_at.isoformat() if prop.created_at else None,
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
        
        # Delete the property
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
        
        # Get active/accepted bookings (tenants)
        active_bookings = db.query(Booking).filter(
            Booking.property_id.in_(property_ids),
            Booking.status.in_([BookingStatus.active, BookingStatus.accepted, BookingStatus.paid])
        ).offset(skip).limit(limit).all()
        
        result = []
        for booking in active_bookings:
            user = db.query(User).filter(User.id == booking.customer_id).first()
            profile = db.query(Profile).filter(Profile.user_id == booking.customer_id).first()
            property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
            room = db.query(Room).filter(Room.id == booking.room_id).first() if booking.room_id else None
            
            result.append({
                "id": str(user.id if user else booking.customer_id),
                "name": profile.name if profile else None,
                "email": user.email if user else "",
                "phone": profile.phone if profile else None,
                "property_title": property_obj.title if property_obj else None,
                "room_type": room.room_type if room else None,
                "booking_status": booking.status.value if hasattr(booking.status, 'value') else str(booking.status),
                "start_date": booking.start_date.isoformat() if booking.start_date else None,
                "end_date": booking.end_date.isoformat() if booking.end_date else None,
                "monthly_rent": booking.amount,
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
