"""City and Area models for location management."""
import uuid
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class City(Base):
    """City model for available cities."""
    __tablename__ = "cities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)
    slug = Column(String(100), index=True)  # URL-friendly name (hyderabad)
    image_url = Column(Text)  # URL to city image
    tagline = Column(String(200))  # e.g., "City of Pearls"
    status = Column(String(20), default="AVAILABLE")  # AVAILABLE or COMING_SOON
    is_active = Column(Boolean, default=True)
    priority_order = Column(Integer, default=0)  # Lower = first
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    areas = relationship("Area", back_populates="city", cascade="all, delete-orphan")
    properties = relationship("Property", back_populates="city_relationship")


class Area(Base):
    """Area model for localities within a city."""
    __tablename__ = "areas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    city_id = Column(UUID(as_uuid=True), ForeignKey("cities.id"), nullable=False)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), index=True)  # URL-friendly name
    is_active = Column(Boolean, default=True)
    is_popular = Column(Boolean, default=False)  # Show in city card
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    city = relationship("City", back_populates="areas")
