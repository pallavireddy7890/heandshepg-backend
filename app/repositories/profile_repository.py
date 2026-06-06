from sqlalchemy.orm import Session
from uuid import UUID
from app.models import Profile

class ProfileRepository:
    @staticmethod
    def get_profile_by_user_id(db: Session, user_id: UUID) -> Profile | None:
        """Fetch a user profile by user ID."""
        return db.query(Profile).filter(Profile.user_id == user_id).first()
