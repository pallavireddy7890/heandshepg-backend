"""Admin router for audit logs, KYC approval, user management, and system settings."""
from typing import List, Optional, Any
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from app.database import get_db
from app.models import User, Profile, UserRole, OwnersProfile, AuditLog, SystemSettings, AppRole, KycStatus
from app.utils.security import get_current_user, require_role

require_admin = require_role("admin")

router = APIRouter(prefix="/admin", tags=["Admin"])


# ========== Pydantic Schemas ==========

class AuditLogResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID]
    action: str
    entity_type: Optional[str]
    entity_id: Optional[UUID]
    details: Optional[str]
    ip_address: Optional[str]
    created_at: datetime
    user_name: Optional[str] = None

    class Config:
        from_attributes = True


class OwnerApplicationResponse(BaseModel):
    id: UUID
    user_id: UUID
    approval_status: str
    id_proof_url: Optional[str]
    property_documents: Optional[List[str]]
    admin_notes: Optional[str]
    created_at: datetime
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    user_phone: Optional[str] = None

    class Config:
        from_attributes = True


class KycApprovalRequest(BaseModel):
    admin_notes: Optional[str] = None


class UserWithRoleResponse(BaseModel):
    id: UUID
    email: str
    name: Optional[str]
    phone: Optional[str]
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class RoleUpdateRequest(BaseModel):
    role: str


class SystemSettingResponse(BaseModel):
    id: UUID
    key: str
    value: Any
    description: Optional[str]
    updated_at: datetime

    class Config:
        from_attributes = True


class SystemSettingUpdate(BaseModel):
    value: str


# ========== Audit Logs ==========

@router.get("/audit-logs", response_model=List[AuditLogResponse], dependencies=[Depends(require_admin)])
async def get_audit_logs(
    db: Session = Depends(get_db),
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    user_id: Optional[UUID] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=100),
):
    """Get audit logs (admin only)."""
    query = db.query(AuditLog)
    
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    
    logs = query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
    
    # Enrich with user names
    result = []
    for log in logs:
        log_dict = AuditLogResponse.model_validate(log)
        if log.user_id:
            profile = db.query(Profile).filter(Profile.user_id == log.user_id).first()
            log_dict.user_name = profile.name if profile else None
        result.append(log_dict)
    
    return result


def create_audit_log(
    db: Session,
    user_id: UUID,
    action: str,
    entity_type: str = None,
    entity_id: UUID = None,
    details: str = None,
    ip_address: str = None,
    user_agent: str = None,
):
    """Helper function to create an audit log entry."""
    log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(log)
    db.commit()
    return log


# ========== KYC / Owner Applications ==========

@router.get("/owner-applications", response_model=List[OwnerApplicationResponse], dependencies=[Depends(require_admin)])
async def get_owner_applications(
    db: Session = Depends(get_db),
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=100),
):
    """Get owner applications for KYC approval (admin only)."""
    query = db.query(OwnersProfile)
    
    if status_filter:
        query = query.filter(OwnersProfile.approval_status == status_filter)
    
    applications = query.order_by(OwnersProfile.created_at.desc()).offset(skip).limit(limit).all()
    
    # Enrich with user info
    result = []
    for app in applications:
        app_dict = OwnerApplicationResponse.model_validate(app)
        app_dict.approval_status = app.approval_status.value if app.approval_status else "pending"
        
        user = db.query(User).filter(User.id == app.user_id).first()
        profile = db.query(Profile).filter(Profile.user_id == app.user_id).first()
        
        app_dict.user_email = user.email if user else None
        app_dict.user_name = profile.name if profile else None
        app_dict.user_phone = profile.phone if profile else None
        
        result.append(app_dict)
    
    return result


