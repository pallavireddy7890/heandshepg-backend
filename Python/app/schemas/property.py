"""Pydantic schemas for property-related data."""
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from uuid import UUID
from datetime import date, datetime
from enum import Enum


class GenderPreferenceEnum(str, Enum):
    male = "male"
    female = "female"
    mixed = "mixed"


# Property Schemas
class PropertyBase(BaseModel):
    title: str
    description: Optional[str] = None
    address: str
    city: str
    locality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    gender_preference: GenderPreferenceEnum
    amenities: Optional[List[str]] = None
    monthly_rent: int = Field(..., ge=0)
    deposit: int = Field(..., ge=0)
    rules: Optional[str] = None
    photos: Optional[List[str]] = None
    available_from: date
    auto_approve: Optional[bool] = False
    instant_booking: Optional[bool] = False
    cancellation_policy: Optional[str] = None
    virtual_tour_url: Optional[str] = None
    safety_score: Optional[int] = Field(None, ge=0, le=100)
    nearby_amenities: Optional[dict] = None


class PropertyCreate(PropertyBase):
    pass


class PropertyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    locality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    gender_preference: Optional[GenderPreferenceEnum] = None
    amenities: Optional[List[str]] = None
    monthly_rent: Optional[int] = Field(None, ge=0)
    deposit: Optional[int] = Field(None, ge=0)
    rules: Optional[str] = None
    photos: Optional[List[str]] = None
    available_from: Optional[date] = None
    status: Optional[str] = None
    auto_approve: Optional[bool] = None
    instant_booking: Optional[bool] = None
    cancellation_policy: Optional[str] = None
    virtual_tour_url: Optional[str] = None
    safety_score: Optional[int] = Field(None, ge=0, le=100)
    nearby_amenities: Optional[dict] = None


class PropertyResponse(PropertyBase):
    id: UUID
    owner_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PropertyListResponse(BaseModel):
    id: UUID
    owner_id: UUID
    title: str
    city: str
    locality: Optional[str]
    monthly_rent: int
    deposit: int
    gender_preference: str
    amenities: Optional[List[str]]
    photos: Optional[List[str]]
    available_from: date
    status: str

    class Config:
        from_attributes = True


class PropertyDetailResponse(PropertyResponse):
    rooms: Optional[List["RoomResponse"]] = None
    owner_profile: Optional[dict] = None
    average_rating: Optional[float] = None
    review_count: Optional[int] = None


# Room Schemas
class RoomBase(BaseModel):
    room_type: str
    bed_count: int = Field(..., gt=0)
    price: int = Field(..., ge=0)
    is_available: Optional[bool] = True
    room_photos: Optional[List[str]] = None


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    room_type: Optional[str] = None
    bed_count: Optional[int] = Field(None, gt=0)
    price: Optional[int] = Field(None, ge=0)
    is_available: Optional[bool] = None
    room_photos: Optional[List[str]] = None


class RoomResponse(RoomBase):
    id: UUID
    property_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Search/Filter Schemas
class PropertyFilter(BaseModel):
    city: Optional[str] = None
    locality: Optional[str] = None
    gender_preference: Optional[GenderPreferenceEnum] = None
    min_rent: Optional[int] = None
    max_rent: Optional[int] = None
    amenities: Optional[List[str]] = None
    available_from: Optional[date] = None
    sort_by: Optional[str] = "newest"  # newest, price_low, price_high


# Update forward reference
PropertyDetailResponse.model_rebuild()
