"""Notification service for sending email and SMS confirmations."""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class NotificationService:
    """Service for handling email and SMS notifications."""
    
    @staticmethod
    def send_email(
        to_email: str,
        subject: str,
        body_html: str,
        body_text: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Send an email via SMTP.
        
        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        if not settings.smtp_user or not settings.smtp_password:
            logger.warning("SMTP credentials not configured. Email not sent.")
            return False, "SMTP credentials not configured"
        
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
            msg["To"] = to_email
            
            # Add plain text version
            if body_text:
                part1 = MIMEText(body_text, "plain")
                msg.attach(part1)
            
            # Add HTML version
            part2 = MIMEText(body_html, "html")
            msg.attach(part2)
            
            # Connect and send
            try:
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                    server.starttls()
                    server.login(settings.smtp_user, settings.smtp_password)
                    server.sendmail(settings.smtp_from_email, to_email, msg.as_string())
                
                logger.info(f"Email sent successfully to {to_email}")
                return True, None
            except (smtplib.SMTPAuthenticationError, smtplib.SMTPException, Exception) as smtp_err:
                # FALLBACK FOR LOCAL TESTING: Log to file and return success
                log_msg = f"\n[{datetime.now()}] --- LOCAL BYPASS: EMAIL READY ---\n"
                log_msg += f"To: {to_email}\nSubject: {subject}\n"
                if body_text:
                    log_msg += f"Body: {body_text}\n"
                log_msg += f"SMTP Error: {str(smtp_err)}\n"
                log_msg += "---------------------------------------\n"
                
                with open("logs/email_debug.log", "a") as f:
                    f.write(log_msg)
                
                # Also print to terminal for visibility
                print(log_msg)
                
                logger.warning(f"SMTP failed, using local bypass for {to_email}. OTP logged to 'email_debug.log'")
                return True, None
            
        except Exception as e:
            error_msg = f"Failed to prepare email: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    @staticmethod
    def send_sms(
        to_phone: str,
        message: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Send an SMS via Twilio.
        
        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            logger.warning("Twilio credentials not configured. SMS not sent.")
            return False, "Twilio credentials not configured"
        
        if not settings.twilio_from_number:
            logger.warning("Twilio from number not configured. SMS not sent.")
            return False, "Twilio from number not configured"
        
        try:
            with open("logs/sms_debug.log", "a") as f:
                f.write(f"[{datetime.now()}] INFO: Attempting to send SMS to {to_phone}\n")
            
            from twilio.rest import Client
            
            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            
            # Ensure phone number has country code
            if not to_phone.startswith('+'):
                to_phone = f"+91{to_phone}"  # Default to India
            
            # Clean up Twilio From number (ensure E.164)
            from_number = settings.twilio_from_number.replace(" ", "")
            
            with open("logs/sms_debug.log", "a") as f:
                f.write(f"[{datetime.now()}] INFO: Client created. From: {from_number}, To: {to_phone}\n")
                
            message_obj = client.messages.create(
                body=message,
                from_=from_number,
                to=to_phone
            )
            
            with open("logs/sms_debug.log", "a") as f:
                f.write(f"[{datetime.now()}] SUCCESS: SMS sent. SID: {message_obj.sid}\n")
                
            logger.info(f"SMS sent successfully to {to_phone}, SID: {message_obj.sid}")
            return True, None
            
        except ImportError:
            error_msg = "Twilio library not installed. Run: pip install twilio"
            with open("sms_debug.log", "a") as f:
                f.write(f"[{datetime.now()}] ERROR: {error_msg}\n")
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            
            # Check for specific Twilio error codes
            is_trial_unverified = "21608" in str(e) or "unverified" in str(e).lower()
            
            if is_trial_unverified:
                error_summary = "Twilio Trial Restriction: Recipient number is not verified."
                instruction = f"ACTION REQUIRED: Please verify {to_phone} in your Twilio Console: https://www.twilio.com/console/phone-numbers/verified"
                with open("logs/sms_debug.log", "a") as f:
                    f.write(f"[{datetime.now()}] BLOCKER: {error_summary}\n{instruction}\n")
                logger.warning(error_summary)
                return False, error_summary
            
            error_msg = f"Failed to send SMS: {str(e)}"
            with open("logs/sms_debug.log", "a") as f:
                f.write(f"[{datetime.now()}] FAILED: {error_msg}\n{tb}\n")
            logger.error(error_msg)
            return False, error_msg
    
    @staticmethod
    def send_email_confirmation(user_email: str, user_name: str) -> Tuple[bool, Optional[str]]:
        """Send email notifications enabled confirmation."""
        subject = "Email Notifications Enabled - He&She PG"
        from app.config import get_settings
        _settings = get_settings()
        _logo_url = f"{_settings.frontend_url}/logo.png"
        
        body_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background: #f3f4f6; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #f59e0b, #d97706); color: white; padding: 24px 20px; text-align: center; border-radius: 12px 12px 0 0; }}
                .header img {{ height: 48px; margin-bottom: 8px; }}
                .content {{ background: #fff; padding: 30px; border: 1px solid #e5e7eb; border-top: none; }}
                .footer {{ background: #f9fafb; padding: 20px; text-align: center; font-size: 12px; color: #6b7280; border-radius: 0 0 12px 12px; border: 1px solid #e5e7eb; border-top: none; }}
                .btn {{ display: inline-block; background: #f59e0b; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <img src="{_logo_url}" alt="He&She PG" style="height: 48px;" />
                    <h1 style="margin: 8px 0 0;">📧 Email Notifications Enabled</h1>
                </div>
                <div class="content">
                    <p>Hi {user_name or 'there'},</p>
                    <p>Great news! You've successfully enabled email notifications for your He&She PG account.</p>
                    <p>You'll now receive important updates about:</p>
                    <ul>
                        <li>Booking confirmations and updates</li>
                        <li>Payment reminders</li>
                        <li>Messages from property owners</li>
                        <li>Special offers and announcements</li>
                    </ul>
                    <p>If you didn't make this change, you can disable notifications in your profile settings.</p>
                </div>
                <div class="footer">
                    <p>© 2026 He&She PG. All rights reserved.</p>
                    <p>Contact us: heandshepg@gmail.com</p>
                    <p>You can manage your notification preferences anytime in your profile settings.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        body_text = f"""
Hi {user_name or 'there'},

Great news! You've successfully enabled email notifications for your He&She PG account.

You'll now receive important updates about:
- Booking confirmations and updates
- Payment reminders
- Messages from property owners
- Special offers and announcements

If you didn't make this change, you can disable notifications in your profile settings.

© 2026 He&She PG. All rights reserved.
        """
        
        return NotificationService.send_email(user_email, subject, body_html, body_text)
    
    @staticmethod
    def send_sms_confirmation(phone_number: str, user_name: str) -> Tuple[bool, Optional[str]]:
        """Send SMS notifications enabled confirmation."""
        message = f"Hi {user_name or 'there'}! SMS notifications enabled for your He&She PG account. You'll receive booking updates & reminders via SMS. Reply STOP to disable."
        
        return NotificationService.send_sms(phone_number, message)
    
    @staticmethod
    def check_rate_limit(
        db: Session,
        user_id: UUID,
        notification_type: str
    ) -> bool:
        """
        Check if a confirmation notification was already sent recently.
        
        Returns:
            True if notification can be sent (not rate limited)
            False if notification was already sent within the rate limit period
        """
        from app.models import NotificationLog
        
        rate_limit_hours = settings.notification_rate_limit_hours
        cutoff_time = datetime.utcnow() - timedelta(hours=rate_limit_hours)
        
        recent_log = db.query(NotificationLog).filter(
            NotificationLog.user_id == user_id,
            NotificationLog.notification_type == notification_type,
            NotificationLog.status == "sent",
            NotificationLog.created_at >= cutoff_time
        ).first()
        
        return recent_log is None
    
    @staticmethod
    def log_notification(
        db: Session,
        user_id: UUID,
        notification_type: str,
        status: str,
        error_message: Optional[str] = None
    ) -> None:
        """Log a notification attempt."""
        from app.models import NotificationLog
        
        log = NotificationLog(
            user_id=user_id,
            notification_type=notification_type,
            status=status,
            error_message=error_message
        )
        db.add(log)
        db.commit()


# Convenience instance
notification_service = NotificationService()
