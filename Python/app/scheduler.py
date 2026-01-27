"""Background scheduler for rent reminders and other automated tasks."""
from datetime import datetime, timedelta
from typing import List
import logging

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.database import SessionLocal
from app.models import Booking, Payment, User, Profile, Property, Notification
import uuid

logger = logging.getLogger(__name__)


def get_db():
    """Get database session for scheduler tasks."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_rent_due_dates():
    """Check for upcoming rent due dates and create reminders for tenants."""
    logger.info("Running rent due date check...")
    
    db = SessionLocal()
    try:
        # Find active bookings with rent due in the next 7 days
        today = datetime.utcnow().date()
        week_from_now = today + timedelta(days=7)
        
        # Get all active bookings ending today or earlier
        active_bookings = db.query(Booking).filter(
            Booking.end_date <= today,
            Booking.status.in_(['active', 'checked_in', 'paid'])
        ).all()
        
        reminders_created = 0
        
        for booking in active_bookings:
            # Check if next rent is due
            if booking.end_date:
                end_date = booking.end_date.date() if hasattr(booking.end_date, 'date') else booking.end_date
                
                # If booking is ending within 7 days, send reminder
                days_until_due = (end_date - today).days
                
                if 0 <= days_until_due <= 7:
                    # Check if owner has payment reminders enabled
                    owner_profile = db.query(Profile).filter(Profile.user_id == booking.owner_id).first()
                    
                    if owner_profile and owner_profile.payment_reminders_enabled:
                        # Get property info
                        property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
                        property_title = property_obj.title if property_obj else "your PG"
                        
                        # Check if we already sent a reminder today for this booking
                        existing_reminder = db.query(Notification).filter(
                            Notification.user_id == booking.customer_id,
                            Notification.type == "payment_reminder",
                            Notification.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
                        ).first()
                        
                        if not existing_reminder:
                            # Create notification for tenant
                            notification = Notification(
                                id=uuid.uuid4(),
                                user_id=booking.customer_id,
                                title="Rent Payment Reminder",
                                message=f"Your rent for {property_title} is due in {days_until_due} days. Amount: ₹{booking.amount:,.0f}",
                                type="payment_reminder",
                                link="/bookings",
                                read=False
                            )
                            db.add(notification)
                            logger.info(f"Rent reminder created: Booking {booking.id} due in {days_until_due} days")
                            reminders_created += 1
        
        db.commit()
        logger.info(f"Created {reminders_created} rent reminders")
        
    except Exception as e:
        logger.error(f"Error in rent due date check: {e}")
        db.rollback()
    finally:
        db.close()


def check_pending_payments():
    """Check for overdue payments and send reminders."""
    logger.info("Running pending payment check...")
    
    db = SessionLocal()
    try:
        # Find payments that are pending for more than 3 days
        three_days_ago = datetime.utcnow() - timedelta(days=3)
        
        overdue_payments = db.query(Payment).filter(
            and_(
                Payment.status == 'pending',
                Payment.created_at < three_days_ago
            )
        ).all()
        
        for payment in overdue_payments:
            booking = db.query(Booking).filter(Booking.id == payment.booking_id).first()
            if booking:
                logger.info(f"Overdue payment reminder: Booking {booking.id}, Amount: {payment.amount}")
        
        logger.info(f"Found {len(overdue_payments)} overdue payments")
        
    except Exception as e:
        logger.error(f"Error in pending payment check: {e}")
    finally:
        db.close()


def cleanup_expired_bookings():
    """Mark expired booking requests as cancelled."""
    logger.info("Running expired booking cleanup...")
    
    db = SessionLocal()
    try:
        # Find booking requests older than 48 hours that are still pending
        two_days_ago = datetime.utcnow() - timedelta(hours=48)
        
        expired_bookings = db.query(Booking).filter(
            and_(
                Booking.status == 'requested',
                Booking.created_at < two_days_ago
            )
        ).all()
        
        for booking in expired_bookings:
            booking.status = 'expired'
            logger.info(f"Expired booking: {booking.id}")
        
        db.commit()
        logger.info(f"Marked {len(expired_bookings)} bookings as expired")
        
    except Exception as e:
        logger.error(f"Error in booking cleanup: {e}")
        db.rollback()
    finally:
        db.close()


def setup_scheduler(app):
    """Set up APScheduler with background jobs."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        
        scheduler = BackgroundScheduler()
        
        # Daily rent reminder check at 9 AM
        scheduler.add_job(
            check_rent_due_dates,
            CronTrigger(hour=9, minute=0),
            id="rent_reminder",
            name="Daily Rent Reminder Check",
            replace_existing=True
        )
        
        # Check pending payments twice daily
        scheduler.add_job(
            check_pending_payments,
            CronTrigger(hour="9,18", minute=0),
            id="payment_reminder",
            name="Pending Payment Check",
            replace_existing=True
        )
        
        # Cleanup expired bookings daily at midnight
        scheduler.add_job(
            cleanup_expired_bookings,
            CronTrigger(hour=0, minute=0),
            id="booking_cleanup",
            name="Expired Booking Cleanup",
            replace_existing=True
        )
        
        scheduler.start()
        logger.info("Background scheduler started")
        
        # Store scheduler on app for access
        app.state.scheduler = scheduler
        
        return scheduler
        
    except ImportError:
        logger.warning("APScheduler not installed. Background tasks disabled.")
        logger.warning("Install with: pip install apscheduler")
        return None
