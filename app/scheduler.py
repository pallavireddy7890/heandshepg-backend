"""Background scheduler for rent reminders and other automated tasks."""
from datetime import datetime, timedelta
from typing import List
import logging

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.database import SessionLocal
from app.models import Booking, Payment, User, Profile, Property, Notification, Room
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
        today = datetime.utcnow().date()
        reminders_created = 0
        
        # 1. Cyclic Monthly Reminders
        # Find all owners who have payment reminders enabled
        owner_profiles = db.query(Profile).filter(
            and_(
                Profile.payment_reminders_enabled == True,
                Profile.rent_reminder_day == today.day
            )
        ).all()
        
        for owner_profile in owner_profiles:
            # Find all active monthly bookings for this owner
            active_monthly = db.query(Booking).filter(
                Booking.owner_id == owner_profile.user_id,
                Booking.stay_type == 'monthly',
                Booking.status.in_(['active', 'checked_in', 'paid'])
            ).all()
            
            for booking in active_monthly:
                # Check if we already sent a reminder today for this booking
                existing_reminder = db.query(Notification).filter(
                    Notification.user_id == booking.customer_id,
                    Notification.type == "payment_reminder",
                    Notification.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
                ).first()
                
                if not existing_reminder:
                    property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
                    property_title = property_obj.title if property_obj else "your PG"
                    
                    # Construct message
                    due_day = owner_profile.rent_due_day or 5
                    if owner_profile.rent_reminder_message:
                        message = owner_profile.rent_reminder_message.replace("{property}", property_title)
                        message = message.replace("{amount}", f"₹{booking.amount:,.0f}")
                        message = message.replace("{due_day}", str(due_day))
                    else:
                        message = f"Reminder: Your monthly rent for {property_title} is due on the {due_day}th. Amount: ₹{booking.amount:,.0f}"
                    
                    notification = Notification(
                        id=uuid.uuid4(),
                        user_id=booking.customer_id,
                        title="Monthly Rent Reminder",
                        message=message,
                        type="payment_reminder",
                        link="/bookings",
                        read=False
                    )
                    db.add(notification)
                    reminders_created += 1
                    logger.info(f"Cyclic rent reminder created for Booking {booking.id} (Owner {owner_profile.user_id})")

        # 2. Stay-End Reminders
        week_from_now = today + timedelta(days=7)
        ending_bookings = db.query(Booking).filter(
            Booking.end_date >= today,
            Booking.end_date <= week_from_now,
            Booking.status.in_(['active', 'checked_in', 'paid'])
        ).all()
        
        for booking in ending_bookings:
            owner_profile = db.query(Profile).filter(Profile.user_id == booking.owner_id).first()
            if owner_profile and owner_profile.payment_reminders_enabled:
                existing_reminder = db.query(Notification).filter(
                    Notification.user_id == booking.customer_id,
                    Notification.type == "payment_reminder",
                    Notification.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
                ).first()
                
                if not existing_reminder:
                    property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
                    property_title = property_obj.title if property_obj else "your stay"
                    
                    notification = Notification(
                        id=uuid.uuid4(),
                        user_id=booking.customer_id,
                        title="Stay Ending / Rent Reminder",
                        message=f"Your stay at {property_title} is scheduled to end on {booking.end_date}. Please clear any pending dues (₹{booking.amount:,.0f}) if applicable.",
                        type="payment_reminder",
                        link="/bookings",
                        read=False
                    )
                    db.add(notification)
                    reminders_created += 1
        
        db.commit()
        logger.info(f"Created {reminders_created} total rent reminders")
    except Exception as e:
        logger.error(f"Error in rent due date check: {e}")
        db.rollback()
    finally:
        db.close()


def check_maintenance_reminders():
    """Send monthly maintenance reminders to owners (1st of every month)."""
    logger.info("Running maintenance reminder check...")
    db = SessionLocal()
    try:
        today = datetime.utcnow().date()
        # Trigger on 1st of month
        if today.day != 1:
            return
            
        owners = db.query(Profile).filter(Profile.maintenance_reminders_enabled == True).all()
        reminders_sent = 0
        
        for owner in owners:
            notification = Notification(
                id=uuid.uuid4(),
                user_id=owner.user_id,
                title="Monthly Maintenance Check",
                message="It's the 1st of the month! Routine inspection and maintenance check for your properties are recommended.",
                type="maintenance_reminder",
                link="/owner/dashboard",
                read=False
            )
            db.add(notification)
            reminders_sent += 1
            
        db.commit()
        logger.info(f"Sent {reminders_sent} maintenance reminders to owners.")
    except Exception as e:
        logger.error(f"Error in maintenance reminder check: {e}")
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


def complete_ended_stays():
    """Auto-complete bookings where end_date has passed.
    
    This job:
    1. Finds active bookings where end_date < today
    2. Marks them as 'completed'
    3. Notifies user: "Your stay has ended"
    4. Notifies owner: "Bed vacated, vacancy increased"
    """
    logger.info("Running ended stays completion...")
    
    db = SessionLocal()
    try:
        today = datetime.utcnow().date()
        
        # Find active bookings that have ended
        ended_bookings = db.query(Booking).filter(
            Booking.end_date < today,
            Booking.status.in_(['active', 'paid', 'checked_in'])
        ).all()
        
        completed_count = 0
        
        for booking in ended_bookings:
            # Mark as completed
            booking.status = 'completed'
            
            # Get property and room info
            property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
            property_title = property_obj.title if property_obj else "Property"
            
            room = db.query(Room).filter(Room.id == booking.room_id).first() if booking.room_id else None
            room_info = f" ({room.room_type})" if room else ""
            
            # Notify user: Stay ended
            user_notification = Notification(
                id=uuid.uuid4(),
                user_id=booking.customer_id,
                title="Stay Ended",
                message=f"Your stay at {property_title}{room_info} has ended. Thank you for staying with us!",
                type="stay_ended",
                link="/bookings",
                read=False
            )
            db.add(user_notification)
            
            # Notify owner: Bed vacated
            owner_notification = Notification(
                id=uuid.uuid4(),
                user_id=booking.owner_id,
                title="Bed Vacated",
                message=f"Bed vacated at {property_title}{room_info}. Vacancy has been increased.",
                type="bed_vacated",
                link="/owner/dashboard",
                read=False
            )
            db.add(owner_notification)
            
            completed_count += 1
            logger.info(f"Completed booking {booking.id} - stay ended")
        
        db.commit()
        logger.info(f"Completed {completed_count} ended stays")
        
    except Exception as e:
        logger.error(f"Error in ended stays completion: {e}")
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

        # Monthly maintenance reminder at 10 AM on the 1st
        scheduler.add_job(
            check_maintenance_reminders,
            CronTrigger(day=1, hour=10, minute=0),
            id="maintenance_reminder_job",
            name="Monthly Maintenance Check",
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
        
        # Complete ended stays daily at 1 AM
        scheduler.add_job(
            complete_ended_stays,
            CronTrigger(hour=1, minute=0),
            id="complete_ended_stays",
            name="Complete Ended Stays",
            replace_existing=True
        )
        
        scheduler.start()
        logger.info("Background scheduler started")
        
        # Store scheduler on app for access
        app.state.scheduler = scheduler
        
        return scheduler
        
    except ImportError:
        logger.warning("APScheduler not installed. Background tasks disabled.")
        return None
