"""Notification helper utilities."""
from datetime import datetime
from sqlalchemy.orm import Session
from app.models import Notification, User, Profile
import uuid
import logging
import asyncio
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


async def create_notification(
    db: Session,
    user_id: uuid.UUID,
    title: str,
    message: str,
    notification_type: str = "info",
    link: str = None,
    reference_id: str = None,
    reference_type: str = None,
    send_external: bool = True  # Default to True to fulfill omnichannel request
) -> Notification:
    """
    Create a notification for a user, broadcast via WebSocket, and optionally send via Email/SMS.
    Runs the blocking SMTP/Twilio network operations asynchronously in worker threads.
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
    
    # Try to commit, but don't fail if we can't save the log (e.g. DB busy)
    try:
        db.commit()
        db.refresh(notification)
    except Exception as e:
        logger.warning(f"Failed to save notification record: {e}")
    
    # 1. Broadcast via WebSocket
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
        logger.warning(f"Failed to broadcast notification: {e}")
    
    # 2. Omnichannel Delivery (Email + SMS) - Executed asynchronously in threads to prevent request blocking
    if send_external:
        try:
            profile = db.query(Profile).filter(Profile.user_id == user_id).first()
            user = db.query(User).filter(User.id == user_id).first()
            
            if profile and user:
                # Send Email if enabled and email exists
                if profile.email_notifications and user.email:
                    from app.config import get_settings
                    settings = get_settings()
                    
                    email_body = f"""
                    <html>
                    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background: #f3f4f6;">
                        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <div style="background: linear-gradient(135deg, #f59e0b, #d97706); color: white; padding: 24px 20px; text-align: center; border-radius: 12px 12px 0 0;">
                            <h1 style="margin: 0; font-size: 28px; color: white;">🏠 He&She PG</h1>
                            <h2 style="margin: 8px 0 0; font-size: 20px; color: white; font-weight: normal; opacity: 0.9;">{title}</h2>
                        </div>
                        <div style="padding: 24px; border: 1px solid #e5e7eb; border-top: none; background: #fff;">
                            <p>Hi {profile.name or 'there'},</p>
                            <p>{message}</p>
                            {f'<p><a href="{settings.frontend_url}{link}" style="color: #f59e0b; font-weight: bold; text-decoration: none;">View Details</a></p>' if link else ''}
                        </div>
                        <div style="background: #f9fafb; padding: 16px; text-align: center; font-size: 12px; color: #6b7280; border-radius: 0 0 12px 12px; border: 1px solid #e5e7eb; border-top: none;">
                            <p style="margin: 4px 0;">&copy; {datetime.now().year} He&She PG. All rights reserved.</p>
                            <p style="margin: 4px 0;">Contact us: heandshepg@gmail.com</p>
                        </div>
                        </div>
                    </body>
                    </html>
                    """
                    # Schedule sending in a background thread to prevent API blocking
                    asyncio.create_task(asyncio.to_thread(
                        NotificationService.send_email,
                        to_email=user.email,
                        subject=f"He&She PG: {title}",
                        body_html=email_body,
                        body_text=f"He&She PG: {message}"
                    ))
                
                # Send SMS if enabled and phone exists
                if profile.sms_notifications and profile.phone:
                    sms_message = f"He&She PG: {title} - {message}"
                    # Trim long messages for SMS
                    if len(sms_message) > 160:
                        sms_message = sms_message[:157] + "..."
                    
                    # Schedule sending in a background thread to prevent API blocking
                    asyncio.create_task(asyncio.to_thread(
                        NotificationService.send_sms,
                        to_phone=profile.phone,
                        message=sms_message
                    ))
                    
        except Exception as e:
            logger.warning(f"Failed to dispatch external omnichannel notifications: {e}")
        
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


async def notify_payment_received(db: Session, owner_id: uuid.UUID, amount: float, customer_name: str, property_title: str = None):
    """Notify owner when a payment is received."""
    msg = f"Payment of ₹{amount:,.0f} received from {customer_name}"
    if property_title:
        msg += f" for {property_title}"
    msg += ". Please verify the OTP to complete the transaction."
    
    return await create_notification(
        db=db,
        user_id=owner_id,
        title="💰 Payment Received",
        message=msg,
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
            message=f"ADMIN ALERT: {customer_name} paid ₹{amount:,.0f} to {owner_name} for {property_title}.",
            notification_type="payment",
            link="/admin/payments"
        )


async def notify_kyc_status(db: Session, user_id: uuid.UUID, status: str, admin_notes: str = None):
    """Notify owner about their KYC status (Omnichannel: Web, Email, SMS)."""
    title = "KYC Approved! 🎉" if status == "approved" else "KYC Application Update"
    msg = "Your owner account has been approved. You can now start listing your properties."
    if status != "approved":
        msg = f"Your owner application was not approved. Reason: {admin_notes or 'Please contact support.'}"
        
    return await create_notification(
        db=db,
        user_id=user_id,
        title=title,
        message=msg,
        notification_type="info" if status == "approved" else "warning",
        link="/profile",
        send_external=True
    )
