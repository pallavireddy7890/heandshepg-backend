"""Pydantic schemas for vacations."""
from datetime import date, datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field


class VacationBase(BaseModel):
    start_date: date
    end_date: date
    reason: Optional[str] = None


class VacationCreate(VacationBase):
    property_id: UUID


class VacationUpdate(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    reason: Optional[str] = None
    status: Optional[str] = None


class VacationResponse(VacationBase):
    id: UUID
    tenant_id: UUID
    property_id: UUID
    total_days: int
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VacationOwnerView(VacationResponse):
    tenant_name: Optional[str] = None
    property_title: Optional[str] = None
    room_number: Optional[str] = None
    floor_number: Optional[str] = None
