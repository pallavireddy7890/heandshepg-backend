"""Pydantic schemas for booking-related data."""
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import date, datetime
from enum import Enum


class BookingStatusEnum(str, Enum):
    requested = "requested"
    accepted = "accepted"
    paid = "paid"
    checked_in = "checked_in"
    active = "active"
    completed = "completed"
    cancelled = "cancelled"


class PaymentStatusEnum(str, Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"
    refunded = "refunded"


class PaymentTypeEnum(str, Enum):
    booking = "booking"
    monthly_rent = "monthly_rent"
    refund = "refund"
    commission = "commission"


class InvoiceStatusEnum(str, Enum):
    pending = "pending"
    paid = "paid"
    overdue = "overdue"
    cancelled = "cancelled"


# Booking Schemas
class BookingCreate(BaseModel):
    property_id: UUID
    room_id: Optional[UUID] = None
    start_date: date
    end_date: Optional[date] = None


class BookingStatusUpdate(BaseModel):
    status: BookingStatusEnum


class BookingCancelRequest(BaseModel):
    cancel_reason: Optional[str] = None


class BookingResponse(BaseModel):
    id: UUID
    property_id: UUID
    room_id: Optional[UUID]
    customer_id: UUID
    owner_id: UUID
    start_date: date
    end_date: Optional[date]
    status: str
    amount: int
    security_deposit: int
    cancelled_at: Optional[datetime]
    cancel_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BookingDetailResponse(BookingResponse):
    property: Optional[dict] = None
    room: Optional[dict] = None


# Payment Schemas
class PaymentCreate(BaseModel):
    booking_id: Optional[UUID] = None
    amount: int = Field(..., ge=0)
    type: PaymentTypeEnum


class PaymentResponse(BaseModel):
    id: UUID
    booking_id: Optional[UUID]
    user_id: UUID
    amount: int
    currency: str
    razorpay_payment_id: Optional[str]
    razorpay_order_id: Optional[str]
    status: str
    type: str
    commission_amount: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Invoice Schemas
class InvoiceResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    booking_id: UUID
    month: str
    amount: int
    due_date: date
    status: str
    paid_at: Optional[datetime]
    payment_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
