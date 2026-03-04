"""SQLAlchemy models for properties and rooms."""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Text, Date, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.database import Base


class GenderPreference(str, enum.Enum):
    male = "male"
    female = "female"
    mixed = "mixed"


class Property(Base):
    __tablename__ = "properties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    address = Column(Text, nullable=False)
    city = Column(String(100), nullable=False, index=True)
    city_id = Column(UUID(as_uuid=True), ForeignKey("cities.id", ondelete="SET NULL"), nullable=True)
    locality = Column(String(100))
    latitude = Column(Numeric(10, 8))
    longitude = Column(Numeric(11, 8))
    gender_preference = Column(ENUM('male', 'female', 'mixed', name='gender_preference', create_type=False), nullable=False)
    amenities = Column(ARRAY(Text))
    monthly_rent = Column(Integer, nullable=True)
    deposit = Column(Integer, nullable=True)
    grace_period = Column(Integer, default=0)
    rules = Column(Text)
    photos = Column(ARRAY(Text))
    available_from = Column(Date, nullable=False)
    status = Column(String(20), default="active", index=True)
    auto_approve = Column(Boolean, default=False)
    instant_booking = Column(Boolean, default=False)
    cancellation_policy = Column(Text)
    virtual_tour_url = Column(Text)
    safety_score = Column(Integer)
    nearby_amenities = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    @property
    def total_vacancy(self) -> int:
        """Calculate total vacancy across all rooms."""
        if not self.rooms:
            return 0
        return sum(f.vacancy_count or 0 for f in self.rooms if f.vacancy_count is not None)

    # Relationships
    owner = relationship("User", back_populates="properties")
    rooms = relationship("Room", back_populates="property", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="property", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="property", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="property", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="property", cascade="all, delete-orphan")
    city_relationship = relationship("City", back_populates="properties")


class Room(Base):
    __tablename__ = "rooms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    room_type = Column(String(50), nullable=False)  # Single Sharing, Double Sharing, etc.
    floor_number = Column(Integer, default=1)
    room_number = Column(String(20))  # 101, 102, 203
    bed_count = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False)  # Legacy: kept for backward compatibility
    deposit = Column(Integer, nullable=True)
    security_deposit = Column(Integer, nullable=True)  # Security deposit per room
    monthly_price = Column(Integer)  # Price per bed per month
    daily_price = Column(Integer)  # Price per bed per day
    daily_price_with_food = Column(Integer)  # Daily price including food
    daily_price_without_food = Column(Integer)  # Daily price without food
    maintenance_charge = Column(Integer, default=0)  # Maintenance charge per room
    vacancy_count = Column(Integer, default=0)
    is_available = Column(Boolean, default=True)
    stay_type = Column(String(20), default="monthly")  # 'monthly' or 'daily'
    min_stay = Column(Integer, default=1)
    is_extension_allowed = Column(Boolean, default=True)
    complementaries = Column(ARRAY(Text))
    room_photos = Column(ARRAY(Text))
    room_description = Column(Text)  # Room description (max 700 chars recommended)
    area_sqft = Column(Integer)  # Room area in square feet
    width_ft = Column(Integer)  # Room width in feet
    has_ventilation = Column(Boolean, default=True)  # Whether room has ventilation
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    property = relationship("Property", back_populates="rooms")
    bookings = relationship("Booking", back_populates="room")
    beds = relationship("RoomBed", back_populates="room", cascade="all, delete-orphan")


class RoomBed(Base):
    __tablename__ = "room_beds"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    bed_number = Column(String(20))
    status = Column(String(20), default="available")  # available, occupied, maintenance
    current_tenant_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    room = relationship("Room", back_populates="beds")
