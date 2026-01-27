"""Announcements router for owner notifications to tenants."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import User, Announcement, AnnouncementPriority, Property, Booking, Profile
from app.utils.security import get_current_user, get_user_role
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/api/announcements", tags=["announcements"])


# Pydantic Schemas
class AnnouncementCreate(BaseModel):
    property_id: Optional[UUID] = None  # None = all properties
    title: str = Field(..., min_length=5, max_length=200)
    message: str = Field(..., min_length=10)
    priority: str = Field(default="normal")  # normal, important, urgent


class AnnouncementResponse(BaseModel):
    id: UUID
    owner_id: UUID
    property_id: Optional[UUID]
    title: str
    message: str
    priority: str
    is_active: bool
    created_at: str
    property_title: Optional[str] = None

    class Config:
        from_attributes = True


class AnnouncementListResponse(BaseModel):
    announcements: List[AnnouncementResponse]
    total: int


@router.post("/", response_model=AnnouncementResponse)
async def create_announcement(
    data: AnnouncementCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new announcement and notify tenants via email."""
    # Verify user is an owner
    role = get_user_role(current_user, db)
    if role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only property owners can create announcements"
        )
    
    # If property_id is specified, verify ownership
    if data.property_id:
        property_obj = db.query(Property).filter(
            Property.id == data.property_id,
            Property.owner_id == current_user.id
        ).first()
        if not property_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Property not found or you don't own it"
            )
    
    # Create the announcement
    announcement = Announcement(
        owner_id=current_user.id,
        property_id=data.property_id,
        title=data.title,
        message=data.message,
        priority=data.priority,
        is_active=True
    )
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    
    # Find all tenants to notify
    tenants_to_notify = []
    
    if data.property_id:
        # Get tenants of specific property
        bookings = db.query(Booking).filter(
            Booking.property_id == data.property_id,
            Booking.status.in_(['paid', 'active', 'checked_in'])
        ).all()
    else:
        # Get tenants of all owner's properties
        owner_properties = db.query(Property.id).filter(
            Property.owner_id == current_user.id
        ).all()
        property_ids = [p.id for p in owner_properties]
        
        bookings = db.query(Booking).filter(
            Booking.property_id.in_(property_ids),
            Booking.status.in_(['paid', 'active', 'checked_in'])
        ).all()
    
    # Collect unique tenant emails
    tenant_emails = set()
    for booking in bookings:
        tenant = db.query(User).filter(User.id == booking.customer_id).first()
        if tenant and tenant.email:
            tenant_emails.add(tenant.email)
    
    # Get owner's name
    owner_profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    owner_name = owner_profile.name if owner_profile else "Property Owner"
    
    # Get property title if specific property
    property_title = None
    if data.property_id:
        prop = db.query(Property).filter(Property.id == data.property_id).first()
        property_title = prop.title if prop else None
    
    # Send email notifications
    priority_colors = {
        "normal": "#3b82f6",  # blue
        "important": "#f59e0b",  # yellow
        "urgent": "#ef4444"  # red
    }
    priority_color = priority_colors.get(data.priority, "#3b82f6")
    
    for email in tenant_emails:
        email_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #f59e0b, #eab308); padding: 20px; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">He&She PG</h1>
            </div>
            <div style="background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px;">
                <div style="background: {priority_color}; color: white; padding: 5px 15px; border-radius: 20px; display: inline-block; margin-bottom: 15px; font-size: 12px; text-transform: uppercase;">
                    {data.priority}
                </div>
                <h2 style="color: #374151; margin-top: 0;">{data.title}</h2>
                <p style="color: #6b7280; font-size: 16px; line-height: 1.6;">
                    {data.message}
                </p>
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
                <p style="color: #9ca3af; font-size: 14px;">
                    <strong>From:</strong> {owner_name}
                    {f'<br><strong>Property:</strong> {property_title}' if property_title else ''}
                </p>
                <p style="color: #9ca3af; font-size: 12px; text-align: center; margin-top: 20px;">
                    © 2024 He&She PG. All rights reserved.
                </p>
            </div>
        </body>
        </html>
        """
        
        NotificationService.send_email(
            to_email=email,
            subject=f"[{data.priority.upper()}] {data.title} - He&She PG",
            html_content=email_body
        )
    
    return AnnouncementResponse(
        id=announcement.id,
        owner_id=announcement.owner_id,
        property_id=announcement.property_id,
        title=announcement.title,
        message=announcement.message,
        priority=announcement.priority,
        is_active=announcement.is_active,
        created_at=announcement.created_at.isoformat(),
        property_title=property_title
    )


@router.get("/", response_model=AnnouncementListResponse)
async def get_owner_announcements(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all announcements created by the current owner."""
    role = get_user_role(current_user, db)
    if role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only property owners can access this endpoint"
        )
    
    announcements = db.query(Announcement).filter(
        Announcement.owner_id == current_user.id
    ).order_by(desc(Announcement.created_at)).all()
    
    result = []
    for ann in announcements:
        property_title = None
        if ann.property_id:
            prop = db.query(Property).filter(Property.id == ann.property_id).first()
            property_title = prop.title if prop else None
        
        result.append(AnnouncementResponse(
            id=ann.id,
            owner_id=ann.owner_id,
            property_id=ann.property_id,
            title=ann.title,
            message=ann.message,
            priority=ann.priority,
            is_active=ann.is_active,
            created_at=ann.created_at.isoformat(),
            property_title=property_title
        ))
    
    return AnnouncementListResponse(announcements=result, total=len(result))


@router.get("/tenant", response_model=AnnouncementListResponse)
async def get_tenant_announcements(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all active announcements for the current tenant based on their bookings."""
    # Find all properties where the user has active bookings
    active_bookings = db.query(Booking).filter(
        Booking.customer_id == current_user.id,
        Booking.status.in_(['paid', 'active', 'checked_in'])
    ).all()
    
    if not active_bookings:
        return AnnouncementListResponse(announcements=[], total=0)
    
    property_ids = [b.property_id for b in active_bookings]
    owner_ids = [b.owner_id for b in active_bookings]
    
    # Get announcements for these properties or from these owners (for all-property announcements)
    announcements = db.query(Announcement).filter(
        Announcement.is_active == True,
        (
            Announcement.property_id.in_(property_ids) |
            (Announcement.property_id.is_(None) & Announcement.owner_id.in_(owner_ids))
        )
    ).order_by(desc(Announcement.created_at)).limit(20).all()
    
    result = []
    for ann in announcements:
        property_title = None
        if ann.property_id:
            prop = db.query(Property).filter(Property.id == ann.property_id).first()
            property_title = prop.title if prop else None
        
        result.append(AnnouncementResponse(
            id=ann.id,
            owner_id=ann.owner_id,
            property_id=ann.property_id,
            title=ann.title,
            message=ann.message,
            priority=ann.priority,
            is_active=ann.is_active,
            created_at=ann.created_at.isoformat(),
            property_title=property_title
        ))
    
    return AnnouncementListResponse(announcements=result, total=len(result))


@router.delete("/{announcement_id}")
async def delete_announcement(
    announcement_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an announcement (owner only)."""
    announcement = db.query(Announcement).filter(
        Announcement.id == announcement_id,
        Announcement.owner_id == current_user.id
    ).first()
    
    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found or you don't have permission to delete it"
        )
    
    db.delete(announcement)
    db.commit()
    
    return {"message": "Announcement deleted successfully"}
