"""Wallet service for managing user wallets and transactions."""
import logging
import random
import string
from datetime import datetime, timedelta
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Wallet, WalletTransaction, TransactionOTP, TransactionType, TransactionStatus, Profile
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class WalletService:
    """Service for wallet operations."""
    
    OTP_EXPIRY_MINUTES = 10
    OTP_LENGTH = 6
    
    @staticmethod
    def get_or_create_wallet(db: Session, user_id: UUID) -> Wallet:
        """Get existing wallet or create a new one for the user."""
        wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
        
        if not wallet:
            wallet = Wallet(
                user_id=user_id,
                balance=0,
                pending_balance=0,
                is_active=True
            )
            db.add(wallet)
            db.commit()
            db.refresh(wallet)
            logger.info(f"Created new wallet for user {user_id}")
        
        return wallet
    
    @staticmethod
    def get_balance(db: Session, user_id: UUID) -> dict:
        """Get wallet balance for a user."""
        wallet = WalletService.get_or_create_wallet(db, user_id)
        return {
            "balance": wallet.balance,
            "pending_balance": wallet.pending_balance,
            "available_balance": wallet.balance - wallet.pending_balance,
            "currency": "INR",
            "balance_inr": wallet.balance / 100,  # Convert paise to INR
        }
    
    @staticmethod
    def generate_otp() -> str:
        """Generate a random 6-digit OTP."""
        return ''.join(random.choices(string.digits, k=WalletService.OTP_LENGTH))
    
    @staticmethod
    def create_transaction(
        db: Session,
        wallet_id: UUID,
        booking_id: UUID,
        payer_id: UUID,
        receiver_id: UUID,
        amount: int,
        transaction_type: TransactionType,
        razorpay_payment_id: Optional[str] = None,
        razorpay_order_id: Optional[str] = None,
        description: Optional[str] = None,
    ) -> WalletTransaction:
        """Create a new wallet transaction."""
        transaction = WalletTransaction(
            wallet_id=wallet_id,
            booking_id=booking_id,
            payer_id=payer_id,
            receiver_id=receiver_id,
            amount=amount,
            transaction_type=transaction_type,
            status=TransactionStatus.pending,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_order_id=razorpay_order_id,
            description=description,
        )
        db.add(transaction)
        
        # Add to owner's pending_balance
        owner_wallet = db.query(Wallet).filter(Wallet.id == wallet_id).first()
        if owner_wallet:
            owner_wallet.pending_balance += amount
        
        db.commit()
        db.refresh(transaction)
        return transaction
    
    @staticmethod
    def create_and_send_otp(
        db: Session,
        transaction_id: UUID,
        user_id: UUID,
        otp_type: str,  # 'customer' or 'owner'
        phone_number: str
    ) -> Tuple[bool, Optional[str]]:
        """Create OTP and send via SMS."""
        from datetime import timezone
        otp_code = WalletService.generate_otp()
        # Use timezone-aware UTC datetime to match verification
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=WalletService.OTP_EXPIRY_MINUTES)
        
        # Create OTP record
        otp = TransactionOTP(
            transaction_id=transaction_id,
            otp_code=otp_code,
            otp_type=otp_type,
            user_id=user_id,
            expires_at=expires_at,
        )
        db.add(otp)
        
        # Get transaction and update status
        transaction = db.query(WalletTransaction).filter(WalletTransaction.id == transaction_id).first()
        if transaction:
            transaction.status = TransactionStatus.otp_sent
        
        db.commit()
        
        # Send SMS
        amount_inr = transaction.amount / 100 if transaction else 0
        message = f"Your He&She PG transaction OTP is {otp_code}. Amount: Rs.{amount_inr:.2f}. Valid for {WalletService.OTP_EXPIRY_MINUTES} mins. Do not share."
        
        # Log OTP for debugging (since SMS might not work in India)
        logger.info(f"Transaction OTP for {otp_type} ({phone_number}): {otp_code}")
        
        success, error = NotificationService.send_sms(phone_number, message)
        
        if not success:
            logger.warning(f"Failed to send OTP SMS to {phone_number}: {error}")
            # Still return success since OTP was created (can be verified via logs)
        
        return True, otp_code
    
    @staticmethod
    def create_otp_for_display(
        db: Session,
        transaction_id: UUID,
        user_id: UUID,
        otp_type: str,  # 'customer' or 'owner'
    ) -> Tuple[bool, Optional[str]]:
        """
        Create OTP for in-website display (no SMS required).
        This is used when the customer makes a payment and needs to share the OTP
        with the owner in person or via any communication method.
        """
        from datetime import timezone
        otp_code = WalletService.generate_otp()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=WalletService.OTP_EXPIRY_MINUTES)
        
        # Delete any existing unverified OTPs for this transaction and type
        db.query(TransactionOTP).filter(
            TransactionOTP.transaction_id == transaction_id,
            TransactionOTP.otp_type == otp_type,
            TransactionOTP.is_verified == False
        ).delete()
        
        # Create OTP record
        otp = TransactionOTP(
            transaction_id=transaction_id,
            otp_code=otp_code,
            otp_type=otp_type,
            user_id=user_id,
            expires_at=expires_at,
        )
        db.add(otp)
        
        # Get transaction and update status
        transaction = db.query(WalletTransaction).filter(WalletTransaction.id == transaction_id).first()
        if transaction:
            transaction.status = TransactionStatus.otp_sent
        
        db.commit()
        
        # Get amount for logging
        amount_inr = transaction.amount / 100 if transaction else 0
        logger.info(f"Generated OTP for display - Transaction: {transaction_id}, Type: {otp_type}, Amount: Rs.{amount_inr:.2f}, OTP: {otp_code}")
        
        return True, otp_code
    
    @staticmethod
    def verify_otp(
        db: Session,
        transaction_id: UUID,
        user_id: UUID,
        otp_code: str
    ) -> Tuple[bool, str]:
        """Verify OTP for a transaction."""
        from datetime import timezone
        
        # Find the LATEST OTP for this transaction - order by created_at desc
        otp = db.query(TransactionOTP).filter(
            TransactionOTP.transaction_id == transaction_id,
            TransactionOTP.otp_type == "owner",
            TransactionOTP.is_verified == False
        ).order_by(TransactionOTP.created_at.desc()).first()
        
        if not otp:
            return False, "OTP not found or already verified"
        
        # Check expiry - compare timestamps properly
        now = datetime.now(timezone.utc)
        expires_at = otp.expires_at
        
        # Log for debugging
        logger.info(f"OTP Verification - Now: {now}, Expires At: {expires_at}, OTP in DB: {otp.otp_code}, Input: {otp_code}")
        
        # Compare timestamps properly - both should be timezone-aware
        # If expires_at already has tzinfo, comparison will handle conversion
        # If not, assume it's UTC
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        # Convert both to UTC for comparison
        expires_at_utc = expires_at.astimezone(timezone.utc)
        
        logger.info(f"Comparison - Now UTC: {now}, Expires UTC: {expires_at_utc}, Expired: {now > expires_at_utc}")
        
        if now > expires_at_utc:
            return False, "OTP has expired"
        
        # Check attempts
        if otp.attempts >= otp.max_attempts:
            return False, "Maximum OTP attempts exceeded"
        
        # Increment attempts
        otp.attempts += 1
        
        # Verify OTP
        if otp.otp_code != otp_code:
            db.commit()
            return False, f"Invalid OTP. {otp.max_attempts - otp.attempts} attempts remaining"
        
        # Mark as verified
        otp.is_verified = True
        otp.verified_at = datetime.now(timezone.utc)
        db.commit()
        
        return True, "OTP verified successfully"
    
    @staticmethod
    def complete_transaction(
        db: Session,
        transaction_id: UUID
    ) -> Tuple[bool, str]:
        """Complete the transaction after OTP verification."""
        transaction = db.query(WalletTransaction).filter(
            WalletTransaction.id == transaction_id
        ).first()
        
        if not transaction:
            return False, "Transaction not found"
        
        # Check if owner OTP is verified
        owner_otp = db.query(TransactionOTP).filter(
            TransactionOTP.transaction_id == transaction_id,
            TransactionOTP.otp_type == "owner",
            TransactionOTP.is_verified == True
        ).first()
        
        if not owner_otp:
            return False, "Owner OTP verification required"
        
        # Get owner's wallet
        owner_wallet = db.query(Wallet).filter(Wallet.user_id == transaction.receiver_id).first()
        if not owner_wallet:
            return False, "Owner wallet not found"
        
        # Move from pending_balance to balance
        owner_wallet.balance += transaction.amount
        owner_wallet.pending_balance = max(0, owner_wallet.pending_balance - transaction.amount)
        
        # Update transaction status
        transaction.status = TransactionStatus.completed
        transaction.otp_verified = True
        transaction.otp_verified_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Transaction {transaction_id} completed. Credited {transaction.amount} paise to wallet {owner_wallet.id}")
        
        return True, "Transaction completed successfully"
    
    @staticmethod
    def get_transactions(
        db: Session,
        user_id: UUID,
        limit: int = 50
    ) -> list:
        """Get transaction history for a user."""
        # Get user's wallet (may be None)
        wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
        
        # Build query - include transactions where user is payer or receiver
        # even if they don't have a wallet yet
        if wallet:
            transactions = db.query(WalletTransaction).filter(
                (WalletTransaction.wallet_id == wallet.id) |
                (WalletTransaction.payer_id == user_id) |
                (WalletTransaction.receiver_id == user_id)
            ).order_by(WalletTransaction.created_at.desc()).limit(limit).all()
        else:
            # No wallet yet - still show transactions where user is payer/receiver
            transactions = db.query(WalletTransaction).filter(
                (WalletTransaction.payer_id == user_id) |
                (WalletTransaction.receiver_id == user_id)
            ).order_by(WalletTransaction.created_at.desc()).limit(limit).all()
        
        result = []
        for txn in transactions:
            # Get payer and receiver names
            payer_profile = db.query(Profile).filter(Profile.user_id == txn.payer_id).first() if txn.payer_id else None
            receiver_profile = db.query(Profile).filter(Profile.user_id == txn.receiver_id).first() if txn.receiver_id else None
            
            # Get booking and property info for better description
            property_title = None
            booking_info = None
            if txn.booking_id:
                from app.models import Booking, Property
                booking = db.query(Booking).filter(Booking.id == txn.booking_id).first()
                if booking:
                    property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
                    if property_obj:
                        property_title = property_obj.title
                    booking_info = {
                        "start_date": booking.start_date.isoformat() if booking.start_date else None,
                        "status": booking.status,
                    }
            
            # Create meaningful description
            description = txn.description
            if property_title and payer_profile:
                description = f"Payment from {payer_profile.name} for {property_title}"
            elif property_title:
                description = f"Payment for {property_title}"
            
            result.append({
                "id": str(txn.id),
                "amount": txn.amount,
                "amount_inr": txn.amount / 100,
                "transaction_type": txn.transaction_type.value if hasattr(txn.transaction_type, 'value') else txn.transaction_type,
                "status": txn.status.value if hasattr(txn.status, 'value') else txn.status,
                "payer_name": payer_profile.name if payer_profile else None,
                "receiver_name": receiver_profile.name if receiver_profile else None,
                "property_title": property_title,
                "description": description,
                "otp_verified": txn.otp_verified,
                "razorpay_payment_id": txn.razorpay_payment_id,
                "created_at": txn.created_at.isoformat() if txn.created_at else None,
            })
        
        return result


# Convenience instance
wallet_service = WalletService()
