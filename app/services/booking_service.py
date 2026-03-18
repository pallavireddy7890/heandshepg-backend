"""Booking business logic service."""
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.models import Booking, Room
from app.services.vacancy import sync_room_vacancy

class BookingService:
    @staticmethod
    def handle_payment_completion(db: Session, booking_id: UUID, payment_type: str) -> tuple[bool, str]:
        """
        Handle booking state updates after a payment is verified.
        Consolidates logic for updating flags, status, and vacancy.
        """
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            return False, "Booking not found"
            
        # 1. Update specific payment flags
        if payment_type == 'rent':
            booking.rent_paid = True
        elif payment_type == 'deposit':
            booking.deposit_paid = True
        elif payment_type == 'maintenance':
            booking.maintenance_paid = True
        elif payment_type in ['total', 'booking']:
            booking.rent_paid = True
            booking.deposit_paid = True
            booking.maintenance_paid = True
            
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
        return True, "Booking updated successfully"
