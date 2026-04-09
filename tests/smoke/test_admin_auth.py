"""Tests for admin authentication on twin plane endpoints."""

import pytest

from twins_livekit.app import create_app
from twins_livekit_local.storage_sqlite import SQLiteStorage

ADMIN_TOKEN = "test-admin-secret-token"


@pytest.fixture
def admin_storage(tmp_path):
    return SQLiteStorage(db_path=str(tmp_path / "test.db"))


@pytest.fixture
def admin_app(admin_storage):
    app = create_app(
        storage=admin_storage,
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


class TestAdminAuthRequired:
    """Verify that state-mutating endpoints require admin auth when token is configured."""

    def test_create_fault_requires_auth(self, admin_client):
        resp = admin_client.post("/_twin/faults", json={
            "target": "CreateRoom", "action": "error",
        })
        assert resp.status_code == 401

    def test_create_fault_with_auth(self, admin_client, admin_headers):
        resp = admin_client.post("/_twin/faults", json={
            "target": "CreateRoom", "action": "error",
        }, headers=admin_headers)
        assert resp.status_code == 201

    def test_delete_fault_requires_auth(self, admin_client, admin_headers):
        # Create with auth
        resp = admin_client.post("/_twin/faults", json={
            "target": "CreateRoom", "action": "error",
        }, headers=admin_headers)
        fault_id = resp.get_json()["fault"]["id"]

        # Delete without auth
        resp = admin_client.delete(f"/_twin/faults/{fault_id}")
        assert resp.status_code == 401

    def test_clear_faults_requires_auth(self, admin_client):
        resp = admin_client.delete("/_twin/faults")
        assert resp.status_code == 401

    def test_reset_requires_auth(self, admin_client):
        resp = admin_client.post("/_twin/reset")
        assert resp.status_code == 401

    def test_reset_with_auth(self, admin_client, admin_headers):
        resp = admin_client.post("/_twin/reset", headers=admin_headers)
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
    """Verify that read-only endpoints don't require auth even when token is configured."""

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

    def test_logs_no_auth(self, admin_client):
        assert admin_client.get("/_twin/logs").status_code == 200

    def test_webhooks_no_auth(self, admin_client):
        assert admin_client.get("/_twin/webhooks").status_code == 200
