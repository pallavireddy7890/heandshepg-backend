"""Users router for profile management."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Profile, Notification
from app.schemas import ProfileUpdate, ProfileResponse, NotificationResponse, SendPhoneOTPRequest, VerifyPhoneOTPRequest
from app.utils.security import get_current_user

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/profile")
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's profile with owner approval status if applicable."""
    from app.models import UserRole, AppRole, OwnersProfile
    
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    
    # Convert profile to dict for response
    profile_dict = {
        "id": profile.id,
        "user_id": profile.user_id,
        "name": profile.name,
        "display_name": profile.display_name,
        "business_name": profile.business_name,
        "about": profile.about,
        "phone": profile.phone,
        "phone_verified": profile.phone_verified,
        "email": profile.email,
        "profile_photo": profile.profile_photo,
        "address": profile.address,
        "current_address": profile.current_address,
        "permanent_address": profile.permanent_address,
        "city": profile.city,
        "gender": profile.gender,
        "date_of_birth": profile.date_of_birth,
        "work_type": profile.work_type,
        "work_place": profile.work_place,
        "mother_tongue": profile.mother_tongue,
        "languages_known": profile.languages_known,
        "emergency_contact_name": profile.emergency_contact_name,
        "emergency_contact_phone": profile.emergency_contact_phone,
        "emergency_contact_address": profile.emergency_contact_address,
        "payment_reminders_enabled": profile.payment_reminders_enabled,
        "rent_reminder_day": profile.rent_reminder_day,
        "rent_reminder_days_before": profile.rent_reminder_days_before,
        "rent_due_day": profile.rent_due_day,
        "rent_reminder_message": profile.rent_reminder_message,
        "maintenance_reminders_enabled": profile.maintenance_reminders_enabled,
        "email_notifications": profile.email_notifications,
        "sms_notifications": profile.sms_notifications,
        "push_notifications": profile.push_notifications,
        "hide_contact_info": profile.hide_contact_info,
        "bank_account_number": profile.bank_account_number,
        "bank_ifsc_code": profile.bank_ifsc_code,
        "bank_name": profile.bank_name,
        "pan_card_url": profile.pan_card_url,
        "gst_doc_url": profile.gst_doc_url,
        "aadhar_front_url": profile.aadhar_front_url,
        "aadhar_back_url": profile.aadhar_back_url,
        "dl_front_url": profile.dl_front_url,
        "dl_back_url": profile.dl_back_url,
        "college_company_id_url": profile.college_company_id_url,
        "profile_verification_status": profile.profile_verification_status,
        "hosting_since": profile.hosting_since.isoformat() if profile.hosting_since else None,
        "response_rate": profile.response_rate,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }
    
    # Check if user is an owner and add approval_status
    user_role = db.query(UserRole).filter(UserRole.user_id == current_user.id).first()
    if user_role and user_role.role == AppRole.owner:
        owners_profile = db.query(OwnersProfile).filter(OwnersProfile.user_id == current_user.id).first()
        if owners_profile:
            profile_dict["approval_status"] = owners_profile.approval_status.value if owners_profile.approval_status else "pending"
        else:
            profile_dict["approval_status"] = "pending"
    
    return profile_dict



