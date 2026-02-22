"""Test configuration and fixtures."""
import pytest


@pytest.fixture
def test_user():
    return {
        "user_id": 1,
        "email": "test@capillarytech.com",
        "is_admin": False,
        "capillary_token": "test-token",
        "cluster": "apac2",
        "base_url": "https://apac2.intouch.capillarytech.com",
    }


@pytest.fixture
def admin_user():
    return {
        "user_id": 1,
        "email": "akhil.kumar@capillarytech.com",
        "is_admin": True,
        "capillary_token": "admin-token",
        "cluster": "apac2",
        "base_url": "https://apac2.intouch.capillarytech.com",
    }
