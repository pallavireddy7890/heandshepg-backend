"""Booking business logic service."""
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.models import Booking, Room
from app.services.vacancy import sync_room_vacancy

class BookingService:
    @staticmethod
    def handle_payment_completion(db: Session, booking_id: UUID, payment_type: str = None) -> tuple[bool, str]:
        """Recalculate booking payment flags and update overall status."""
        from app.models.wallet import WalletTransaction, TransactionStatus
        from app.services.vacancy import sync_room_vacancy
        from sqlalchemy import func
        
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            return False, "Booking not found"
            
        # 1. Recalculate all paid amounts from database transactions
        # Query recurring payments (rent) for this booking in the current billing cycle
        from datetime import datetime, date
        from app.services.wallet_service import WalletService
        import calendar
        
        # Determine cycle start and end based on current time or booking reference
        today = date.today()
        ref_day = min(booking.start_date.day, calendar.monthrange(today.year, today.month)[1])
        reference_date = date(today.year, today.month, ref_day)
        period_start, period_end = WalletService.get_billing_period(booking.start_date, reference_date)
        
        start_dt = datetime.combine(period_start, datetime.min.time())
        end_dt = datetime.combine(period_end, datetime.max.time())
        
        rent_payments = db.query(WalletTransaction).filter(
            WalletTransaction.booking_id == booking.id,
            WalletTransaction.status == TransactionStatus.completed,
            WalletTransaction.payment_type.in_(['rent', 'total']),
            WalletTransaction.created_at >= start_dt,
            WalletTransaction.created_at <= end_dt
        ).all()
        
        rent_paid_amt = 0
        for p in rent_payments:
            if p.payment_type == 'rent':
                rent_paid_amt += p.amount / 100
            elif p.payment_type == 'total':
                rent_paid_amt += booking.amount
                
        # Query security deposit and maintenance payments across all time (since they are lifetime/upfront payments)
        maint_payments = db.query(WalletTransaction).filter(
            WalletTransaction.booking_id == booking.id,
            WalletTransaction.status == TransactionStatus.completed,
            WalletTransaction.payment_type.in_(['maintenance', 'total'])
        ).all()
        
        total_maint_txns_amount = 0
        for p in maint_payments:
            if p.payment_type == 'maintenance':
                total_maint_txns_amount += p.amount / 100
            elif p.payment_type == 'total':
                total_maint_txns_amount += (booking.maintenance_charge or 0)
                
        all_payments = db.query(WalletTransaction).filter(
            WalletTransaction.booking_id == booking.id,
            WalletTransaction.status == TransactionStatus.completed,
            WalletTransaction.payment_type.in_(['deposit', 'total'])
        ).all()
        
        total_deposit_txns_amount = 0
        for p in all_payments:
            if p.payment_type == 'deposit':
                total_deposit_txns_amount += p.amount / 100
            elif p.payment_type == 'total':
                total_deposit_txns_amount += (booking.security_deposit or 0)
                
        # Allocate lifetime deposit transactions to security deposit and maintenance charge
        security_cap = float(booking.security_deposit or 0)
        deposit_paid_amt = min(total_deposit_txns_amount, security_cap)
        leftover_deposit = max(0.0, total_deposit_txns_amount - security_cap)
        
        maintenance_paid_amt = total_maint_txns_amount + leftover_deposit

        booking.rent_paid = (rent_paid_amt >= booking.amount)
        booking.deposit_paid = (deposit_paid_amt >= (booking.security_deposit or 0))
        booking.maintenance_paid = (maintenance_paid_amt >= (booking.maintenance_charge or 0))
            
        # 2. Update last payment date for rent cycles
        if payment_type in ['rent', 'total', 'booking']:
            booking.last_payment_date = func.now()
            
        # 3. Transition overall status
        # If both rent and deposit are paid, it's fully paid
        if booking.rent_paid and booking.deposit_paid:
            booking.status = "paid"
        # If at least rent is paid, consider them "checked_in" (occupying bed)
        elif booking.rent_paid:
            booking.status = "checked_in"
        else:
            # If rent is not fully paid and status was paid, downgrade to checked_in
            if booking.status == "paid":
                booking.status = "checked_in"
            
        # 4. SYNC VACANCY
        # This fixes the double-decrement bug by recalculating the absolute truth
        if booking.room_id:
            sync_room_vacancy(db, booking.room_id)
            
        # 5. Handle Referral Completion
        # If the booking is now "paid", and it's the customer's first booking, complete any pending referral
        if booking.status == "paid":
            from app.services.referral_service import ReferralService
            ReferralService.complete_referral_for_booking(db, booking.customer_id, booking.id)
            
        db.commit()
        return True, "Booking status updated successfully"
