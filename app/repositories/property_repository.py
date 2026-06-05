from sqlalchemy.orm import Session
from uuid import UUID
from app.models import Property

class PropertyRepository:
    @staticmethod
    def get_property_by_id(db: Session, property_id: UUID) -> Property | None:
        """Fetch a property by its ID."""
        return db.query(Property).filter(Property.id == property_id).first()

    @staticmethod
    def get_owner_property_by_id(db: Session, property_id: UUID, owner_id: UUID) -> Property | None:
        """Fetch a property by its ID and owner ID."""
        return db.query(Property).filter(
            Property.id == property_id,
            Property.owner_id == owner_id
        ).first()

    @staticmethod
    def delete_property(db: Session, property: Property) -> None:
        """Delete a property record from the database."""
        db.delete(property)
        db.commit()
