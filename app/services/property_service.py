from sqlalchemy.orm import Session
from uuid import UUID
from app.repositories.property_repository import PropertyRepository
from app.repositories.booking_repository import BookingRepository
from app.utils.notifications import create_notification
from fastapi import HTTPException, status
import logging

logger = logging.getLogger(__name__)

class PropertyService:
    @staticmethod
    async def moderate_property(
        db: Session,
        property_id: UUID,
        status_value: str,
        reason: str | None,
        current_user_id: UUID,
        ip_address: str | None
    ) -> dict:
        """
        Moderate a property (set status to active/inactive/banned).
        Handles active booking checks, notifications, audit log generation, and status updates.
        Only allows deactivating or banning when there are no active bookings.
        """
        property = PropertyRepository.get_property_by_id(db, property_id)
        if not property:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
            
        warning_suffix = ""
        has_active_bookings = False
        
        if status_value in ["inactive", "banned"]:
            active_bookings = BookingRepository.get_active_bookings_by_property_id(db, property_id)
            if active_bookings:
                has_active_bookings = True
                warning_suffix = ". Warning: This property has active bookings. Tenants and owner have been notified."
                
                # Notify tenants
                for booking in active_bookings:
                    tenant_msg = f"Your PG '{property.title}' is going to be {status_value}. Please contact the emergency support number (+1 419 820 7374) immediately."
                    try:
                        await create_notification(
                            db=db,
                            user_id=booking.customer_id,
                            title="PG Account Moderated",
                            message=tenant_msg,
                            notification_type="warning",
                            link="/bookings",
                            send_external=True
                        )
                    except Exception:
                        logger.exception(f"Failed to send moderation notification to tenant {booking.customer_id} for property {property_id}")
                
                # Notify owner
                owner_msg = f"Your property '{property.title}' status has been updated to {status_value} by admin. Note: This property has active bookings."
                try:
                    await create_notification(
                        db=db,
                        user_id=property.owner_id,
                        title="Property Moderated",
                        message=owner_msg,
                        notification_type="warning",
                        link="/owner/bookings",
                        send_external=True
                    )
                except Exception:
                    logger.exception(f"Failed to send moderation notification to owner {property.owner_id} for property {property_id}")
                
        if not has_active_bookings:
            old_status = property.status
            property.status = status_value
            # Create audit log
            from app.routers.admin import create_audit_log
            try:
                create_audit_log(
                    db=db,
                    user_id=current_user_id,
                    action="property_moderation",
                    entity_type="property",
                    entity_id=property_id,
                    details=f"Changed status from {old_status} to {status_value}. Reason: {reason or 'Not specified'}",
                    ip_address=ip_address,
                )
            except Exception:
                logger.exception(f"Failed to create audit log for moderation on property {property_id}")
        
        db.commit()
        return {
            "message": f"Property status updated to {status_value}{warning_suffix}" if not has_active_bookings else "You cannot ban or deactivate because your property has active bookings. Owner and tenant will be notified.",
            "has_active_bookings": has_active_bookings
        }

    @staticmethod
    async def delete_property(
        db: Session,
        property_id: UUID,
        current_user_id: UUID,
        is_admin: bool,
        ip_address: str | None = None
    ) -> dict:
        """
        Delete a property (admin or owner initiated).
        Handles active booking checks, notifications, audit log generation, and cascading deletion.
        """
        if is_admin:
            property = PropertyRepository.get_property_by_id(db, property_id)
        else:
            property = PropertyRepository.get_owner_property_by_id(db, property_id, current_user_id)
            
        if not property:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Property not found or you don't have permission to delete it"
            )
            
        # Check for active bookings
        active_bookings = BookingRepository.get_active_bookings_by_property_id(db, property_id)
        
        if active_bookings:
            # 1. Notify tenants
            for booking in active_bookings:
                tenant_msg = f"Your PG '{property.title}' has active bookings and cannot be deleted. Please contact the emergency support number (+1 419 820 7374) immediately."
                try:
                    await create_notification(
                        db=db,
                        user_id=booking.customer_id,
                        title="PG Deletion Blocked",
                        message=tenant_msg,
                        notification_type="warning",
                        link="/bookings",
                        send_external=True
                    )
                except Exception:
                    logger.exception(f"Failed to send deletion blocked notification to tenant {booking.customer_id} for property {property_id}")
            
            # 2. Notify admins
            from app.utils.notifications import get_admin_user_ids
            admin_ids = get_admin_user_ids(db)
            admin_msg = f"Blocked deletion of property '{property.title}' (ID: {property.id}) owned by user {property.owner_id} due to active bookings."
            for admin_id in admin_ids:
                try:
                    await create_notification(
                        db=db,
                        user_id=admin_id,
                        title="Property Deletion Blocked",
                        message=admin_msg,
                        notification_type="warning",
                        link="/admin",
                        send_external=True
                    )
                except Exception:
                    logger.exception(f"Failed to send deletion blocked notification to admin {admin_id}")
                    
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot delete this property because it has active bookings. Admin and tenant have been notified."
            )
            
        # Create audit log if admin
        if is_admin:
            from app.routers.admin import create_audit_log
            try:
                create_audit_log(
                    db=db,
                    user_id=current_user_id,
                    action="property_deletion",
                    entity_type="property",
                    entity_id=property_id,
                    details=f"Deleted property: {property.title}",
                    ip_address=ip_address,
                )
            except Exception:
                logger.exception(f"Failed to create audit log for deletion on property {property_id}")
            
        PropertyRepository.delete_property(db, property)
        return {"message": "Property deleted successfully"}
