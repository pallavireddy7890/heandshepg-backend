"""Background scheduler for rent reminders and other automated tasks."""
from datetime import datetime, timedelta
from typing import List
import logging
import asyncio

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.database import SessionLocal
from app.models import Booking, Payment, User, Profile, Property, Notification, Room, RoomBed, Vacation, VacationStatus
from app.services.wallet_service import WalletService
from app.services.vacancy import sync_room_vacancy
import uuid

logger = logging.getLogger(__name__)


def _send_notification_sync(
    db: Session,
    user_id,
    title: str,
    message: str,
    notification_type: str = "info",
    link: str = None,
):
    """Sync wrapper to create notification with email/SMS delivery."""
    from app.utils.notifications import create_notification
    
    coro = create_notification(
        db=db, user_id=user_id, title=title, message=message,
        notification_type=notification_type, link=link,
        send_external=True,
    )
    
    try:
        # If we're in an async context (like inside uvicorn/fastapi thread)
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        # No running event loop, safe to use asyncio.run
        asyncio.run(coro)


def get_db():
    """Get database session for scheduler tasks."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_rent_due_dates():
    """Check for upcoming rent due dates and create reminders for tenants.
    
    Logic:
    - Each tenant's rent is due on the same day of the month as their booking start_date.
    - The owner configures how many days before the due date to start sending reminders
      (rent_reminder_days_before, default 5).
    - Reminders are sent daily from N days before until the due date.
    - Example: Tenant joined on 15th, owner set 5 days before → reminders on 10th-15th.
    """
    logger.info("Running rent due date check...")
    
    db = SessionLocal()
    try:
        today = datetime.utcnow().date()
        reminders_created = 0
        
        # 1. Per-Tenant Monthly Rent Reminders
        # Find all active monthly bookings
        active_bookings = db.query(Booking).filter(
            Booking.stay_type == 'monthly',
            Booking.status.in_(['active', 'checked_in', 'paid'])
        ).all()
        
        for booking in active_bookings:
            # Get owner's reminder settings
            owner_profile = db.query(Profile).filter(
                Profile.user_id == booking.owner_id
            ).first()
            
            # Skip if owner disabled payment reminders
            if not owner_profile or not owner_profile.payment_reminders_enabled:
                continue
            
            # Tenant's rent due day = day of month they joined
            due_day = booking.start_date.day
            
            # Owner's configurable reminder window (default 5 days)
            days_before = owner_profile.rent_reminder_days_before or 5
            
            # Calculate the rent due date for the current month
            import calendar
            current_month_days = calendar.monthrange(today.year, today.month)[1]
            # Clamp due_day to max days in current month (e.g., 31st in Feb → 28th)
            actual_due_day = min(due_day, current_month_days)
            
            try:
                due_date = today.replace(day=actual_due_day)
            except ValueError:
                continue
            
            # Calculate how many days until due date
            days_until_due = (due_date - today).days
            
            # If due date already passed this month, check next month
            if days_until_due < 0:
                # Check next month's due date
                if today.month == 12:
                    next_month = today.replace(year=today.year + 1, month=1, day=1)
                else:
                    next_month = today.replace(month=today.month + 1, day=1)
                next_month_days = calendar.monthrange(next_month.year, next_month.month)[1]
                actual_due_day_next = min(due_day, next_month_days)
                try:
                    due_date = next_month.replace(day=actual_due_day_next)
                    days_until_due = (due_date - today).days
                except ValueError:
                    continue
            
            # Send reminder if within the reminder window (0 to days_before days before due)
            if 0 <= days_until_due <= days_before:
                # Check if we already sent a reminder today for this booking (tenant)
                existing_reminder = db.query(Notification).filter(
                    Notification.user_id == booking.customer_id,
                    Notification.type == "payment_reminder",
                    Notification.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
                ).first()
                
                if not existing_reminder:
                    property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
                    property_title = property_obj.title if property_obj else "your PG"
                    
                    # Get tenant name for owner notification
                    tenant_profile = db.query(Profile).filter(Profile.user_id == booking.customer_id).first()
                    tenant_name = tenant_profile.name if tenant_profile else "Tenant"
                    
                    # Construct dynamic message per tenant
                    if days_until_due == 0:
                        tenant_msg = f"⚠️ Your monthly rent for {property_title} is due TODAY! Amount: ₹{booking.amount:,.0f}"
                        owner_msg = f"⚠️ {tenant_name}'s rent for {property_title} is due TODAY! Amount: ₹{booking.amount:,.0f}"
                    elif days_until_due == 1:
                        tenant_msg = f"Reminder: Your monthly rent for {property_title} is due TOMORROW. Amount: ₹{booking.amount:,.0f}"
                        owner_msg = f"🔔 {tenant_name}'s rent for {property_title} is due TOMORROW. Amount: ₹{booking.amount:,.0f}"
                    else:
                        tenant_msg = f"Reminder: Your monthly rent for {property_title} is due in {days_until_due} days (on the {actual_due_day}th). Amount: ₹{booking.amount:,.0f}"
                        owner_msg = f"🔔 {tenant_name}'s rent for {property_title} is due in {days_until_due} days (on the {actual_due_day}th). Amount: ₹{booking.amount:,.0f}"
                    
                    # Tenant notification (with email + SMS)
                    _send_notification_sync(
                        db=db, user_id=booking.customer_id,
                        title="Monthly Rent Reminder", message=tenant_msg,
                        notification_type="payment_reminder", link="/bookings",
                    )
                    reminders_created += 1
                    
                    # Owner notification (check if not already sent today)
                    existing_owner_reminder = db.query(Notification).filter(
                        Notification.user_id == booking.owner_id,
                        Notification.type == "payment_reminder",
                        Notification.message.contains(tenant_name),
                        Notification.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
                    ).first()
                    
                    if not existing_owner_reminder:
                        _send_notification_sync(
                            db=db, user_id=booking.owner_id,
                            title="Tenant Rent Due Soon", message=owner_msg,
                            notification_type="payment_reminder", link="/owner/bookings",
                        )
                        reminders_created += 1
                    
                    logger.info(f"Rent reminder for Booking {booking.id}: {days_until_due} days until due")
        
        # 1b. Overdue Reminders (after due date, no payment made)
        for booking in active_bookings:
            owner_profile = db.query(Profile).filter(Profile.user_id == booking.owner_id).first()
            if not owner_profile or not owner_profile.payment_reminders_enabled:
                continue
            
            due_day = booking.start_date.day
            current_month_days = calendar.monthrange(today.year, today.month)[1]
            actual_due_day = min(due_day, current_month_days)
            
            try:
                due_date = today.replace(day=actual_due_day)
            except ValueError:
                continue
            
            days_overdue = (today - due_date).days
            
            # Only check overdue if between 1 and 15 days past due date
            if 1 <= days_overdue <= 15:
                # Check if rent was already paid for this billing cycle
                from datetime import date as date_type
                period_start, period_end = WalletService.get_billing_period(booking.start_date, today)
                already_paid = WalletService.check_payment_overlap(db, booking.id, period_start, period_end)
                
                if not already_paid:
                    # Check if overdue reminder already sent today (tenant)
                    existing_overdue = db.query(Notification).filter(
                        Notification.user_id == booking.customer_id,
                        Notification.type == "overdue_reminder",
                        Notification.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
                    ).first()
                    
                    if not existing_overdue:
                        property_obj = db.query(Property).filter(Property.id == booking.property_id).first()
                        property_title = property_obj.title if property_obj else "your PG"
                        tenant_profile = db.query(Profile).filter(Profile.user_id == booking.customer_id).first()
                        tenant_name = tenant_profile.name if tenant_profile else "Tenant"
                        
                        # Tenant overdue notification (with email + SMS)
                        _send_notification_sync(
                            db=db, user_id=booking.customer_id,
                            title="⚠️ Rent Overdue",
                            message=f"Your rent for {property_title} was due on the {actual_due_day}th ({days_overdue} days ago). Amount: ₹{booking.amount:,.0f}. Please pay immediately.",
                            notification_type="overdue_reminder", link="/bookings",
                        )
                        reminders_created += 1
                        
                        # Owner overdue notification
                        existing_owner_overdue = db.query(Notification).filter(
                            Notification.user_id == booking.owner_id,
                            Notification.type == "overdue_reminder",
                            Notification.message.contains(tenant_name),
                            Notification.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
                        ).first()
                        
                        if not existing_owner_overdue:
                            _send_notification_sync(
                                db=db, user_id=booking.owner_id,
                                title="🚨 Tenant Rent Overdue",
                                message=f"{tenant_name}'s rent for {property_title} is {days_overdue} days overdue (was due on the {actual_due_day}th). Amount: ₹{booking.amount:,.0f}",
                                notification_type="overdue_reminder", link="/owner/bookings",
                            )
                            reminders_created += 1
                        
                        logger.info(f"Overdue reminder for Booking {booking.id}: {days_overdue} days overdue")

        # 2. Stay-End Reminders (7 days before end_date)
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
                    
                    # Stay ending reminder (with email + SMS)
                    _send_notification_sync(
                        db=db, user_id=booking.customer_id,
                        title="Stay Ending / Rent Reminder",
                        message=f"Your stay at {property_title} is scheduled to end on {booking.end_date}. Please clear any pending dues (₹{booking.amount:,.0f}) if applicable.",
                        notification_type="payment_reminder", link="/bookings",
                    )
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
            # Maintenance reminder (with email + SMS)
            _send_notification_sync(
                db=db, user_id=owner.user_id,
                title="Monthly Maintenance Check",
                message="It's the 1st of the month! Routine inspection and maintenance check for your properties are recommended.",
                notification_type="maintenance_reminder", link="/owner/dashboard",
            )
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
    """Mark expired booking requests as cancelled and release holds."""
    logger.info("Running expired booking cleanup...")
    
    db = SessionLocal()
    try:
        # 1. Find booking requests (unaccepted) older than 48 hours
        two_days_ago = datetime.utcnow() - timedelta(hours=48)
        
        expired_requests = db.query(Booking).filter(
            and_(
                Booking.status == 'requested',
                Booking.created_at < two_days_ago
            )
        ).all()
        
        for booking in expired_requests:
            booking.status = 'cancelled'
            logger.info(f"Expired unaccepted booking request: {booking.id}")
            if booking.room_id:
                sync_room_vacancy(db, booking.room_id)
        
        # 2. Find accepted bookings (unpaid) older than 24 hours
        one_day_ago = datetime.utcnow() - timedelta(hours=24)
        
        unpaid_bookings = db.query(Booking).filter(
            and_(
                Booking.status == 'accepted',
                Booking.updated_at < one_day_ago
            )
        ).all()
        
        for booking in unpaid_bookings:
            booking.status = 'cancelled'
            logger.info(f"Expired accepted unpaid booking: {booking.id}")
            
            # Release the physical bed hold
            if booking.bed_id:
                bed = db.query(RoomBed).filter(RoomBed.id == booking.bed_id).first()
                if bed:
                    bed.status = "available"
                    bed.current_tenant_id = None
            
            # Recalculate room vacancy
            if booking.room_id:
                sync_room_vacancy(db, booking.room_id)
                
            # Send notifications
            try:
                _send_notification_sync(
                    db=db,
                    user_id=booking.customer_id,
                    title="Booking Expired",
                    message="Your booking request was accepted but has expired due to non-payment within 24 hours.",
                    notification_type="info",
                    link="/bookings"
                )
                _send_notification_sync(
                    db=db,
                    user_id=booking.owner_id,
                    title="Booking Expired (Unpaid)",
                    message="An accepted booking request expired because the tenant did not pay within 24 hours. The bed is now available.",
                    notification_type="info",
                    link="/owner/bookings"
                )
            except Exception as e:
                logger.warning(f"Failed to send expiration notifications for booking {booking.id}: {e}")
        
        db.commit()
        logger.info(f"Marked {len(expired_requests)} unaccepted requests and {len(unpaid_bookings)} unpaid bookings as cancelled due to expiration")
        
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
            
            # Notify user: Stay ended (with email + SMS)
            _send_notification_sync(
                db=db, user_id=booking.customer_id,
                title="Stay Ended",
                message=f"Your stay at {property_title}{room_info} has ended. Thank you for staying with us!",
                notification_type="stay_ended", link="/bookings",
            )
            
            # Notify owner: Bed vacated (with email + SMS)
            _send_notification_sync(
                db=db, user_id=booking.owner_id,
                title="Bed Vacated",
                message=f"Bed vacated at {property_title}{room_info}. Vacancy has been increased.",
                notification_type="bed_vacated", link="/owner/dashboard",
            )
            
            completed_count += 1
            logger.info(f"Completed booking {booking.id} - stay ended")
        
        db.commit()
        logger.info(f"Completed {completed_count} ended stays")
        
    except Exception as e:
        logger.error(f"Error in ended stays completion: {e}")
        db.rollback()
    finally:
        db.close()


def update_vacation_statuses():
    """Update vacation statuses based on the current date.
    
    Logic:
    - upcoming -> active: if start_date <= today
    - active -> completed: if end_date < today
    """
    logger.info("Running vacation status update check...")
    db = SessionLocal()
    try:
        today = datetime.utcnow().date()
        
        # 1. Start upcoming vacations
        upcoming_vacations = db.query(Vacation).filter(
            Vacation.status == VacationStatus.upcoming,
            Vacation.start_date <= today
        ).all()
        
        started_count = 0
        for v in upcoming_vacations:
            v.status = VacationStatus.active
            started_count += 1
            logger.info(f"Vacation started: {v.id} (Tenant: {v.tenant_id})")
            
        # 2. Complete ended vacations
        active_vacations = db.query(Vacation).filter(
            Vacation.status == VacationStatus.active,
            Vacation.end_date < today
        ).all()
        
        completed_count = 0
        for v in active_vacations:
            v.status = VacationStatus.completed
            completed_count += 1
            logger.info(f"Vacation completed: {v.id} (Tenant: {v.tenant_id})")
            
        if started_count > 0 or completed_count > 0:
            db.commit()
            logger.info(f"Updated {started_count} vacations to ACTIVE and {completed_count} to COMPLETED")
        else:
            logger.info("No vacation status updates needed")
            
    except Exception as e:
        logger.error(f"Error in vacation status update: {e}")
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
        
        # Update vacation statuses daily at 12:05 AM
        scheduler.add_job(
            update_vacation_statuses,
            CronTrigger(hour=0, minute=5),
            id="update_vacation_statuses",
            name="Update Vacation Statuses",
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
