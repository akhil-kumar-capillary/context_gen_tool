"""Tests for health and basic app configuration."""
import pytest
from httpx import AsyncClient


class TestHealth:
    async def test_health_returns_ok(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "aira-context-gen"

    async def test_cors_headers_present(self, client: AsyncClient):
        resp = await client.options(
            "/health",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
        )
        assert resp.status_code in (200, 204)
        assert "access-control-allow-origin" in resp.headers