@router.put("/owner-applications/{application_id}/approve", dependencies=[Depends(require_admin)])
async def approve_owner_application(
    application_id: UUID,
    approval_data: KycApprovalRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approve an owner application (admin only)."""
    from app.models import Notification
    from app.services.notification_service import NotificationService
    
    application = db.query(OwnersProfile).filter(OwnersProfile.id == application_id).first()
    
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    
    application.approval_status = KycStatus.approved
    application.admin_notes = approval_data.admin_notes
    
    # Update user role to owner
    user_role = db.query(UserRole).filter(UserRole.user_id == application.user_id).first()
    if user_role:
        user_role.role = AppRole.owner
    else:
        new_role = UserRole(user_id=application.user_id, role=AppRole.owner)
        db.add(new_role)
    
    # Get owner info for notification
    owner_user = db.query(User).filter(User.id == application.user_id).first()
    owner_profile = db.query(Profile).filter(Profile.user_id == application.user_id).first()
    owner_name = owner_profile.name if owner_profile else "Owner"
    owner_email = owner_user.email if owner_user else None
    
    # Create welcome notification for owner
    welcome_notification = Notification(
        user_id=application.user_id,
        type="owner_approved",
        title="🎉 Welcome to He&She PG!",
        message=f"Congratulations {owner_name}! Your owner account has been approved. You can now add properties and start accepting bookings.",
        read=False,
    )
    db.add(welcome_notification)
    
    # Create audit log
    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="kyc_approval",
        entity_type="owner_application",
        entity_id=application_id,
        details=f"Approved owner application. Notes: {approval_data.admin_notes or 'None'}",
        ip_address=request.client.host if request.client else None,
    )
    
    db.commit()
    
    # Send welcome email to the approved owner
    if owner_email:
        try:
            email_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #f59e0b, #eab308); padding: 20px; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0;">🎉 Welcome to He&She PG!</h1>
                </div>
                <div style="background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #374151;">Congratulations, {owner_name}!</h2>
                    <p style="color: #6b7280; font-size: 16px;">
                        Your owner account has been <strong>approved</strong>! You now have full access to the Owner Dashboard.
                    </p>
                    <p style="color: #6b7280; font-size: 16px;">
                        Here's what you can do now:
                    </p>
                    <ul style="color: #6b7280; font-size: 16px;">
                        <li>📍 Add your properties with detailed room configurations</li>
                        <li>📅 Manage bookings from potential tenants</li>
                        <li>💰 Track payments and revenue</li>
                        <li>👥 Manage your tenants</li>
                        <li>📢 Send announcements to your tenants</li>
                    </ul>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="http://localhost:8080/owner/dashboard" 
                           style="background: #f59e0b; color: white; padding: 15px 30px; 
                                  text-decoration: none; border-radius: 8px; font-weight: bold;
                                  display: inline-block;">
                            Go to Owner Dashboard
                        </a>
                    </div>
                    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
                    <p style="color: #9ca3af; font-size: 12px; text-align: center;">
                        © 2024 He&She PG. All rights reserved.
                    </p>
                </div>
            </body>
            </html>
            """
            NotificationService.send_email(
                to_email=owner_email,
                subject="🎉 Your He&She PG Owner Account is Approved!",
                body_html=email_body
            )
        except Exception as e:
            # Don't fail the approval if email fails
            import logging
            logging.warning(f"Failed to send welcome email to owner {owner_email}: {e}")
    
    return {"message": "Application approved successfully"}



@router.put("/owner-applications/{application_id}/reject", dependencies=[Depends(require_admin)])
async def reject_owner_application(
    application_id: UUID,
    rejection_data: KycApprovalRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reject an owner application (admin only)."""
    application = db.query(OwnersProfile).filter(OwnersProfile.id == application_id).first()
    
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    
    application.approval_status = KycStatus.rejected
    application.admin_notes = rejection_data.admin_notes
    
    # Create audit log
    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="kyc_rejection",
        entity_type="owner_application",
        entity_id=application_id,
        details=f"Rejected owner application. Reason: {rejection_data.admin_notes or 'Not specified'}",
        ip_address=request.client.host if request.client else None,
    )
    
    db.commit()
    return {"message": "Application rejected"}


# ========== User Management ==========

@router.get("/users", response_model=List[UserWithRoleResponse], dependencies=[Depends(require_admin)])
async def get_all_users(
    db: Session = Depends(get_db),
    role_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=100),
):
    """Get all users with their roles (admin only)."""
    query = db.query(User)
    users = query.order_by(User.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for user in users:
        profile = db.query(Profile).filter(Profile.user_id == user.id).first()
        user_role = db.query(UserRole).filter(UserRole.user_id == user.id).first()
        
        role = user_role.role.value if user_role else "customer"
        
        if role_filter and role != role_filter:
            continue
        
        result.append(UserWithRoleResponse(
            id=user.id,
            email=user.email,
            name=profile.name if profile else None,
            phone=profile.phone if profile else None,
            role=role,
            is_active=user.is_active,
            created_at=user.created_at,
        ))
    
    return result


@router.put("/users/{user_id}/role", dependencies=[Depends(require_admin)])
async def update_user_role(
    user_id: UUID,
    role_data: RoleUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a user's role (admin only)."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    try:
        new_role = AppRole(role_data.role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {[r.value for r in AppRole]}"
        )
    
    user_role = db.query(UserRole).filter(UserRole.user_id == user_id).first()
    old_role = user_role.role.value if user_role else "customer"
    
    if user_role:
        user_role.role = new_role
    else:
        user_role = UserRole(user_id=user_id, role=new_role)
        db.add(user_role)
    
    # Create audit log
    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="role_change",
        entity_type="user",
        entity_id=user_id,
        details=f"Changed role from {old_role} to {new_role.value}",
        ip_address=request.client.host if request.client else None,
    )
    
    db.commit()
    return {"message": f"User role updated to {new_role.value}"}


# ========== System Settings ==========

@router.get("/settings", response_model=List[SystemSettingResponse], dependencies=[Depends(require_admin)])
async def get_system_settings(db: Session = Depends(get_db)):
    """Get all system settings (admin only)."""
    settings = db.query(SystemSettings).all()
    return settings


@router.put("/settings/{key}", response_model=SystemSettingResponse, dependencies=[Depends(require_admin)])
async def update_system_setting(
    key: str,
    setting_data: SystemSettingUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a system setting (admin only)."""
    setting = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    
    if not setting:
        # Create new setting
        setting = SystemSettings(key=key, value=setting_data.value, updated_by=current_user.id)
        db.add(setting)
    else:
        setting.value = setting_data.value
        setting.updated_by = current_user.id
    
    db.commit()
    db.refresh(setting)
    return setting


# ========== Dashboard Stats ==========

@router.get("/stats", dependencies=[Depends(require_admin)])
async def get_admin_stats(db: Session = Depends(get_db)):
    """Get admin dashboard statistics."""
    from app.models import Property, Booking
    
    total_users = db.query(func.count(User.id)).scalar()
    total_properties = db.query(func.count(Property.id)).scalar()
    total_bookings = db.query(func.count(Booking.id)).scalar()
    pending_kyc = db.query(func.count(OwnersProfile.id)).filter(
        OwnersProfile.approval_status == KycStatus.pending
    ).scalar()
    
    return {
        "total_users": total_users or 0,
        "total_properties": total_properties or 0,
        "total_bookings": total_bookings or 0,
        "pending_kyc_applications": pending_kyc or 0,
    }


# ========== Property Moderation ==========

class PropertyModerationRequest(BaseModel):
    status: str  # active, inactive, banned
    reason: Optional[str] = None


class PropertyModerationResponse(BaseModel):
    id: UUID
    title: str
    owner_name: Optional[str]
    owner_email: Optional[str]
    city: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/properties", response_model=List[PropertyModerationResponse], dependencies=[Depends(require_admin)])
async def get_all_properties_for_moderation(
    db: Session = Depends(get_db),
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=100),
):
    """Get all properties for moderation (admin only)."""
    from app.models import Property
    
    query = db.query(Property)
    
    if status_filter:
        query = query.filter(Property.status == status_filter)
    
    properties = query.order_by(Property.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for prop in properties:
        owner_profile = db.query(Profile).filter(Profile.user_id == prop.owner_id).first()
        owner_user = db.query(User).filter(User.id == prop.owner_id).first()
        
        result.append(PropertyModerationResponse(
            id=prop.id,
            title=prop.title,
            owner_name=owner_profile.name if owner_profile else None,
            owner_email=owner_user.email if owner_user else None,
            city=prop.city,
            status=prop.status,
            created_at=prop.created_at,
        ))
    
    return result


@router.put("/properties/{property_id}/moderate", dependencies=[Depends(require_admin)])
async def moderate_property(
    property_id: UUID,
    moderation_data: PropertyModerationRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Moderate a property - set to active/inactive/banned (admin only)."""
    from app.models import Property
    
    valid_statuses = ["active", "inactive", "banned", "pending"]
    if moderation_data.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {valid_statuses}"
        )
    
    property = db.query(Property).filter(Property.id == property_id).first()
    
    if not property:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    
    old_status = property.status
    property.status = moderation_data.status
    
    # Create audit log
    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="property_moderation",
        entity_type="property",
        entity_id=property_id,
        details=f"Changed status from {old_status} to {moderation_data.status}. Reason: {moderation_data.reason or 'Not specified'}",
        ip_address=request.client.host if request.client else None,
    )
    
    db.commit()
    return {"message": f"Property status updated to {moderation_data.status}"}


@router.delete("/properties/{property_id}", dependencies=[Depends(require_admin)])
async def admin_delete_property(
    property_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a property (admin only)."""
    from app.models import Property
    
    property = db.query(Property).filter(Property.id == property_id).first()
    
    if not property:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    
    # Create audit log before deletion
    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="property_deletion",
        entity_type="property",
        entity_id=property_id,
        details=f"Deleted property: {property.title}",
        ip_address=request.client.host if request.client else None,
    )
    
    db.delete(property)
    db.commit()
    return {"message": "Property deleted successfully"}


# ========== Setup Endpoint (for fixing admin role) ==========

@router.post("/setup-admin")
async def setup_admin_role(
    email: str,
    secret_key: str,
    password: str = None,
    name: str = "Admin",
    db: Session = Depends(get_db),
):
    """
    Setup endpoint to create or fix admin user.
    - If user exists: Updates their role to admin
    - If user doesn't exist: Creates new admin user with given credentials
    Requires the SECRET_KEY from environment as authorization.
    """
    from app.config import get_settings
    from app.utils.security import get_password_hash
    
    settings = get_settings()
    
    # Verify secret key for authorization
    if secret_key != settings.secret_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid secret key"
        )
    
    # Find user by email
    user = db.query(User).filter(User.email == email).first()
    
    if user:
        # User exists - update role to admin
        user_role = db.query(UserRole).filter(UserRole.user_id == user.id).first()
        
        if user_role:
            old_role = user_role.role.value
            user_role.role = AppRole.admin
            message = f"Updated role from '{old_role}' to 'admin'"
        else:
            new_role = UserRole(user_id=user.id, role=AppRole.admin)
            db.add(new_role)
            message = "Created admin role for existing user"
        
        db.commit()
        
        return {
            "success": True,
            "message": message,
            "user_email": email,
            "role": "admin",
            "action": "updated"
        }
    else:
        # User doesn't exist - create new admin user
        if not password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password is required to create new admin user"
            )
        
        # Create user
        hashed_password = get_password_hash(password)
        new_user = User(
            email=email,
            hashed_password=hashed_password,
            is_active=True,
            is_verified=True,
        )
        db.add(new_user)
        db.flush()
        
        # Create profile
        profile = Profile(
            user_id=new_user.id,
            name=name,
            email=email,
        )
        db.add(profile)
        
        # Assign admin role
        admin_role = UserRole(user_id=new_user.id, role=AppRole.admin)
        db.add(admin_role)
        
        db.commit()
        
        return {
            "success": True,
            "message": f"Created new admin user: {email}",
            "user_email": email,
            "role": "admin",
            "action": "created"
        }


