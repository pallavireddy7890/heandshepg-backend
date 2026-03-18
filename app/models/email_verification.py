"""Email verification model for OTP-based signup verification."""
import uuid
from datetime import datetime, timedelta
from sqlalchemy import Column, String, Boolean, Integer, DateTime, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base
from app.models.user import AppRole


class EmailVerification(Base):
    """
    Stores pending email verifications during signup.
    
    Flow:
    1. User submits signup form
    2. System creates EmailVerification record with OTP
    3. System sends OTP to user's email
    4. User enters OTP
    5. System verifies OTP and creates actual User account
    6. EmailVerification record is deleted
    """
    __tablename__ = "email_verifications"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False, index=True)
    otp_code = Column(String(6), nullable=False)
    
    # Store user data temporarily until verification
    name = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=True)  # Phone number
    hashed_password = Column(String(255), nullable=False)
    role = Column(SQLEnum(AppRole), nullable=False, default=AppRole.customer)
    referral_code = Column(String(20), nullable=True)  # Store referral code until verification
    
    # Verification status
    is_verified = Column(Boolean, default=False)
    attempts = Column(Integer, default=0)  # Track failed attempts
    
    # Timestamps
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Constants
    OTP_EXPIRY_MINUTES = 10
    MAX_ATTEMPTS = 3
    MAX_OTPS_PER_HOUR = 5
    
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
