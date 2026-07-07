
"""Wallet router for payment and transaction management."""
from typing import Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import User, Booking, Profile, Wallet, WalletTransaction, TransactionType, TransactionStatus, Property, Room
from app.utils.security import get_current_user, get_user_role
from app.services.wallet_service import WalletService, parse_transaction_metadata
from app.services.booking_service import BookingService
from app.services.vacancy import sync_room_vacancy
from app.config import get_settings
from app.utils.notifications import notify_payment_received, notify_payment_verified

settings = get_settings()

router = APIRouter(prefix="/wallet", tags=["Wallet"])


# ========== Pydantic Schemas ==========

class WalletBalanceResponse(BaseModel):
    balance: int
    pending_balance: int
    available_balance: int
    online_balance: int
    offline_balance: int
    pending_online: int
    pending_offline: int
    pending_withdrawals: int
    currency: str
    balance_inr: float


class InitiatePaymentRequest(BaseModel):
    booking_id: str
    amount: float  # Amount in INR
    payment_type: Optional[str] = "total"  # total, rent, deposit
    use_wallet_balance: Optional[bool] = False


class InitiatePaymentResponse(BaseModel):
    transaction_id: str
    razorpay_order_id: str
    amount: int
    currency: str
    key_id: str
    message: str
    otp: Optional[str] = None
    owner_name: Optional[str] = None
    
    
class InitiateOfflinePaymentRequest(BaseModel):
    booking_id: str
    amount: float  # Amount in INR
    payment_type: Optional[str] = "total"  # total, rent, deposit
    payment_method: Optional[str] = "cash"  # cash, upi, bank_transfer, other
    offline_notes: Optional[str] = None
    offline_reference: Optional[str] = None


class CollectOfflinePaymentRequest(BaseModel):
    booking_id: str
    amount: float  # Amount in INR
    payment_type: str = "total"  # total, rent, deposit
    payment_method: str = "cash"  # cash, upi, bank_transfer, other
    offline_notes: Optional[str] = None
    offline_reference: Optional[str] = None
    force_payment: Optional[bool] = False  # Set to True to bypass overlap checks


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
    property_id: Optional[UUID] = None,
):
    """Get current user's wallet balance."""
    balance = WalletService.get_balance(db, current_user.id, property_id)
    return WalletBalanceResponse(**balance)


@router.get("/transactions")
async def get_transaction_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
    property_id: Optional[UUID] = None,
):
    """Get transaction history for current user."""
    return WalletService.get_transactions(db, current_user.id, limit, property_id)


