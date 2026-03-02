"""Wallet router for payment and transaction management."""
from typing import Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import User, Booking, Profile, Wallet, WalletTransaction, TransactionType, TransactionStatus, Property, Room
from app.utils.security import get_current_user
from app.services.wallet_service import WalletService
from app.config import get_settings
from app.utils.notifications import notify_payment_received, notify_payment_verified

settings = get_settings()

router = APIRouter(prefix="/wallet", tags=["Wallet"])


# ========== Pydantic Schemas ==========

class WalletBalanceResponse(BaseModel):
    balance: int
    pending_balance: int
    available_balance: int
    currency: str
    balance_inr: float


class InitiatePaymentRequest(BaseModel):
    booking_id: str
    amount: float  # Amount in INR
    payment_type: Optional[str] = "total"  # total, rent, deposit


class InitiatePaymentResponse(BaseModel):
    transaction_id: str
    razorpay_order_id: str
    amount: int
    currency: str
    key_id: str
    message: str
    
    
class InitiateOfflinePaymentRequest(BaseModel):
    booking_id: str
    amount: float  # Amount in INR
    payment_type: Optional[str] = "total"  # total, rent, deposit
    offline_notes: Optional[str] = None


class VerifyRazorpayRequest(BaseModel):
    transaction_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class VerifyOTPRequest(BaseModel):
    transaction_id: str
    otp: str


class ResendOTPRequest(BaseModel):
    transaction_id: str


class WithdrawRequest(BaseModel):
    amount: float  # Amount in INR


# ========== Endpoints ==========

@router.get("/balance", response_model=WalletBalanceResponse)
async def get_wallet_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's wallet balance."""
    balance = WalletService.get_balance(db, current_user.id)
    return WalletBalanceResponse(**balance)


@router.get("/transactions")
async def get_transaction_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
):
    """Get transaction history for current user."""
    return WalletService.get_transactions(db, current_user.id, limit)


@router.get("/my-pending-payments")
async def get_my_pending_payments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get customer's pending payments that need OTP verification by owner."""
    # Get transactions where current user is the payer and OTP not verified
    transactions = db.query(WalletTransaction).filter(
        WalletTransaction.payer_id == current_user.id,
        WalletTransaction.otp_verified == False
    ).order_by(WalletTransaction.created_at.desc()).all()
    
    result = []
    for txn in transactions:
        # Get owner info
        owner_profile = db.query(Profile).filter(Profile.user_id == txn.receiver_id).first()
        
        # Get property info from booking
        property_title = None
        if txn.booking_id:
            booking = db.query(Booking).filter(Booking.id == txn.booking_id).first()
            if booking:
                from app.models import Property
                prop = db.query(Property).filter(Property.id == booking.property_id).first()
                if prop:
                    property_title = prop.title
        
        result.append({
            "transaction_id": str(txn.id),
            "amount": txn.amount / 100,  # In INR
            "owner_name": owner_profile.name if owner_profile else "Property Owner",
            "property_title": property_title,
            "status": txn.status.value if hasattr(txn.status, 'value') else txn.status,
            "payment_method": txn.payment_method,
            "offline_notes": txn.offline_notes,
            "created_at": txn.created_at.isoformat() if txn.created_at else None,
        })
    
    return result


@router.get("/owner-pending-payments")
async def get_owner_pending_payments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get owner's pending payments (offline or online awaiting OTP)."""
    # Get transactions where current user is the receiver and not completed
    transactions = db.query(WalletTransaction).filter(
        WalletTransaction.receiver_id == current_user.id,
        WalletTransaction.status != TransactionStatus.completed,
        WalletTransaction.status != TransactionStatus.failed,
        WalletTransaction.status != TransactionStatus.rejected
    ).order_by(WalletTransaction.created_at.desc()).all()
    
    result = []
    for txn in transactions:
        # Get payer (customer) info
        payer_profile = db.query(Profile).filter(Profile.user_id == txn.payer_id).first()
        
        # Get property info from booking
        property_title = None
        if txn.booking_id:
            booking = db.query(Booking).filter(Booking.id == txn.booking_id).first()
            if booking:
                from app.models import Property
                prop = db.query(Property).filter(Property.id == booking.property_id).first()
                if prop:
                    property_title = prop.title
        
        result.append({
            "transaction_id": str(txn.id),
            "amount": txn.amount / 100,  # In INR
            "customer_name": payer_profile.name if payer_profile else "Customer",
            "property_title": property_title,
            "status": txn.status.value if hasattr(txn.status, 'value') else txn.status,
            "payment_method": txn.payment_method,
            "offline_notes": txn.offline_notes,
            "created_at": txn.created_at.isoformat() if txn.created_at else None,
        })
    
    return result


