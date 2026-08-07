"""Wallet service for managing user wallets and transactions."""
import logging
import random
import string
from datetime import datetime, timedelta, date
from typing import Optional, Tuple, List
from uuid import UUID
import calendar

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Wallet, WalletTransaction, TransactionOTP, TransactionType, TransactionStatus, Profile
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


def parse_transaction_metadata(description: str):
    import re
    if not description:
        return 0, 0, description
    
    wallet_contribution = 0
    total_amount = 0
    clean_desc = description
    
    # Try to find [wallet_contribution:xxx]
    wc_match = re.search(r'\[wallet_contribution:(\d+)\]', clean_desc)
    if wc_match:
        wallet_contribution = int(wc_match.group(1))
        clean_desc = re.sub(r'\[wallet_contribution:\d+\]', '', clean_desc)
        
    # Try to find [total_amount:xxx]
    ta_match = re.search(r'\[total_amount:(\d+)\]', clean_desc)
    if ta_match:
        total_amount = int(ta_match.group(1))
        clean_desc = re.sub(r'\[total_amount:\d+\]', '', clean_desc)
        
    # Clean up any double spaces/brackets
    clean_desc = clean_desc.strip()
    return wallet_contribution, total_amount, clean_desc


def calculate_transaction_breakdown(txn, booking_details: Optional[dict] = None, booking_obj = None) -> dict:
    """Calculate the breakdown of payment categories for a transaction in INR."""
    # (1) Return all-zero breakdown when there is no booking context
    if not txn.booking_id:
        return {
            "rent": 0.0,
            "security_deposit": 0.0,
            "maintenance": 0.0
        }

    _wallet_contribution, total_amount, _ = parse_transaction_metadata(txn.description)
    total_amt_inr = (total_amount / 100) if total_amount > 0 else (txn.amount / 100)
    
    breakdown = {
        "rent": 0.0,
        "security_deposit": 0.0,
        "maintenance": 0.0
    }
    
    p_type = txn.payment_type
    
    # (2) Infer p_type from the description when payment_type is missing or "total"
    desc_lower = (txn.description or "").lower()
    inferred_type = None
    has_rent = "rent" in desc_lower
    has_deposit = "deposit" in desc_lower or "security" in desc_lower
    has_maint = "maintenance" in desc_lower or "maint" in desc_lower
    
    # If only one of the categories is mentioned, infer that type
    if has_rent and not has_deposit and not has_maint:
        inferred_type = "rent"
    elif has_deposit and not has_rent and not has_maint:
        inferred_type = "deposit"
    elif has_maint and not has_rent and not has_deposit:
        inferred_type = "maintenance"
        
    if not p_type or p_type == "total":
        if inferred_type:
            p_type = inferred_type
        elif not p_type:
            p_type = "total"
    
    if p_type == "rent":
        breakdown["rent"] = total_amt_inr
    elif p_type == "deposit":
        breakdown["security_deposit"] = total_amt_inr
    elif p_type == "maintenance":
        breakdown["maintenance"] = total_amt_inr
    elif p_type == "total":
        if booking_details or booking_obj:
            rent_val = float(booking_details.get("amount") or 0.0) if booking_details else float(booking_obj.amount or 0.0)
            deposit_val = float(booking_details.get("security_deposit") or 0.0) if booking_details else float(booking_obj.security_deposit or 0.0)

            
            remaining = total_amt_inr
            
            # Priority 1: Security Deposit
            allocated_deposit = min(remaining, deposit_val)
            remaining -= allocated_deposit
        
            # Priority 2: Rent
            allocated_rent = min(remaining, rent_val)
            remaining -= allocated_rent
            
            # Leftover/excess goes to Rent
            if remaining > 0:
                allocated_rent += remaining
                
            breakdown["rent"] = allocated_rent
            breakdown["security_deposit"] = allocated_deposit
            breakdown["maintenance"] = 0.0
        else:
            breakdown["rent"] = total_amt_inr
            
    return breakdown


