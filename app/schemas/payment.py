"""Pydantic schemas for payment operations."""
from pydantic import BaseModel
from typing import Optional


class CreateOrderRequest(BaseModel):
    """Request to create a Razorpay order."""
    booking_id: str
    amount: float  # Amount in INR


class CreateOrderResponse(BaseModel):
    """Response after creating a Razorpay order."""
    order_id: str
    amount: int  # Amount in paise
    currency: str
    key_id: str
    booking_id: str
    user_email: str
    user_name: str


class VerifyPaymentRequest(BaseModel):
    """Request to verify a Razorpay payment."""
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    booking_id: str


class PaymentHistoryItem(BaseModel):
    """Payment history item response."""
    id: str
    amount: float
    status: str
    payment_type: str
    payment_date: Optional[str] = None
    transaction_id: Optional[str] = None
    property_title: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True
