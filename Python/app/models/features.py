"""SQLAlchemy models for roommate matching and referrals."""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Integer, Float, Enum
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.database import Base


class RoommatePreference(str, enum.Enum):
    early_bird = "early_bird"
    night_owl = "night_owl"
    vegetarian = "vegetarian"
    non_vegetarian = "non_vegetarian"
    smoker = "smoker"
    non_smoker = "non_smoker"
    pet_friendly = "pet_friendly"
    quiet = "quiet"
    social = "social"


class RoommateProfile(Base):
    __tablename__ = "roommate_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Basic Info
    age = Column(Integer)
    gender = Column(String(20))
    occupation = Column(String(100))
    budget_min = Column(Integer)
    budget_max = Column(Integer)
    preferred_location = Column(String(255))
    preferred_city = Column(String(100))
    move_in_date = Column(DateTime)
    
    # Preferences
    preferences = Column(ARRAY(String))  # List of RoommatePreference values
    languages = Column(ARRAY(String))
    hobbies = Column(ARRAY(String))
    bio = Column(Text)
    
    # Additional preferences (frontend compatibility)
    dietary_preference = Column(String(50))
    smoking = Column(Boolean, default=False)
    drinking = Column(Boolean, default=False)
    pets_allowed = Column(Boolean, default=False)
    cleanliness_level = Column(Integer, default=3)
    
    # Matching
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User")


class RoommateMatch(Base):
    __tablename__ = "roommate_matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    matched_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    match_score = Column(Float)  # 0-100 compatibility score
    status = Column(String(20), default="pending")  # pending, accepted, rejected
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ReferralCode(Base):
    __tablename__ = "referral_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    code = Column(String(20), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User")


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    referrer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    referred_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    referral_code_id = Column(UUID(as_uuid=True), ForeignKey("referral_codes.id"))
    status = Column(String(20), default="pending")  # pending, completed, expired
    reward_amount = Column(Float, default=0)
    reward_claimed = Column(Boolean, default=False)
    booking_id = Column(UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))

    # Relationships
    referrer = relationship("User", foreign_keys=[referrer_id])
    referred = relationship("User", foreign_keys=[referred_id])
