"""Razorpay Payment Gateway Integration."""
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
import hashlib
import hmac

from app.database import get_db
from app.models import User, Booking, Payment, PaymentStatus, PaymentType
from app.utils.security import get_current_user
from app.config import get_settings

settings = get_settings()

router = APIRouter(prefix="/payments", tags=["Payments"])


# ========== Pydantic Schemas ==========

class CreateOrderRequest(BaseModel):
    booking_id: str
    amount: float  # Amount in INR


class CreateOrderResponse(BaseModel):
    order_id: str
    amount: int  # Amount in paise
    currency: str
    key_id: str
    booking_id: str
    user_email: str
    user_name: str


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    booking_id: str


# ========== Endpoints ==========

@router.post("/create-order", response_model=CreateOrderResponse)
async def create_payment_order(
    request: CreateOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a Razorpay order for booking payment."""
    from app.models import Profile
    
    # Verify booking exists and belongs to user
    booking = db.query(Booking).filter(Booking.id == request.booking_id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    
    if str(booking.customer_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    
    # Get user profile
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    
    try:
        import razorpay
        
        # Initialize Razorpay client
        client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
        
        # Amount in paise (INR * 100)
        amount_paise = int(request.amount * 100)
        
        # Create order
        order_data = {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": f"b_{str(request.booking_id)[-24:]}",  # Max 40 chars for Razorpay
            "notes": {
                "booking_id": request.booking_id,
                "user_id": str(current_user.id),
            }
        }
        
        razorpay_order = client.order.create(data=order_data)
        
        # Store order ID in payment record
        payment = Payment(
            booking_id=UUID(request.booking_id),
            amount=request.amount,
            payment_type=PaymentType.rent,
            status=PaymentStatus.pending,
            transaction_id=razorpay_order["id"],
        )
        db.add(payment)
        db.commit()
        
        return CreateOrderResponse(
            order_id=razorpay_order["id"],
            amount=amount_paise,
            currency="INR",
            key_id=settings.razorpay_key_id,
            booking_id=request.booking_id,
            user_email=current_user.email,
            user_name=profile.name if profile else "Customer",
        )
        
    except ImportError:
        # Razorpay not installed - only allow mock orders in debug mode
        if not settings.debug:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Payment service unavailable. Please try again later."
            )
        
        mock_order_id = f"order_mock_{datetime.now().timestamp()}"
        return CreateOrderResponse(
            order_id=mock_order_id,
            amount=int(request.amount * 100),
            currency="INR",
            key_id=settings.razorpay_key_id or "rzp_test_mock",
            booking_id=request.booking_id,
            user_email=current_user.email,
            user_name=profile.name if profile else "Customer",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create payment order: {str(e)}"
        )


@router.post("/verify")
async def verify_payment(
    request: VerifyPaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify Razorpay payment signature and update booking status."""
    
    # Find payment by order ID
    payment = db.query(Payment).filter(
        Payment.transaction_id == request.razorpay_order_id
    ).first()
    
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    
    # Verify signature
    try:
        key_secret = settings.razorpay_key_secret or ""
        
        # Create signature
        message = f"{request.razorpay_order_id}|{request.razorpay_payment_id}"
        generated_signature = hmac.new(
            key_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if generated_signature != request.razorpay_signature:
            # Only allow mock payments in debug mode
            is_mock_order = request.razorpay_order_id.startswith("order_mock_")
            if not is_mock_order or not settings.debug:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid payment signature"
                )
        
        # Update payment status
        payment.status = PaymentStatus.completed
        payment.payment_date = datetime.now(timezone.utc)
        payment.transaction_id = request.razorpay_payment_id
        
        # Update booking status
        booking = db.query(Booking).filter(Booking.id == payment.booking_id).first()
        if booking:
            booking.status = "paid"
        
        db.commit()
        
        return {
            "success": True,
            "message": "Payment verified successfully",
            "booking_id": str(payment.booking_id),
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Payment verification failed: {str(e)}"
        )


@router.get("/history")
async def get_payment_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get payment history for current user."""
    from app.models import Property, Room
    
    # Get user's bookings
    bookings = db.query(Booking).filter(Booking.customer_id == current_user.id).all()
    booking_ids = [b.id for b in bookings]
    
    # Get payments for these bookings
    payments = db.query(Payment).filter(Payment.booking_id.in_(booking_ids)).order_by(
        Payment.created_at.desc()
    ).all()
    
    result = []
    for payment in payments:
        booking = db.query(Booking).filter(Booking.id == payment.booking_id).first()
        property = db.query(Property).filter(Property.id == booking.property_id).first() if booking else None
        
        result.append({
            "id": str(payment.id),
            "amount": payment.amount,
            "status": payment.status.value if payment.status else "pending",
            "payment_type": payment.payment_type.value if payment.payment_type else "rent",
            "payment_date": payment.payment_date.isoformat() if payment.payment_date else None,
            "transaction_id": payment.transaction_id,
            "property_title": property.title if property else None,
            "created_at": payment.created_at.isoformat() if payment.created_at else None,
        })
    
    return result
