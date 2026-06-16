import pytest
from datetime import datetime, timedelta, date
from uuid import uuid4
from unittest.mock import patch

from sqlalchemy.orm import Session
from app.models import User, Profile, Property, Room, RoomBed, Booking, Notification
from app.scheduler import cleanup_expired_bookings

@pytest.fixture
def setup_test_data(db: Session):
    # 1. Create Owner and Tenant
    owner = User(
        email=f"owner_{uuid4().hex[:8]}@example.com",
        hashed_password="hashed_password",
        is_active=True,
        is_verified=True
    )
    tenant = User(
        email=f"tenant_{uuid4().hex[:8]}@example.com",
        hashed_password="hashed_password",
        is_active=True,
        is_verified=True
    )
    db.add_all([owner, tenant])
    db.commit()
    db.refresh(owner)
    db.refresh(tenant)

    owner_profile = Profile(user_id=owner.id, name="Test Owner", phone="1234567890")
    tenant_profile = Profile(user_id=tenant.id, name="Test Tenant", phone="0987654321")
    db.add_all([owner_profile, tenant_profile])

    # 2. Create Property
    prop = Property(
        id=uuid4(),
        owner_id=owner.id,
        title="Test PG Property",
        address="123 PG Lane",
        city="Mumbai",
        gender_preference="mixed",
        available_from=date.today(),
        status="active"
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)

    # 3. Create Room
    room = Room(
        id=uuid4(),
        property_id=prop.id,
        room_type="Double Sharing",
        bed_count=2,
        price=5000,
        vacancy_count=2,
        is_available=True
    )
    db.add(room)
    db.commit()
    db.refresh(room)

    # 4. Create RoomBeds
    bed1 = RoomBed(id=uuid4(), room_id=room.id, bed_number="A", status="available")
    bed2 = RoomBed(id=uuid4(), room_id=room.id, bed_number="B", status="available")
    db.add_all([bed1, bed2])
    db.commit()
    db.refresh(bed1)
    db.refresh(bed2)

    return {
        "owner": owner,
        "tenant": tenant,
        "property": prop,
        "room": room,
        "beds": [bed1, bed2]
    }

def test_cleanup_expired_bookings_requested(db: Session, setup_test_data):
    data = setup_test_data
    room = data["room"]
    tenant = data["tenant"]
    owner = data["owner"]
    prop = data["property"]

    # Create a requested booking created 49 hours ago
    created_at_time = datetime.utcnow() - timedelta(hours=49)
    booking = Booking(
        id=uuid4(),
        property_id=prop.id,
        room_id=room.id,
        customer_id=tenant.id,
        owner_id=owner.id,
        start_date=date.today(),
        amount=5000,
        security_deposit=10000,
        status="requested",
        created_at=created_at_time,
        updated_at=created_at_time
    )
    db.add(booking)
    db.commit()

    # Verify initial vacancy count is 2 (sync_room_vacancy counts paid/checked_in/active/vacate_requested)
    # The requested status is excluded from the room's stored vacancy_count.
    assert room.vacancy_count == 2

    # Patch SessionLocal in app.scheduler to use our in-memory test db session factory
    with patch("app.scheduler.SessionLocal", return_value=db):
        with patch.object(db, "close", lambda: None):
            cleanup_expired_bookings()

    # Refresh booking
    db.refresh(booking)
    assert booking.status == "cancelled"


def test_cleanup_expired_bookings_accepted_unpaid(db: Session, setup_test_data):
    data = setup_test_data
    room = data["room"]
    tenant = data["tenant"]
    owner = data["owner"]
    prop = data["property"]
    bed1 = data["beds"][0]

    # Set bed1 to occupied representing a hold/assignment
    bed1.status = "occupied"
    bed1.current_tenant_id = tenant.id
    db.commit()

    # Create an accepted booking updated 25 hours ago
    updated_at_time = datetime.utcnow() - timedelta(hours=25)
    booking = Booking(
        id=uuid4(),
        property_id=prop.id,
        room_id=room.id,
        bed_id=bed1.id,
        customer_id=tenant.id,
        owner_id=owner.id,
        start_date=date.today(),
        amount=5000,
        security_deposit=10000,
        status="accepted",
        created_at=updated_at_time - timedelta(hours=2),
        updated_at=updated_at_time
    )
    db.add(booking)
    db.commit()

    # Patch SessionLocal in app.scheduler to use our in-memory test db session factory
    with patch("app.scheduler.SessionLocal", return_value=db):
        with patch.object(db, "close", lambda: None):
            cleanup_expired_bookings()

    # Refresh booking, bed, and room
    db.refresh(booking)
    db.refresh(bed1)
    db.refresh(room)

    # Check status and hold release
    assert booking.status == "cancelled"
    assert bed1.status == "available"
    assert bed1.current_tenant_id is None
    
    # Check notifications
    notifications = db.query(Notification).filter(Notification.title.like("%Booking Expired%")).all()
    # Should have notifications for both customer and owner
    assert len(notifications) >= 2
