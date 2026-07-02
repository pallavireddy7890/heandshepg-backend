"""Owner router for financial tracking and tenant management."""
from typing import List, Optional
from uuid import UUID
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text, String
from pydantic import BaseModel

from app.database import get_db
from app.models import User, Profile, Property, Booking, Payment, Invoice, Room, PaymentStatus, BookingStatus, SystemSettings
from app.utils.security import get_current_user, require_role, get_user_role
from app.schemas import PropertyDeletionResponse
from app.services.vacancy import sync_room_vacancy

import logging
logger = logging.getLogger(__name__)
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


class RentManagementItem(BaseModel):
    id: UUID
    booking_id: UUID
    tenant_name: str
    phone: Optional[str]
    email: str
    property_title: str
    room_number: Optional[str]
    floor_number: Optional[str] = None
    monthly_rent: float
    status: str  # paid, unpaid, partial, upcoming, due_today
    payment_type: Optional[str]
    payment_date: Optional[datetime]
    last_payment_method: Optional[str]
    due_date: Optional[date] = None
    security_paid: float = 0
    maintenance_paid: float = 0
    security_deposit: float = 0
    maintenance_charge: float = 0
    remaining_rent: float = 0
    deposit_paid: bool = False
    rent_paid: bool = False
    maintenance_paid_status: bool = False
    rent_paid_this_period: float = 0
    billing_cycle_start: Optional[date] = None
    billing_cycle_end: Optional[date] = None


class RentManagementStats(BaseModel):
    total_tenants: int
    paid_count: int
    unpaid_count: int
    partial_count: int
    upcoming_count: int
    collected_amount: float


class RentManagementResponse(BaseModel):
    tenants: List[RentManagementItem]
    stats: RentManagementStats


# ========== Helpers ==========

def calculate_month_rent_stats(db: Session, booking: Booking, month: int, year: int):
    from sqlalchemy import and_, or_
    from app.models.wallet import WalletTransaction, TransactionStatus
    from datetime import datetime, date
    from app.services.wallet_service import WalletService
    import calendar

    today = date.today()

    # Use billing cycle (based on tenant's start_date) instead of calendar month
    # This matches the logic used in collect-offline-payment endpoint
    # to prevent mismatch between displayed due amount and actual remaining amount.
    #
    # For past months that don't contain the current billing cycle,
    # we approximate by using the Nth of that month as reference.
    ref_day = min(booking.start_date.day, calendar.monthrange(year, month)[1])
    reference_date = date(year, month, ref_day)
    period_start, period_end = WalletService.get_billing_period(booking.start_date, reference_date)

    start_dt = datetime.combine(period_start, datetime.min.time())
    end_dt = datetime.combine(period_end, datetime.max.time())

    # Query recurring payments (rent and maintenance) for this booking in this billing cycle
    payments = db.query(WalletTransaction).filter(
        WalletTransaction.booking_id == booking.id,
        WalletTransaction.status == TransactionStatus.completed,
        WalletTransaction.payment_type.in_(['rent', 'total', 'maintenance']),
        WalletTransaction.created_at >= start_dt,
        WalletTransaction.created_at <= end_dt
    ).all()

    # Query security deposit payments across all time (since it is a lifetime payment)
    deposit_payments = db.query(WalletTransaction).filter(
        WalletTransaction.booking_id == booking.id,
        WalletTransaction.status == TransactionStatus.completed,
        WalletTransaction.payment_type.in_(['deposit', 'total'])
    ).all()

    rent_paid = 0
    total_maint_txns_amount = 0
    p_date = None
    p_type = None

    # Calculate recurring rent and maintenance
    for p in payments:
        if not p_date or p.created_at > p_date:
            p_date = p.created_at
            p_type = p.payment_type

        if p.payment_type == 'rent':
            rent_paid += p.amount / 100
        elif p.payment_type == 'total':
            rent_paid += booking.amount
            total_maint_txns_amount += (booking.maintenance_charge or 0)
        elif p.payment_type == 'maintenance':
            total_maint_txns_amount += p.amount / 100

    # Calculate completed deposit transactions (lifetime)
    total_deposit_txns_amount = 0
    for p in deposit_payments:
        if not p_date or p.created_at > p_date:
            p_date = p.created_at
            p_type = p.payment_type

        if p.payment_type == 'deposit':
            total_deposit_txns_amount += p.amount / 100
        elif p.payment_type == 'total':
            total_deposit_txns_amount += (booking.security_deposit or 0)

    # Allocate lifetime deposit transactions to security deposit and maintenance charge
    security_cap = float(booking.security_deposit or 0)
    security_paid = min(total_deposit_txns_amount, security_cap)
    leftover_deposit = max(0.0, total_deposit_txns_amount - security_cap)
    
    maintenance_paid = total_maint_txns_amount + leftover_deposit

    # Calculate due date for this billing cycle
    due_on = min(booking.start_date.day, calendar.monthrange(year, month)[1])
    calculated_due_date = date(year, month, due_on)

    # Determine Status with due-date awareness
    if rent_paid >= booking.amount:
        status = "paid"
    elif rent_paid > 0:
        status = "partial"
    else:
        # No rent paid yet — check due date to distinguish upcoming vs unpaid
        if calculated_due_date > today:
            status = "upcoming"
        elif calculated_due_date == today:
            status = "due_today"
        else:
            status = "unpaid"

    return {
        "rent_paid": rent_paid,
        "security_paid": security_paid,
        "maintenance_paid": maintenance_paid,
        "status": status,
        "last_payment_date": p_date,
        "last_payment_type": p_type,
        "billing_cycle_start": period_start,
        "billing_cycle_end": period_end,
    }


