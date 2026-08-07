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



# Room Schemas
class RoomBase(BaseModel):
    room_type: str
    floor_number: Optional[str] = Field("1", max_length=50)
    room_number: Optional[str] = None
    bed_count: int = Field(..., gt=0)
    price: int = Field(..., ge=0)
    deposit: Optional[int] = Field(None, ge=0)
    security_deposit: Optional[int] = Field(None, ge=0)
    monthly_price: Optional[int] = Field(None, ge=0)
    daily_price: Optional[int] = Field(None, ge=0)
    daily_price_with_food: Optional[int] = Field(None, ge=0)
    daily_price_without_food: Optional[int] = Field(None, ge=0)
    vacancy_count: Optional[int] = Field(0, ge=0)
    is_available: Optional[bool] = True
    stay_type: Optional[str] = "monthly"
    min_stay: Optional[int] = 1
    is_extension_allowed: Optional[bool] = True
    complementaries: Optional[List[str]] = None
    room_photos: Optional[List[str]] = None
    room_description: Optional[str] = Field(None, max_length=700)
    area_sqft: Optional[int] = Field(None, ge=0)
    width_ft: Optional[int] = Field(None, ge=0)
    has_ventilation: Optional[bool] = True
    maintenance_charge: Optional[int] = Field(0, ge=0)
    refundable_amount: Optional[int] = Field(0, ge=0)


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    room_type: Optional[str] = None
    floor_number: Optional[str] = Field(None, max_length=50)
    room_number: Optional[str] = None
    bed_count: Optional[int] = Field(None, gt=0)
    price: Optional[int] = Field(None, ge=0)
    deposit: Optional[int] = Field(None, ge=0)
    security_deposit: Optional[int] = Field(None, ge=0)
    monthly_price: Optional[int] = Field(None, ge=0)
    daily_price: Optional[int] = Field(None, ge=0)
    daily_price_with_food: Optional[int] = Field(None, ge=0)
    daily_price_without_food: Optional[int] = Field(None, ge=0)
    vacancy_count: Optional[int] = Field(None, ge=0)
    is_available: Optional[bool] = None
    stay_type: Optional[str] = None
    min_stay: Optional[int] = None
    is_extension_allowed: Optional[bool] = None
    complementaries: Optional[List[str]] = None
    room_photos: Optional[List[str]] = None
    room_description: Optional[str] = Field(None, max_length=700)
    area_sqft: Optional[int] = Field(None, ge=0)
    width_ft: Optional[int] = Field(None, ge=0)
    has_ventilation: Optional[bool] = None
    maintenance_charge: Optional[int] = Field(None, ge=0)
    refundable_amount: Optional[int] = Field(None, ge=0)


class RoomResponse(RoomBase):
    id: UUID
    property_id: UUID
    created_at: datetime
    updated_at: datetime

    upcoming_vacancy: bool = False
    upcoming_vacancy_date: Optional[date] = None
    upcoming_vacancy_count: int = 0

    class Config:
        from_attributes = True


# Property Schemas
class PropertyBase(BaseModel):
    title: str
    description: Optional[str] = None
    address: str
    city: str
    city_id: Optional[UUID] = None
    locality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    gender_preference: GenderPreferenceEnum
    amenities: Optional[List[str]] = None
    monthly_rent: Optional[int] = Field(None, ge=0)
    deposit: Optional[int] = Field(None, ge=0)
    grace_period: Optional[int] = Field(0, ge=0)
    payment_expiry_hours: Optional[int] = Field(24, ge=1)
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
    rooms: Optional[List[RoomCreate]] = None


class PropertyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    city_id: Optional[UUID] = None
    locality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    gender_preference: Optional[GenderPreferenceEnum] = None
    amenities: Optional[List[str]] = None
    monthly_rent: Optional[int] = Field(None, ge=0)
    deposit: Optional[int] = Field(None, ge=0)
    grace_period: Optional[int] = Field(None, ge=0)
    payment_expiry_hours: Optional[int] = Field(None, ge=1)
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
    rooms: Optional[List[RoomCreate]] = None


class PropertyResponse(PropertyBase):
    id: UUID
    owner_id: UUID
    status: str
    total_vacancy: Optional[int] = 0
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
    monthly_rent: Optional[int]
    deposit: Optional[int] = 0  # Allow None, default to 0
    gender_preference: str
    amenities: Optional[List[str]]
    photos: Optional[List[str]]
    available_from: date
    status: str
    total_vacancy: Optional[int] = 0
    rooms: Optional[List[RoomResponse]] = None

    class Config:
        from_attributes = True


class PropertyDetailResponse(PropertyResponse):
    rooms: Optional[List["RoomResponse"]] = None
    owner_profile: Optional[dict] = None
    average_rating: Optional[float] = None
    review_count: Optional[int] = None




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


class PropertyStatusUpdateResponse(BaseModel):
    message: str
    has_active_bookings: bool


class PropertyDeletionResponse(BaseModel):
    message: str


# Update forward reference
PropertyDetailResponse.model_rebuild()
