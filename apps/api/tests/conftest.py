"""Test configuration and fixtures."""
import pytest

from app.services.config_apis.client import CapillaryAPIClient

# ---------------------------------------------------------------------------
# Constants (shared with tests)
# ---------------------------------------------------------------------------
TEST_HOST = "test.example.com"
TEST_TOKEN = "test-token-abc123"
TEST_ORG_ID = 100
BASE_URL = f"https://{TEST_HOST}"


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# CapillaryAPIClient fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def api_client():
    """Async CapillaryAPIClient wired with test credentials."""
    async with CapillaryAPIClient(
        host=TEST_HOST, token=TEST_TOKEN, org_id=TEST_ORG_ID
    ) as client:
        yield client