# ========== Admin Payments View ==========

class AdminPaymentResponse(BaseModel):
    id: UUID
    booking_id: Optional[UUID]
    user_id: UUID
    user_name: Optional[str]
    user_email: Optional[str]
    property_title: Optional[str]
    amount: int
    currency: str
    status: str
    type: str
    razorpay_payment_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/payments", response_model=List[AdminPaymentResponse], dependencies=[Depends(require_admin)])
async def get_all_payments(
    db: Session = Depends(get_db),
    status_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=100),
):
    """Get all payments platform-wide (admin only)."""
    from app.models import Payment, Booking, Property
    
    query = db.query(Payment)
    
    if status_filter:
        query = query.filter(Payment.status == status_filter)
    if type_filter:
        query = query.filter(Payment.type == type_filter)
    
    payments = query.order_by(Payment.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for payment in payments:
        user = db.query(User).filter(User.id == payment.user_id).first()
        profile = db.query(Profile).filter(Profile.user_id == payment.user_id).first()
        
        property_title = None
        if payment.booking_id:
            booking = db.query(Booking).filter(Booking.id == payment.booking_id).first()
            if booking:
                prop = db.query(Property).filter(Property.id == booking.property_id).first()
                property_title = prop.title if prop else None
        
        result.append(AdminPaymentResponse(
            id=payment.id,
            booking_id=payment.booking_id,
            user_id=payment.user_id,
            user_name=profile.name if profile else None,
            user_email=user.email if user else None,
            property_title=property_title,
            amount=payment.amount,
            currency=payment.currency or "INR",
            status=payment.status if isinstance(payment.status, str) else payment.status.value if payment.status else "pending",
            type=payment.type if isinstance(payment.type, str) else payment.type.value if payment.type else "booking",
            razorpay_payment_id=payment.razorpay_payment_id,
            created_at=payment.created_at,
        ))
    
    return result


@router.get("/payments/stats", dependencies=[Depends(require_admin)])
async def get_payment_stats(db: Session = Depends(get_db)):
    """Get payment statistics for admin dashboard."""
    from app.models import Payment
    
    total_payments = db.query(func.count(Payment.id)).scalar() or 0
    total_revenue = db.query(func.sum(Payment.amount)).filter(Payment.status == "completed").scalar() or 0
    pending_payments = db.query(func.count(Payment.id)).filter(Payment.status == "pending").scalar() or 0
    failed_payments = db.query(func.count(Payment.id)).filter(Payment.status == "failed").scalar() or 0
    
    return {
        "total_payments": total_payments,
        "total_revenue": total_revenue,
        "pending_payments": pending_payments,
        "failed_payments": failed_payments,
    }


# ========== Block/Unblock Users ==========

class UserStatusUpdate(BaseModel):
    is_active: bool
    reason: Optional[str] = None


@router.put("/users/{user_id}/status", dependencies=[Depends(require_admin)])
async def toggle_user_status(
    user_id: UUID,
    status_data: UserStatusUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Block or unblock a user (admin only)."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own status"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    old_status = "active" if user.is_active else "blocked"
    user.is_active = status_data.is_active
    new_status = "active" if status_data.is_active else "blocked"
    
    # Create audit log
    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="user_status_change",
        entity_type="user",
        entity_id=user_id,
        details=f"Changed status from {old_status} to {new_status}. Reason: {status_data.reason or 'Not specified'}",
        ip_address=request.client.host if request.client else None,
    )
    
    db.commit()
    return {"message": f"User {'activated' if status_data.is_active else 'blocked'} successfully"}


# ========== Admin Announcements ==========

class AdminAnnouncementCreate(BaseModel):
    title: str
    message: str
    target_audience: str = "all"  # all, owners, tenants
    priority: str = "normal"  # low, normal, high, urgent
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class AdminAnnouncementResponse(BaseModel):
    id: UUID
    title: str
    message: str
    target_audience: str
    priority: str
    is_admin: bool
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

    class Config:
        from_attributes = True


@router.post("/announcements", response_model=AdminAnnouncementResponse, dependencies=[Depends(require_admin)])
async def create_admin_announcement(
    data: AdminAnnouncementCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create an admin announcement and notify users (admin only)."""
    from app.models import Notification, UserRole
    from app.models.announcement import Announcement
    
    valid_audiences = ["all", "owners", "tenants"]
    if data.target_audience not in valid_audiences:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid target audience. Must be one of: {valid_audiences}"
        )
    
    # 1. Create the persistent announcement
    announcement = Announcement(
        owner_id=current_user.id,
        title=data.title,
        message=data.message,
        priority=data.priority,
        target_audience=data.target_audience,
        is_admin=True,
        start_time=data.start_time or datetime.utcnow(),
        end_time=data.end_time,
        is_active=True
    )
    db.add(announcement)
    db.flush() # Get ID
    
    # 2. Get target users based on audience
    if data.target_audience == "all":
        users = db.query(User).filter(User.is_active == True).all()
    elif data.target_audience == "owners":
        users = db.query(User).join(UserRole).filter(
            User.is_active == True,
            UserRole.role == AppRole.owner
        ).all()
    else:  # tenants
        users = db.query(User).join(UserRole).filter(
            User.is_active == True,
            UserRole.role == AppRole.customer
        ).all()
    
    # 3. Create notifications for all target users
    sent_count = 0
    for user in users:
        notification = Notification(
            user_id=user.id,
            title=f"📢 {data.title}",
            message=data.message,
            type="admin_announcement",
        )
        db.add(notification)
        sent_count += 1
    
    # 4. Create audit log
    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="admin_announcement",
        entity_type="announcement",
        entity_id=announcement.id,
        details=f"Sent announcement '{data.title}' to {data.target_audience} ({sent_count} users)",
        ip_address=request.client.host if request.client else None,
    )
    
    db.commit()
    db.refresh(announcement)
    
    return announcement


@router.get("/announcements", response_model=List[AdminAnnouncementResponse], dependencies=[Depends(require_admin)])
async def list_admin_announcements(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=50, le=100),
):
    """List all admin announcements (admin only)."""
    from app.models.announcement import Announcement
    
    announcements = db.query(Announcement).filter(
        Announcement.is_admin == True
    ).order_by(Announcement.created_at.desc()).offset(skip).limit(limit).all()
    
    return announcements


@router.delete("/announcements/{announcement_id}", dependencies=[Depends(require_admin)])
async def delete_admin_announcement(
    announcement_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an admin announcement (admin only)."""
    from app.models.announcement import Announcement
    
    announcement = db.query(Announcement).filter(
        Announcement.id == announcement_id,
        Announcement.is_admin == True
    ).first()
    
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    
    # Create audit log
    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="delete_announcement",
        entity_type="announcement",
        entity_id=announcement_id,
        details=f"Deleted announcement: {announcement.title}",
        ip_address=request.client.host if request.client else None,
    )
    
    db.delete(announcement)
    db.commit()
    
    return {"message": "Announcement deleted"}


# ========== Refund Management ==========

class RefundRequest(BaseModel):
    reason: str
    amount: Optional[int] = None  # If None, full refund


@router.post("/payments/{payment_id}/refund", dependencies=[Depends(require_admin)])
async def initiate_refund(
    payment_id: UUID,
    refund_data: RefundRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Initiate a refund for a payment (admin only)."""
    from app.models import Payment
    from app.config import get_settings
    
    settings = get_settings()
    
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    
    if payment.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only completed payments can be refunded"
        )
    
    refund_amount = refund_data.amount or payment.amount
    
    if refund_amount > payment.amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refund amount cannot exceed payment amount"
        )
    
    # Try Razorpay refund if payment has razorpay_payment_id
    razorpay_refund_id = None
    if payment.razorpay_payment_id:
        try:
            import razorpay
            client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
            refund = client.payment.refund(payment.razorpay_payment_id, {
                "amount": refund_amount * 100,  # Convert to paise
                "notes": {"reason": refund_data.reason}
            })
            razorpay_refund_id = refund.get("id")
        except Exception as e:
            # Log error but continue with manual refund tracking
            pass
    
    # Update payment status
    payment.status = "refunded"
    
    # Create refund record
    refund_payment = Payment(
        booking_id=payment.booking_id,
        user_id=payment.user_id,
        amount=-refund_amount,  # Negative amount for refund
        currency=payment.currency,
        razorpay_payment_id=razorpay_refund_id,
        status="completed",
        type="refund",
    )
    db.add(refund_payment)
    
    # Create audit log
    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="payment_refund",
        entity_type="payment",
        entity_id=payment_id,
        details=f"Refunded ₹{refund_amount}. Reason: {refund_data.reason}",
        ip_address=request.client.host if request.client else None,
    )
    
    db.commit()
    
    return {
        "message": f"Refund of ₹{refund_amount} processed successfully",
        "original_payment_id": str(payment_id),
        "refund_amount": refund_amount,
        "razorpay_refund_id": razorpay_refund_id,
    }


# ========== Asset Management ==========

from fastapi import UploadFile, File
import os
import uuid as uuid_lib

# Configure admin asset directory
ADMIN_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "admin_assets")
os.makedirs(ADMIN_ASSETS_DIR, exist_ok=True)

@router.post("/upload-asset", dependencies=[Depends(require_admin)])
async def upload_admin_asset(
    file: UploadFile = File(...),
    asset_type: str = "general"
):
    """Upload an asset for the platform (city images, etc)."""
    # Validate file extension
    ext = os.path.splitext(file.filename)[1].lower()
    allowed_exts = {".jpg", ".jpeg", ".png", ".webp"}
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(allowed_exts)}"
        )
    
    # Read file content
    content = await file.read()
    
    # Validate file size (max 5MB)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size is 5MB."
        )
    
    # Generate unique filename
    unique_filename = f"{asset_type}_{uuid_lib.uuid4().hex}{ext}"
    file_path = os.path.join(ADMIN_ASSETS_DIR, unique_filename)
    
    # Save file
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Return URL path
    from app.config import get_settings
    settings = get_settings()
    # Assuming the app mounts /uploads to StaticFiles
    url_path = f"/uploads/admin_assets/{unique_filename}"
    
    return {
        "message": "Asset uploaded successfully",
        "url": url_path,
        "filename": unique_filename
    }


# ========== City Management ==========

class CityCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    image_url: Optional[str] = None
    tagline: Optional[str] = None
    status: str = "AVAILABLE"  # AVAILABLE, COMING_SOON, DISABLED
    priority_order: int = 0


class CityUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    image_url: Optional[str] = None
    tagline: Optional[str] = None
    status: Optional[str] = None
    priority_order: Optional[int] = None
    is_active: Optional[bool] = None


class AdminCityResponse(BaseModel):
    id: UUID
    name: str
    slug: Optional[str] = None
    image_url: Optional[str] = None
    tagline: Optional[str] = None
    status: str = "AVAILABLE"
    is_active: bool = True
    priority_order: int = 0
    property_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/cities", response_model=List[AdminCityResponse], dependencies=[Depends(require_admin)])
async def get_admin_cities(
    db: Session = Depends(get_db),
    include_inactive: bool = Query(default=False),
):
    """Get all cities for admin management with property counts."""
    from app.models.city import City
    from app.models.property import Property
    from sqlalchemy import func
    
    query = db.query(City)
    if not include_inactive:
        query = query.filter(City.is_active == True)
    
    cities = query.order_by(City.priority_order, City.name).all()
    
    # Get property counts per city
    property_counts = {}
    counts = db.query(
        func.lower(Property.city), func.count(Property.id)
    ).filter(Property.status == "active").group_by(func.lower(Property.city)).all()
    for city_name, count in counts:
        if city_name:
            property_counts[city_name.lower()] = count
    
    result = []
    for city in cities:
        city_data = {
            "id": city.id,
            "name": city.name,
            "slug": city.slug,
            "image_url": city.image_url,
            "tagline": city.tagline,
            "status": city.status or "AVAILABLE",
            "is_active": city.is_active,
            "priority_order": city.priority_order or 0,
            "property_count": property_counts.get(city.name.lower(), 0),
            "created_at": city.created_at,
        }
        result.append(city_data)
    
    return result


@router.post("/cities", dependencies=[Depends(require_admin)])
async def create_city(
    city_data: CityCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new city (admin only)."""
    from app.models.city import City
    
    # Check if city already exists
    existing = db.query(City).filter(func.lower(City.name) == city_data.name.lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"City '{city_data.name}' already exists"
        )
    
    slug = city_data.slug or city_data.name.lower().replace(" ", "-").replace(".", "")
    
    new_city = City(
        name=city_data.name,
        slug=slug,
        image_url=city_data.image_url,
        tagline=city_data.tagline,
        status=city_data.status,
        priority_order=city_data.priority_order,
        is_active=True,
    )
    db.add(new_city)
    
    # Create audit log
    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="city_created",
        entity_type="city",
        entity_id=new_city.id,
        details=f"Created city: {city_data.name}",
        ip_address=request.client.host if request.client else None,
    )
    
    db.commit()
    db.refresh(new_city)
    
    return {
        "message": f"City '{city_data.name}' created successfully",
        "city": {
            "id": new_city.id,
            "name": new_city.name,
            "slug": new_city.slug,
            "status": new_city.status,
        }
    }


@router.put("/cities/{city_id}", dependencies=[Depends(require_admin)])
async def update_city(
    city_id: UUID,
    city_data: CityUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a city (admin only)."""
    from app.models.city import City
    
    city = db.query(City).filter(City.id == city_id).first()
    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="City not found"
        )
    
    # Update fields
    update_details = []
    if city_data.name is not None:
        update_details.append(f"name: {city.name} → {city_data.name}")
        city.name = city_data.name
    if city_data.slug is not None:
        city.slug = city_data.slug
    if city_data.image_url is not None:
        city.image_url = city_data.image_url
    if city_data.tagline is not None:
        city.tagline = city_data.tagline
    if city_data.status is not None:
        update_details.append(f"status: {city.status} → {city_data.status}")
        city.status = city_data.status
    if city_data.priority_order is not None:
        city.priority_order = city_data.priority_order
    if city_data.is_active is not None:
        update_details.append(f"is_active: {city.is_active} → {city_data.is_active}")
        city.is_active = city_data.is_active
    
    # Create audit log
    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="city_updated",
        entity_type="city",
        entity_id=city_id,
        details=f"Updated city: {city.name}. Changes: {', '.join(update_details) if update_details else 'minor updates'}",
        ip_address=request.client.host if request.client else None,
    )
    
    db.commit()
    db.refresh(city)
    
    return {
        "message": f"City '{city.name}' updated successfully",
        "city": {
            "id": city.id,
            "name": city.name,
            "slug": city.slug,
            "status": city.status,
            "is_active": city.is_active,
        }
    }


@router.delete("/cities/{city_id}", dependencies=[Depends(require_admin)])
async def delete_city(
    city_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a city (admin only). Only allowed if no properties exist for this city."""
    from app.models.city import City
    from app.models.property import Property
    
    city = db.query(City).filter(City.id == city_id).first()
    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="City not found"
        )
    
    # Check for properties
    property_count = db.query(func.count(Property.id)).filter(
        func.lower(Property.city) == city.name.lower()
    ).scalar() or 0
    
    if property_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete city '{city.name}' - {property_count} properties exist. Disable the city instead."
        )
    
    city_name = city.name
    
    # Create audit log before deletion
    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="city_deleted",
        entity_type="city",
        entity_id=city_id,
        details=f"Deleted city: {city_name}",
        ip_address=request.client.host if request.client else None,
    )
    
    db.delete(city)
    db.commit()
    
    return {"message": f"City '{city_name}' deleted successfully"}
