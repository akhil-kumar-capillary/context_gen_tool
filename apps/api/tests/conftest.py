"""Test configuration and shared fixtures.

Uses an in-memory SQLite database so tests run without PostgreSQL.
JSONB columns are transparently mapped to SQLite JSON via type adaptation.
Each test function gets a fresh database via the ``db`` fixture.
"""
import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.auth import create_session_token
from app.database import Base, get_db

# ---------------------------------------------------------------------------
# SQLite compatibility: map PostgreSQL types to SQLite equivalents
# ---------------------------------------------------------------------------
# Monkey-patch the SQLite compiler to handle JSONB and ARRAY as plain JSON.
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

_original_visit = getattr(SQLiteTypeCompiler, "visit_JSON", None)


def _visit_jsonb(self, type_, **kw):
    return "JSON"


SQLiteTypeCompiler.visit_JSONB = _visit_jsonb  # type: ignore[attr-defined]
SQLiteTypeCompiler.visit_ARRAY = _visit_jsonb  # type: ignore[attr-defined]
from app.models.user import User, Role, Permission, UserRole, RolePermission, UserOrg
from app.models.context_tree import ContextTreeRun
from app.services.config_apis.client import CapillaryAPIClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TEST_HOST = "test.example.com"
TEST_TOKEN = "test-token-abc123"
TEST_ORG_ID = 100

# ---------------------------------------------------------------------------
# Async SQLite engine (in-memory, one per test)
# ---------------------------------------------------------------------------

_test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    echo=False,
    connect_args={"check_same_thread": False},
)
_test_session_factory = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(autouse=True)
async def _setup_db():
    """Create all tables before each test, drop after."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db():
    """Provide a clean async DB session for the test."""
    async with _test_session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# User / auth fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def test_user(db: AsyncSession) -> User:
    """Create and persist a regular (non-admin) user."""
    user = User(
        email="test@capillarytech.com",
        display_name="Test User",
        cluster="apac2",
        base_url="https://apac2.intouch.capillarytech.com",
        is_admin=False,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def admin_user(db: AsyncSession) -> User:
    """Create and persist an admin user."""
    user = User(
        email="admin@capillarytech.com",
        display_name="Admin User",
        cluster="apac2",
        base_url="https://apac2.intouch.capillarytech.com",
        is_admin=True,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def test_org(db: AsyncSession, test_user: User) -> UserOrg:
    """Associate test_user with TEST_ORG_ID."""
    org = UserOrg(user_id=test_user.id, org_id=TEST_ORG_ID, org_name="Test Org")
    db.add(org)
    await db.commit()
    return org


def make_token(user: User) -> str:
    """Generate a JWT for the given user."""
    return create_session_token(
        user_id=user.id,
        email=user.email,
        is_admin=user.is_admin,
        capillary_token="test-cap-token",
        cluster=user.cluster or "apac2",
        base_url=user.base_url or "",
    )


# ---------------------------------------------------------------------------
# FastAPI test client (overrides DB dependency)
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(db: AsyncSession):
    """Async HTTP test client with the real app, backed by the test DB.

    Patches both the FastAPI ``get_db`` dependency AND the module-level
    ``async_session`` used directly by some routers (context_engine, etc.).
    """
    from unittest.mock import patch
    from app.main import app
    import app.database as database_mod

    # Override the DB dependency to use our test session
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    # Patch async_session everywhere it's imported at module level.
    import app.routers.context_engine as ce_mod
    import app.routers.confluence as conf_mod
    import app.services.context_engine.orchestrator as orch_mod
    import app.services.databricks.storage as db_storage_mod
    import app.services.config_apis.storage as ca_storage_mod

    patches = [
        patch.object(database_mod, "async_session", _test_session_factory),
        patch.object(ce_mod, "async_session", _test_session_factory),
        patch.object(conf_mod, "async_session", _test_session_factory),
        patch.object(orch_mod, "async_session", _test_session_factory),
        patch.object(db_storage_mod, "async_session", _test_session_factory),
        patch.object(ca_storage_mod, "async_session", _test_session_factory),
    ]
    for p in patches:
        p.start()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    for p in patches:
        p.stop()

    app.dependency_overrides.clear()


@pytest.fixture
async def auth_client(client: AsyncClient, test_user: User, test_org: UserOrg):
    """Test client pre-configured with a valid auth header."""
    token = make_token(test_user)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
async def admin_client(client: AsyncClient, admin_user: User):
    """Test client pre-configured with an admin auth header."""
    token = make_token(admin_user)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


# ---------------------------------------------------------------------------
# RBAC seed fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def viewer_role(db: AsyncSession) -> Role:
    """Create a 'viewer' role with context_management:view permission."""
    role = Role(name="viewer", description="Read-only access")
    db.add(role)
    await db.flush()

    perm = Permission(module="context_management", operation="view")
    db.add(perm)
    await db.flush()

    db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    await db.commit()
    return role


@pytest.fixture
async def user_with_viewer_role(
    db: AsyncSession, test_user: User, viewer_role: Role
) -> User:
    """test_user assigned the viewer role."""
    db.add(UserRole(user_id=test_user.id, role_id=viewer_role.id))
    await db.flush()
    return test_user


# ---------------------------------------------------------------------------
# Context engine fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def completed_run(db: AsyncSession, test_user: User) -> ContextTreeRun:
    """A completed context tree run with sample tree data."""
    run = ContextTreeRun(
        id=uuid.uuid4(),
        user_id=test_user.id,
        org_id=TEST_ORG_ID,
        status="completed",
        tree_data={
            "id": "root",
            "name": "Organization Context",
            "type": "root",
            "health": 90,
            "children": [
                {
                    "id": "cat_1",
                    "name": "Analytics",
                    "type": "cat",
                    "health": 85,
                    "children": [
                        {
                            "id": "leaf_1",
                            "name": "SQL Patterns",
                            "type": "leaf",
                            "health": 80,
                            "desc": "Common SQL patterns used in analytics.",
                            "visibility": "public",
                        }
                    ],
                }
            ],
        },
        input_context_count=3,
        model_used="claude-opus-4-6",
        provider_used="anthropic",
        version=1,
    )
    db.add(run)
    await db.commit()
    return run


# ---------------------------------------------------------------------------
# CapillaryAPIClient fixture (for config_apis tests)
# ---------------------------------------------------------------------------


@pytest.fixture
async def api_client():
    """Async CapillaryAPIClient wired with test credentials."""
    async with CapillaryAPIClient(
        host=TEST_HOST, token=TEST_TOKEN, org_id=TEST_ORG_ID
    ) as c:
        yield c
