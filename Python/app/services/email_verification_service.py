"""Email verification service for OTP-based signup verification."""
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from app.models.email_verification import EmailVerification
from app.models.user import AppRole
from app.utils.security import get_password_hash
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class EmailVerificationService:
    """Service for handling email verification during signup."""
    
    @staticmethod
    def generate_otp() -> str:
        """Generate a secure 6-digit OTP."""
        return ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    
    @staticmethod
    def check_rate_limit(db: Session, email: str) -> Tuple[bool, Optional[str]]:
        """
        Check if email has exceeded OTP request rate limit.
        
        Returns:
            Tuple of (allowed: bool, error_message: Optional[str])
        """
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        recent_count = db.query(EmailVerification).filter(
            EmailVerification.email == email.lower(),
            EmailVerification.created_at >= one_hour_ago
        ).count()
        
        if recent_count >= EmailVerification.MAX_OTPS_PER_HOUR:
            return False, f"Too many verification attempts. Please try again in 1 hour."
        
        return True, None
    
    @staticmethod
    def create_verification(
        db: Session,
        email: str,
        name: str,
        password: str,
        role: str = "customer",
        phone: str = None
    ) -> Tuple[Optional[EmailVerification], Optional[str]]:
        """
        Create a new email verification record and send OTP.
        
        Returns:
            Tuple of (verification: Optional[EmailVerification], error: Optional[str])
        """
        email_lower = email.lower().strip()
        
        # Check rate limit
        allowed, error = EmailVerificationService.check_rate_limit(db, email_lower)
        if not allowed:
            return None, error
        
        # Delete any existing pending verifications for this email
        db.query(EmailVerification).filter(
            EmailVerification.email == email_lower
        ).delete()
        db.commit()
        
        # Generate OTP and hash password
        otp_code = EmailVerificationService.generate_otp()
        logger.info(f"Generated OTP for {email_lower}: '{otp_code}'")
        hashed_password = get_password_hash(password)
        
        # Map role string to AppRole enum
        role_enum = AppRole.customer
        if role == "owner":
            role_enum = AppRole.owner
        elif role == "admin":
            role_enum = AppRole.customer  # Admin cannot self-assign
        
        # Create verification record
        verification = EmailVerification(
            email=email_lower,
            otp_code=otp_code,
            name=name,
            phone=phone,
            hashed_password=hashed_password,
            role=role_enum,
            expires_at=EmailVerification.get_expiry_time()
        )
        db.add(verification)
        db.commit()
        db.refresh(verification)
        
        logger.info(f"Stored verification record - email: {email_lower}, OTP in record: '{verification.otp_code}'")
        
        # Send OTP email
        success, email_error = EmailVerificationService.send_otp_email(
            email_lower, otp_code, name
        )
        
        if not success:
            logger.error(f"Failed to send OTP email to {email_lower}: {email_error}")
            # Don't delete the verification - user can retry
            return verification, f"Failed to send verification email: {email_error}"
        
        logger.info(f"Verification OTP sent to {email_lower}")
        return verification, None
    
    @staticmethod
    def send_otp_email(email: str, otp_code: str, name: str) -> Tuple[bool, Optional[str]]:
        """Send OTP verification email."""
        subject = "Verify Your Email - He&She PG"
        
        body_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #f59e0b, #d97706); color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #fff; padding: 30px; border: 1px solid #e5e7eb; border-top: none; }}
                .otp-box {{ background: #fef3c7; border: 2px dashed #f59e0b; padding: 20px; text-align: center; margin: 20px 0; border-radius: 8px; }}
                .otp-code {{ font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #d97706; }}
                .footer {{ background: #f9fafb; padding: 20px; text-align: center; font-size: 12px; color: #6b7280; border-radius: 0 0 8px 8px; }}
                .warning {{ color: #dc2626; font-size: 14px; margin-top: 15px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📧 Verify Your Email</h1>
                </div>
                <div class="content">
                    <p>Hi {name or 'there'},</p>
                    <p>Thank you for signing up with He&She PG! Please use the following OTP to verify your email address:</p>
                    
                    <div class="otp-box">
                        <div class="otp-code">{otp_code}</div>
                    </div>
                    
                    <p><strong>This OTP is valid for 10 minutes.</strong></p>
                    
                    <p class="warning">⚠️ If you didn't request this verification, please ignore this email.</p>
                </div>
                <div class="footer">
                    <p>© 2026 He&She PG. All rights reserved.</p>
                    <p>This is an automated message. Please do not reply.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        body_text = f"""
Hi {name or 'there'},

Thank you for signing up with He&She PG!

Your verification code is: {otp_code}

This OTP is valid for 10 minutes.

If you didn't request this verification, please ignore this email.

© 2026 He&She PG. All rights reserved.
        """
        
        return NotificationService.send_email(email, subject, body_html, body_text)
    
    @staticmethod
    def verify_otp(
        db: Session,
        email: str,
        otp_code: str
    ) -> Tuple[Optional[EmailVerification], Optional[str]]:
        """
        Verify OTP code for an email.
        
        Returns:
            Tuple of (verification: Optional[EmailVerification], error: Optional[str])
        """
        email_lower = email.lower().strip()
        # Clean the OTP code - strip whitespace and ensure string format
        otp_code_clean = str(otp_code).strip() if otp_code else ""
        
        logger.info(f"Verifying OTP for email: {email_lower}, OTP received: '{otp_code_clean}'")
        
        # Find the verification record
        verification = db.query(EmailVerification).filter(
            EmailVerification.email == email_lower,
            EmailVerification.is_verified == False
        ).first()
        
        if not verification:
            logger.warning(f"No pending verification found for email: {email_lower}")
            return None, "No pending verification found. Please sign up again."
        
        logger.info(f"Found verification record - stored OTP: '{verification.otp_code}', attempts: {verification.attempts}")
        
        # Check if expired
        if verification.is_expired():
            logger.warning(f"OTP expired for email: {email_lower}")
            db.delete(verification)
            db.commit()
            return None, "OTP has expired. Please request a new one."
        
        # Check if max attempts exceeded
        if verification.has_max_attempts():
            logger.warning(f"Max attempts reached for email: {email_lower}")
            return None, "Too many failed attempts. Please request a new OTP."
        
        # Clean the stored OTP for comparison
        stored_otp_clean = str(verification.otp_code).strip() if verification.otp_code else ""
        
        # Verify OTP - compare cleaned versions
        if stored_otp_clean != otp_code_clean:
            logger.warning(f"OTP mismatch for email: {email_lower} - stored: '{stored_otp_clean}' vs received: '{otp_code_clean}'")
            verification.increment_attempts()
            db.commit()
            remaining = EmailVerification.MAX_ATTEMPTS - verification.attempts
            if remaining > 0:
                return None, f"Invalid OTP. {remaining} attempts remaining."
            else:
                return None, "Too many failed attempts. Please request a new OTP."
        
        logger.info(f"OTP verified successfully for email: {email_lower}")
        
        # Mark as verified
        verification.is_verified = True
        db.commit()
        
        return verification, None
    
    @staticmethod
    def resend_otp(db: Session, email: str) -> Tuple[bool, Optional[str]]:
        """
        Resend OTP to an email address.
        
        Returns:
            Tuple of (success: bool, error: Optional[str])
        """
        email_lower = email.lower().strip()
        
        # Find existing verification
        verification = db.query(EmailVerification).filter(
            EmailVerification.email == email_lower,
            EmailVerification.is_verified == False
        ).first()
        
        if not verification:
            return False, "No pending verification found. Please sign up again."
        
        # Check rate limit
        allowed, error = EmailVerificationService.check_rate_limit(db, email_lower)
        if not allowed:
            return False, error
        
        # Generate new OTP
        new_otp = EmailVerificationService.generate_otp()
        verification.otp_code = new_otp
        verification.attempts = 0
        verification.expires_at = EmailVerification.get_expiry_time()
        db.commit()
        
        # Send new OTP
        success, email_error = EmailVerificationService.send_otp_email(
            email_lower, new_otp, verification.name
        )
        
        if not success:
            return False, f"Failed to send verification email: {email_error}"
        
        logger.info(f"Resent verification OTP to {email_lower}")
        return True, None
    
    @staticmethod
    def cleanup_expired(db: Session) -> int:
        """
        Delete expired verification records.
        
        Returns:
            Number of records deleted
        """
        deleted = db.query(EmailVerification).filter(
            EmailVerification.expires_at < datetime.utcnow()
        ).delete()
        db.commit()
        
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired email verifications")
        
        return deleted
    
    @staticmethod
    def get_verification_data(verification: EmailVerification) -> dict:
        """Get the user data from a verified EmailVerification record."""
        return {
            "email": verification.email,
            "name": verification.name,
            "phone": verification.phone,
            "hashed_password": verification.hashed_password,
            "role": verification.role
        }


# Convenience instance
email_verification_service = EmailVerificationService()
