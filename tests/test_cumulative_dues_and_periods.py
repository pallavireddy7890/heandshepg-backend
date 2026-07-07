import pytest
from datetime import date, datetime, timedelta
from uuid import uuid4
from sqlalchemy.orm import Session

from app.models import User, Profile, Property, Room, Booking, BookingStatus, AppRole, UserRole
from app.models.wallet import Wallet, WalletTransaction, TransactionStatus, TransactionType
from app.routers.owner import calculate_month_rent_stats, get_rent_management_data
from app.services.wallet_service import WalletService
from app.utils.notifications import notify_payment_verified, notify_payment_received


@pytest.fixture
def test_owner(db: Session) -> User:
    """Create and return a verified owner."""
    user = User(
        email=f"owner_{uuid4().hex[:8]}@example.com",
        hashed_password="hashed_password",
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
def test_property(db: Session, test_owner: User) -> Property:
    """Create and return an active property."""
    prop = Property(
        id=uuid4(),
        owner_id=test_owner.id,
        title="Bandra Premium PG",
        description="A nice place to stay",
        address="123 Ocean Drive",
        city="Mumbai",
        locality="Bandra",
        monthly_rent=10000,
        deposit=20000,
        gender_preference="mixed",
        available_from=date.today(),
        status="active"
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop


@pytest.fixture
def test_room(db: Session, test_property: Property) -> Room:
    """Create and return a room."""
    room = Room(
        id=uuid4(),
        property_id=test_property.id,
        room_type="Single Room",
        bed_count=1,
        price=10000,
        security_deposit=20000,
        maintenance_charge=1000,
        vacancy_count=1,
        is_available=True
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


@pytest.fixture
def test_tenant(db: Session) -> User:
    """Create a tenant user."""
    user = User(
        email=f"tenant_{uuid4().hex[:8]}@example.com",
        hashed_password="hashed_password",
        is_active=True,
        is_verified=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    profile = Profile(
        user_id=user.id,
        name="Test Tenant",
        phone="9876543210"
    )
    db.add(profile)
    db.commit()
    return user


@pytest.mark.anyio
async def test_cumulative_dues_calculation_and_periods(db: Session, test_owner: User, test_property: Property, test_room: Room, test_tenant: User):
    """Test that rent is calculated cumulatively, and transaction billing periods/times are correct."""
    
    # 1. Setup a booking starting 45 days ago
    today_date = date.today()
    start_date = today_date - timedelta(days=45)
    
    booking = Booking(
        id=uuid4(),
        property_id=test_property.id,
        room_id=test_room.id,
        customer_id=test_tenant.id,
        owner_id=test_owner.id,
        start_date=start_date,
        amount=10000,
        security_deposit=20000,
        maintenance_charge=1000,
        status=BookingStatus.active,
        deposit_paid=False,
        maintenance_paid=False
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # Make sure owner and customer wallets exist
    owner_wallet = WalletService.get_or_create_wallet(db, test_owner.id)
    customer_wallet = WalletService.get_or_create_wallet(db, test_tenant.id)

    # Calculate expected billing cycles to check against
    # Cycle 1 starts at start_date
    c1_start = start_date
    import calendar
    def get_date_for_month(base_date, month_offset: int):
        m = (base_date.month + month_offset - 1) % 12 + 1
        y = base_date.year + (base_date.month + month_offset - 1) // 12
        last_day_of_m = calendar.monthrange(y, m)[1]
        return date(y, m, min(base_date.day, last_day_of_m))

    c2_start = get_date_for_month(start_date, 1)
    c1_end = c2_start - timedelta(days=1)

    # 2. Query stats for the current month
    stats = calculate_month_rent_stats(db, booking, month=today_date.month, year=today_date.year)
    
    assert stats["cumulative_due"] == 30000.0
    assert stats["rent_paid"] == 0.0
    assert stats["status"] == "unpaid"

    # 3. Create a payment for first cycle (made 40 days ago)
    payment_time = datetime.combine(start_date + timedelta(days=5), datetime.min.time()) + timedelta(hours=10, minutes=30)
    txn = WalletTransaction(
        id=uuid4(),
        wallet_id=owner_wallet.id,
        booking_id=booking.id,
        payer_id=test_tenant.id,
        receiver_id=test_owner.id,
        amount=1000000,  # 10000 in rupees (10000 * 100 paise)
        payment_type="rent",
        transaction_type=TransactionType.credit,
        status=TransactionStatus.completed,
        payment_method="offline",
        created_at=payment_time
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)

    # 4. Re-query stats for current month
    stats_updated = calculate_month_rent_stats(db, booking, month=today_date.month, year=today_date.year)
    assert stats_updated["cumulative_due"] == 30000.0
    assert stats_updated["rent_paid"] == 10000.0
    # Since today is start_date + 45 days, and c2 starts at start_date + ~30 days, c2 is active.
    # Total due up to today is 20000, paid 10000. So status must be partial.
    assert stats_updated["status"] == "partial"

    # 5. Check get_transactions response
    transactions = WalletService.get_transactions(db, test_owner.id)
    assert len(transactions) == 1
    t_res = transactions[0]
    expected_period = f"{c1_start.strftime('%d %b %Y')} - {c1_end.strftime('%d %b %Y')}"
    assert t_res["billing_period"] == expected_period
    
    # 10:30 UTC + 5:30 = 16:00 (4:00 PM)
    expected_time = (payment_time + timedelta(hours=5, minutes=30)).strftime("%d %b %Y %I:%M %p")
    assert t_res["payment_time"] == expected_time

    # 6. Check notify_payment_verified message contents
    notification = await notify_payment_verified(db, test_tenant.id, 10000.0, test_property.title, transaction_id=txn.id)
    assert expected_time in notification.message
    assert expected_period in notification.message
