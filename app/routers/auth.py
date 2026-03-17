"""Authentication router."""
import re
from datetime import datetime, timedelta
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


@router.get("/debug-sms")
async def debug_sms():
    """Diagnostic endpoint to check if SMS settings are loaded."""
    return {
        "twilio_configured": bool(settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from_number),
        "account_sid_prefix": settings.twilio_account_sid[:5] if settings.twilio_account_sid else None,
        "from_number": settings.twilio_from_number,
        "debug_mode": settings.debug
    }


def normalize_phone(phone: str) -> str:
    """Normalize phone number to a clean digit format.
    
    1. Removes all non-digit characters.
    2. Strips leading '0' (common in domestic formats).
    3. Strips leading '91' if the result is 12 digits (Indian country code).
    4. Ensures we return the most likely 10-digit mobile number for India.
    """
    if not phone:
        return ""
    # Remove all non-digit characters
    digits = ''.join(c for c in phone.strip() if c.isdigit())
    
    # Strip leading zero
    if digits.startswith('0'):
        digits = digits[1:]
        
    # Strip leading '91' if it looks like an Indian country code + 10-digit number
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
        
    return digits


def phone_variants(phone: str) -> list:
    """Return all possible stored formats of a phone number.
    
    Handles existing DB records that may have +91 prefix or raw digits.
    """
    normalized = normalize_phone(phone)
    if not normalized:
        return []
    variants = [
        normalized,            # 6303348984
        f"+91{normalized}",    # +916303348984
        f"91{normalized}",     # 916303348984
    ]
    return variants


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
    if existing_user and existing_user.is_verified:
        # Check current role
        user_role = db.query(UserRole).filter(UserRole.user_id == existing_user.id).first()
        current_role = user_role.role if user_role else AppRole.customer
        
        # Scenario 1: Tenant trying to sign up as Owner -> BLOCK
        if current_role == AppRole.customer and user_data.role == AppRole.owner:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This email is already registered as a tenant account. Tenants cannot become owners."
            )
            
        # Scenario 2: Owner trying to sign up as Tenant -> ALLOW if NOT APPROVED
        if current_role == AppRole.owner and user_data.role == AppRole.customer:
            from app.models import OwnersProfile, KycStatus
            owner_profile = db.query(OwnersProfile).filter(OwnersProfile.user_id == existing_user.id).first()
            if owner_profile and owner_profile.approval_status == KycStatus.approved:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This email is already registered as a verified owner. Verified owners cannot become tenants."
                )
            # If not approved, we allow them to continue with the signup as customer
            pass
        else:
            # Otherwise, standard block for duplicate email
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists"
            )
    
    # Check if phone number already exists (in registered profiles)
    if user_data.phone:
        phone_clean = normalize_phone(user_data.phone)
        variants = phone_variants(user_data.phone)
        if phone_clean and variants:
            existing_profile = db.query(Profile).filter(Profile.phone.in_(variants)).first()
            if existing_profile:
                # Only block if the profile belongs to a verified user
                profile_owner = db.query(User).filter(User.id == existing_profile.user_id).first()
                if profile_owner and profile_owner.is_verified:
                    # Allow if it's an unapproved owner transitioning to tenant (same email)
                    is_transition = False
                    if user_data.role == AppRole.customer:
                        from app.models import OwnersProfile, KycStatus
                        owner_prof = db.query(OwnersProfile).filter(OwnersProfile.user_id == profile_owner.id).first()
                        if owner_prof and owner_prof.approval_status != KycStatus.approved and profile_owner.email == email_lower:
                            is_transition = True
                    
                    if not is_transition:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Phone number already exists"
                        )
            
            # Also check pending verifications (someone started signup but hasn't verified yet)
            from app.models import EmailVerification as EV
            pending_phone = db.query(EV).filter(
                EV.phone.in_(variants),
                EV.is_verified == False,
                EV.expires_at > datetime.utcnow()
            ).first()
            if pending_phone and pending_phone.email != email_lower:
                # If a phone number is pending for a DIFFERENT email, allow taking it over.
                # This solves the "mistyped email" scenario where the phone is locked.
                db.delete(pending_phone)
                db.commit()
    
    # Create verification and send OTP
    verification, error = EmailVerificationService.create_verification(
        db=db,
        email=email_lower,
        name=user_data.name,
        password=user_data.password,
        role=user_data.role.value,
        phone=normalize_phone(user_data.phone) if user_data.phone else None
    )
    
    if error and not verification:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error
        )
    
    phone_clean = normalize_phone(user_data.phone) if user_data.phone else None
    msg = "Verification OTP sent to your email"
    if phone_clean:
        msg += " and phone number"
    
    return {
        "message": msg,
        "email": email_lower,
        "expires_in_minutes": EmailVerification.OTP_EXPIRY_MINUTES,
        "requires_verification": True,
        "sms_sent": bool(phone_clean)
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
    
    # Double-check: prevent race condition where two users sign up with same email/phone simultaneously
    existing_user = db.query(User).filter(User.email == user_data["email"]).first()
    if existing_user and existing_user.is_verified:
        # Check if we are transitioning from owner to customer
        user_role_record = db.query(UserRole).filter(UserRole.user_id == existing_user.id).first()
        current_role = user_role_record.role if user_role_record else AppRole.customer
        
        if current_role == AppRole.owner and user_data["role"] == AppRole.customer:
            # Allow transition for unapproved owners
            from app.models import OwnersProfile, KycStatus
            owner_profile = db.query(OwnersProfile).filter(OwnersProfile.user_id == existing_user.id).first()
            if owner_profile and owner_profile.approval_status != KycStatus.approved:
                # Transition: Update role and password
                user_role_record.role = AppRole.customer
                existing_user.hashed_password = user_data["hashed_password"]
                # Optionally delete or reset owner profile
                db.delete(verification)
                db.commit()
                
                # Get/Create profile to return
                profile = db.query(Profile).filter(Profile.user_id == existing_user.id).first()
                if not profile:
                    profile = Profile(
                        user_id=existing_user.id,
                        name=user_data["name"],
                        email=user_data["email"],
                        phone=normalize_phone(user_data.get("phone")) if user_data.get("phone") else None,
                    )
                    db.add(profile)
                    db.commit()
                
                access_token = create_access_token(data={"sub": str(existing_user.id), "email": existing_user.email})
                return AuthResponse(
                    user=UserResponse.model_validate(existing_user),
                    profile=ProfileResponse.model_validate(profile),
                    role=AppRoleEnum.customer,
                    token=Token(access_token=access_token),
                )
        
        db.delete(verification)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists"
        )
    
    if user_data.get("phone"):
        pv = phone_variants(user_data["phone"])
        existing_profile = db.query(Profile).filter(Profile.phone.in_(pv)).first()
        if existing_profile:
            # Check if this profile belongs to an unverified owner-created account
            profile_user = db.query(User).filter(User.id == existing_profile.user_id).first()
            if profile_user and profile_user.is_verified:
                db.delete(verification)
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Phone number already exists"
                )
    
    if existing_user and not existing_user.is_verified:
        # Owner-created account: update password, verify, and update profile
        existing_user.hashed_password = user_data["hashed_password"]
        existing_user.is_verified = True
        
        # Update profile
        profile = db.query(Profile).filter(Profile.user_id == existing_user.id).first()
        if profile:
            profile.name = user_data["name"]
            profile.email = user_data["email"]
            if user_data.get("phone"):
                profile.phone = normalize_phone(user_data["phone"])
        else:
            profile = Profile(
                user_id=existing_user.id,
                name=user_data["name"],
                email=user_data["email"],
                phone=normalize_phone(user_data.get("phone")) if user_data.get("phone") else None,
            )
            db.add(profile)
        
        # Ensure role exists
        role_to_assign = user_data["role"]
        existing_role = db.query(UserRole).filter(UserRole.user_id == existing_user.id).first()
        if not existing_role:
            user_role = UserRole(user_id=existing_user.id, role=role_to_assign)
            db.add(user_role)
        
        if role_to_assign == AppRole.owner:
            from app.models import OwnersProfile, KycStatus
            existing_owner_profile = db.query(OwnersProfile).filter(OwnersProfile.user_id == existing_user.id).first()
            if not existing_owner_profile:
                owners_profile = OwnersProfile(user_id=existing_user.id, approval_status=KycStatus.pending)
                db.add(owners_profile)
        
        db.delete(verification)
        db.commit()
        db.refresh(existing_user)
        db.refresh(profile)
        
        new_user = existing_user  # For token/response below
    else:
        # Create new user
        new_user = User(
            email=user_data["email"],
            hashed_password=user_data["hashed_password"],
            is_active=True,
            is_verified=True,
        )
        db.add(new_user)
        db.flush()
        
        # Create profile
        profile = Profile(
            user_id=new_user.id,
            name=user_data["name"],
            email=user_data["email"],
            phone=normalize_phone(user_data.get("phone")) if user_data.get("phone") else None,
        )
        db.add(profile)
        
        # Assign role
        role_to_assign = user_data["role"]
        if role_to_assign == AppRole.owner:
            from app.models import OwnersProfile, KycStatus
            owners_profile = OwnersProfile(user_id=new_user.id, approval_status=KycStatus.pending)
            db.add(owners_profile)
        
        user_role = UserRole(user_id=new_user.id, role=role_to_assign)
        db.add(user_role)
        
        db.delete(verification)
        db.commit()
        db.refresh(new_user)
        db.refresh(profile)
    
    # Create welcome notification for user (Omnichannel: Web, Email, SMS)
    try:
        from app.utils.notifications import create_notification
        welcome_title = "🎉 Welcome to He&She PG!"
        welcome_msg = f"Hi {user_data['name']}, welcome to He&She PG! Explore our platform to find the best PG accommodations."
        if role_to_assign == AppRole.owner:
            welcome_msg = f"Hi {user_data['name']}, welcome to He&She PG! Please complete your KYC details in the profile to start listing your properties."
            
        await create_notification(
            db=db,
            user_id=new_user.id,
            title=welcome_title,
            message=welcome_msg,
            notification_type="info",
            link="/profile",
            send_external=(role_to_assign != AppRole.owner)  # Owners get email only after KYC approval
        )
    except Exception as e:
        import logging
        logging.warning(f"Failed to send welcome notification: {e}")
        
    # Notify admins if a new owner signed up
    if role_to_assign == AppRole.owner:
        try:
            from app.utils.notifications import notify_admins_owner_signup
            await notify_admins_owner_signup(db, user_data["name"], user_data["email"])
        except Exception:
            pass  # Don't fail signup if notification fails
    
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
        "message": "New verification OTP sent to your email and phone number",
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
    """Login with email or phone number."""
    
    identifier = login_data.identifier.strip()
    user = None
    
    # Check if identifier looks like an email
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    is_email = re.match(email_pattern, identifier)
    
    if is_email:
        # Login by email
        user = db.query(User).filter(User.email == identifier.lower()).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found with this email",
            )
    else:
        # Login by phone number - look up through profile
        # Normalize phone number and check all format variants
        pv = phone_variants(identifier)
        
        # Try to find profile with this phone number
        profile = db.query(Profile).filter(Profile.phone.in_(pv)).first() if pv else None
        if not profile:
            # Try without country code variations
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found with this phone number",
            )
        
        user = db.query(User).filter(User.id == profile.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account not found",
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
    from app.services.notification_service import NotificationService
    
    user = db.query(User).filter(User.email == data.email).first()
    
    # Always return success to prevent email enumeration
    if user:
        # Generate reset token for password reset
        reset_token = create_access_token(
            data={"sub": str(user.id), "type": "password_reset"},
            expires_delta=timedelta(hours=1)
        )
        
        # Build reset URL - frontend will handle #type=recovery
        frontend_url = settings.frontend_url or "http://localhost:8080"
        reset_url = f"{frontend_url}/resetpassword?token={reset_token}"
        
        # Send password reset email
        email_subject = "Reset Your He&She PG Password"
        email_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f3f4f6;">
            <div style="background: linear-gradient(135deg, #f59e0b, #eab308); padding: 24px 20px; border-radius: 12px 12px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 28px;">🏠 He&She PG</h1>
            </div>
            <div style="background: #f9fafb; padding: 30px; border-radius: 0 0 12px 12px;">
                <h2 style="color: #374151;">Password Reset Request</h2>
                <p style="color: #6b7280; font-size: 16px;">
                    We received a request to reset your password. Click the button below to create a new password:
                </p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_url}" 
                       style="background: #f59e0b; color: white; padding: 15px 30px; 
                              text-decoration: none; border-radius: 8px; font-weight: bold;
                              display: inline-block;">
                        Reset Password
                    </a>
                </div>
                <p style="color: #9ca3af; font-size: 14px;">
                    This link will expire in 1 hour.
                </p>
                <p style="color: #9ca3af; font-size: 14px;">
                    If you didn't request this, please ignore this email. Your password will remain unchanged.
                </p>
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
                <p style="color: #9ca3af; font-size: 12px; text-align: center;">
                    © 2026 He&She PG. All rights reserved.<br/>Contact us: heandshepg@gmail.com
                </p>
            </div>
        </body>
        </html>
        """
        
        # Send the email
        email_sent, email_error = NotificationService.send_email(
            to_email=data.email,
            subject=email_subject,
            body_html=email_body
        )
        
        if not email_sent:
            # Log the failure but don't expose to user
            import logging
            logging.warning(f"Failed to send password reset email to {data.email}")
    
    return {"message": "If the email exists, a password reset link has been sent"}


@router.post("/resetpassword")
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
    
    # Prevent reusing the current password
    if verify_password(data.new_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your new password cannot be the same as your current password. Please choose a different password."
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
