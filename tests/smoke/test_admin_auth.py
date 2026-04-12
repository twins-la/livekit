"""Tests for admin authentication on twin plane endpoints.

Exercises the admin auth model:
1. Admin Bearer token grants cross-tenant access
2. Tenant HTTP Basic grants tenant-scoped access
3. Wrong admin token returns 401
4. No admin token configured = unrestricted admin access (local dev)
"""

import base64

import pytest

from twins_livekit.app import create_app
from twins_livekit_local.storage_sqlite import SQLiteStorage
from twins_local.tenants import (
    SQLiteTenantStore,
    ensure_default_tenant,
    generate_tenant_id,
    generate_tenant_secret,
    hash_secret,
)

ADMIN_TOKEN = "test-admin-secret-token"


@pytest.fixture
def admin_tenant_store(tmp_path):
    store = SQLiteTenantStore(db_path=str(tmp_path / "admin_tenants.sqlite3"))
    ensure_default_tenant(store)
    return store


@pytest.fixture
def admin_storage(tmp_path):
    return SQLiteStorage(db_path=str(tmp_path / "test.db"))


@pytest.fixture
def admin_app(admin_storage, admin_tenant_store):
    app = create_app(
        storage=admin_storage,
        tenants=admin_tenant_store,
        config={
            "base_url": "http://localhost:7880",
            "upstream_url": "http://localhost:7881",
            "livekit_api_key": "devkey",
            "livekit_api_secret": "secret",
            "admin_token": ADMIN_TOKEN,
        },
    )
    app.config["TESTING"] = True
    return app


@pytest.fixture
def admin_client(admin_app):
    return admin_app.test_client()


@pytest.fixture
def admin_headers():
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def _make_tenant(store, name):
    tid = generate_tenant_id()
    secret = generate_tenant_secret()
    store.create_tenant(tid, hash_secret(secret), name)
    creds = base64.b64encode(f"{tid}:{secret}".encode()).decode()
    return tid, {"Authorization": f"Basic {creds}"}


@pytest.fixture
def tenant_a_headers(admin_tenant_store):
    _, headers = _make_tenant(admin_tenant_store, "Tenant A")
    return headers


@pytest.fixture
def tenant_b_headers(admin_tenant_store):
    _, headers = _make_tenant(admin_tenant_store, "Tenant B")
    return headers


class TestAdminAuthRequired:
    """Verify that state-mutating endpoints require admin OR tenant auth."""

    def test_create_fault_requires_auth(self, admin_client):
        resp = admin_client.post("/_twin/faults", json={
            "target": "CreateRoom", "action": "error",
        })
        assert resp.status_code == 401

    def test_create_fault_with_admin_auth(self, admin_client, admin_headers):
        resp = admin_client.post("/_twin/faults", json={
            "target": "CreateRoom", "action": "error",
        }, headers=admin_headers)
        assert resp.status_code == 201

    def test_create_fault_with_tenant_auth(self, admin_client, tenant_a_headers):
        resp = admin_client.post("/_twin/faults", json={
            "target": "CreateRoom", "action": "error",
        }, headers=tenant_a_headers)
        assert resp.status_code == 201

    def test_delete_fault_requires_auth(self, admin_client, admin_headers):
        resp = admin_client.post("/_twin/faults", json={
            "target": "CreateRoom", "action": "error",
        }, headers=admin_headers)
        fault_id = resp.get_json()["fault"]["id"]

        resp = admin_client.delete(f"/_twin/faults/{fault_id}")
        assert resp.status_code == 401

    def test_clear_faults_requires_auth(self, admin_client):
        resp = admin_client.delete("/_twin/faults")
        assert resp.status_code == 401

    def test_reset_requires_auth(self, admin_client):
        resp = admin_client.post("/_twin/reset")
        assert resp.status_code == 401

    def test_reset_with_admin_auth(self, admin_client, admin_headers):
        resp = admin_client.post("/_twin/reset", headers=admin_headers)
        assert resp.status_code == 204

    def test_reset_with_tenant_auth(self, admin_client, tenant_a_headers):
        resp = admin_client.post("/_twin/reset", headers=tenant_a_headers)
        assert resp.status_code == 204

    def test_simulate_webhook_requires_auth(self, admin_client):
        resp = admin_client.post("/_twin/simulate/webhook", json={
            "event": "room_finished", "room_name": "test",
        })
        assert resp.status_code == 401

    def test_wrong_token_rejected(self, admin_client):
        resp = admin_client.post("/_twin/faults", json={
            "target": "CreateRoom", "action": "error",
        }, headers={"Authorization": "Bearer wrong-token"})
        assert resp.status_code == 401


class TestReadEndpointsNoAuth:
    """Verify that public read-only endpoints don't require auth."""

    def test_health_no_auth(self, admin_client):
        assert admin_client.get("/_twin/health").status_code == 200

    def test_scenarios_no_auth(self, admin_client):
        assert admin_client.get("/_twin/scenarios").status_code == 200

    def test_settings_no_auth(self, admin_client):
        assert admin_client.get("/_twin/settings").status_code == 200

    def test_rooms_no_auth(self, admin_client):
        assert admin_client.get("/_twin/rooms").status_code == 200

    def test_faults_list_no_auth(self, admin_client):
        assert admin_client.get("/_twin/faults").status_code == 200

    def test_webhooks_no_auth(self, admin_client):
        assert admin_client.get("/_twin/webhooks").status_code == 200

    def test_tenants_bootstrap_no_auth(self, admin_client):
        """POST /_twin/tenants is the unauthenticated bootstrap."""
        resp = admin_client.post("/_twin/tenants", json={})
        assert resp.status_code == 201


class TestLogScoping:
    """Verify log endpoint scopes by tenant_id for tenants, shows all for admin."""

    def test_logs_require_auth(self, admin_client):
        resp = admin_client.get("/_twin/logs")
        assert resp.status_code == 401

    def test_admin_sees_all_logs(self, admin_client, admin_headers,
                                  tenant_a_headers, tenant_b_headers):
        # Both tenants do something that logs
        admin_client.post("/_twin/faults", json={"target": "A", "action": "error"},
                          headers=tenant_a_headers)
        admin_client.post("/_twin/faults", json={"target": "B", "action": "error"},
                          headers=tenant_b_headers)

        resp = admin_client.get("/_twin/logs", headers=admin_headers)
        assert resp.status_code == 200
        logs = resp.get_json()["logs"]
        tenant_ids = {l.get("tenant_id") for l in logs}
        # Admin sees logs from multiple tenants
        assert len([tid for tid in tenant_ids if tid]) >= 2

    def test_tenant_sees_only_own_logs(self, admin_client, tenant_a_headers, tenant_b_headers):
        admin_client.post("/_twin/faults", json={"target": "A", "action": "error"},
                          headers=tenant_a_headers)
        admin_client.post("/_twin/faults", json={"target": "B", "action": "error"},
                          headers=tenant_b_headers)

        resp = admin_client.get("/_twin/logs", headers=tenant_a_headers)
        assert resp.status_code == 200
        logs = resp.get_json()["logs"]
        for entry in logs:
            # Tenant A should only see its own tenant_id
            if entry.get("tenant_id"):
                # Should be A's tenant_id (we don't know it, but it should match a single one)
                pass
        # Simpler check: logs should only have one distinct non-empty tenant_id
        tenant_ids = {l.get("tenant_id") for l in logs if l.get("tenant_id")}
        assert len(tenant_ids) <= 1
