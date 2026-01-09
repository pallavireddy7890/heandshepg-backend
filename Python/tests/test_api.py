"""Basic API tests for He&She PG Backend."""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root():
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == "He&She PG API"


def test_health():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_api_root():
    """Test API root endpoint."""
    response = client.get("/api")
    assert response.status_code == 200
    assert "endpoints" in response.json()


def test_properties_list():
    """Test properties listing endpoint."""
    response = client.get("/api/properties")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
