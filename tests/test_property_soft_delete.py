import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from uuid import uuid4
from datetime import datetime, timezone, date

from app.models import User, Profile, UserRole, AppRole, Property, Room, GenderPreference
from app.repositories.property_repository import PropertyRepository
from app.utils.security import get_password_hash, create_access_token

@pytest.fixture
def test_owner(db: Session) -> User:
    """Create and return a verified owner."""
    user = User(
        email=f"owner_{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("OwnerPass123!"),
        is_active=True,
        is_verified=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    profile = Profile(
        user_id=user.id,
        name="Test Owner",
        phone="9876543211"
    )
    db.add(profile)
    
    user_role = UserRole(
        user_id=user.id,
        role=AppRole.owner
    )
    db.add(user_role)
    db.commit()
    return user

@pytest.fixture
def owner_headers(test_owner: User) -> dict:
    """Get authentication headers for owner."""
    token = create_access_token(data={"sub": str(test_owner.id)})
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def test_property(db: Session, test_owner: User) -> Property:
    """Create and return an active property."""
    prop = Property(
        id=uuid4(),
        owner_id=test_owner.id,
        title="Beautiful Sea View Apartment",
        description="A nice place to stay",
        address="123 Ocean Drive",
        city="Mumbai",
        locality="Bandra",
        monthly_rent=15000,
        deposit=30000,
        gender_preference=GenderPreference.mixed,
        available_from=date.today(),
        status="active"
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop

def test_repository_soft_delete(db: Session, test_property: Property):
    """Test that deleting a property updates status and sets inactive_at."""
    assert test_property.status == "active"
    assert test_property.inactive_at is None
    
    # Run repository soft delete
    PropertyRepository.delete_property(db, test_property)
    
    # Refresh property from database directly bypass get_property_by_id (which would return None)
    # Using Session.query directly bypasses the soft delete filter in PropertyRepository
    db.refresh(test_property)
    
    assert test_property.status == "inactive"
    assert test_property.inactive_at is not None
    
    # Check that it cannot be retrieved via repository get methods
    retrieved = PropertyRepository.get_property_by_id(db, test_property.id)
    assert retrieved is None
    
    retrieved_owner = PropertyRepository.get_owner_property_by_id(db, test_property.id, test_property.owner_id)
    assert retrieved_owner is None

@pytest.mark.anyio
async def test_get_owner_properties_direct(db: Session, test_owner: User, test_property: Property):
    """Test get_owner_properties router logic directly (avoiding test client HTTPX/Starlette signature issue)."""
    from app.routers.owner import get_owner_properties
    
    # Call get_owner_properties
    result = await get_owner_properties(current_user=test_owner, db=db)
    
    assert len(result) == 1
    assert result[0]["id"] == str(test_property.id)
    assert result[0]["title"] == test_property.title
    assert result[0]["city"] == test_property.city
