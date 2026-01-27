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
    phone: str = Field(..., min_length=10, max_length=15, description="Phone number with country code")
    role: AppRoleEnum = AppRoleEnum.customer


class UserLogin(BaseModel):
    identifier: str  # Can be email or phone number
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
    display_name: Optional[str] = None
    business_name: Optional[str] = None
    about: Optional[str] = None
    phone: Optional[str] = None
    phone_verified: Optional[bool] = False
    email: Optional[str] = None
    profile_photo: Optional[str] = None
    address: Optional[str] = None
    current_address: Optional[str] = None
    permanent_address: Optional[str] = None
    city: Optional[str] = None
    
    # Personal details
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    
    # Work details
    work_type: Optional[str] = None
    work_place: Optional[str] = None
    mother_tongue: Optional[str] = None
    languages_known: Optional[List[str]] = None
    
    # Emergency contact
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_address: Optional[str] = None
    
    # Notification preferences
    payment_reminders_enabled: Optional[bool] = True
    maintenance_reminders_enabled: Optional[bool] = True
    email_notifications: Optional[bool] = True
    sms_notifications: Optional[bool] = True
    push_notifications: Optional[bool] = False
    
    # Privacy settings
    hide_contact_info: Optional[bool] = False
    
    # Bank details
    bank_account_number: Optional[str] = None
    bank_ifsc_code: Optional[str] = None
    bank_name: Optional[str] = None
    
    # KYC Documents
    pan_card_url: Optional[str] = None
    gst_doc_url: Optional[str] = None
    aadhar_front_url: Optional[str] = None
    aadhar_back_url: Optional[str] = None
    college_company_id_url: Optional[str] = None
    profile_verification_status: Optional[str] = "pending"


class ProfileCreate(ProfileBase):
    pass


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    business_name: Optional[str] = None
    about: Optional[str] = None
    phone: Optional[str] = None
    profile_photo: Optional[str] = None
    address: Optional[str] = None
    current_address: Optional[str] = None
    permanent_address: Optional[str] = None
    city: Optional[str] = None
    
    # Personal details
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    
    # Work details
    work_type: Optional[str] = None
    work_place: Optional[str] = None
    mother_tongue: Optional[str] = None
    languages_known: Optional[List[str]] = None
    
    # Emergency contact
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_address: Optional[str] = None
    
    # Notification preferences
    payment_reminders_enabled: Optional[bool] = None
    maintenance_reminders_enabled: Optional[bool] = None
    email_notifications: Optional[bool] = None
    sms_notifications: Optional[bool] = None
    push_notifications: Optional[bool] = None
    
    # Privacy settings
    hide_contact_info: Optional[bool] = None
    
    # Bank details
    bank_account_number: Optional[str] = None
    bank_ifsc_code: Optional[str] = None
    bank_name: Optional[str] = None
    
    # KYC Documents
    pan_card_url: Optional[str] = None
    gst_doc_url: Optional[str] = None
    aadhar_front_url: Optional[str] = None
    aadhar_back_url: Optional[str] = None
    college_company_id_url: Optional[str] = None
    profile_verification_status: Optional[str] = None


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


# Notification Status (for profile update response)
class NotificationStatus(BaseModel):
    """Status of confirmation notifications sent after profile update."""
    email_confirmation_sent: Optional[bool] = None
    email_confirmation_error: Optional[str] = None
    sms_confirmation_sent: Optional[bool] = None
    sms_confirmation_error: Optional[str] = None
    email_already_confirmed: Optional[bool] = None
    sms_already_confirmed: Optional[bool] = None


class ProfileUpdateResponse(BaseModel):
    """Response for profile update including notification status."""
    profile: ProfileResponse
    notification_status: Optional[NotificationStatus] = None
    message: str = "Profile updated successfully"
