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


