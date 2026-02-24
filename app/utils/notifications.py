"""Notification helper utilities."""
from sqlalchemy.orm import Session
from app.models import Notification
import uuid


async def create_notification(
    db: Session,
    user_id: uuid.UUID,
    title: str,
    message: str,
    notification_type: str = "info",
    link: str = None,
    reference_id: str = None,
    reference_type: str = None
) -> Notification:
    """
    Create a notification for a user and broadcast via WebSocket.
    """
    notification = Notification(
        id=uuid.uuid4(),
        user_id=user_id,
        title=title,
        message=message,
        type=notification_type,
        link=link or ("/owner/bookings" if reference_type == "booking" else None),
        read=False
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    
    # Broadcast via WebSocket
    try:
        from app.routers.websocket import notification_manager
        await notification_manager.send_personal_message({
            "type": "notification",
            "id": str(notification.id),
            "title": notification.title,
            "message": notification.message,
            "notification_type": notification.type,
            "link": notification.link,
            "created_at": notification.created_at.isoformat() if notification.created_at else None
        }, str(user_id))
    except Exception as e:
        import logging
        logging.warning(f"Failed to broadcast notification: {e}")
        
    return notification


async def notify_vacate_request(db: Session, owner_id: uuid.UUID, customer_name: str, property_title: str, booking_id: uuid.UUID):
    """Notify owner when a tenant requests to vacate."""
    return await create_notification(
        db=db,
        user_id=owner_id,
        title="🏠 Vacate Request",
        message=f"{customer_name} has requested to vacate from {property_title}. Please review and process their checkout.",
        notification_type="vacate_request",
        link="/owner/bookings?tab=requests",
        reference_id=str(booking_id),
        reference_type="booking"
    )


async def notify_booking_created(db: Session, owner_id: uuid.UUID, customer_name: str, property_title: str, booking_id: uuid.UUID):
    """Notify owner when a new booking is created."""
    return await create_notification(
        db=db,
        user_id=owner_id,
        title="New Booking Request",
        message=f"{customer_name} has requested to book {property_title}",
        notification_type="booking",
        link="/owner/bookings?tab=requests"
    )


async def notify_booking_accepted(db: Session, customer_id: uuid.UUID, property_title: str, booking_id: uuid.UUID):
    """Notify customer when their booking is accepted."""
    return await create_notification(
        db=db,
        user_id=customer_id,
        title="Booking Accepted!",
        message=f"Your booking for {property_title} has been accepted. You can now proceed with payment.",
        notification_type="success",
        link="/bookings"
    )


async def notify_booking_rejected(db: Session, customer_id: uuid.UUID, property_title: str):
    """Notify customer when their booking is rejected."""
    return await create_notification(
        db=db,
        user_id=customer_id,
        title="Booking Declined",
        message=f"Unfortunately, your booking for {property_title} was not approved.",
        notification_type="warning",
        link="/bookings"
    )


async def notify_payment_received(db: Session, owner_id: uuid.UUID, amount: float, customer_name: str):
    """Notify owner when a payment is received."""
    return await create_notification(
        db=db,
        user_id=owner_id,
        title="Payment Received",
        message=f"₹{amount:,.0f} received from {customer_name}. Please verify the OTP to complete the transaction.",
        notification_type="payment",
        link="/owner/wallet"
    )


async def notify_payment_verified(db: Session, customer_id: uuid.UUID, amount: float, property_title: str):
    """Notify customer when their payment is verified."""
    return await create_notification(
        db=db,
        user_id=customer_id,
        title="Payment Verified",
        message=f"Your payment of ₹{amount:,.0f} for {property_title} has been verified successfully.",
        notification_type="success",
        link="/bookings"
    )


async def notify_new_message(db: Session, user_id: uuid.UUID, sender_name: str, property_title: str = None):
    """Notify user when they receive a new message."""
    message_text = f"New message from {sender_name}"
    if property_title:
        message_text += f" regarding {property_title}"
    
    return await create_notification(
        db=db,
        user_id=user_id,
        title="New Message",
        message=message_text,
        notification_type="message",
        link="/messages"
    )


def get_admin_user_ids(db: Session) -> list:
    """Get all admin user IDs for broadcasting notifications."""
    from app.models import UserRole, AppRole
    admin_roles = db.query(UserRole).filter(UserRole.role == AppRole.admin).all()
    return [role.user_id for role in admin_roles]


async def notify_admins_owner_signup(db: Session, owner_name: str, owner_email: str):
    """Notify all admins when a new owner signs up."""
    admin_ids = get_admin_user_ids(db)
    for admin_id in admin_ids:
        await create_notification(
            db=db,
            user_id=admin_id,
            title="🏢 New Owner Registration",
            message=f"New owner registered: {owner_name} ({owner_email}). Review their application in the admin dashboard.",
            notification_type="info",
            link="/admin?tab=applications"
        )


async def notify_admins_payment_completed(db: Session, customer_name: str, owner_name: str, amount: float, property_title: str):
    """Notify all admins when a payment is completed."""
    admin_ids = get_admin_user_ids(db)
    for admin_id in admin_ids:
        await create_notification(
            db=db,
            user_id=admin_id,
            title="💰 Payment Completed",
            message=f"{customer_name} paid ₹{amount:,.0f} to {owner_name} for {property_title}.",
            notification_type="payment",
            link="/admin/payments"
        )