# ========== Owner Properties ==========

@router.get("/properties", dependencies=[Depends(require_owner)])
async def get_owner_properties(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all properties owned by the current user."""
    try:
        today = date.today()
        properties = db.query(Property).filter(
            Property.owner_id == current_user.id,
            Property.inactive_at.is_(None)
        ).order_by(Property.created_at.desc()).all()
        
        property_ids = [p.id for p in properties]
        
        # Bulk query bookings for these properties in one go
        all_bookings = db.query(Booking).filter(
            Booking.property_id.in_(property_ids),
            Booking.status.in_([
                BookingStatus.active, 
                BookingStatus.paid, 
                BookingStatus.checked_in, 
                BookingStatus.vacate_requested,
                BookingStatus.accepted,
                BookingStatus.requested
            ])
        ).all() if property_ids else []
        
        # Group bookings by room_id
        from collections import defaultdict
        bookings_by_room = defaultdict(list)
        for b in all_bookings:
            if b.room_id:
                bookings_by_room[b.room_id].append(b)
                
        # Collect customer IDs to bulk-query users and profiles
        customer_ids = {b.customer_id for b in all_bookings}
        profiles = db.query(Profile).filter(Profile.user_id.in_(customer_ids)).all() if customer_ids else []
        users = db.query(User).filter(User.id.in_(customer_ids)).all() if customer_ids else []
        
        profile_map = {p.user_id: p for p in profiles}
        user_map = {u.id: u for u in users}
        
        result = []
        for prop in properties:
            rooms_list = []
            for r in prop.rooms:
                room_bookings = bookings_by_room.get(r.id, [])
                
                # Filter for occupied bookings (actually in beds)
                occupied_bookings = [
                    b for b in room_bookings 
                    if b.status in [BookingStatus.active, BookingStatus.paid, BookingStatus.checked_in, BookingStatus.vacate_requested]
                ]
                vacancy_count = max(0, r.bed_count - len(occupied_bookings))
                is_available = vacancy_count > 0
                
                # Tenants list
                tenants_list = []
                for b in room_bookings:
                    profile = profile_map.get(b.customer_id)
                    user = user_map.get(b.customer_id)
                    
                    email = user.email if user else ""
                    name = (profile.name if profile else None) or email or "Tenant"
                    phone = profile.phone if profile else None
                    
                    tenants_list.append({
                        "booking_id": str(b.id),
                        "name": name,
                        "email": email,
                        "phone": phone,
                        "start_date": b.start_date.isoformat() if b.start_date else None,
                        "room_id": str(r.id),
                        "status": calculate_month_rent_stats(
                            db, b, date.today().month, date.today().year
                        )["status"]
                    })
                
                rooms_list.append({
                    "id": str(r.id),
                    "room_type": r.room_type,
                    "room_number": r.room_number,
                    "floor_number": r.floor_number if r.floor_number is not None else "1",
                    "bed_count": r.bed_count,
                    "price": r.price,
                    "monthly_price": r.monthly_price,
                    "daily_price": r.daily_price,
                    "daily_price_with_food": r.daily_price_with_food,
                    "daily_price_without_food": r.daily_price_without_food,
                    "deposit": r.deposit,
                    "security_deposit": r.security_deposit,
                    "maintenance_charge": r.maintenance_charge,
                    "status_month": today.strftime('%B %Y'),
                    "vacancy_count": vacancy_count,
                    "is_available": is_available,
                    "stay_type": r.stay_type,
                    "room_photos": r.room_photos or [],
                    "room_description": r.room_description,
                    "area_sqft": r.area_sqft,
                    "width_ft": r.width_ft,
                    "has_ventilation": r.has_ventilation,
                    "tenants": tenants_list,
                })
                
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
                "rooms": rooms_list,
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Financial Tracking ==========

@router.delete("/properties/{property_id}", response_model=PropertyDeletionResponse, dependencies=[Depends(require_owner)])
async def delete_owner_property(
    property_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a property owned by the current user."""
    try:
        from app.services.property_service import PropertyService
        return await PropertyService.delete_property(
            db=db,
            property_id=property_id,
            current_user_id=current_user.id,
            is_admin=False
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Failed to delete owner property {property_id}")
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
        owner_properties = db.query(Property).filter(
            Property.owner_id == current_user.id,
            Property.inactive_at.is_(None)
        ).all()
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
            Booking.status.in_([
                BookingStatus.active, 
                BookingStatus.paid, 
                BookingStatus.checked_in, 
                BookingStatus.vacate_requested
            ])
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


@router.get("/rent-management", response_model=RentManagementResponse, dependencies=[Depends(require_owner)])
async def get_rent_management_data(
    month: int = Query(..., ge=0, le=12),  # 0 means yearly
    year: int = Query(..., ge=2000),
    property_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get rent management data for a specific month/year or the entire year.
    Only includes tenants active during that period.
    """
    import calendar
    from sqlalchemy import or_, and_
    from app.models.wallet import WalletTransaction, TransactionStatus

    try:
        # Get owner's property IDs
        prop_query = db.query(Property.id).filter(Property.owner_id == current_user.id)
        if property_id:
            prop_query = prop_query.filter(Property.id == property_id)
        
        owned_property_ids = [p.id for p in prop_query.all()]
        if not owned_property_ids:
            return {
                "tenants": [],
                "stats": {
                    "total_tenants": 0,
                    "paid_count": 0,
                    "unpaid_count": 0,
                    "partial_count": 0,
                    "upcoming_count": 0,
                    "collected_amount": 0
                }
            }

        today = date.today()
        if month > 0:
            # Monthly View
            last_day = calendar.monthrange(year, month)[1]
            month_start = date(year, month, 1)
            month_end = date(year, month, last_day)
            
            period_start = month_start
            period_end = month_end
            
            # Future Month Check: If selected month/year is in the future, don't show names
            if year > today.year or (year == today.year and month > today.month):
                return {
                    "tenants": [], 
                    "stats": {
                        "total_tenants": 0, 
                        "paid_count": 0, 
                        "unpaid_count": 0, 
                        "partial_count": 0,
                        "upcoming_count": 0,
                        "collected_amount": 0
                    }
                }
        else:
            # Yearly View
            period_start = date(year, 1, 1)
            period_end = date(year, 12, 31)

            # Future Year Check
            if year > today.year:
                return {
                    "tenants": [], 
                    "stats": {
                        "total_tenants": 0, 
                        "paid_count": 0, 
                        "unpaid_count": 0, 
                        "partial_count": 0,
                        "upcoming_count": 0,
                        "collected_amount": 0
                    }
                }

        # Find active bookings in this period
        active_bookings = db.query(Booking).filter(
            Booking.property_id.in_(owned_property_ids),
            Booking.start_date <= period_end,
            or_(Booking.end_date == None, Booking.end_date >= period_start),
            Booking.status.in_([
                BookingStatus.active, 
                BookingStatus.paid, 
                BookingStatus.checked_in, 
                BookingStatus.vacate_requested
            ])
        ).all()

        tenants_data = []
        collected_amount = 0
        paid_count = 0
        unpaid_count = 0
        partial_count = 0
        upcoming_count = 0

        for booking in active_bookings:
            user = db.query(User).filter(User.id == booking.customer_id).first()
            if not user: continue
            
            profile = db.query(Profile).filter(Profile.user_id == booking.customer_id).first()
            prop = db.query(Property).filter(Property.id == booking.property_id).first()
            room = db.query(Room).filter(Room.id == booking.room_id).first() if booking.room_id else None

            # Use unified helper for status and amounts
            m_stats = calculate_month_rent_stats(db, booking, month if month > 0 else today.month, year if month > 0 else today.year)
            
            rent_this_period = m_stats["rent_paid"]
            security_this_period = m_stats["security_paid"]
            maintenance_this_period = m_stats["maintenance_paid"]
            status = m_stats["status"]
            p_date = m_stats["last_payment_date"]
            p_type = m_stats["last_payment_type"]
            billing_start = m_stats.get("billing_cycle_start")
            billing_end = m_stats.get("billing_cycle_end")

            if status == "paid":
                paid_count += 1
            elif "partial" in status:
                partial_count += 1
            elif status in ("upcoming", "due_today"):
                upcoming_count += 1
            else:
                unpaid_count += 1

            # Calculate Due Date
            if month > 0:
                day_of_month = booking.start_date.day
                max_days = calendar.monthrange(year, month)[1]
                due_on = min(day_of_month, max_days)
                calculated_due_date = date(year, month, due_on)
            else:
                calculated_due_date = None

            tenants_data.append({
                "id": user.id,
                "booking_id": booking.id,
                "tenant_name": profile.name if profile else user.email,
                "phone": profile.phone if profile else None,
                "email": user.email,
                "property_title": prop.title,
                "room_number": room.room_number if room else None,
                "floor_number": room.floor_number if room else None,
                "monthly_rent": booking.amount,
                "status": status,
                "payment_type": p_type,
                "payment_date": p_date,
                "last_payment_method": p_type,
                "due_date": calculated_due_date,
                "security_paid": security_this_period,
                "maintenance_paid": maintenance_this_period,
                "rent_paid_this_period": rent_this_period,
                "security_deposit": booking.security_deposit or 0,
                "maintenance_charge": booking.maintenance_charge or 0,
                "remaining_rent": max(0.0, float(booking.amount) - rent_this_period),
                "deposit_paid": booking.deposit_paid,
                "rent_paid": booking.rent_paid,
                "maintenance_paid_status": booking.maintenance_paid,
                "billing_cycle_start": billing_start,
                "billing_cycle_end": billing_end,
            })

        # Sort tenants_data by due_date ascending (put None/null at the end)
        tenants_data.sort(
            key=lambda x: (
                0 if x["due_date"] is not None else 1,
                x["due_date"] or date(9999, 12, 31)
            )
        )

        return {
            "tenants": tenants_data,
            "stats": {
                "total_tenants": len(active_bookings),
                "paid_count": paid_count,
                "unpaid_count": unpaid_count,
                "partial_count": partial_count,
                "upcoming_count": upcoming_count,
                "collected_amount": sum(t.get('rent_paid_this_period', 0) for t in tenants_data)
            }
        }
    except Exception as e:
        print(f"Error in rent management: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== Tenant Transaction History ==========

@router.get("/tenant-transactions/{booking_id}", dependencies=[Depends(require_owner)])
async def get_tenant_transaction_history(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all wallet transactions for a specific booking (tenant payment history)."""
    from app.models.wallet import WalletTransaction, TransactionStatus

    try:
        # Get the booking
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        # Verify ownership
        property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
        if not property_obj or property_obj.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized")

        # Get tenant info
        profile = db.query(Profile).filter(Profile.user_id == booking.customer_id).first()
        user = db.query(User).filter(User.id == booking.customer_id).first()
        room = db.query(Room).filter(Room.id == booking.room_id).first() if booking.room_id else None

        # Get all transactions for this booking
        transactions = db.query(WalletTransaction).filter(
            WalletTransaction.booking_id == booking_id,
            WalletTransaction.status.in_([
                TransactionStatus.completed,
                TransactionStatus.pending,
                TransactionStatus.verified,
            ])
        ).order_by(WalletTransaction.created_at.desc()).all()

        tenant_name = profile.name if profile else (user.email if user else "Unknown")
        room_desc = f"Room {room.room_number}" if room else "Room"
        desc_replacement = f"{room_desc} ({tenant_name})" if tenant_name != "Unknown" else room_desc

        from app.services.wallet_service import calculate_transaction_breakdown
        result = []
        for txn in transactions:
            description = txn.description  # preserve None if absent
            booking_uuid_str = str(booking.id)
            if description and booking_uuid_str in description:
                if f"booking {booking_uuid_str}" in description:
                    description = description.replace(f"booking {booking_uuid_str}", desc_replacement)
                else:
                    description = description.replace(booking_uuid_str, desc_replacement)
            result.append({
                "id": str(txn.id),
                "amount": txn.amount / 100,  # Convert paise to rupees
                "payment_type": txn.payment_type or "rent",
                "payment_method": txn.payment_method or "online",
                "status": txn.status.value if hasattr(txn.status, 'value') else str(txn.status),
                "description": description,
                "offline_notes": txn.offline_notes,
                "offline_reference": txn.offline_reference,
                "created_at": txn.created_at.isoformat() if txn.created_at else None,
                "breakdown": calculate_transaction_breakdown(txn, booking_obj=booking),
            })

        return {
            "tenant_name": profile.name if profile else (user.email if user else "Unknown"),
            "tenant_email": user.email if user else "",
            "room_number": room.room_number if room else None,
            "property_title": property_obj.title if property_obj else None,
            "monthly_rent": booking.amount or 0,
            "transactions": result,
            "total_paid": sum(t["amount"] for t in result if t["status"] == "completed"),
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in tenant transaction history: {str(e)}")
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
        properties_query = db.query(Property).filter(
            Property.owner_id == current_user.id,
            Property.inactive_at.is_(None)
        )
        
        if property_id:
            properties_query = properties_query.filter(Property.id == property_id)
        
        owner_properties = properties_query.all()
        property_ids = [p.id for p in owner_properties]
        
        if not property_ids:
            return []
        
        # Get paid/checked_in/active bookings (tenants actually occupying beds)
        active_bookings = db.query(Booking).filter(
            Booking.property_id.in_(property_ids),
            Booking.status.in_([BookingStatus.requested, BookingStatus.accepted, BookingStatus.active, BookingStatus.paid, BookingStatus.checked_in, BookingStatus.vacate_requested])
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
                "floor_number": room.floor_number if room else None,
                "room_type": room.room_type if room else None,
                "booking_status": booking.status.value if hasattr(booking.status, 'value') else str(booking.status),
                "start_date": booking.start_date.isoformat() if booking.start_date else None,
                "end_date": booking.end_date.isoformat() if booking.end_date else None,
                "monthly_rent": booking.amount,
                "security_deposit": booking.security_deposit or 0,
                "maintenance_charge": booking.maintenance_charge or (room.maintenance_charge if room and hasattr(room, 'maintenance_charge') else 0),
                "stay_type": booking.stay_type or "monthly",
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
        owner_properties = db.query(Property).filter(
            Property.owner_id == current_user.id,
            Property.inactive_at.is_(None)
        ).all()
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
async def lookup_tenant(
    query: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Look up a tenant by email or phone number to verify they exist and are verified before adding."""
    query_clean = query.strip().lower()
    if not query_clean:
        raise HTTPException(status_code=400, detail="Valid email or phone number is required")

    # Try to find user by email first
    user = db.query(User).filter(User.email == query_clean).first()
    
    # If not found by email, try finding by phone number in Profile
    if not user:
        # Basic phone normalization: take only last 10 digits for matching or try exact match
        digits_only = "".join(filter(str.isdigit, query_clean))
        if digits_only:
            # Match by phone ending with digits or exact match
            profile_query = db.query(Profile).filter(
                (Profile.phone == digits_only) | 
                (Profile.phone.endswith(digits_only[-10:] if len(digits_only) >= 10 else digits_only))
            )
            profile = profile_query.first()
            if profile:
                user = db.query(User).filter(User.id == profile.user_id).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="No account found with this email or phone number. The tenant must sign up on He&She PG first."
        )
    
    if not user.is_verified:
        raise HTTPException(
            status_code=400,
            detail="This account is not verified yet. The tenant must complete signup and verify their account first."
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
        "tenant_id": str(user.id),
        "tenant_name": profile.name if profile else "Tenant",
        "tenant_phone": profile.phone if profile else "",
        "tenant_email": user.email,
        "has_active_booking": active_booking is not None,
        "active_booking_message": f"This tenant already has an active booking in another property." if active_booking else None,
    }


class AddTenantRequest(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    join_date: Optional[date] = None
    security_deposit: Optional[int] = None
    deposit_paid: Optional[int] = None
    deposit_payment_mode: Optional[str] = None
    deposit_payment_date: Optional[date] = None
    deposit_notes: Optional[str] = None
    maintenance_charge: Optional[int] = None
    maintenance_paid: Optional[int] = None
    maintenance_payment_mode: Optional[str] = None


@router.post("/rooms/{room_id}/add-tenant", dependencies=[Depends(require_owner)])
async def add_tenant_to_room(
    room_id: UUID,
    request: AddTenantRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a verified tenant to a room. Tenant must have signed up first."""
    try:
        if not request.email and not request.phone:
            raise HTTPException(status_code=400, detail="Email or phone number is required")

        # Get the room
        room = db.query(Room).filter(Room.id == room_id).first()
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")

        # Verify the room belongs to owner's property
        property_obj = db.query(Property).filter(Property.id == room.property_id).first()
        if not property_obj or property_obj.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="This room does not belong to your property")

        # Refresh stored vacancy before enforcing the rule so stale room state
        # does not block valid tenant assignments.
        current_vacancy = sync_room_vacancy(db, room.id)
        if current_vacancy <= 0:
            raise HTTPException(status_code=400, detail="No vacancy available in this room")

        # Look up verified user
        tenant_user = None
        if request.email:
            tenant_user = db.query(User).filter(User.email == request.email.strip().lower()).first()
        
        if not tenant_user and request.phone:
            digits_only = "".join(filter(str.isdigit, request.phone))
            profile = db.query(Profile).filter(
                (Profile.phone == digits_only) | 
                (Profile.phone.endswith(digits_only[-10:] if len(digits_only) >= 10 else digits_only))
            ).first()
            if profile:
                tenant_user = db.query(User).filter(User.id == profile.user_id).first()

        if not tenant_user:
            raise HTTPException(
                status_code=404,
                detail="No account found. The tenant must sign up on He&She PG first."
            )
        if not tenant_user.is_verified:
            raise HTTPException(
                status_code=400,
                detail="This account is not verified yet. The tenant must complete their signup and verify their account first."
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
        sec_deposit = request.security_deposit if request.security_deposit is not None else (room.deposit or 0)
        maint_charge = request.maintenance_charge if request.maintenance_charge is not None else (room.maintenance_charge or 0)

        booking = Booking(
            property_id=property_obj.id,
            room_id=room.id,
            customer_id=tenant_user.id,
            owner_id=current_user.id,
            start_date=start_date,
            status="active",
            amount=room.price or 0,
            security_deposit=sec_deposit,
            maintenance_charge=maint_charge,
            stay_type=room.stay_type or "monthly",
            customer_snapshot={
                "name": tenant_name,
                "email": tenant_email,
                "phone": tenant_phone,
            },
        )
        db.add(booking)
        db.flush()

        # Create wallet transactions if offline payments were recorded
        from app.services.wallet_service import WalletService
        from app.services.booking_service import BookingService
        
        owner_wallet = WalletService.get_or_create_wallet(db, current_user.id)
        
        # 1. Deposit Payment
        dep_paid = request.deposit_paid or 0
        if dep_paid > 0:
            dep_mode = request.deposit_payment_mode or "cash"
            dep_date = request.deposit_payment_date or start_date
            dep_notes = request.deposit_notes or "Initial offline deposit payment"
            
            transaction = WalletService.create_offline_transaction(
                db=db,
                wallet_id=owner_wallet.id,
                booking_id=booking.id,
                payer_id=tenant_user.id,
                receiver_id=current_user.id,
                amount=int(dep_paid * 100),
                payment_type="deposit",
                payment_method=dep_mode,
                offline_notes=dep_notes,
                description="Initial offline deposit payment recorded during tenant addition",
            )
            WalletService.complete_transaction(db, transaction.id, bypass_otp=True)

        # 2. Maintenance Payment
        maint_paid = request.maintenance_paid or 0
        if maint_paid > 0:
            maint_mode = request.maintenance_payment_mode or "cash"
            transaction = WalletService.create_offline_transaction(
                db=db,
                wallet_id=owner_wallet.id,
                booking_id=booking.id,
                payer_id=tenant_user.id,
                receiver_id=current_user.id,
                amount=int(maint_paid * 100),
                payment_type="maintenance",
                payment_method=maint_mode,
                offline_notes="Initial offline maintenance payment",
                description="Initial offline maintenance payment recorded during tenant addition",
            )
            WalletService.complete_transaction(db, transaction.id, bypass_otp=True)

        # Recalculate status and flags
        BookingService.handle_payment_completion(db, booking.id, "total")

        # Sync vacancy using centralized service
        sync_room_vacancy(db, room.id)
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

        # Sync vacancy using centralized service
        if booking.room_id:
            sync_room_vacancy(db, booking.room_id)

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
@router.get("/search", dependencies=[Depends(require_owner)])
async def owner_global_search(
    q: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Global search for owner's properties, tenants, and bookings."""
    try:
        # 1. Search Properties
        properties = db.query(Property).filter(
            Property.owner_id == current_user.id,
            Property.inactive_at.is_(None),
            ((Property.title.ilike(f"%{q}%")) | 
             (Property.locality.ilike(f"%{q}%")) | 
             (Property.city.ilike(f"%{q}%")) |
             (Property.address.ilike(f"%{q}%")))
        ).limit(10).all()

        # 2. Search Tenants (via bookings related to owner properties)
        # Search by name or phone in Profile
        tenants = db.query(Profile).join(
            Booking, Booking.customer_id == Profile.user_id
        ).filter(
            Booking.owner_id == current_user.id,
            (Profile.name.ilike(f"%{q}%")) | 
            (Profile.phone.ilike(f"%{q}%")) |
            (Profile.email.ilike(f"%{q}%"))
        ).distinct().limit(10).all()

        # 3. Search Bookings (by ID fragment)
        bookings = db.query(Booking).filter(
            Booking.owner_id == current_user.id,
            Booking.id.cast(String).ilike(f"%{q}%")
        ).limit(10).all()

        # Format results
        result = {
            "properties": [
                {
                    "id": str(p.id),
                    "title": p.title,
                    "city": p.city,
                    "locality": p.locality,
                    "status": p.status
                } for p in properties
            ],
            "tenants": [
                {
                    "id": str(t.user_id),
                    "name": t.name,
                    "phone": t.phone,
                    "email": t.email,
                } for t in tenants
            ],
            "bookings": [
                {
                    "id": str(b.id),
                    "status": b.status.value if hasattr(b.status, 'value') else str(b.status),
                    "property_id": str(b.property_id),
                    "customer_id": str(b.customer_id),
                } for b in bookings
            ]
        }

        return result
    except Exception as e:
        print(f"Error in owner search: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== System Settings (Whitelisted) ==========

@router.get("/settings/{key}", dependencies=[Depends(require_owner)])
async def get_owner_setting(
    key: str,
    db: Session = Depends(get_db),
):
    """
    Get a specific system setting value.
    Only allows specific whitelisted keys for security.
    """
    whitelist = [
        "max_properties_per_owner",
        "referral_reward",
        "cancellation_policy_hours",
        "minimum_booking_days"
    ]
    
    if key not in whitelist:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this setting is restricted"
        )
    
    setting = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    
    if not setting:
        # Return default values if setting not found in DB
        defaults = {
            "max_properties_per_owner": "10",
            "referral_reward": "500",
            "cancellation_policy_hours": "24",
            "minimum_booking_days": "30"
        }
        return {"key": key, "value": defaults.get(key, "")}
    
    return {"key": setting.key, "value": setting.value}