class WalletService:
    """Service for wallet operations."""
    
    OTP_EXPIRY_MINUTES = 10
    OTP_LENGTH = 6

    @staticmethod
    def get_billing_period(start_date: date, current_date: date) -> Tuple[date, date]:
        """Calculate the start and end of the current billing cycle (1 month long)."""
        # If today is before start_date, the first cycle is upcoming
        if current_date < start_date:
            return start_date, start_date + timedelta(days=30)
            
        # Calculate how many full months have passed
        years_diff = current_date.year - start_date.year
        months_diff = current_date.month - start_date.month
        total_months = years_diff * 12 + months_diff
        
        def get_date_for_month(base_date: date, month_offset: int) -> date:
            m = (base_date.month + month_offset - 1) % 12 + 1
            y = base_date.year + (base_date.month + month_offset - 1) // 12
            last_day_of_m = calendar.monthrange(y, m)[1]
            return date(y, m, min(base_date.day, last_day_of_m))

        period_start = get_date_for_month(start_date, total_months)
        
        # If calculated period_start is in the future, it means we are still in previous month's cycle
        if period_start > current_date:
            total_months -= 1
            period_start = get_date_for_month(start_date, total_months)
            
        period_end = get_date_for_month(start_date, total_months + 1) - timedelta(days=1)
        
        return period_start, period_end

    @staticmethod
    def check_payment_overlap(db: Session, booking_id: UUID, period_start: date, period_end: date) -> bool:
        """Check if rent is fully paid for the given booking in the specified period."""
        start_dt = datetime.combine(period_start, datetime.min.time())
        end_dt = datetime.combine(period_end, datetime.max.time())
        
        # Get booking to know the full rent amount
        from app.models.booking import Booking
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            return False
            
        payments = db.query(WalletTransaction).filter(
            WalletTransaction.booking_id == booking_id,
            WalletTransaction.status == TransactionStatus.completed,
            WalletTransaction.payment_type.in_(['rent', 'total']),
            WalletTransaction.created_at >= start_dt,
            WalletTransaction.created_at <= end_dt
        ).all()
        
        rent_paid = 0
        for p in payments:
            if p.payment_type == 'rent':
                rent_paid += p.amount / 100
            elif p.payment_type == 'total':
                rent_paid += booking.amount
                
        return rent_paid >= booking.amount
    
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
    def get_balance(db: Session, user_id: UUID, property_id: Optional[UUID] = None) -> dict:
        """Get wallet balance for a user with online/offline breakdown."""
        wallet = WalletService.get_or_create_wallet(db, user_id)
        
        def build_sum_query(payment_method_online: Optional[bool], status_list: list, tx_type: TransactionType) -> int:
            q = db.query(func.sum(WalletTransaction.amount)).filter(
                WalletTransaction.wallet_id == wallet.id,
                WalletTransaction.transaction_type == tx_type
            )
            if payment_method_online is not None:
                if payment_method_online:
                    q = q.filter(WalletTransaction.payment_method == 'online')
                else:
                    q = q.filter(WalletTransaction.payment_method != 'online')
            if status_list:
                q = q.filter(WalletTransaction.status.in_(status_list))
                
            if property_id:
                from app.models import Booking
                q = q.join(Booking, WalletTransaction.booking_id == Booking.id).filter(Booking.property_id == property_id)
                
            return q.scalar() or 0

        online_completed = build_sum_query(True, [TransactionStatus.completed], TransactionType.credit)
        offline_completed = build_sum_query(False, [TransactionStatus.completed], TransactionType.credit)
        
        online_pending = build_sum_query(True, [TransactionStatus.otp_sent, TransactionStatus.verified], TransactionType.credit)
        offline_pending = build_sum_query(False, [TransactionStatus.pending, TransactionStatus.otp_sent, TransactionStatus.verified], TransactionType.credit)
        
        # Withdrawals are not associated with properties, so they are 0 if property_id is provided
        if property_id:
            withdrawals_completed = 0
            withdrawals_pending = 0
        else:
            withdrawals_completed = db.query(func.sum(WalletTransaction.amount)).filter(
                WalletTransaction.wallet_id == wallet.id,
                WalletTransaction.transaction_type == TransactionType.withdrawal,
                WalletTransaction.status == TransactionStatus.completed
            ).scalar() or 0
            
            withdrawals_pending = db.query(func.sum(WalletTransaction.amount)).filter(
                WalletTransaction.wallet_id == wallet.id,
                WalletTransaction.transaction_type == TransactionType.withdrawal,
                WalletTransaction.status == TransactionStatus.pending
            ).scalar() or 0

        # Calculate dynamic balances
        available = max(0, online_completed - withdrawals_completed - withdrawals_pending)
        
        # If property-specific, total balance and pending balance are computed dynamically for that property
        if property_id:
            balance_val = online_completed + offline_completed
            pending_balance_val = online_pending + offline_pending
        else:
            balance_val = wallet.balance
            pending_balance_val = wallet.pending_balance

        return {
            "balance": balance_val,
            "pending_balance": pending_balance_val,
            "available_balance": available,
            "online_balance": online_completed - withdrawals_completed,
            "offline_balance": offline_completed,
            "pending_online": online_pending,
            "pending_offline": offline_pending,
            "pending_withdrawals": withdrawals_pending,
            "currency": "INR",
            "balance_inr": balance_val / 100,
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
            payment_method='online',
            razorpay_payment_id=razorpay_payment_id,
            razorpay_order_id=razorpay_order_id,
            description=description,
        )
        db.add(transaction)
        
        # Add to owner's pending_balance (only if it is not a pending online transaction)
        owner_wallet = db.query(Wallet).filter(Wallet.id == wallet_id).first()
        if owner_wallet:
            pay_method = transaction.payment_method or 'online'
            is_pending_online = (pay_method == 'online' and transaction.status == TransactionStatus.pending)
            if not is_pending_online:
                owner_wallet.pending_balance += amount
        
        db.commit()
        db.refresh(transaction)
        return transaction
    
    @staticmethod
    def create_offline_transaction(
        db: Session,
        wallet_id: UUID,
        booking_id: UUID,
        payer_id: UUID,
        receiver_id: UUID,
        amount: int,
        payment_type: str = 'total',
        payment_method: str = 'offline',
        offline_notes: Optional[str] = None,
        offline_reference: Optional[str] = None,
        description: Optional[str] = None,
    ) -> WalletTransaction:
        """Create a new offline wallet transaction."""
        transaction = WalletTransaction(
            wallet_id=wallet_id,
            booking_id=booking_id,
            payer_id=payer_id,
            receiver_id=receiver_id,
            amount=amount,
            payment_type=payment_type,
            transaction_type=TransactionType.credit,
            status=TransactionStatus.pending,
            payment_method=payment_method,
            offline_notes=offline_notes,
            offline_reference=offline_reference,
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
            # Add online transaction amount to owner's pending_balance when transitioning from pending to otp_sent
            if transaction.status == TransactionStatus.pending and transaction.payment_method == 'online':
                owner_wallet = db.query(Wallet).filter(Wallet.id == transaction.wallet_id).first()
                if owner_wallet:
                    owner_wallet.pending_balance += transaction.amount
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
            
        # Send Email as well for omnichannel support
        try:
            from app.models import User
            user = db.query(User).filter(User.id == user_id).first()
            if user and user.email:
                email_body = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6;">
                    <h2 style="color: #f59e0b;">Transaction OTP</h2>
                    <p>Your He&She PG transaction OTP is: <strong>{otp_code}</strong></p>
                    <p>Amount: <strong>Rs.{amount_inr:.2f}</strong></p>
                    <p>This code is valid for {WalletService.OTP_EXPIRY_MINUTES} minutes.</p>
                    <p>If you did not initiate this transaction, please ignore this email.</p>
                </body>
                </html>
                """
                NotificationService.send_email(
                    to_email=user.email,
                    subject="He&She PG: Transaction Verification OTP",
                    body_html=email_body,
                    body_text=message
                )
        except Exception as e:
            logger.warning(f"Failed to send OTP Email to user {user_id}: {e}")
        
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
            # Add online transaction amount to owner's pending_balance when transitioning from pending to otp_sent
            if transaction.status == TransactionStatus.pending and transaction.payment_method == 'online':
                owner_wallet = db.query(Wallet).filter(Wallet.id == transaction.wallet_id).first()
                if owner_wallet:
                    owner_wallet.pending_balance += transaction.amount
            transaction.status = TransactionStatus.otp_sent
        
        db.commit()

        # Create notification for owner
        try:
            from app.models import Notification,Booking

            amount_inr = transaction.amount / 100 if transaction else 0
            booking = db.query(Booking).filter(
                Booking.id == transaction.booking_id
            ).first()

            notification = Notification(
                user_id=transaction.receiver_id,
                property_id=booking.property_id if booking else None,
                title="Payment Verification Required",
                message=f"Payment verification pending for ₹{amount_inr:.2f}. Please verify OTP.",
                type="PAYMENT_VERIFICATION",
                link="/owner/wallet",
                read=False
            )

            db.add(notification)
            db.commit()

        except Exception as e:
            logger.warning(f"Failed to create payment verification notification: {e}")
        
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
        transaction_id: UUID,
        bypass_otp: bool = False
    ) -> Tuple[bool, str]:
        """Complete the transaction after OTP verification or bypass for offline."""
        transaction = db.query(WalletTransaction).filter(
            WalletTransaction.id == transaction_id
        ).first()
        
        if not transaction:
            return False, "Transaction not found"
        
        # Check if owner OTP is verified (skip for offline if requested)
        if not bypass_otp:
            owner_otp = db.query(TransactionOTP).filter(
                TransactionOTP.transaction_id == transaction_id,
                TransactionOTP.otp_type == "owner",
                TransactionOTP.is_verified == True
            ).first()
            
            if not owner_otp:
                return False, "Owner OTP verification required"
        else:
            # For offline/bypass, ensure it's not already completed
            if transaction.status == TransactionStatus.completed:
                return False, "Transaction already completed"
        
        # Get owner's wallet
        owner_wallet = db.query(Wallet).filter(Wallet.user_id == transaction.receiver_id).first()
        if not owner_wallet:
            return False, "Owner wallet not found"
        
        # Parse wallet contribution from description
        wallet_contribution = 0
        if transaction.description:
            wallet_contribution, _, _ = parse_transaction_metadata(transaction.description)
        
        # Move from pending_balance to balance
        owner_wallet.balance += (transaction.amount + wallet_contribution)
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
        limit: int = 50,
        property_id: Optional[UUID] = None
    ) -> list:
        """Get transaction history for a user."""
        # Get user's wallet (may be None)
        wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
        
        # Build query - include transactions where user is payer or receiver
        # even if they don't have a wallet yet
        if wallet:
            query = db.query(WalletTransaction).filter(
                (WalletTransaction.wallet_id == wallet.id) |
                (WalletTransaction.payer_id == user_id) |
                (WalletTransaction.receiver_id == user_id)
            )
        else:
            # No wallet yet - still show transactions where user is payer/receiver
            query = db.query(WalletTransaction).filter(
                (WalletTransaction.payer_id == user_id) |
                (WalletTransaction.receiver_id == user_id)
            )
        
        # Exclude debit transactions where the user is NOT the payer (so owner doesn't see tenant's debit transaction)
        query = query.filter(
            ~((WalletTransaction.transaction_type == TransactionType.debit) & 
              (WalletTransaction.payer_id != user_id))
        )
        
        from sqlalchemy import or_
        # Exclude unpaid/pending online transactions from history
        query = query.filter(
            or_(
                WalletTransaction.payment_method != 'online',
                WalletTransaction.status != TransactionStatus.pending
            )
        )
        
        if property_id:
            from app.models import Booking
            query = query.join(Booking, WalletTransaction.booking_id == Booking.id).filter(Booking.property_id == property_id)
            
        transactions = query.order_by(WalletTransaction.created_at.desc()).limit(limit).all()
        
        result = []
        for txn in transactions:
            # Get payer and receiver names
            payer_profile = db.query(Profile).filter(Profile.user_id == txn.payer_id).first() if txn.payer_id else None
            receiver_profile = db.query(Profile).filter(Profile.user_id == txn.receiver_id).first() if txn.receiver_id else None
            
            # Get booking and property info for better description
            property_title = None
            booking_details = None
            if txn.booking_id:
                from app.models import Booking, Property, Room
                booking = db.query(Booking).filter(Booking.id == txn.booking_id).first()
                if booking:
                    property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
                    room_obj = db.query(Room).filter(Room.id == booking.room_id).first() if booking.room_id else None
                    if property_obj:
                        property_title = property_obj.title
                    
                    booking_details = {
                        "id": str(booking.id),
                        "start_date": booking.start_date.isoformat() if booking.start_date else None,
                        "end_date": booking.end_date.isoformat() if booking.end_date else None,
                        "status": booking.status,
                        "stay_type": booking.stay_type,
                        "duration_days": booking.duration_days,
                        "amount": booking.amount,
                        "security_deposit": booking.security_deposit,
                        "property": {
                            "title": property_obj.title if property_obj else None,
                            "locality": property_obj.locality if property_obj else None,
                            "city": property_obj.city if property_obj else None,
                        } if property_obj else None,
                        "room": {
                            "room_type": room_obj.room_type if room_obj else None,
                            "room_number": room_obj.room_number if room_obj else None,
                            "floor_number": room_obj.floor_number if room_obj else None,
                        } if room_obj else None
                    }
            
            # Parse metadata
            wallet_contribution, total_amount, clean_desc = parse_transaction_metadata(txn.description)
            
            # Create meaningful description
            description = clean_desc
            if property_title and payer_profile:
                description = f"Payment from {payer_profile.name} for {property_title}"
            elif property_title:
                description = f"Payment for {property_title}"
            
            # Get payment time in IST
            from datetime import timezone, timedelta
            ist = timezone(timedelta(hours=5, minutes=30))
            created_at_utc = txn.created_at
            if created_at_utc.tzinfo is None:
                created_at_utc = created_at_utc.replace(tzinfo=timezone.utc)
            created_at_ist = created_at_utc.astimezone(ist)
            payment_time = created_at_ist.strftime("%d %b %Y %I:%M %p")

            billing_period = None
            if txn.booking_id and txn.payment_type in ['rent', 'total']:
                if txn.booking_id and booking:
                    period_start, period_end = WalletService.get_billing_period(booking.start_date, txn.created_at.date())
                    billing_period = f"{period_start.strftime('%d %b %Y')} - {period_end.strftime('%d %b %Y')}"

            result.append({
                "id": str(txn.id),
                "booking_id": str(txn.booking_id) if txn.booking_id else None,
                "amount": txn.amount,
                "amount_inr": txn.amount / 100,
                "total_amount_inr": total_amount / 100 if total_amount > 0 else txn.amount / 100,
                "wallet_contribution_inr": wallet_contribution / 100 if wallet_contribution > 0 else 0.0,
                "transaction_type": txn.transaction_type.value if hasattr(txn.transaction_type, 'value') else txn.transaction_type,
                "status": txn.status.value if hasattr(txn.status, 'value') else txn.status,
                "payer_name": payer_profile.name if payer_profile else None,
                "receiver_name": receiver_profile.name if receiver_profile else None,
                "customer_name": payer_profile.name if payer_profile else None,
                "tenant_name": payer_profile.name if payer_profile else None,
                "property_title": property_title,
                "description": description,
                "otp_verified": txn.otp_verified,
                "payment_method": txn.payment_method,
                "payment_type": txn.payment_type or "rent",
                "offline_notes": txn.offline_notes,
                "offline_reference": txn.offline_reference,
                "razorpay_payment_id": txn.razorpay_payment_id,
                "created_at": txn.created_at.isoformat() if txn.created_at else None,
                "payment_time": payment_time,
                "billing_period": billing_period,
                "booking_details": booking_details,
                "breakdown": calculate_transaction_breakdown(txn, booking_details=booking_details),
            })
        
        return result

    @staticmethod
    def create_withdrawal_request(
        db: Session,
        user_id: UUID,
        amount: int,
    ) -> Tuple[bool, str, Optional[WalletTransaction]]:
        """Create a withdrawal request for an owner."""
        # Get user wallet
        wallet = WalletService.get_or_create_wallet(db, user_id)
        
        # Check available balance (amount is in paise)
        available_balance = wallet.balance - wallet.pending_balance
        if available_balance < amount:
            return False, "Insufficient available balance", None
        
        # Get bank details from profile
        profile = db.query(Profile).filter(Profile.user_id == user_id).first()
        if not profile or not profile.bank_account_number or not profile.bank_ifsc_code:
            return False, "Please provide bank details in your profile before requesting withdrawal", None
            
        # Create transaction record
        transaction = WalletTransaction(
            wallet_id=wallet.id,
            payer_id=None, # System/Internal
            receiver_id=user_id,
            amount=amount,
            transaction_type=TransactionType.withdrawal,
            status=TransactionStatus.pending,
            bank_account_number=profile.bank_account_number,
            bank_ifsc_code=profile.bank_ifsc_code,
            bank_name=profile.bank_name,
            description=f"Withdrawal request for Rs.{amount/100:.2f}"
        )
        db.add(transaction)
        
        # Hold the amount in pending_balance
        wallet.pending_balance += amount
        
        db.commit()
        db.refresh(transaction)
        
        return True, "Withdrawal request submitted successfully", transaction

    @staticmethod
    def process_withdrawal(
        db: Session,
        transaction_id: UUID,
        new_status: TransactionStatus, # completed or rejected
        admin_notes: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Process a withdrawal request by admin."""
        transaction = db.query(WalletTransaction).filter(
            WalletTransaction.id == transaction_id,
            WalletTransaction.transaction_type == TransactionType.withdrawal
        ).first()
        
        if not transaction or transaction.status != TransactionStatus.pending:
            return False, "Invalid withdrawal request or already processed"
            
        wallet = db.query(Wallet).filter(Wallet.id == transaction.wallet_id).first()
        if not wallet:
            return False, "Wallet not found"
        
        if new_status == TransactionStatus.completed:
            # Deduct from both balance and pending_balance
            wallet.balance -= transaction.amount
            wallet.pending_balance = max(0, wallet.pending_balance - transaction.amount)
            transaction.status = TransactionStatus.completed
        elif new_status == TransactionStatus.rejected:
            # Release from pending_balance back to available
            wallet.pending_balance = max(0, wallet.pending_balance - transaction.amount)
            transaction.status = TransactionStatus.rejected
            
        transaction.admin_notes = admin_notes
        db.commit()
        
        return True, f"Withdrawal request {new_status.value} successfully"


# Convenience instance
wallet_service = WalletService()
