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


# ========== Financial Tracking ==========

@router.get("/payments", response_model=List[PaymentResponse], dependencies=[Depends(require_owner)])
async def get_owner_payments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=100),
):
    """Get all payments for owner's properties."""
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
        payment_dict = PaymentResponse.model_validate(payment)
        payment_dict.status = payment.status.value if payment.status else "pending"
        payment_dict.payment_type = payment.payment_type.value if payment.payment_type else "rent"
        
        booking = db.query(Booking).filter(Booking.id == payment.booking_id).first()
        if booking:
            property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
            tenant = db.query(Profile).filter(Profile.user_id == booking.customer_id).first()
            
            payment_dict.property_title = property_obj.title if property_obj else None
            payment_dict.tenant_name = tenant.name if tenant else None
        
        result.append(payment_dict)
    
    return result


@router.get("/invoices", response_model=List[InvoiceResponse], dependencies=[Depends(require_owner)])
async def get_owner_invoices(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=100),
):
    """Get all invoices for owner's properties."""
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
        invoice_dict = InvoiceResponse.model_validate(invoice)
        invoice_dict.status = invoice.status.value if invoice.status else "pending"
        
        booking = db.query(Booking).filter(Booking.id == invoice.booking_id).first()
        if booking:
            property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
            tenant = db.query(Profile).filter(Profile.user_id == booking.customer_id).first()
            
            invoice_dict.property_title = property_obj.title if property_obj else None
            invoice_dict.tenant_name = tenant.name if tenant else None
        
        result.append(invoice_dict)
    
    return result


@router.get("/financial-summary", response_model=FinancialSummary, dependencies=[Depends(require_owner)])
async def get_financial_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get financial summary for owner."""
    # Get owner's properties
    owner_properties = db.query(Property).filter(Property.owner_id == current_user.id).all()
    property_ids = [p.id for p in owner_properties]
    
    total_properties = len(owner_properties)
    
    if not property_ids:
        return FinancialSummary(
            total_revenue=0,
            pending_payments=0,
            total_properties=0,
            total_tenants=0,
            monthly_revenue=0,
        )
    
    # Get active bookings (current tenants)
    active_bookings = db.query(Booking).filter(
        Booking.property_id.in_(property_ids),
        Booking.status == BookingStatus.active
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
    
    return FinancialSummary(
        total_revenue=float(total_revenue),
        pending_payments=float(pending_payments),
        total_properties=total_properties,
        total_tenants=total_tenants,
        monthly_revenue=float(monthly_revenue),
    )


# ========== Tenant Management ==========

@router.get("/tenants", response_model=List[TenantResponse], dependencies=[Depends(require_owner)])
async def get_owner_tenants(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    property_id: Optional[UUID] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=100),
):
    """Get all tenants for owner's properties."""
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
        Booking.status.in_([BookingStatus.active, BookingStatus.accepted])
    ).offset(skip).limit(limit).all()
    
    result = []
    for booking in active_bookings:
        user = db.query(User).filter(User.id == booking.customer_id).first()
        profile = db.query(Profile).filter(Profile.user_id == booking.customer_id).first()
        property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
        room = db.query(Room).filter(Room.id == booking.room_id).first() if booking.room_id else None
        
        result.append(TenantResponse(
            id=user.id if user else booking.customer_id,
            name=profile.name if profile else None,
            email=user.email if user else "",
            phone=profile.phone if profile else None,
            property_title=property_obj.title if property_obj else None,
            room_type=room.room_type if room else None,
            booking_status=booking.status.value if booking.status else "active",
            start_date=booking.start_date,
            end_date=booking.end_date,
            monthly_rent=booking.amount,
        ))
    
    return result
