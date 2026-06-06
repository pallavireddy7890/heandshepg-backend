"""Password reset OTP model."""
import uuid
from datetime import datetime, timedelta
from sqlalchemy import Column, String, Boolean, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class PasswordResetOTP(Base):
    """
    Stores OTPs generated for password reset via phone.
    """
    __tablename__ = "password_reset_otps"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone = Column(String(20), nullable=False, index=True)
    otp_code = Column(String(6), nullable=False)
    
    # Verification status
    is_verified = Column(Boolean, default=False)
    attempts = Column(Integer, default=0)
    
    # Timestamps
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Constants
    OTP_EXPIRY_MINUTES = 10
    MAX_ATTEMPTS = 3
    
    @classmethod
    def get_expiry_time(cls) -> datetime:
        """Get the expiry time for a new OTP."""
        return datetime.utcnow() + timedelta(minutes=cls.OTP_EXPIRY_MINUTES)
    
    def is_expired(self) -> bool:
        """Check if the OTP has expired."""
        return datetime.utcnow() > self.expires_at
    
    def has_max_attempts(self) -> bool:
        """Check if max verification attempts have been reached."""
        return self.attempts >= self.MAX_ATTEMPTS
    
    def increment_attempts(self) -> None:
        """Increment the failed attempt counter."""
        self.attempts += 1