@router.get("/my-pending-payments")
async def get_my_pending_payments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get customer's pending payments that need OTP verification by owner."""
    from sqlalchemy import or_, and_
    # Get transactions where current user is the payer, OTP not verified,
    # and either it's online and paid/ready (otp_sent) or it's offline and pending verification
    transactions = db.query(WalletTransaction).filter(
        WalletTransaction.payer_id == current_user.id,
        WalletTransaction.otp_verified == False,
        or_(
            and_(WalletTransaction.payment_method == 'online', WalletTransaction.status == TransactionStatus.otp_sent),
            and_(WalletTransaction.payment_method != 'online', WalletTransaction.status == TransactionStatus.pending)
        )
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
        
        # Parse metadata
        wallet_contribution, total_amount, clean_desc = parse_transaction_metadata(txn.description)
        
        result.append({
            "id": str(txn.id),
            "transaction_id": str(txn.id),
            "booking_id": str(txn.booking_id) if txn.booking_id else None,
            "payment_type": txn.payment_type if hasattr(txn, 'payment_type') else 'total',
            "amount": txn.amount / 100,  # In INR
            "total_amount": total_amount / 100 if total_amount > 0 else txn.amount / 100,
            "wallet_contribution": wallet_contribution / 100 if wallet_contribution > 0 else 0.0,
            "owner_name": owner_profile.name if owner_profile else "Property Owner",
            "property_title": property_title,
            "status": txn.status.value if hasattr(txn.status, 'value') else txn.status,
            "payment_method": txn.payment_method,
            "offline_notes": txn.offline_notes,
            "offline_reference": txn.offline_reference,
            "created_at": txn.created_at.isoformat() if txn.created_at else None,
            "description": clean_desc,
        })
    
    return result


@router.get("/owner-pending-payments")
async def get_owner_pending_payments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get owner's pending payments (offline or online awaiting OTP)."""
    from sqlalchemy import or_, and_
    # Get transactions where current user is the receiver, and either it's online and paid/ready (otp_sent)
    # or it's offline and pending verification
    transactions = db.query(WalletTransaction).filter(
        WalletTransaction.receiver_id == current_user.id,
        or_(
            and_(WalletTransaction.payment_method == 'online', WalletTransaction.status == TransactionStatus.otp_sent),
            and_(WalletTransaction.payment_method != 'online', WalletTransaction.status == TransactionStatus.pending)
        )
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
        
        # Parse metadata
        wallet_contribution, total_amount, clean_desc = parse_transaction_metadata(txn.description)
        
        result.append({
            "id": str(txn.id),
            "transaction_id": str(txn.id),
            "amount": txn.amount / 100,  # In INR
            "total_amount": total_amount / 100 if total_amount > 0 else txn.amount / 100,
            "wallet_contribution": wallet_contribution / 100 if wallet_contribution > 0 else 0.0,
            "customer_name": payer_profile.name if payer_profile else "Customer",
            "property_title": property_title,
            "status": txn.status.value if hasattr(txn.status, 'value') else txn.status,
            "payment_method": txn.payment_method,
            "offline_notes": txn.offline_notes,
            "offline_reference": txn.offline_reference,
            "created_at": txn.created_at.isoformat() if txn.created_at else None,
            "description": clean_desc,
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
    
    # Check for existing pending transaction of the same type for this booking
    # This prevents 'why this got three' confusion by blocking extra starts
    existing_txn = db.query(WalletTransaction).filter(
        WalletTransaction.booking_id == UUID(request.booking_id),
        WalletTransaction.payment_type == request.payment_type,
        WalletTransaction.status.in_([TransactionStatus.pending, TransactionStatus.otp_sent])
    ).first()
    if existing_txn:
        # If it's a pending online transaction (initiated but not paid), we can delete it and retry
        if existing_txn.payment_method == 'online' and existing_txn.status == TransactionStatus.pending:
            db.delete(existing_txn)
            db.commit()
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"You already have a pending {request.payment_type} payment for this booking. Please verify or cancel the existing one first."
            )
    
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
    requested_amount_paise = int(request.amount * 100)
    
    # Handle wallet balance deduction
    wallet_contribution_paise = 0
    if request.use_wallet_balance:
        user_wallet = WalletService.get_or_create_wallet(db, current_user.id)
        balance_info = WalletService.get_balance(db, current_user.id)
        available_paise = int(balance_info["available_balance"])
        
        if available_paise > 0:
            wallet_contribution_paise = min(available_paise, requested_amount_paise)
            
            # Create a debit transaction for the user
            user_debit = WalletTransaction(
                wallet_id=user_wallet.id,
                payer_id=current_user.id,
                receiver_id=booking.owner_id,
                booking_id=UUID(request.booking_id),
                amount=wallet_contribution_paise,
                transaction_type=TransactionType.debit,
                status=TransactionStatus.completed,
                description=f"Used referral/wallet balance for {request.payment_type} - booking {request.booking_id}"
            )
            db.add(user_debit)
            
            # Deduct from user's balance
            user_wallet.balance -= wallet_contribution_paise
            db.flush() # Ensure debit is recorded before credit
    
    remaining_amount_paise = requested_amount_paise - wallet_contribution_paise
    
    razorpay_order_id = None
    if remaining_amount_paise > 0:
        try:
            import razorpay
            
            # Initialize Razorpay client
            client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
            
            # Create order
            order_data = {
                "amount": remaining_amount_paise,
                "currency": "INR",
                "receipt": f"wb_{str(request.booking_id)[-24:]}",
                "notes": {
                    "booking_id": request.booking_id,
                    "customer_id": str(current_user.id),
                    "owner_id": str(booking.owner_id),
                    "wallet_contribution": str(wallet_contribution_paise)
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
    
    # Create wallet transaction for the owner (credit)
    # This represents the REMAINING online amount the owner expects to verify with OTP
    description = f"Payment for {request.payment_type} - booking {request.booking_id}"
    description += f" [wallet_contribution:{wallet_contribution_paise}][total_amount:{requested_amount_paise}]"
        
    transaction = WalletService.create_transaction(
        db=db,
        wallet_id=owner_wallet.id,
        booking_id=UUID(request.booking_id),
        payer_id=current_user.id,
        receiver_id=booking.owner_id,
        amount=remaining_amount_paise, # Online payable amount
        transaction_type=TransactionType.credit,
        razorpay_order_id=razorpay_order_id or "paid_via_wallet",
        description=description,
    )
    
    # Store payment type if column exists
    if hasattr(transaction, 'payment_type'):
        transaction.payment_type = request.payment_type
        db.commit()
    
    # If fully paid via wallet (remaining_amount_paise == 0), generate OTP immediately
    otp_code = None
    owner_name = None
    if remaining_amount_paise == 0:
        transaction.status = TransactionStatus.otp_sent
        db.commit()
        
        # Generate OTP
        success, otp_code = WalletService.create_otp_for_display(
            db=db,
            transaction_id=transaction.id,
            user_id=booking.owner_id,
            otp_type="owner"
        )
        owner_profile = db.query(Profile).filter(Profile.user_id == booking.owner_id).first()
        owner_name = owner_profile.name if owner_profile else "Property Owner"
    
    return InitiatePaymentResponse(
        transaction_id=str(transaction.id),
        razorpay_order_id=razorpay_order_id or "paid_via_wallet",
        amount=remaining_amount_paise,
        currency="INR",
        key_id=settings.razorpay_key_id or "rzp_test_mock",
        message="Payment initiated. " + ("Complete via Razorpay." if remaining_amount_paise > 0 else "Verify with owner via OTP."),
        otp=otp_code,
        owner_name=owner_name
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
    
    # Check for existing pending transaction of the same type for this booking
    existing_txn = db.query(WalletTransaction).filter(
        WalletTransaction.booking_id == UUID(request.booking_id),
        WalletTransaction.payment_type == request.payment_type,
        WalletTransaction.status.in_([TransactionStatus.pending, TransactionStatus.otp_sent])
    ).first()
    if existing_txn:
        # If it's a pending online transaction (initiated but not paid), we can delete it so they can pay offline
        if existing_txn.payment_method == 'online' and existing_txn.status == TransactionStatus.pending:
            db.delete(existing_txn)
            db.commit()
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"You already have a pending {request.payment_type} payment for this booking. Please verify or cancel the existing one first."
            )
    
    # Get owner's wallet
    owner_wallet = WalletService.get_or_create_wallet(db, booking.owner_id)
    
    # Amount in paise
    if request.amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be greater than zero")
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
        payment_method=request.payment_method,
        offline_notes=request.offline_notes,
        offline_reference=request.offline_reference,
        description=f"Offline payment ({request.payment_type}) via {request.payment_method} for booking {request.booking_id}",
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
        from app.models import Booking, Property
        property_title = None
        if transaction.booking_id:
            booking = db.query(Booking).filter(Booking.id == transaction.booking_id).first()
            if booking:
                prop = db.query(Property).filter(Property.id == booking.property_id).first()
                if prop:
                    property_title = prop.title
        await notify_payment_received(
            db=db,
            owner_id=transaction.receiver_id,
            amount=transaction.amount / 100,
            customer_name=customer_name,
            property_title=property_title,
            transaction_id=transaction.id
        )
    except Exception as e:
        import logging
        logging.warning(f"Failed to send notify_payment_received: {e}")
    
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
    
    # Safety Check: For online payments, ensure the transaction has been paid/verified (status is otp_sent)
    if transaction.payment_method == 'online' and transaction.status != TransactionStatus.otp_sent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot verify OTP for an unpaid online transaction"
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
    
    # Update booking status via centralized service
    if transaction.booking_id:
        BookingService.handle_payment_completion(
            db=db, 
            booking_id=transaction.booking_id, 
            payment_type=transaction.payment_type
        )
    
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
        
        await notify_payment_verified(db, transaction.payer_id, transaction.amount / 100, property_title, transaction_id=transaction.id)
        
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
    user_role = get_user_role(current_user, db)
    if str(transaction.receiver_id) != str(current_user.id) and user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the property owner or admin can verify offline payments"
        )
    
    # Complete the transaction (bypass OTP)
    complete_success, complete_message = WalletService.complete_transaction(db, transaction.id, bypass_otp=True)
    
    if not complete_success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=complete_message)
    
    # Update booking status via centralized service
    if transaction.booking_id:
        BookingService.handle_payment_completion(
            db=db, 
            booking_id=transaction.booking_id, 
            payment_type=transaction.payment_type
        )
    
    return {
        "success": True,
        "message": "Offline payment verified successfully",
        "transaction_id": str(transaction.id),
    }


@router.post("/reject-offline")
async def reject_offline_transaction(
    transaction_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Reject an offline transaction (Owner only).
    """
    # Get transaction
    transaction = db.query(WalletTransaction).filter(
        WalletTransaction.id == transaction_id,
        WalletTransaction.status != TransactionStatus.completed
    ).first()
    
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending transaction not found")
    
    # Verify current user is the owner (receiver) or admin
    user_role = get_user_role(current_user, db)
    if str(transaction.receiver_id) != str(current_user.id) and user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the property owner or admin can reject offline payments"
        )
    
    # Update transaction status
    transaction.status = TransactionStatus.rejected
    db.commit()
    
    return {
        "success": True,
        "message": "Offline payment rejected successfully",
        "transaction_id": str(transaction.id),
    }



@router.post("/collect-offline-payment")
async def collect_offline_payment(
    request: CollectOfflinePaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Directly record an offline payment (Owner/Admin only).
    Creates and completes a transaction in one step.
    """
    from sqlalchemy import func
    
    # Get booking
    booking = db.query(Booking).filter(Booking.id == request.booking_id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
        
    # Verify authorization (Owner or Admin)
    user_role = get_user_role(current_user, db)
    if user_role != "admin" and str(booking.owner_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to collect payment for this booking")
        
    # Get owner's wallet
    owner_wallet = WalletService.get_or_create_wallet(db, booking.owner_id)
    
    p_type = request.payment_type
    if request.amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be greater than zero")

    from datetime import date, datetime
    from app.models.wallet import WalletTransaction, TransactionStatus

    # Calculate start and end of current cycle for recurring charges (rent, maintenance)
    period_start, period_end = WalletService.get_billing_period(booking.start_date, date.today())
    start_dt = datetime.combine(period_start, datetime.min.time())
    end_dt = datetime.combine(period_end, datetime.max.time())

    # Get cumulative payments for the current cycle (rent, maintenance, total)
    cycle_payments = db.query(WalletTransaction).filter(
        WalletTransaction.booking_id == booking.id,
        WalletTransaction.status == TransactionStatus.completed,
        WalletTransaction.payment_type.in_(['rent', 'total', 'maintenance']),
        WalletTransaction.created_at >= start_dt,
        WalletTransaction.created_at <= end_dt
    ).all()

    rent_paid = 0
    maint_paid = 0
    for p in cycle_payments:
        if p.payment_type == 'rent':
            rent_paid += p.amount / 100
        elif p.payment_type == 'total':
            rent_paid += booking.amount
            maint_paid += (booking.maintenance_charge or 0)
        elif p.payment_type == 'maintenance':
            maint_paid += p.amount / 100

    # Get lifetime payments for security deposit (deposit, total)
    deposit_payments = db.query(WalletTransaction).filter(
        WalletTransaction.booking_id == booking.id,
        WalletTransaction.status == TransactionStatus.completed,
        WalletTransaction.payment_type.in_(['deposit', 'total'])
    ).all()

    deposit_paid = 0
    for p in deposit_payments:
        if p.payment_type == 'deposit':
            deposit_paid += p.amount / 100
        elif p.payment_type == 'total':
            deposit_paid += (booking.security_deposit or 0)

    # Validate based on payment type
    if p_type == 'rent':
        from app.routers.owner import calculate_month_rent_stats
        stats = calculate_month_rent_stats(db, booking, date.today().month, date.today().year)
        remaining_rent = max(0.0, float(stats["cumulative_due"]) - stats["rent_paid"])
        # If rent is already fully paid, and they don't force it, throw overlap warning
        if remaining_rent <= 0.01 and not request.force_payment:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Rent is already fully paid for all cycles up to now ({period_start.strftime('%d %b')} - {period_end.strftime('%d %b')}). Do you want to record an extra payment?"
            )
        if request.amount > remaining_rent + 0.01 and not request.force_payment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Amount exceeds remaining rent of \u20b9{remaining_rent:.2f}. (Enable 'Force Payment' to bypass)"
            )
    elif p_type == 'deposit':
        remaining_deposit = max(0.0, float(booking.security_deposit or 0) - deposit_paid)
        if remaining_deposit <= 0.01 and not request.force_payment:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Security deposit has already been fully paid."
            )
        if request.amount > remaining_deposit + 0.01 and not request.force_payment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Amount exceeds remaining security deposit of \u20b9{remaining_deposit:.2f}. (Enable 'Force Payment' to bypass)"
            )
    elif p_type == 'maintenance':
        remaining_maint = max(0.0, float(booking.maintenance_charge or 0) - maint_paid)
        if remaining_maint <= 0.01 and not request.force_payment:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Maintenance charge is already fully paid for the current cycle."
            )
        if request.amount > remaining_maint + 0.01 and not request.force_payment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Amount exceeds remaining maintenance charge of \u20b9{remaining_maint:.2f}. (Enable 'Force Payment' to bypass)"
            )
    elif p_type == 'total':
        from app.routers.owner import calculate_month_rent_stats
        stats = calculate_month_rent_stats(db, booking, date.today().month, date.today().year)
        remaining_rent = max(0.0, float(stats["cumulative_due"]) - stats["rent_paid"])
        total_due = remaining_rent + float(booking.security_deposit or 0) + float(booking.maintenance_charge or 0)
        total_paid = deposit_paid + maint_paid
        remaining_total = max(0.0, total_due - total_paid)
        if remaining_total <= 0.01 and not request.force_payment:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="All payments (rent, deposit, maintenance) are already fully paid for this cycle."
            )
        if request.amount > remaining_total + 0.01 and not request.force_payment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Amount exceeds remaining total due of \u20b9{remaining_total:.2f}. (Enable 'Force Payment' to bypass)"
            )

    amount_paise = int(request.amount * 100)
    
    # 1. Create offline transaction
    transaction = WalletService.create_offline_transaction(
        db=db,
        wallet_id=owner_wallet.id,
        booking_id=UUID(request.booking_id),
        payer_id=booking.customer_id,
        receiver_id=booking.owner_id,
        amount=amount_paise,
        payment_type=request.payment_type,
        payment_method=request.payment_method,
        offline_notes=request.offline_notes,
        offline_reference=request.offline_reference,
        description=f"Direct offline payment collection ({request.payment_type}) via {request.payment_method} by owner",
    )
    
    # 2. Complete it immediately (bypass OTP)
    complete_success, complete_message = WalletService.complete_transaction(db, transaction.id, bypass_otp=True)
    
    if not complete_success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=complete_message)
        
    # 3. Update booking status via centralized service
    BookingService.handle_payment_completion(
        db=db, 
        booking_id=booking.id, 
        payment_type=request.payment_type
    )
                
    db.commit()
    
    # Notify customer
    try:
        from app.models import Property
        prop = db.query(Property).filter(Property.id == booking.property_id).first()
        property_title = prop.title if prop else "Property"
        await notify_payment_verified(db, booking.customer_id, request.amount, property_title, transaction_id=transaction.id)
    except Exception:
        pass
        
    return {
        "success": True,
        "message": "Payment collected and recorded successfully",
        "transaction_id": str(transaction.id),
        "booking_status": booking.status
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
    
    # Only allow regenerating OTP if transaction is online AND status is otp_sent
    if transaction.payment_method != 'online':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP verification is not applicable for offline payments"
        )
        
    if transaction.status != TransactionStatus.otp_sent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot generate OTP for an unpaid online transaction"
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
@router.delete("/transactions/{transaction_id}")
async def delete_transaction(
    transaction_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete a transaction and reverse its impact on wallet balance (Owner only).
    """
    # Get transaction
    transaction = db.query(WalletTransaction).filter(WalletTransaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    # Verify ownership
    user_role = get_user_role(current_user, db)
    is_owner = str(transaction.receiver_id) == str(current_user.id)
    is_payer = str(transaction.payer_id) == str(current_user.id)
    
    # Payer can only delete if transaction is NOT completed
    if is_payer:
        if transaction.status == TransactionStatus.completed:
            raise HTTPException(status_code=403, detail="You cannot delete a completed transaction. Please contact the owner for a refund.")
    elif not is_owner and user_role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to delete this transaction")
        
    # Reverse wallet impact if necessary
    # If completed, deduct from owner's main balance. If pending/otp_sent, deduct from pending_balance.
    # Parse wallet contribution metadata from description
    wallet_contribution = 0
    if transaction.description:
        wallet_contribution, _, _ = parse_transaction_metadata(transaction.description)
        
    # Refund to tenant if there is a wallet contribution
    if wallet_contribution > 0 and transaction.payer_id:
        tenant_wallet = db.query(Wallet).filter(Wallet.user_id == transaction.payer_id).first()
        if tenant_wallet:
            tenant_wallet.balance += wallet_contribution
            
            # Create a credit transaction for the tenant's wallet to show refund of wallet balance
            refund_txn = WalletTransaction(
                wallet_id=tenant_wallet.id,
                payer_id=transaction.receiver_id,
                receiver_id=transaction.payer_id,
                booking_id=transaction.booking_id,
                amount=wallet_contribution,
                transaction_type=TransactionType.credit,
                status=TransactionStatus.completed,
                description=f"Refund of wallet contribution for {transaction.payment_type} - booking {transaction.booking_id}"
            )
            db.add(refund_txn)
            
    wallet = db.query(Wallet).filter(Wallet.id == transaction.wallet_id).first()
    if wallet:
        if transaction.status == TransactionStatus.completed:
            # Deduct both online paid amount and wallet contribution
            wallet.balance = max(0, wallet.balance - (transaction.amount + wallet_contribution))
        # Only deduct from pending_balance if the transaction was actually added to pending_balance
        # (online transactions are added when status is otp_sent or verified; offline transactions when status is pending)
        elif transaction.status in [TransactionStatus.otp_sent, TransactionStatus.verified] or (transaction.payment_method != 'online' and transaction.status == TransactionStatus.pending):
            wallet.pending_balance = max(0, wallet.pending_balance - transaction.amount)
            
    # Update booking status if necessary (might be complex to fully revert rent_paid, but let's at least clear relevant flags)
    if transaction.booking_id and transaction.status == TransactionStatus.completed:
        booking = db.query(Booking).filter(Booking.id == transaction.booking_id).first()
        if booking:
            p_type = transaction.payment_type
            if p_type == 'rent':
                booking.rent_paid = False
            elif p_type == 'deposit':
                booking.deposit_paid = False
            elif p_type == 'maintenance':
                booking.maintenance_paid = False
            elif p_type == 'total':
                booking.rent_paid = False
                booking.deposit_paid = False
                booking.maintenance_paid = False
            
            # If we delete a payment that made the booking "active", it should stay active
            # but if it was "paid", we might need to downgrade if rent is no longer paid
            if booking.status == "paid" and not booking.rent_paid:
                booking.status = "accepted"
            
            # SYNC VACANCY
            if booking.room_id:
                sync_room_vacancy(db, booking.room_id)

    # Delete the stale "Payment Received" notification(s) associated with this transaction
    try:
        from app.models import Notification
        db.query(Notification).filter(
            Notification.user_id == transaction.receiver_id,
            Notification.link.like(f"%{transaction_id}%")
        ).delete(synchronize_session=False)
    except Exception as e:
        import logging
        logging.warning(f"Failed to delete stale payment notification: {e}")

    # Notify owner of the cancellation if the tenant cancelled it
    if str(transaction.payer_id) == str(current_user.id) and transaction.status != TransactionStatus.completed:
        try:
            from app.models import Profile, Property, Booking
            customer_profile = db.query(Profile).filter(Profile.user_id == transaction.payer_id).first()
            customer_name = customer_profile.name if customer_profile else "Customer"
            
            property_title = None
            if transaction.booking_id:
                booking = db.query(Booking).filter(Booking.id == transaction.booking_id).first()
                if booking:
                    prop = db.query(Property).filter(Property.id == booking.property_id).first()
                    if prop:
                        property_title = prop.title
            
            from app.utils.notifications import create_notification
            msg = f"{customer_name} has cancelled their payment of ₹{transaction.amount / 100:,.0f}"
            if property_title:
                msg += f" for {property_title}"
            msg += "."
            
            await create_notification(
                db=db,
                user_id=transaction.receiver_id,
                title="❌ Payment Cancelled",
                message=msg,
                notification_type="warning",
                link="/owner/bookings"
            )
        except Exception as e:
            import logging
            logging.warning(f"Failed to notify owner of payment cancellation: {e}")

    # Delete transaction (CASCADE will handle OTPs)
    db.delete(transaction)
    db.commit()
    
    return {"message": "Transaction deleted successfully"}
