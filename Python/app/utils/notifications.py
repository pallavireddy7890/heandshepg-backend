"""Notification helper utilities."""
from sqlalchemy.orm import Session
from app.models import Notification
import uuid


def create_notification(
    db: Session,
    user_id: uuid.UUID,
    title: str,
    message: str,
    notification_type: str = "info",
    link: str = None
) -> Notification:
    """
    Create a notification for a user.
    
    Args:
        db: Database session
        user_id: UUID of the user to notify
        title: Notification title
        message: Notification message
        notification_type: Type of notification (info, success, warning, booking, payment)
        link: Optional link to navigate to when clicked
    
    Returns:
        Created notification object
    """
    notification = Notification(
        id=uuid.uuid4(),
        user_id=user_id,
        title=title,
        message=message,
        type=notification_type,
        link=link,
        read=False
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def notify_booking_created(db: Session, owner_id: uuid.UUID, customer_name: str, property_title: str, booking_id: uuid.UUID):
    """Notify owner when a new booking is created."""
    return create_notification(
        db=db,
        user_id=owner_id,
        title="New Booking Request",
        message=f"{customer_name} has requested to book {property_title}",
        notification_type="booking",
        link=f"/owner/bookings"
    )


def notify_booking_accepted(db: Session, customer_id: uuid.UUID, property_title: str, booking_id: uuid.UUID):
    """Notify customer when their booking is accepted."""
    return create_notification(
        db=db,
        user_id=customer_id,
        title="Booking Accepted!",
        message=f"Your booking for {property_title} has been accepted. You can now proceed with payment.",
        notification_type="success",
        link="/bookings"
    )


def notify_booking_rejected(db: Session, customer_id: uuid.UUID, property_title: str):
    """Notify customer when their booking is rejected."""
    return create_notification(
        db=db,
        user_id=customer_id,
        title="Booking Declined",
        message=f"Unfortunately, your booking for {property_title} was not approved.",
        notification_type="warning",
        link="/bookings"
    )


def notify_payment_received(db: Session, owner_id: uuid.UUID, amount: float, customer_name: str):
    """Notify owner when a payment is received."""
    return create_notification(
        db=db,
        user_id=owner_id,
        title="Payment Received",
        message=f"₹{amount:,.0f} received from {customer_name}. Please verify the OTP to complete the transaction.",
        notification_type="payment",
        link="/owner/wallet"
    )


def notify_payment_verified(db: Session, customer_id: uuid.UUID, amount: float, property_title: str):
    """Notify customer when their payment is verified."""
    return create_notification(
        db=db,
        user_id=customer_id,
        title="Payment Verified",
        message=f"Your payment of ₹{amount:,.0f} for {property_title} has been verified successfully.",
        notification_type="success",
        link="/bookings"
    )


def notify_new_message(db: Session, user_id: uuid.UUID, sender_name: str, property_title: str = None):
    """Notify user when they receive a new message."""
    message_text = f"New message from {sender_name}"
    if property_title:
        message_text += f" regarding {property_title}"
    
    return create_notification(
        db=db,
        user_id=user_id,
        title="New Message",
        message=message_text,
        notification_type="message",
        link="/messages"
    )
