from sqlalchemy.orm import Session
from uuid import UUID
from app.models import Property

class PropertyRepository:
    @staticmethod
    def get_property_by_id(db: Session, property_id: UUID) -> Property | None:
        """Fetch a property by its ID."""
        return db.query(Property).filter(
            Property.id == property_id,
            Property.inactive_at.is_(None)
        ).first()

    @staticmethod
    def get_owner_property_by_id(db: Session, property_id: UUID, owner_id: UUID) -> Property | None:
        """Fetch a property by its ID and owner ID."""
        return db.query(Property).filter(
            Property.id == property_id,
            Property.owner_id == owner_id,
            Property.inactive_at.is_(None)
        ).first()

    @staticmethod
    def delete_property(db: Session, property: Property) -> None:
        """Soft-delete a property by marking it inactive and recording the timestamp."""
        from datetime import datetime, timezone
        property.status = "inactive"
        property.inactive_at = datetime.now(timezone.utc)
        db.commit()
