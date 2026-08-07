"""Maintenance tickets router."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Property, Booking, Profile, Room
from app.models.maintenance import Ticket, TicketStatus
from app.schemas.maintenance import TicketCreate, TicketUpdate, TicketResponse
from app.utils.security import get_current_user
from sqlalchemy.orm import joinedload

router = APIRouter(prefix="/maintenance", tags=["Maintenance"])


@router.post("/tickets", response_model=TicketResponse)
async def raise_ticket(
    ticket_data: TicketCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Raise a maintenance ticket (Tenant only)."""
    # Verify the tenant has an active booking for this property
    booking = db.query(Booking).filter(
        Booking.customer_id == current_user.id,
        Booking.property_id == ticket_data.property_id,
        Booking.status.in_(["active", "checked_in", "paid"])
    ).first()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active booking found to raise a ticket for this property"
        )
        
    new_ticket = Ticket(
        tenant_id=current_user.id,
        property_id=ticket_data.property_id,
        room_id=ticket_data.room_id or booking.room_id,
        booking_id=ticket_data.booking_id or booking.id,
        title=ticket_data.title,
        description=ticket_data.description,
        priority=ticket_data.priority
    )
    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)
    
    # Notify owner about new maintenance ticket (Omnichannel: Web, Email, SMS)
    try:
        from app.utils.notifications import create_notification

        property_obj = db.query(Property).filter(
            Property.id == new_ticket.property_id
        ).first()

        tenant = (
            db.query(User)
            .options(joinedload(User.profile))
            .filter(User.id == new_ticket.tenant_id)
            .first()
        )

        room = None
        if new_ticket.room_id:
            room = db.query(Room).filter(Room.id == new_ticket.room_id).first()

        tenant_name = (
            tenant.profile.name
            if tenant and tenant.profile
            else tenant.email
            if tenant
            else "Tenant"
        )


        if property_obj:
            await create_notification(
                db=db,
                user_id=property_obj.owner_id,
                property_id=property_obj.id,
                title="🔧 New Maintenance Ticket",
                message=(
                    f"A new maintenance request has been raised by {tenant_name} "
                    f"for Room {room.room_number}, Floor {room.floor_number} "
                    f"in {property_obj.title}. "
                    f"Priority: {new_ticket.priority.value.title()}."
                ),
                notification_type="maintenance",
                link="/owner/dashboard?tab=maintenance",
                send_external=True
            )

    except Exception as e:
        import logging
        logging.warning(f"Failed to send ticket creation notification: {e}")

    return new_ticket


@router.get("/tickets/me", response_model=List[TicketResponse])
async def list_my_tickets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List tickets raised by the current user."""
    return db.query(Ticket).filter(Ticket.tenant_id == current_user.id).order_by(Ticket.created_at.desc()).all()


'''@router.get("/tickets/owner", response_model=List[TicketResponse])
async def list_owner_tickets(
    property_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List tickets for properties owned by the current user."""
    query = db.query(Ticket).join(Property, Ticket.property_id == Property.id).filter(Property.owner_id == current_user.id)
    if property_id:
        query = query.filter(Ticket.property_id == property_id)
    return query.order_by(Ticket.created_at.desc()).all()'''



@router.get("/tickets/owner", response_model=List[TicketResponse])
async def list_owner_tickets(
    property_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List tickets for properties owned by the current user."""

    query = (
        db.query(Ticket)
        .join(Property, Ticket.property_id == Property.id)
        .options(
            joinedload(Ticket.tenant).joinedload(User.profile),
            joinedload(Ticket.property),
            joinedload(Ticket.room)
        )
        .filter(Property.owner_id == current_user.id)
    )

    if property_id:
        query = query.filter(Ticket.property_id == property_id)

    tickets = query.order_by(Ticket.created_at.desc()).all()

    response = []

    for ticket in tickets:
        response.append(
            TicketResponse(
                id=ticket.id,
                tenant_id=ticket.tenant_id,
                property_id=ticket.property_id,
                room_id=ticket.room_id,
                booking_id=ticket.booking_id,

                title=ticket.title,
                description=ticket.description,
                priority=ticket.priority,
                status=ticket.status,

                created_at=ticket.created_at,
                updated_at=ticket.updated_at,

                tenant_name=ticket.tenant.profile.name
                if ticket.tenant and ticket.tenant.profile
                else None,

                tenant_email=ticket.tenant.email
                if ticket.tenant
                else None,

                property_title=ticket.property.title
                if ticket.property
                else None,

                room_number=ticket.room.room_number
                if ticket.room
                else None,

                floor=ticket.room.floor_number
                if ticket.room
                else None,
            )
        )

    return response


@router.patch("/tickets/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    ticket_id: UUID,
    ticket_update: TicketUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update ticket status/priority (Owner or Tenant)."""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    # Check if owner or tenant
    property = db.query(Property).filter(Property.id == ticket.property_id).first()
    is_tenant = ticket.tenant_id == current_user.id
    is_owner = property.owner_id == current_user.id
    
    if not is_tenant and not is_owner:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    if ticket_update.status:
        # Only owner can mark as in_progress or resolved
        if ticket_update.status in [TicketStatus.in_progress, TicketStatus.resolved] and not is_owner:
            raise HTTPException(status_code=403, detail="Only owner can update to in_progress or resolved")
        ticket.status = ticket_update.status
        
    if ticket_update.priority:
        ticket.priority = ticket_update.priority
        
    db.commit()
    db.refresh(ticket)
    
    # Notify tenant about ticket update (Omnichannel: Web, Email, SMS)
    try:
        from app.utils.notifications import create_notification
        if ticket_update.status:
            status_msg = ticket_update.status.value if hasattr(ticket_update.status, 'value') else str(ticket_update.status)
            await create_notification(
                db=db,
                user_id=ticket.tenant_id,
                property_id=ticket.property_id,
                title="🔧 Ticket Update",
                message=f"Your maintenance ticket '{ticket.title}' status has been updated to: {status_msg}",
                notification_type="maintenance",
                link="/maintenance",
                send_external=True
            )
    except Exception as e:
        import logging
        logging.warning(f"Failed to send ticket update notification: {e}")
        
    return ticket
