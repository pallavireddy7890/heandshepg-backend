"""Maintenance tickets router."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Property, Booking
from app.models.maintenance import Ticket, TicketStatus
from app.schemas.maintenance import TicketCreate, TicketUpdate, TicketResponse
from app.utils.security import get_current_user

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
    return new_ticket


@router.get("/tickets/me", response_model=List[TicketResponse])
async def list_my_tickets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List tickets raised by the current user."""
    return db.query(Ticket).filter(Ticket.tenant_id == current_user.id).order_by(Ticket.created_at.desc()).all()


@router.get("/tickets/owner", response_model=List[TicketResponse])
async def list_owner_tickets(
    property_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List tickets for properties owned by the current user."""
    query = db.query(Ticket).join(Property, Ticket.property_id == Property.id).filter(Property.owner_id == current_user.id)
    if property_id:
        query = query.filter(Ticket.property_id == property_id)
    return query.order_by(Ticket.created_at.desc()).all()


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
    return ticket