@router.put("/profile")
async def update_profile(
    profile_data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update current user's profile.
    
    When email_notifications or sms_notifications are enabled (changed from false to true),
    sends a confirmation notification to the user.
    """
    from app.schemas import NotificationStatus, ProfileUpdateResponse
    from app.services import notification_service
    
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    
    # Track notification setting changes before update
    old_email_notifications = profile.email_notifications
    old_sms_notifications = profile.sms_notifications
    
    # Get update data
    update_data = profile_data.model_dump(exclude_unset=True)
    
    # Check if notifications are being enabled (changed from false/None to true)
    email_enabled = (
        update_data.get('email_notifications') is True and
        old_email_notifications is not True
    )
    sms_enabled = (
        update_data.get('sms_notifications') is True and
        old_sms_notifications is not True
    )
    
    # Normalize phone number if provided
    if 'phone' in update_data and update_data['phone']:
        from app.routers.auth import normalize_phone
        update_data['phone'] = normalize_phone(update_data['phone'])
    
    # Apply updates to profile
    for field, value in update_data.items():
        setattr(profile, field, value)
    
    # Auto-verification logic for customer profiles
    # Check if user is a customer (not owner/admin) and has all required fields filled
    from app.models import UserRole, AppRole
    user_role = db.query(UserRole).filter(UserRole.user_id == current_user.id).first()
    
    if user_role and user_role.role == AppRole.customer:
        # Helper function to check if a field has actual content (not empty/whitespace)
        def is_filled(value):
            if value is None:
                return False
            if isinstance(value, str):
                return len(value.strip()) > 0
            return bool(value)
        
        # Required fields for customer verification
        required_fields_filled = all([
            is_filled(profile.name),
            is_filled(profile.phone),
            is_filled(profile.gender),
            is_filled(profile.date_of_birth),
            is_filled(profile.city),
            is_filled(profile.aadhar_front_url),
            is_filled(profile.aadhar_back_url),
            is_filled(profile.college_company_id_url)
        ])
        
        # Update verification status based on whether all fields are filled
        if required_fields_filled:
            profile.profile_verification_status = "verified"
        else:
            profile.profile_verification_status = "pending"
    
    db.commit()
    db.refresh(profile)
    
    # Initialize notification status
    notification_status = NotificationStatus()
    
    # Send email confirmation if enabled
    if email_enabled and current_user.email:
        # Check rate limit
        can_send = notification_service.check_rate_limit(
            db, current_user.id, "email_confirmation"
        )
        if can_send:
            success, error = notification_service.send_email_confirmation(
                current_user.email,
                profile.name or profile.display_name or "User"
            )
            notification_status.email_confirmation_sent = success
            notification_status.email_confirmation_error = error
            
            # Log the notification attempt
            notification_service.log_notification(
                db,
                current_user.id,
                "email_confirmation",
                "sent" if success else "failed",
                error
            )
        else:
            notification_status.email_already_confirmed = True
    
    # Send SMS confirmation if enabled
    if sms_enabled and profile.phone:
        # Check rate limit
        can_send = notification_service.check_rate_limit(
            db, current_user.id, "sms_confirmation"
        )
        if can_send:
            success, error = notification_service.send_sms_confirmation(
                profile.phone,
                profile.name or profile.display_name or "User"
            )
            notification_status.sms_confirmation_sent = success
            notification_status.sms_confirmation_error = error
            
            # Log the notification attempt
            notification_service.log_notification(
                db,
                current_user.id,
                "sms_confirmation",
                "sent" if success else "failed",
                error
            )
        else:
            notification_status.sms_already_confirmed = True
    
    # Check if any notification was attempted
    has_notification_status = (
        notification_status.email_confirmation_sent is not None or
        notification_status.sms_confirmation_sent is not None or
        notification_status.email_already_confirmed or
        notification_status.sms_already_confirmed
    )
    
    return ProfileUpdateResponse(
        profile=profile,
        notification_status=notification_status if has_notification_status else None,
        message="Profile updated successfully"
    )




@router.get("/notifications", response_model=List[NotificationResponse])
async def get_notifications(
    property_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    unread_only: bool = False
):
    
    """Get user's notifications."""
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if property_id:
        query = query.filter(
            Notification.property_id == property_id
        )
    if unread_only:
        query = query.filter(Notification.read == False)
    notifications = query.order_by(Notification.created_at.desc()).limit(50).all()
    
    return notifications


@router.put("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark a notification as read."""
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id
    ).first()
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    notification.read = True
    db.commit()
    return {"message": "Notification marked as read"}


@router.put("/notifications/read-all")
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark all notifications as read."""
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.read == False
    ).update({"read": True})
    db.commit()
    return {"message": "All notifications marked as read"}



@router.put("/notifications/read-by-type/{notification_type}")
async def mark_notifications_by_type(
    notification_type: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notifications = (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user.id,
            Notification.type == notification_type,
            Notification.read == False,
        )
        .all()
    )

    for notification in notifications:
        notification.read = True

    db.commit()

    return {
        "message": f"{len(notifications)} notifications marked as read"
    }


# ========== File Upload ==========
from fastapi import UploadFile, File
import os
import uuid as uuid_lib
from datetime import datetime

# Configure upload directory
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".csv", ".ppt", ".pptx", ".zip"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


@router.post("/upload-document")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = "general",
    current_user: User = Depends(get_current_user)
):
    """Upload a document (KYC, ID proof, etc)."""
    # Validate file extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Read file content
    content = await file.read()
    
    # Validate file size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size is 5MB."
        )
    
    # Create user-specific directory
    user_dir = os.path.join(UPLOAD_DIR, str(current_user.id))
    os.makedirs(user_dir, exist_ok=True)
    
    # Generate unique filename
    unique_filename = f"{document_type}_{uuid_lib.uuid4().hex}{ext}"
    file_path = os.path.join(user_dir, unique_filename)
    
    # Save file
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Return URL path (relative) - user must click "Save Changes" to persist to profile
    url_path = f"/uploads/{current_user.id}/{unique_filename}"
    
    return {
        "message": "File uploaded successfully",
        "url": url_path,
        "filename": unique_filename,
        "document_type": document_type
    }


@router.post("/send-phone-otp")
async def send_phone_otp(
    data: SendPhoneOTPRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Send OTP for profile phone verification.
    """
    from app.routers.auth import normalize_phone, phone_variants
    from app.services.email_verification_service import EmailVerificationService
    from app.services.notification_service import NotificationService
    from app.models.phone_verification_otp import PhoneVerificationOTP
    
    phone_clean = normalize_phone(data.phone)
    if not phone_clean:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number"
        )
        
    # Check if another verified user already has this phone number.
    variants = phone_variants(phone_clean)
    existing_profile = db.query(Profile).filter(
        Profile.phone.in_(variants),
        Profile.user_id != current_user.id
    ).first()
    if existing_profile:
        profile_owner = db.query(User).filter(User.id == existing_profile.user_id).first()
        if profile_owner and profile_owner.is_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number is already registered to another account."
            )
            
    # Delete old verification OTPs for this phone number
    db.query(PhoneVerificationOTP).filter(
        PhoneVerificationOTP.phone == phone_clean,
        PhoneVerificationOTP.is_verified == False
    ).delete()
    db.commit()
    
    # Generate 6-digit OTP
    otp_code = EmailVerificationService.generate_otp()
    
    # Create OTP record
    db_otp = PhoneVerificationOTP(
        phone=phone_clean,
        otp_code=otp_code,
        expires_at=PhoneVerificationOTP.get_expiry_time()
    )
    db.add(db_otp)
    db.commit()
    
    # Send OTP SMS
    message = f"He&She PG: Your phone verification code is {otp_code}. Valid for 10 minutes."
    sms_sent, sms_error = NotificationService.send_sms(phone_clean, message)
    
    # Local debugging bypass log
    if not sms_sent:
        from datetime import datetime
        log_msg = f"\n[{datetime.utcnow()}] --- LOCAL BYPASS: PHONE VERIFICATION OTP READY ---\n"
        log_msg += f"Phone: {phone_clean}\nOTP: {otp_code}\n"
        log_msg += f"SMS Error: {sms_error or 'Twilio not configured'}\n"
        log_msg += "---------------------------------------\n"
        try:
            import os
            os.makedirs("logs", exist_ok=True)
            with open("logs/sms_debug.log", "a") as f:
                f.write(log_msg)
        except Exception:
            pass
        print(log_msg)
        
    return {
        "message": "Verification OTP sent to your phone number",
        "phone": phone_clean,
        "expires_in_minutes": PhoneVerificationOTP.OTP_EXPIRY_MINUTES
    }


