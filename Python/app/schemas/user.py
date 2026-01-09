"""Pydantic schemas for user-related data."""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from enum import Enum


class AppRoleEnum(str, Enum):
    customer = "customer"
    owner = "owner"
    admin = "admin"


class KycStatusEnum(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


# Auth Schemas
class UserSignUp(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: str = Field(..., min_length=2)
    role: AppRoleEnum = AppRoleEnum.customer


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[UUID] = None
    email: Optional[str] = None


class PasswordReset(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


# User Schemas
class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str
    name: str


class UserResponse(UserBase):
    id: UUID
    is_active: bool
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserWithRole(UserResponse):
    role: Optional[AppRoleEnum] = None


# Profile Schemas
class ProfileBase(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    profile_photo: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    work_type: Optional[str] = None
    work_place: Optional[str] = None
    mother_tongue: Optional[str] = None
    languages_known: Optional[List[str]] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_address: Optional[str] = None
    payment_reminders_enabled: Optional[bool] = True
    maintenance_reminders_enabled: Optional[bool] = True


class ProfileCreate(ProfileBase):
    pass


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    profile_photo: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    work_type: Optional[str] = None
    work_place: Optional[str] = None
    mother_tongue: Optional[str] = None
    languages_known: Optional[List[str]] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_address: Optional[str] = None
    payment_reminders_enabled: Optional[bool] = None
    maintenance_reminders_enabled: Optional[bool] = None


class ProfileResponse(ProfileBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Owner Profile Schemas
class OwnersProfileResponse(BaseModel):
    id: UUID
    user_id: UUID
    id_proof_url: Optional[str] = None
    property_documents: Optional[List[str]] = None
    approval_status: KycStatusEnum
    admin_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Combined Auth Response
class AuthResponse(BaseModel):
    user: UserResponse
    profile: Optional[ProfileResponse] = None
    role: Optional[AppRoleEnum] = None
    token: Token
