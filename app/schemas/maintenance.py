"""Pydantic schemas for maintenance tickets."""
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime
from enum import Enum


class TicketPriority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class TicketStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"


class TicketCreate(BaseModel):
    property_id: UUID
    room_id: Optional[UUID] = None
    booking_id: Optional[UUID] = None
    title: str
    description: str
    priority: Optional[TicketPriority] = TicketPriority.medium


class TicketUpdate(BaseModel):
    priority: Optional[TicketPriority] = None
    status: Optional[TicketStatus] = None


class TicketResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    property_id: UUID
    room_id: Optional[UUID]
    booking_id: Optional[UUID]
    title: str
    description: str
    priority: TicketPriority
    status: TicketStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