@router.post("/verify-phone-otp")
async def verify_phone_otp(
    data: VerifyPhoneOTPRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verify the phone OTP and update user profile's phone number to verified.
    """
    from app.routers.auth import normalize_phone
    from app.models.phone_verification_otp import PhoneVerificationOTP
    
    phone_clean = normalize_phone(data.phone)
    if not phone_clean:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number"
        )
        
    # Find active verification record
    verification = db.query(PhoneVerificationOTP).filter(
        PhoneVerificationOTP.phone == phone_clean,
        PhoneVerificationOTP.is_verified == False
    ).order_by(PhoneVerificationOTP.created_at.desc()).first()
    
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending verification request found for this phone number."
        )
        
    # Check if expired
    if verification.is_expired():
        db.delete(verification)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The verification code has expired. Please request a new code."
        )
        
    # Check max attempts
    if verification.has_max_attempts():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many incorrect attempts. Please request a new code."
        )
        
    # Compare OTP code
    if verification.otp_code != data.otp_code:
        verification.increment_attempts()
        db.commit()
        remaining = PhoneVerificationOTP.MAX_ATTEMPTS - verification.attempts
        if remaining > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Incorrect code. You have {remaining} attempts remaining."
            )
        else:
            db.delete(verification)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many incorrect attempts. Please request a new code."
            )
            
    # Success: Mark OTP as verified
    verification.is_verified = True
    
    # Update profile phone and mark as verified!
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if profile:
        profile.phone = phone_clean
        profile.phone_verified = True
        db.commit()
        db.refresh(profile)
    else:
        # Create profile if not exists (fallback)
        profile = Profile(
            user_id=current_user.id,
            phone=phone_clean,
            phone_verified=True,
            name=current_user.email.split('@')[0]
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        
    # Remove verification record
    db.delete(verification)
    db.commit()
    
    # Convert profile to dict for response
    profile_dict = {
        "id": str(profile.id),
        "user_id": str(profile.user_id),
        "name": profile.name,
        "display_name": profile.display_name,
        "business_name": profile.business_name,
        "about": profile.about,
        "phone": profile.phone,
        "phone_verified": profile.phone_verified,
        "email": profile.email,
        "profile_photo": profile.profile_photo,
        "address": profile.address,
        "current_address": profile.current_address,
        "permanent_address": profile.permanent_address,
        "city": profile.city,
        "gender": profile.gender,
        "date_of_birth": profile.date_of_birth,
        "work_type": profile.work_type,
        "work_place": profile.work_place,
        "mother_tongue": profile.mother_tongue,
        "languages_known": profile.languages_known,
        "emergency_contact_name": profile.emergency_contact_name,
        "emergency_contact_phone": profile.emergency_contact_phone,
        "emergency_contact_address": profile.emergency_contact_address,
        "payment_reminders_enabled": profile.payment_reminders_enabled,
        "rent_reminder_day": profile.rent_reminder_day,
        "rent_reminder_days_before": profile.rent_reminder_days_before,
        "rent_due_day": profile.rent_due_day,
        "rent_reminder_message": profile.rent_reminder_message,
        "maintenance_reminders_enabled": profile.maintenance_reminders_enabled,
        "email_notifications": profile.email_notifications,
        "sms_notifications": profile.sms_notifications,
        "push_notifications": profile.push_notifications,
        "hide_contact_info": profile.hide_contact_info,
        "bank_account_number": profile.bank_account_number,
        "bank_ifsc_code": profile.bank_ifsc_code,
        "bank_name": profile.bank_name,
        "pan_card_url": profile.pan_card_url,
        "gst_doc_url": profile.gst_doc_url,
        "aadhar_front_url": profile.aadhar_front_url,
        "aadhar_back_url": profile.aadhar_back_url,
        "dl_front_url": profile.dl_front_url,
        "dl_back_url": profile.dl_back_url,
        "college_company_id_url": profile.college_company_id_url,
        "profile_verification_status": profile.profile_verification_status,
        "hosting_since": profile.hosting_since.isoformat() if profile.hosting_since else None,
        "response_rate": profile.response_rate,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }
    
    return {
        "message": "Phone number verified and updated successfully",
        "profile": profile_dict
    }



