"""SQLAlchemy models for bookings, payments, and invoices."""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text, ARRAY, Date, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.database import Base


class BookingStatus(str, enum.Enum):
    requested = "requested"
    accepted = "accepted"
    paid = "paid"
    checked_in = "checked_in"
    active = "active"
    completed = "completed"
    cancelled = "cancelled"
    vacate_requested = "vacate_requested"
    vacated = "vacated"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"
    refunded = "refunded"
    pending_verification = "pending_verification"


class PaymentType(str, enum.Enum):
    booking = "booking"
    monthly_rent = "monthly_rent"
    refund = "refund"
    commission = "commission"


class InvoiceStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    overdue = "overdue"
    cancelled = "cancelled"


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"))
    bed_id = Column(UUID(as_uuid=True), ForeignKey("room_beds.id", ondelete="SET NULL"))
    # Changed to SET NULL - preserve booking history when customer deletes account
    customer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    status = Column(ENUM('requested', 'accepted', 'paid', 'checked_in', 'active', 'completed', 'cancelled', 
                         'vacate_requested', 'vacated',
                         name='booking_status', create_type=False), default='requested', index=True)
    amount = Column(Integer, nullable=False)
    security_deposit = Column(Integer, nullable=False)
    maintenance_charge = Column(Integer, default=0)
    rent_paid = Column(Boolean, default=False)
    deposit_paid = Column(Boolean, default=False)
    maintenance_paid = Column(Boolean, default=False)
    last_payment_date = Column(DateTime(timezone=True))
    stay_type = Column(String(20), default="monthly")  # 'monthly' or 'daily'
    duration_days = Column(Integer)
    payment_id = Column(UUID(as_uuid=True))
    cancelled_at = Column(DateTime(timezone=True))
    cancel_reason = Column(Text)
    customer_documents = Column(ARRAY(Text))
    # Snapshot of customer info - preserved even if customer deletes account
    customer_snapshot = Column(JSONB, nullable=True)  # {name, email, phone}
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    property = relationship("Property", back_populates="bookings")
    room = relationship("Room", back_populates="bookings")
    customer = relationship("User", foreign_keys=[customer_id], back_populates="customer_bookings")
    owner = relationship("User", foreign_keys=[owner_id], back_populates="owner_bookings")
    payments = relationship("Payment", back_populates="booking")
    invoices = relationship("Invoice", back_populates="booking")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id = Column(UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="SET NULL"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Integer, nullable=False)
    currency = Column(String(3), default="INR")
    razorpay_payment_id = Column(String(255))
    razorpay_order_id = Column(String(255))
    status = Column(ENUM('pending', 'completed', 'failed', 'refunded', 'pending_verification',
                         name='payment_status', create_type=False), default='pending')
    type = Column(ENUM('booking', 'monthly_rent', 'refund', 'commission', 
                       name='payment_type', create_type=False), nullable=False)
    payment_method = Column(String(20), default="online")  # 'online' or 'offline'
    offline_reference = Column(Text)  # Transaction ID or notes for offline payment
    verified_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    payment_date = Column(DateTime(timezone=True))
    commission_amount = Column(Integer, default=0)
    payment_metadata = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    booking = relationship("Booking", back_populates="payments")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    booking_id = Column(UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False)
    month = Column(String(7), nullable=False)
    amount = Column(Integer, nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(ENUM('pending', 'paid', 'overdue', 'cancelled', 
                         name='invoice_status', create_type=False), default='pending')
    paid_at = Column(DateTime(timezone=True))
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    booking = relationship("Booking", back_populates="invoices")
