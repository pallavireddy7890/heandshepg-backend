"""Authentication router."""
from datetime import timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Profile, UserRole, AppRole
from app.schemas import (
    UserSignUp,
    UserLogin,
    Token,
    PasswordReset,
    PasswordResetConfirm,
    UserResponse,
    ProfileResponse,
    AuthResponse,
    AppRoleEnum,
)
from app.utils.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user,
    get_user_role,
)
from app.config import get_settings

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


@router.post("/signup")
async def signup(user_data: UserSignUp, db: Session = Depends(get_db)):
    """
    Step 1 of signup: Create pending verification and send OTP email.
    
    The actual user account is created only after email verification.
    """
    from app.services.email_verification_service import EmailVerificationService
    from app.models import EmailVerification
    
    email_lower = user_data.email.lower().strip()
    
    # Check if email already exists as a registered user
    existing_user = db.query(User).filter(User.email == email_lower).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create verification and send OTP
    verification, error = EmailVerificationService.create_verification(
        db=db,
        email=email_lower,
        name=user_data.name,
        password=user_data.password,
        role=user_data.role.value,
        phone=user_data.phone
    )
    
    if error and not verification:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error
        )
    
    return {
        "message": "Verification OTP sent to your email",
        "email": email_lower,
        "expires_in_minutes": EmailVerification.OTP_EXPIRY_MINUTES,
        "requires_verification": True
    }


from pydantic import BaseModel as PydanticModel

class VerifyEmailRequest(PydanticModel):
    email: str
    otp_code: str


@router.post("/verify-email", response_model=AuthResponse)
async def verify_email(data: VerifyEmailRequest, db: Session = Depends(get_db)):
    """
    Step 2 of signup: Verify OTP and create the user account.
    """
    from app.services.email_verification_service import EmailVerificationService
    from app.models import OwnersProfile, KycStatus, EmailVerification
    
    # Verify OTP
    verification, error = EmailVerificationService.verify_otp(
        db=db,
        email=data.email,
        otp_code=data.otp_code
    )
    
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )
    
    # OTP verified - create the actual user account
    user_data = EmailVerificationService.get_verification_data(verification)
    
    # Create user
    new_user = User(
        email=user_data["email"],
        hashed_password=user_data["hashed_password"],
        is_active=True,
        is_verified=True,  # Email is now verified
    )
    db.add(new_user)
    db.flush()
    
    # Create profile
    profile = Profile(
        user_id=new_user.id,
        name=user_data["name"],
        email=user_data["email"],
        phone=user_data.get("phone"),
    )
    db.add(profile)
    
    # Assign role
    role_to_assign = user_data["role"]
    if role_to_assign == AppRole.owner:
        # Create OwnersProfile for KYC tracking
        owners_profile = OwnersProfile(
            user_id=new_user.id,
            approval_status=KycStatus.pending,
        )
        db.add(owners_profile)
    
    user_role = UserRole(
        user_id=new_user.id,
        role=role_to_assign,
    )
    db.add(user_role)
    
    # Delete the verification record
    db.delete(verification)
    
    db.commit()
    db.refresh(new_user)
    db.refresh(profile)
    
    # Create access token
    access_token = create_access_token(
        data={"sub": str(new_user.id), "email": new_user.email}
    )
    
    return AuthResponse(
        user=UserResponse.model_validate(new_user),
        profile=ProfileResponse.model_validate(profile),
        role=AppRoleEnum(role_to_assign.value),
        token=Token(access_token=access_token),
    )


class ResendOTPRequest(PydanticModel):
    email: str


@router.post("/resend-otp")
async def resend_otp(data: ResendOTPRequest, db: Session = Depends(get_db)):
    """Resend verification OTP to email."""
    from app.services.email_verification_service import EmailVerificationService
    from app.models import EmailVerification
    
    success, error = EmailVerificationService.resend_otp(db, data.email)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )
    
    return {
        "message": "New verification OTP sent to your email",
        "email": data.email.lower().strip(),
        "expires_in_minutes": EmailVerification.OTP_EXPIRY_MINUTES
    }


@router.post("/login", response_model=AuthResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login with email and password."""
    user = db.query(User).filter(User.email == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )
    
    # Get profile
    profile = db.query(Profile).filter(Profile.user_id == user.id).first()
    
    # Get role
    role = get_user_role(user, db)
    
    # Create access token
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    
    return AuthResponse(
        user=UserResponse.model_validate(user),
        profile=ProfileResponse.model_validate(profile) if profile else None,
        role=AppRoleEnum(role) if role else None,
        token=Token(access_token=access_token),
    )


@router.post("/login/json", response_model=AuthResponse)
async def login_json(login_data: UserLogin, db: Session = Depends(get_db)):
    """Login with JSON body (alternative to form data)."""
    user = db.query(User).filter(User.email == login_data.email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found with this email",
        )
    
    if not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )
    
    # Get profile
    profile = db.query(Profile).filter(Profile.user_id == user.id).first()
    
    # Get role from database
    role = get_user_role(user, db)
    
    if not role:
        # Default to customer if no role found
        role = "customer"
    
    # Create access token
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    
    return AuthResponse(
        user=UserResponse.model_validate(user),
        profile=ProfileResponse.model_validate(profile) if profile else None,
        role=AppRoleEnum(role) if role else None,
        token=Token(access_token=access_token),
    )


@router.get("/me", response_model=AuthResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current authenticated user info."""
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    role = get_user_role(current_user, db)
    
    return AuthResponse(
        user=UserResponse.model_validate(current_user),
        profile=ProfileResponse.model_validate(profile) if profile else None,
        role=AppRoleEnum(role) if role else None,
        token=Token(access_token=""),  # Don't return token on /me
    )


@router.post("/forgot-password")
async def forgot_password(data: PasswordReset, db: Session = Depends(get_db)):
    """Send password reset email."""
    user = db.query(User).filter(User.email == data.email).first()
    
    # Always return success to prevent email enumeration
    if user:
        # Generate reset token for password reset
        reset_token = create_access_token(
            data={"sub": str(user.id), "type": "password_reset"},
            expires_delta=timedelta(hours=1)
        )
        # TODO: Send reset token via email in production
    
    return {"message": "If the email exists, a password reset link has been sent"}


@router.post("/reset-password")
async def reset_password(data: PasswordResetConfirm, db: Session = Depends(get_db)):
    """Reset password with token."""
    from app.utils.security import decode_access_token
    
    payload = decode_access_token(data.token)
    if not payload or payload.get("type") != "password_reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == UUID(user_id)).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.hashed_password = get_password_hash(data.new_password)
    db.commit()
    
    return {"message": "Password reset successfully"}


from pydantic import BaseModel, Field

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change password for authenticated user."""
    # Verify current password
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Update password
    current_user.hashed_password = get_password_hash(data.new_password)
    db.commit()
    
    return {"message": "Password changed successfully"}
