"""SQLAlchemy models for users, profiles, and roles."""
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Enum, Text, ARRAY, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.database import Base


class AppRole(str, enum.Enum):
    customer = "customer"
    owner = "owner"
    admin = "admin"


class KycStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_online = Column(Boolean, default=False)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    profile = relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    owner_profile = relationship("OwnersProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    properties = relationship("Property", back_populates="owner", cascade="all, delete-orphan")
    customer_bookings = relationship("Booking", foreign_keys="Booking.customer_id", back_populates="customer")
    owner_bookings = relationship("Booking", foreign_keys="Booking.owner_id", back_populates="owner")
    favorites = relationship("Favorite", back_populates="user", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    wallet = relationship("Wallet", back_populates="user", uselist=False, cascade="all, delete-orphan")


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255))
    business_name = Column(String(255))
    about = Column(Text)
    phone = Column(String(20))
    phone_verified = Column(Boolean, default=False)
    email = Column(String(255))
    profile_photo = Column(Text)
    address = Column(Text)
    current_address = Column(Text)
    permanent_address = Column(Text)
    city = Column(String(100))
    
    # Personal details
    gender = Column(String(20))
    date_of_birth = Column(String(20))
    
    # Work details
    work_type = Column(String(100))
    work_place = Column(String(255))
    mother_tongue = Column(String(50))
    languages_known = Column(ARRAY(Text))
    
    # Emergency contact
    emergency_contact_name = Column(String(255))
    emergency_contact_phone = Column(String(20))
    emergency_contact_address = Column(Text)
    
    # Notification preferences
    payment_reminders_enabled = Column(Boolean, default=True)
    rent_reminder_day = Column(Integer, default=1)  # Day of month to send reminder
    rent_reminder_days_before = Column(Integer, default=5)  # How many days before due date to start reminders
    rent_due_day = Column(Integer, default=5)       # Day of month rent is due
    rent_reminder_message = Column(Text)            # Custom reminder message template
    maintenance_reminders_enabled = Column(Boolean, default=True)
    email_notifications = Column(Boolean, default=True)
    sms_notifications = Column(Boolean, default=True)
    push_notifications = Column(Boolean, default=False)
    
    # Privacy settings
    hide_contact_info = Column(Boolean, default=False)
    
    # Bank details
    bank_account_number = Column(String(50))
    bank_ifsc_code = Column(String(20))
    bank_name = Column(String(255))
    
    # KYC Documents
    pan_card_url = Column(Text)
    gst_doc_url = Column(Text)
    aadhar_front_url = Column(Text)
    aadhar_back_url = Column(Text)
    dl_front_url = Column(Text)
    dl_back_url = Column(Text)
    college_company_id_url = Column(Text)
    profile_verification_status = Column(String(20), default="pending")
    
    # NOTE: Owner availability fields removed temporarily until database migration is run
    # Run: ALTER TABLE profiles ADD COLUMN IF NOT EXISTS owner_available BOOLEAN DEFAULT TRUE;
    #      ALTER TABLE profiles ADD COLUMN IF NOT EXISTS available_from VARCHAR(10);
    #      ALTER TABLE profiles ADD COLUMN IF NOT EXISTS available_to VARCHAR(10);
    #      ALTER TABLE profiles ADD COLUMN IF NOT EXISTS available_days TEXT[];
    # Then uncomment these lines:
    # owner_available = Column(Boolean, default=True)
    # available_from = Column(String(10))
    # available_to = Column(String(10))
    # available_days = Column(ARRAY(Text))
    
    # Hosting experience - date when owner started hosting (for calculating years hosting)
    hosting_since = Column(Date)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="profile")


class UserRole(Base):
    __tablename__ = "user_roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(AppRole), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="roles")


class OwnersProfile(Base):
    __tablename__ = "owners_profile"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    id_proof_url = Column(Text)
    property_documents = Column(ARRAY(Text))
    approval_status = Column(Enum(KycStatus), default=KycStatus.pending)
    admin_notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="owner_profile")
