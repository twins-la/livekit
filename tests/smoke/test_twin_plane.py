"""Tests for Twin Plane management endpoints."""


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/_twin/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["twin"] == "livekit"
        assert data["version"] == "0.2.0"


class TestScenarios:
    def test_scenarios_lists_capabilities(self, client):
        resp = client.get("/_twin/scenarios")
        assert resp.status_code == 200
        data = resp.get_json()
        names = [s["name"] for s in data["scenarios"]]
        assert "rooms" in names
        assert "participants" in names
        assert "egress" in names
        assert "webhooks" in names
        assert "fault_injection" in names


class TestSettings:
    def test_settings_returns_config(self, client):
        resp = client.get("/_twin/settings")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["twin"] == "livekit"
        assert data["api_key"] == "devkey"
        assert "upstream_url" in data


class TestReferences:
    def test_references_returns_sources(self, client):
        resp = client.get("/_twin/references")
        assert resp.status_code == 200
        data = resp.get_json()
        refs = data["references"]
        assert len(refs) >= 1
        for ref in refs:
            assert "title" in ref
            assert "url" in ref
            assert "retrieved" in ref
        titles = [r["title"] for r in refs]
        assert any("LiveKit" in t for t in titles)


class TestTenants:
    def test_create_tenant(self, client):
        resp = client.post("/_twin/tenants", json={"friendly_name": "My Org"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert "tenant_id" in data
        assert "tenant_secret" in data
        assert data["friendly_name"] == "My Org"
        assert "created_at" in data


class TestAccounts:
    def test_create_account_returns_dev(self, client, tenant_headers):
        resp = client.post("/_twin/accounts", headers=tenant_headers)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["api_key"] == "devkey"
        assert data["status"] == "active"

    def test_create_account_requires_auth(self, client):
        resp = client.post("/_twin/accounts")
        assert resp.status_code == 401

    def test_list_accounts_returns_dev(self, client, tenant_headers):
        resp = client.get("/_twin/accounts", headers=tenant_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["api_key"] == "devkey"


class TestRoomInspection:
    def test_list_rooms_empty(self, client):
        resp = client.get("/_twin/rooms")
        assert resp.status_code == 200
        assert resp.get_json()["rooms"] == []

    def test_list_rooms_after_create(self, client, storage):
        storage.create_room({"name": "sc-123", "max_participants": 2})
        resp = client.get("/_twin/rooms")
        data = resp.get_json()
        assert len(data["rooms"]) == 1
        assert data["rooms"][0]["name"] == "sc-123"

    def test_get_room_with_participants(self, client, storage):
        storage.create_room({"name": "sc-123"})
        storage.add_participant("sc-123", {"identity": "alice"})
        resp = client.get("/_twin/rooms/sc-123")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "sc-123"
        assert len(data["participants"]) == 1
        assert data["participants"][0]["identity"] == "alice"

    def test_get_room_not_found(self, client):
        resp = client.get("/_twin/rooms/nonexistent")
        assert resp.status_code == 404


class TestEgressInspection:
    def test_list_egresses_empty(self, client):
        resp = client.get("/_twin/egresses")
        assert resp.status_code == 200
        assert resp.get_json()["egresses"] == []

    def test_get_egress_not_found(self, client):
        resp = client.get("/_twin/egresses/nonexistent")
        assert resp.status_code == 404


class TestWebhookInspection:
    def test_list_webhooks_empty(self, client):
        resp = client.get("/_twin/webhooks")
        assert resp.status_code == 200
        assert resp.get_json()["webhooks"] == []


class TestFaultInjection:
    def test_create_fault(self, client, tenant_headers):
        resp = client.post("/_twin/faults", json={
            "target": "CreateRoom",
            "action": "error",
            "config": {"status_code": 500, "message": "boom"},
        }, headers=tenant_headers)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["fault"]["target"] == "CreateRoom"
        assert data["fault"]["action"] == "error"
        assert "id" in data["fault"]

    def test_create_fault_requires_auth(self, client):
        resp = client.post("/_twin/faults", json={
            "target": "CreateRoom", "action": "error",
        })
        assert resp.status_code == 401

    def test_list_faults(self, client, tenant_headers):
        client.post("/_twin/faults", json={"target": "CreateRoom", "action": "error"},
                     headers=tenant_headers)
        resp = client.get("/_twin/faults")
        assert resp.status_code == 200
        assert len(resp.get_json()["faults"]) == 1

    def test_delete_fault(self, client, tenant_headers):
        resp = client.post("/_twin/faults", json={"target": "CreateRoom", "action": "error"},
                           headers=tenant_headers)
        fault_id = resp.get_json()["fault"]["id"]

        resp = client.delete(f"/_twin/faults/{fault_id}", headers=tenant_headers)
        assert resp.status_code == 204

        resp = client.get("/_twin/faults")
        assert len(resp.get_json()["faults"]) == 0

    def test_clear_all_faults(self, client, tenant_headers):
        client.post("/_twin/faults", json={"target": "CreateRoom", "action": "error"},
                     headers=tenant_headers)
        client.post("/_twin/faults", json={"target": "DeleteRoom", "action": "delay"},
                     headers=tenant_headers)

        resp = client.delete("/_twin/faults", headers=tenant_headers)
        assert resp.status_code == 204

        resp = client.get("/_twin/faults")
        assert len(resp.get_json()["faults"]) == 0

    def test_create_fault_invalid_action(self, client, tenant_headers):
        resp = client.post("/_twin/faults", json={"target": "CreateRoom", "action": "invalid"},
                           headers=tenant_headers)
        assert resp.status_code == 400

    def test_create_fault_missing_target(self, client, tenant_headers):
        resp = client.post("/_twin/faults", json={"action": "error"},
                           headers=tenant_headers)
        assert resp.status_code == 400


class TestLogs:
    def test_list_logs_empty(self, client, tenant_headers):
        resp = client.get("/_twin/logs", headers=tenant_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["logs"] == []
        assert data["limit"] == 100
        assert data["offset"] == 0

    def test_list_logs_requires_auth(self, client):
        resp = client.get("/_twin/logs")
        assert resp.status_code == 401


class TestReset:
    def test_reset_clears_state(self, client, storage, tenant_headers):
        storage.create_room({"name": "room-1"})
        storage.set_fault({"id": "FT_1", "target": "x", "action": "error"})

        resp = client.post("/_twin/reset", headers=tenant_headers)
        assert resp.status_code == 204

        # State should be cleared (logs has the reset entry)
        assert storage.list_rooms() == []
        assert storage.list_faults() == []

    def test_reset_requires_auth(self, client):
        resp = client.post("/_twin/reset")
        assert resp.status_code == 401


class TestSimulateWebhook:
    def test_simulate_webhook(self, client, storage, tenant_headers):
        storage.create_room({"name": "sc-123"})
        resp = client.post("/_twin/simulate/webhook", json={
            "event": "participant_joined",
            "room_name": "sc-123",
            "participant_identity": "alice",
        }, headers=tenant_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["webhook"]["event_type"] == "participant_joined"

        # Participant should be added to twin state
        participants = storage.list_participants("sc-123")
        assert len(participants) == 1
        assert participants[0]["identity"] == "alice"

    def test_simulate_webhook_missing_fields(self, client, tenant_headers):
        resp = client.post("/_twin/simulate/webhook",
                           json={"event": "room_finished"},
                           headers=tenant_headers)
        assert resp.status_code == 400

    def test_simulate_room_finished_deletes_room(self, client, storage, tenant_headers):
        storage.create_room({"name": "sc-456"})
        client.post("/_twin/simulate/webhook", json={
            "event": "room_finished",
            "room_name": "sc-456",
        }, headers=tenant_headers)
        assert storage.get_room("sc-456") is None

    def test_simulate_webhook_requires_auth(self, client):
        resp = client.post("/_twin/simulate/webhook", json={
            "event": "room_finished", "room_name": "test",
        })
        assert resp.status_code == 401
