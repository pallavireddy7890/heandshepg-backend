"""Pydantic schemas for reviews and favorites."""
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


# Review Schemas
class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
    cleanliness_rating: Optional[int] = Field(None, ge=1, le=5)
    food_rating: Optional[int] = Field(None, ge=1, le=5)
    safety_rating: Optional[int] = Field(None, ge=1, le=5)


class ReviewUpdate(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    comment: Optional[str] = None
    cleanliness_rating: Optional[int] = Field(None, ge=1, le=5)
    food_rating: Optional[int] = Field(None, ge=1, le=5)
    safety_rating: Optional[int] = Field(None, ge=1, le=5)


class ReviewResponse(BaseModel):
    id: UUID
    property_id: UUID
    user_id: UUID
    rating: int
    comment: Optional[str]
    cleanliness_rating: Optional[int]
    food_rating: Optional[int]
    safety_rating: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReviewWithUser(ReviewResponse):
    user_name: Optional[str] = None
    user_photo: Optional[str] = None


# Favorite Schemas
class FavoriteResponse(BaseModel):
    id: UUID
    user_id: UUID
    property_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class FavoriteWithProperty(FavoriteResponse):
    property: Optional[dict] = None
