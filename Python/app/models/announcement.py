"""SQLAlchemy model for owner announcements/notices."""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Announcement(Base):
    """Announcements/notices from property owners to their tenants."""
    __tablename__ = "announcements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=True, index=True)
    
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    priority = Column(String(20), default='normal')  # normal, important, urgent
    start_time = Column(DateTime(timezone=True), server_default=func.now())  # When announcement becomes visible
    end_time = Column(DateTime(timezone=True))  # When announcement expires
    
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id])
    property = relationship("Property", foreign_keys=[property_id])


# Keep enum for reference but don't use in model
class AnnouncementPriority:
    NORMAL = "normal"
    IMPORTANT = "important"
    URGENT = "urgent"
