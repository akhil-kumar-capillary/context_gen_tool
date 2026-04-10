"""Tests for context engine endpoints — tree CRUD, optimistic locking, run lifecycle.

Uses admin_client since admin bypasses RBAC, keeping tests focused on
business logic rather than permission setup.
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.context_tree import ContextTreeRun
from tests.conftest import TEST_ORG_ID, make_token


class TestRunListAndGet:
    """Tests for listing and fetching tree runs."""

    async def test_list_runs_empty(self, admin_client: AsyncClient):
        resp = await admin_client.get(f"/api/context-engine/runs?org_id={TEST_ORG_ID}")
        assert resp.status_code == 200
        assert resp.json()["runs"] == []

    async def test_list_runs_returns_completed(
        self, admin_client: AsyncClient, completed_run: ContextTreeRun
    ):
        resp = await admin_client.get(f"/api/context-engine/runs?org_id={TEST_ORG_ID}")
        assert resp.status_code == 200
        runs = resp.json()["runs"]
        assert len(runs) == 1
        assert runs[0]["id"] == str(completed_run.id)
        assert runs[0]["status"] == "completed"
        assert "version" in runs[0]

    async def test_get_run_returns_tree_data(
        self, admin_client: AsyncClient, completed_run: ContextTreeRun
    ):
        resp = await admin_client.get(
            f"/api/context-engine/runs/{completed_run.id}?org_id={TEST_ORG_ID}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tree_data"]["id"] == "root"
        assert len(data["tree_data"]["children"]) == 1

    async def test_get_latest_returns_completed(
        self, admin_client: AsyncClient, completed_run: ContextTreeRun
    ):
        resp = await admin_client.get(
            f"/api/context-engine/runs/latest?org_id={TEST_ORG_ID}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(completed_run.id)


class TestTreeMutationsWithVersioning:
    """Tests for tree CRUD with optimistic locking."""

    async def test_update_tree_with_correct_version(
        self, admin_client: AsyncClient, completed_run: ContextTreeRun
    ):
        new_tree = completed_run.tree_data.copy()
        new_tree["name"] = "Updated Root"
        resp = await admin_client.put(
            f"/api/context-engine/runs/{completed_run.id}/tree?org_id={TEST_ORG_ID}",
            json={"tree_data": new_tree, "version": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["version"] == 2

    async def test_update_tree_stale_version_returns_409(
        self, admin_client: AsyncClient, completed_run: ContextTreeRun
    ):
        new_tree = completed_run.tree_data.copy()
        resp = await admin_client.put(
            f"/api/context-engine/runs/{completed_run.id}/tree?org_id={TEST_ORG_ID}",
            json={"tree_data": new_tree, "version": 99},  # wrong version
        )
        assert resp.status_code == 409

    async def test_add_node(
        self, admin_client: AsyncClient, completed_run: ContextTreeRun
    ):
        resp = await admin_client.post(
            f"/api/context-engine/runs/{completed_run.id}/node?org_id={TEST_ORG_ID}",
            json={
                "parent_id": "cat_1",
                "node": {"name": "New Leaf", "type": "leaf", "desc": "Test content"},
                "version": 1,
            },
        )
        assert resp.status_code == 200
        tree = resp.json()["tree_data"]
        cat = next(c for c in tree["children"] if c["id"] == "cat_1")
        assert len(cat["children"]) == 2  # original leaf + new one
        assert resp.json()["version"] == 2

    async def test_add_node_bad_parent_returns_404(
        self, admin_client: AsyncClient, completed_run: ContextTreeRun
    ):
        resp = await admin_client.post(
            f"/api/context-engine/runs/{completed_run.id}/node?org_id={TEST_ORG_ID}",
            json={
                "parent_id": "nonexistent",
                "node": {"name": "Orphan", "type": "leaf"},
                "version": 1,
            },
        )
        assert resp.status_code == 404

    async def test_update_node(
        self, admin_client: AsyncClient, completed_run: ContextTreeRun
    ):
        resp = await admin_client.put(
            f"/api/context-engine/runs/{completed_run.id}/node/leaf_1?org_id={TEST_ORG_ID}",
            json={"name": "Renamed Leaf", "version": 1},
        )
        assert resp.status_code == 200
        tree = resp.json()["tree_data"]
        cat = tree["children"][0]
        assert cat["children"][0]["name"] == "Renamed Leaf"

    async def test_delete_node(
        self, admin_client: AsyncClient, completed_run: ContextTreeRun
    ):
        resp = await admin_client.delete(
            f"/api/context-engine/runs/{completed_run.id}/node/leaf_1"
            f"?org_id={TEST_ORG_ID}&version=1"
        )
        assert resp.status_code == 200
        tree = resp.json()["tree_data"]
        cat = tree["children"][0]
        assert len(cat["children"]) == 0

    async def test_delete_root_returns_400(
        self, admin_client: AsyncClient, completed_run: ContextTreeRun
    ):
        resp = await admin_client.delete(
            f"/api/context-engine/runs/{completed_run.id}/node/root"
            f"?org_id={TEST_ORG_ID}&version=1"
        )
        assert resp.status_code == 400

    async def test_delete_run(
        self, admin_client: AsyncClient, completed_run: ContextTreeRun
    ):
        resp = await admin_client.delete(
            f"/api/context-engine/runs/{completed_run.id}?org_id={TEST_ORG_ID}"
        )
        assert resp.status_code == 200

        resp2 = await admin_client.get(
            f"/api/context-engine/runs?org_id={TEST_ORG_ID}"
        )
        assert len(resp2.json()["runs"]) == 0


class TestRunAuth:
    """Tests for authentication on context engine endpoints."""

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get(f"/api/context-engine/runs?org_id={TEST_ORG_ID}")
        assert resp.status_code == 401
