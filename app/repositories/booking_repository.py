from sqlalchemy.orm import Session
from uuid import UUID
from app.models import Booking

class BookingRepository:
    @staticmethod
    def get_active_bookings_by_property_id(db: Session, property_id: UUID) -> list[Booking]:
        """Fetch all active bookings for a given property."""
        return db.query(Booking).filter(
            Booking.property_id == property_id,
            Booking.status.in_(["requested", "accepted", "paid", "checked_in", "active", "vacate_requested","vacate_approved"])
        ).all()
