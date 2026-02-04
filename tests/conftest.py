"""
Pytest configuration and fixtures for He&She PG backend tests.

This module provides:
- Test database setup
- Test client
- Authentication helpers
- Common fixtures
"""
import os
import sys
from typing import Generator, Dict, Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.database import Base, get_db
from app.models import User, Profile, UserRole, AppRole
from app.utils.security import create_access_token, get_password_hash


# Test database - use SQLite in memory for speed
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for tests."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    """Create fresh database for each test function."""
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Drop all tables after test
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db: Session) -> Generator[TestClient, None, None]:
    """Get test client with database override."""
    # Override the dependency
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as c:
        yield c
    
    # Clear overrides after test
    app.dependency_overrides.clear()


@pytest.fixture
def test_user_data() -> Dict[str, Any]:
    """Sample user data for signup."""
    return {
        "email": f"test_{uuid4().hex[:8]}@example.com",
        "password": "TestPass123!",
        "name": "Test User",
        "phone": "9876543210",
        "role": "customer"
    }


@pytest.fixture
def test_owner_data() -> Dict[str, Any]:
    """Sample owner data for signup."""
    return {
        "email": f"owner_{uuid4().hex[:8]}@example.com",
        "password": "OwnerPass123!",
        "name": "Test Owner",
        "phone": "9876543211",
        "role": "owner"
    }


@pytest.fixture
def created_user(db: Session) -> User:
    """Create and return a verified user."""
    # Create user
    user = User(
        email=f"existing_{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("TestPass123!"),
        is_active=True,
        is_verified=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Create profile
    profile = Profile(
        user_id=user.id,
        name="Existing User",
        phone="9876543212"
    )
    db.add(profile)
    
    # Create customer role
    customer_role = db.query(AppRole).filter(AppRole.name == "customer").first()
    if not customer_role:
        customer_role = AppRole(name="customer")
        db.add(customer_role)
        db.commit()
    
    user_role = UserRole(
        user_id=user.id,
        role=customer_role.name
    )
    db.add(user_role)
    db.commit()
    
    return user


@pytest.fixture
def auth_headers(created_user: User) -> Dict[str, str]:
    """Get authentication headers for a user."""
    token = create_access_token(data={"sub": str(created_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_user(db: Session) -> User:
    """Create and return an admin user."""
    user = User(
        email=f"admin_{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("AdminPass123!"),
        is_active=True,
        is_verified=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Create profile
    profile = Profile(
        user_id=user.id,
        name="Admin User",
        phone="9876543213"
    )
    db.add(profile)
    
    # Create admin role
    admin_role = db.query(AppRole).filter(AppRole.name == "admin").first()
    if not admin_role:
        admin_role = AppRole(name="admin")
        db.add(admin_role)
        db.commit()
    
    user_role = UserRole(
        user_id=user.id,
        role=admin_role.name
    )
    db.add(user_role)
    db.commit()
    
    return user


@pytest.fixture
def admin_headers(admin_user: User) -> Dict[str, str]:
    """Get authentication headers for admin."""
    token = create_access_token(data={"sub": str(admin_user.id)})
    return {"Authorization": f"Bearer {token}"}
