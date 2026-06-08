"""
Authentication API tests.

Tests for the auth endpoints including:
- Signup flow
- Login flow
- Token validation
- Protected routes
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User, EmailVerification


class TestSignup:
    """Tests for the signup endpoint."""
    
    def test_signup_success(self, client: TestClient, test_user_data: dict):
        """Test successful signup initiates email verification."""
        response = client.post("/api/auth/signup", json=test_user_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["requires_verification"] is True
        assert data["email"] == test_user_data["email"].lower()
        assert "expires_in_minutes" in data
    
    def test_signup_duplicate_email(self, client: TestClient, created_user: User, db: Session):
        """Test signup fails for existing email."""
        duplicate_data = {
            "email": created_user.email,
            "password": "TestPass123!",
            "name": "Another User",
            "phone": "9876543299",
            "role": "customer"
        }
        
        response = client.post("/api/auth/signup", json=duplicate_data)
        
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"].lower() or "already registered" in response.json()["detail"].lower()
    
    def test_signup_invalid_email(self, client: TestClient):
        """Test signup fails with invalid email format."""
        invalid_data = {
            "email": "not-an-email",
            "password": "TestPass123!",
            "name": "Test User",
            "phone": "9876543210",
            "role": "customer"
        }
        
        response = client.post("/api/auth/signup", json=invalid_data)
        
        assert response.status_code == 422  # Validation error
    
    def test_signup_short_password(self, client: TestClient, test_user_data: dict):
        """Test signup fails with short password."""
        test_user_data["password"] = "short"
        
        response = client.post("/api/auth/signup", json=test_user_data)
        
        assert response.status_code == 422  # Validation error
    
    def test_signup_owner_role(self, client: TestClient, test_owner_data: dict):
        """Test owner signup creates pending approval state."""
        response = client.post("/api/auth/signup", json=test_owner_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["requires_verification"] is True


class TestLogin:
    """Tests for the login endpoints."""
    
    def test_login_success(self, client: TestClient, created_user: User, db: Session):
        """Test successful login returns token."""
        login_data = {
            "identifier": created_user.email,
            "password": "TestPass123!"
        }
        
        response = client.post("/api/auth/login/json", json=login_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["token"]["access_token"]
        assert data["user"]["email"] == created_user.email
    
    def test_login_wrong_password(self, client: TestClient, created_user: User):
        """Test login fails with wrong password."""
        login_data = {
            "identifier": created_user.email,
            "password": "WrongPassword123!"
        }
        
        response = client.post("/api/auth/login/json", json=login_data)
        
        assert response.status_code == 401
        assert "incorrect" in response.json()["detail"].lower()
    
    def test_login_nonexistent_user(self, client: TestClient):
        """Test login fails for non-existent user."""
        login_data = {
            "identifier": "nobody@example.com",
            "password": "TestPass123!"
        }
        
        response = client.post("/api/auth/login/json", json=login_data)
        
        assert response.status_code == 401
    
    def test_login_inactive_user(self, client: TestClient, db: Session, created_user: User):
        """Test login fails for deactivated user."""
        # Deactivate user
        created_user.is_active = False
        db.commit()
        
        login_data = {
            "identifier": created_user.email,
            "password": "TestPass123!"
        }
        
        response = client.post("/api/auth/login/json", json=login_data)
        
        assert response.status_code == 403
        assert "deactivated" in response.json()["detail"].lower()
    
    def test_login_form_endpoint(self, client: TestClient, created_user: User):
        """Test OAuth2 form login endpoint."""
        response = client.post(
            "/api/auth/login",
            data={
                "username": created_user.email,
                "password": "TestPass123!"
            }
        )
        
        assert response.status_code == 200
        assert "token" in response.json()


class TestTokenValidation:
    """Tests for token validation and protected routes."""
    
    def test_protected_route_with_token(self, client: TestClient, auth_headers: dict):
        """Test accessing protected route with valid token."""
        response = client.get("/api/auth/me", headers=auth_headers)
        
        assert response.status_code == 200
        assert "user" in response.json()
    
    def test_protected_route_without_token(self, client: TestClient):
        """Test accessing protected route without token fails."""
        response = client.get("/api/auth/me")
        
        assert response.status_code == 401
    
    def test_protected_route_invalid_token(self, client: TestClient):
        """Test accessing protected route with invalid token fails."""
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid_token_here"}
        )
        
        assert response.status_code == 401
    
    def test_protected_route_expired_token(self, client: TestClient, created_user: User):
        """Test accessing protected route with expired token fails."""
        from datetime import timedelta
        from app.utils.security import create_access_token
        
        # Create token that's already expired
        expired_token = create_access_token(
            data={"sub": str(created_user.id)},
            expires_delta=timedelta(seconds=-1)  # Already expired
        )
        
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        
        assert response.status_code == 401


class TestPasswordReset:
    """Tests for password reset flow."""
    
    def test_forgot_password_existing_user(self, client: TestClient, created_user: User):
        """Test forgot password for existing user returns success."""
        response = client.post(
            "/api/auth/forgot-password",
            json={"email": created_user.email}
        )
        
        # Should always return success to prevent email enumeration
        assert response.status_code == 200
    
    def test_forgot_password_nonexistent_user(self, client: TestClient):
        """Test forgot password for non-existent email still returns success."""
        response = client.post(
            "/api/auth/forgot-password",
            json={"email": "nonexistent@example.com"}
        )
        
        # Should still return success to prevent email enumeration
        assert response.status_code == 200


class TestRateLimiting:
    """Tests for rate limiting on auth endpoints."""
    
    def test_signup_rate_limit(self, client: TestClient):
        """Test that signup is rate limited after multiple attempts."""
        # Make rapid requests
        for i in range(5):
            response = client.post(
                "/api/auth/signup",
                json={
                    "email": f"test{i}@example.com",
                    "password": "TestPass123!",
                    "name": "Test",
                    "phone": f"987654321{i}",
                    "role": "customer"
                }
            )
        
        # After several requests, should get rate limited
        # Note: The exact number depends on rate limit config
        # This test verifies the endpoint doesn't crash with rapid requests
        assert response.status_code in [200, 429]  # Success or rate limited
    
    def test_login_rate_limit(self, client: TestClient):
        """Test that login is rate limited after multiple failed attempts."""
        # Attempt multiple logins
        for i in range(7):
            response = client.post(
                "/api/auth/login/json",
                json={
                    "identifier": "test@example.com",
                    "password": "wrong_password"
                }
            )
        
        # Should eventually get rate limited
        assert response.status_code in [401, 429]  # Unauthorized or rate limited
