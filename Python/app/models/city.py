"""City and Area models for location management."""
import uuid
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class City(Base):
    """City model for available cities."""
    __tablename__ = "cities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)
    image_url = Column(Text)  # URL to city image
    is_active = Column(Boolean, default=True)
    display_order = Column(String(10), default="0")  # For sorting
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    areas = relationship("Area", back_populates="city", cascade="all, delete-orphan")


class Area(Base):
    """Area model for localities within a city."""
    __tablename__ = "areas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    city_id = Column(UUID(as_uuid=True), ForeignKey("cities.id"), nullable=False)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    display_order = Column(String(10), default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    city = relationship("City", back_populates="areas")
