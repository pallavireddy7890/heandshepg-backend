import pytest
from datetime import date
from uuid import uuid4
from sqlalchemy.orm import Session

from app.models import User, Profile, Property, Room, Booking, BookingStatus, AppRole, UserRole
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
        gender_preference="mixed",
        available_from=date.today(),
        status="active"
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop


@pytest.mark.anyio
async def test_rent_price_propagation_on_room_update(db: Session, test_owner: User, test_property: Property, owner_headers: dict):
    """Test that updating a room's financial details propagates to active bookings."""
    from app.routers.properties import update_room
    from app.schemas import RoomUpdate

    # 1. Create a room
    room = Room(
        id=uuid4(),
        property_id=test_property.id,
        room_type="Double Sharing",
        bed_count=2,
        price=5000,
        security_deposit=10000,
        maintenance_charge=500,
        vacancy_count=2,
        is_available=True
    )
    db.add(room)
    db.commit()
    db.refresh(room)

    # 2. Create a tenant user
    tenant = User(
        email=f"tenant_{uuid4().hex[:8]}@example.com",
        hashed_password="hashed_password",
        is_active=True,
        is_verified=True
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    # 3. Create active bookings
    # Booking 1: Fully active, deposit/maintenance not paid
    booking_active = Booking(
        id=uuid4(),
        property_id=test_property.id,
        room_id=room.id,
        customer_id=tenant.id,
        owner_id=test_owner.id,
        start_date=date.today(),
        amount=5000,
        security_deposit=10000,
        maintenance_charge=500,
        status=BookingStatus.active,
        deposit_paid=False,
        maintenance_paid=False
    )
    # Booking 2: Active, but deposit and maintenance already paid
    booking_paid = Booking(
        id=uuid4(),
        property_id=test_property.id,
        room_id=room.id,
        customer_id=tenant.id,
        owner_id=test_owner.id,
        start_date=date.today(),
        amount=5000,
        security_deposit=10000,
        maintenance_charge=500,
        status=BookingStatus.active,
        deposit_paid=True,
        maintenance_paid=True
    )
    # Booking 3: Cancelled (should NOT be updated)
    booking_cancelled = Booking(
        id=uuid4(),
        property_id=test_property.id,
        room_id=room.id,
        customer_id=tenant.id,
        owner_id=test_owner.id,
        start_date=date.today(),
        amount=5000,
        security_deposit=10000,
        maintenance_charge=500,
        status=BookingStatus.cancelled,
        deposit_paid=False,
        maintenance_paid=False
    )
    db.add_all([booking_active, booking_paid, booking_cancelled])
    db.commit()

    # 4. Perform room update via router logic
    room_update = RoomUpdate(
        price=6000,
        security_deposit=12000,
        maintenance_charge=600
    )
    
    updated_room = await update_room(
        property_id=test_property.id,
        room_id=room.id,
        room_data=room_update,
        current_user=test_owner,
        db=db
    )

    assert updated_room.price == 6000
    assert updated_room.security_deposit == 12000
    assert updated_room.maintenance_charge == 600

    # Refresh bookings from database
    db.refresh(booking_active)
    db.refresh(booking_paid)
    db.refresh(booking_cancelled)

    # Booking 1: should have all values updated because deposit/maintenance were not paid
    assert booking_active.amount == 6000
    assert booking_active.security_deposit == 12000
    assert booking_active.maintenance_charge == 600

    # Booking 2: rent should be updated, but deposit/maintenance should NOT be updated because they were already paid
    assert booking_paid.amount == 6000
    assert booking_paid.security_deposit == 10000
    assert booking_paid.maintenance_charge == 500

    # Booking 3: should NOT be updated at all because it is cancelled
    assert booking_cancelled.amount == 5000
    assert booking_cancelled.security_deposit == 10000
    assert booking_cancelled.maintenance_charge == 500