@router.post("/initiate-payment", response_model=InitiatePaymentResponse)
async def initiate_wallet_payment(
    request: InitiatePaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Initiate a payment for a booking.
    1. Creates Razorpay order
    2. Creates wallet transaction in pending state
    Returns order details for Razorpay checkout.
    """
    import hashlib
    import hmac
    
    # Get booking
    booking = db.query(Booking).filter(Booking.id == request.booking_id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    
    # Verify customer is making the payment
    if str(booking.customer_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to pay for this booking")
    
    # Booking must be accepted before payment
    if booking.status not in ["accepted", "requested"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Booking status must be 'accepted' to make payment. Current: {booking.status}")
    
    # Check for vacancy before allowing payment initiation
    if booking.room_id:
        room = db.query(Room).filter(Room.id == booking.room_id).first()
        if room and (not room.is_available or (room.vacancy_count is not None and room.vacancy_count <= 0)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This room is no longer available"
            )
    
    # Get owner's wallet (create if not exists)
    owner_wallet = WalletService.get_or_create_wallet(db, booking.owner_id)
    
    # Amount in paise
    amount_paise = int(request.amount * 100)
    
    try:
        import razorpay
        
        # Initialize Razorpay client
        client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
        
        # Create order
        order_data = {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": f"wb_{str(request.booking_id)[-24:]}",  # Max 40 chars for Razorpay
            "notes": {
                "booking_id": request.booking_id,
                "customer_id": str(current_user.id),
                "owner_id": str(booking.owner_id),
            }
        }
        
        razorpay_order = client.order.create(data=order_data)
        razorpay_order_id = razorpay_order["id"]
        
    except ImportError:
        # Mock order for development
        razorpay_order_id = f"order_mock_{datetime.now().timestamp()}"
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create Razorpay order: {str(e)}"
        )
    
    # Create wallet transaction
    transaction = WalletService.create_transaction(
        db=db,
        wallet_id=owner_wallet.id,
        booking_id=UUID(request.booking_id),
        payer_id=current_user.id,
        receiver_id=booking.owner_id,
        amount=amount_paise,
        transaction_type=TransactionType.credit,
        razorpay_order_id=razorpay_order_id,
        description=f"Payment for {request.payment_type} - booking {request.booking_id}",
    )
    
    # Store payment type if column exists
    if hasattr(transaction, 'payment_type'):
        transaction.payment_type = request.payment_type
        db.commit()
    
    return InitiatePaymentResponse(
        transaction_id=str(transaction.id),
        razorpay_order_id=razorpay_order_id,
        amount=amount_paise,
        currency="INR",
        key_id=settings.razorpay_key_id or "rzp_test_mock",
        message="Payment initiated. Complete payment via Razorpay."
    )


@router.post("/initiate-offline-payment")
async def initiate_offline_wallet_payment(
    request: InitiateOfflinePaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Initiate an offline payment for a booking.
    Creates a wallet transaction in pending state with payment_method='offline'.
    """
    # Get booking
    booking = db.query(Booking).filter(Booking.id == request.booking_id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    
    # Verify customer is making the payment
    if str(booking.customer_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to pay for this booking")
    
    # Booking must be accepted before payment
    if booking.status not in ["accepted", "requested"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking must be accepted to make payment")
    
    # Get owner's wallet
    owner_wallet = WalletService.get_or_create_wallet(db, booking.owner_id)
    
    # Amount in paise
    amount_paise = int(request.amount * 100)
    
    # Create offline transaction
    transaction = WalletService.create_offline_transaction(
        db=db,
        wallet_id=owner_wallet.id,
        booking_id=UUID(request.booking_id),
        payer_id=current_user.id,
        receiver_id=booking.owner_id,
        amount=amount_paise,
        payment_type=request.payment_type,
        offline_notes=request.offline_notes,
        description=f"Offline payment ({request.payment_type}) for booking {request.booking_id}",
    )
    
    return {
        "success": True,
        "message": "Offline payment request submitted. The property owner will verify it.",
        "transaction_id": str(transaction.id),
        "amount": request.amount,
        "status": "pending_verification"
    }


@router.post("/verify-razorpay")
async def verify_razorpay_payment(
    request: VerifyRazorpayRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Verify Razorpay payment and generate OTP for owner verification.
    Called after user completes Razorpay payment.
    The OTP is displayed on the website for the customer to share with the owner.
    """
    import hashlib
    import hmac
    
    # Get transaction
    transaction = db.query(WalletTransaction).filter(
        WalletTransaction.id == request.transaction_id
    ).first()
    
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    
    # Verify transaction belongs to user
    if str(transaction.payer_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    
    # Verify Razorpay signature
    if not request.razorpay_order_id.startswith("order_mock_"):
        key_secret = settings.razorpay_key_secret or ""
        message = f"{request.razorpay_order_id}|{request.razorpay_payment_id}"
        generated_signature = hmac.new(
            key_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if generated_signature != request.razorpay_signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payment signature"
            )
    
    # Update transaction with payment ID
    transaction.razorpay_payment_id = request.razorpay_payment_id
    db.commit()
    
    # Get profile info
    customer_profile = db.query(Profile).filter(Profile.user_id == transaction.payer_id).first()
    owner_profile = db.query(Profile).filter(Profile.user_id == transaction.receiver_id).first()
    
    # Generate OTP for owner verification - NO SMS required
    # OTP will be displayed on website for customer to share with owner
    success, otp_code = WalletService.create_otp_for_display(
        db=db,
        transaction_id=transaction.id,
        user_id=transaction.receiver_id,  # OTP is for owner to verify
        otp_type="owner"
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate OTP"
        )
    
    # Get owner name for display
    owner_name = owner_profile.name if owner_profile else "Property Owner"
    customer_name = customer_profile.name if customer_profile else "Customer"
    
    # Notify owner about incoming payment (optional - won't fail if notification fails)
    try:
        await notify_payment_received(db, transaction.receiver_id, transaction.amount / 100, customer_name)
    except Exception:
        pass  # Don't fail payment if notification fails
    
    return {
        "success": True,
        "message": "Payment successful! Share the OTP below with the property owner to complete the transaction.",
        "transaction_id": str(transaction.id),
        "requires_owner_verification": True,
        "otp": otp_code,  # OTP displayed on website for customer to share with owner
        "owner_name": owner_name,
        "amount": transaction.amount / 100,  # Amount in INR
        "expires_in_minutes": WalletService.OTP_EXPIRY_MINUTES
    }


@router.post("/verify-otp")
async def verify_transaction_otp(
    request: VerifyOTPRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Verify OTP for the transaction.
    Owner must verify OTP to complete the transaction and receive funds.
    """
    # Get transaction
    transaction = db.query(WalletTransaction).filter(
        WalletTransaction.id == request.transaction_id
    ).first()
    
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    
    # Verify current user is the owner (receiver)
    if str(transaction.receiver_id) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the recipient (property owner) can verify this OTP"
        )
    
    # Verify OTP
    success, message = WalletService.verify_otp(
        db=db,
        transaction_id=transaction.id,
        user_id=current_user.id,
        otp_code=request.otp
    )
    
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    
    # Complete the transaction (credit to owner's wallet)
    complete_success, complete_message = WalletService.complete_transaction(db, transaction.id)
    
    if not complete_success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=complete_message)
    
    # Update booking status
    if transaction.booking_id:
        booking = db.query(Booking).filter(Booking.id == transaction.booking_id).first()
        if booking:
            # Update specific flags based on payment_type
            p_type = transaction.payment_type
            if p_type == 'rent':
                booking.rent_paid = True
            elif p_type == 'deposit':
                booking.deposit_paid = True
            elif p_type == 'maintenance':
                booking.maintenance_paid = True
            elif p_type == 'total':
                booking.rent_paid = True
                booking.deposit_paid = True
                booking.maintenance_paid = True
            
            # Update last payment date for grace period logic
            if p_type in ['rent', 'total']:
                booking.last_payment_date = func.now()
            
            # Update overall status
            # If both rent and deposit are paid, it's fully paid
            if booking.rent_paid and booking.deposit_paid:
                booking.status = "paid"
            # If at least rent is paid, consider them "checked_in"
            elif booking.rent_paid:
                booking.status = "checked_in"
            
            # AUTOMATIC VACANCY DEDUCTION
            # If the booking is now "paid" or "checked_in", and it has a room assigned,
            # we should decrease the vacancy count by 1.
            if booking.status in ["paid", "checked_in"] and booking.room_id:
                room = db.query(Room).filter(Room.id == booking.room_id).first()
                if room and room.vacancy_count and room.vacancy_count > 0:
                    room.vacancy_count -= 1
                    # If vacancy reaches 0, mark as not available
                    if room.vacancy_count == 0:
                        room.is_available = False
                        
                    # Log vacancy update
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(f"Vacancy deducted for room {room.id}. New count: {room.vacancy_count}")
            
            db.commit()
    
    # Get updated balance
    balance = WalletService.get_balance(db, current_user.id)
    
    # Notify customer about payment verification
    try:
        # Get property title for notification
        property_title = "Property"
        customer_name = "Customer"
        owner_name = "Owner"
        if transaction.booking_id:
            booking = db.query(Booking).filter(Booking.id == transaction.booking_id).first()
            if booking:
                prop = db.query(Property).filter(Property.id == booking.property_id).first()
                if prop:
                    property_title = prop.title
                # Get customer name
                from app.models import Profile
                customer_profile = db.query(Profile).filter(Profile.user_id == transaction.payer_id).first()
                if customer_profile:
                    customer_name = customer_profile.name
                # Get owner name
                owner_profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
                if owner_profile:
                    owner_name = owner_profile.name
        
        await notify_payment_verified(db, transaction.payer_id, transaction.amount / 100, property_title)
        
        # Notify admins about completed payment
        from app.utils.notifications import notify_admins_payment_completed
        await notify_admins_payment_completed(db, customer_name, owner_name, transaction.amount / 100, property_title)
    except Exception:
        pass  # Don't fail if notification fails
    
    return {
        "success": True,
        "message": "Transaction verified and completed. Funds credited to your wallet.",
        "transaction_id": str(transaction.id),
        "amount_credited": transaction.amount / 100,
        "new_balance": balance["balance_inr"],
    }


@router.post("/verify-offline")
async def verify_offline_transaction(
    transaction_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Directly verify an offline transaction (Owner only).
    Bypasses OTP as the owner is manually confirming they received the funds.
    """
    # Get transaction
    transaction = db.query(WalletTransaction).filter(
        WalletTransaction.id == transaction_id,
        WalletTransaction.payment_method == 'offline'
    ).first()
    
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offline transaction not found")
    
    # Verify current user is the owner (receiver) or admin
    if str(transaction.receiver_id) != str(current_user.id) and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the property owner or admin can verify offline payments"
        )
    
    # Complete the transaction (bypass OTP)
    complete_success, complete_message = WalletService.complete_transaction(db, transaction.id, bypass_otp=True)
    
    if not complete_success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=complete_message)
    
    # Update booking status (Logic duplicated from verify-otp, ideally should be in a shared service method)
    if transaction.booking_id:
        booking = db.query(Booking).filter(Booking.id == transaction.booking_id).first()
        if booking:
            p_type = transaction.payment_type
            if p_type == 'rent':
                booking.rent_paid = True
            elif p_type == 'deposit':
                booking.deposit_paid = True
            elif p_type == 'maintenance':
                booking.maintenance_paid = True
            elif p_type == 'total':
                booking.rent_paid = True
                booking.deposit_paid = True
                booking.maintenance_paid = True
            
            # Update last payment date for grace period logic
            if p_type in ['rent', 'total']:
                booking.last_payment_date = func.now()
            
            if booking.rent_paid and booking.deposit_paid:
                booking.status = "paid"
            elif booking.rent_paid:
                booking.status = "checked_in"
            
            # Vacancy deduction
            if booking.status in ["paid", "checked_in"] and booking.room_id:
                room = db.query(Room).filter(Room.id == booking.room_id).first()
                if room and room.vacancy_count and room.vacancy_count > 0:
                    room.vacancy_count -= 1
                    if room.vacancy_count == 0:
                        room.is_available = False
            
            db.commit()
    
    return {
        "success": True,
        "message": "Offline payment verified successfully",
        "transaction_id": str(transaction.id),
    }


@router.post("/resend-otp")
async def resend_transaction_otp(
    request: ResendOTPRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Resend OTP for a transaction - generates new OTP for customer to share with owner."""
    # Get transaction
    transaction = db.query(WalletTransaction).filter(
        WalletTransaction.id == request.transaction_id
    ).first()
    
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    
    # Only the payer (customer) can regenerate OTP
    if str(transaction.payer_id) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Only the customer who made the payment can regenerate OTP"
        )
    
    # Check if transaction is pending verification
    status_value = transaction.status.value if hasattr(transaction.status, 'value') else transaction.status
    if status_value == 'completed':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Transaction already completed"
        )
    
    # Get owner profile
    owner_profile = db.query(Profile).filter(Profile.user_id == transaction.receiver_id).first()
    
    # Create new OTP for owner verification (no SMS needed - displayed on website)
    success, otp_code = WalletService.create_otp_for_display(
        db=db,
        transaction_id=transaction.id,
        user_id=transaction.receiver_id,  # OTP is for owner to verify
        otp_type="owner"
    )
    
    # Get owner name for display
    owner_name = owner_profile.name if owner_profile else "Property Owner"
    
    return {
        "success": success,
        "message": "New OTP generated! Share this with the property owner.",
        "otp": otp_code,  # OTP displayed on website for customer to share
        "owner_name": owner_name,
        "amount": transaction.amount / 100,
        "expires_in_minutes": WalletService.OTP_EXPIRY_MINUTES
    }


@router.post("/withdraw")
async def request_withdrawal(
    request: WithdrawRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Request a withdrawal from owner's wallet."""
    # Amount in paise
    amount_paise = int(request.amount * 100)
    
    if amount_paise <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid amount")
        
    success, message, transaction = WalletService.create_withdrawal_request(
        db=db,
        user_id=current_user.id,
        amount=amount_paise
    )
    
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
        
    return {
        "success": True,
        "message": message,
        "transaction_id": str(transaction.id),
        "amount": request.amount
    }
