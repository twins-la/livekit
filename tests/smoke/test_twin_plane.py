"""Tests for Twin Plane management endpoints."""


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/_twin/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["twin"] == "livekit"
        assert data["version"] == "0.1.0"


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


class TestAccounts:
    def test_create_account_returns_dev(self, client):
        resp = client.post("/_twin/accounts")
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["api_key"] == "devkey"
        assert data["status"] == "active"

    def test_list_accounts_returns_dev(self, client):
        resp = client.get("/_twin/accounts")
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
    def test_create_fault(self, client):
        resp = client.post("/_twin/faults", json={
            "target": "CreateRoom",
            "action": "error",
            "config": {"status_code": 500, "message": "boom"},
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["fault"]["target"] == "CreateRoom"
        assert data["fault"]["action"] == "error"
        assert "id" in data["fault"]

    def test_list_faults(self, client):
        client.post("/_twin/faults", json={"target": "CreateRoom", "action": "error"})
        resp = client.get("/_twin/faults")
        assert resp.status_code == 200
        assert len(resp.get_json()["faults"]) == 1

    def test_delete_fault(self, client):
        resp = client.post("/_twin/faults", json={"target": "CreateRoom", "action": "error"})
        fault_id = resp.get_json()["fault"]["id"]

        resp = client.delete(f"/_twin/faults/{fault_id}")
        assert resp.status_code == 204

        resp = client.get("/_twin/faults")
        assert len(resp.get_json()["faults"]) == 0

    def test_clear_all_faults(self, client):
        client.post("/_twin/faults", json={"target": "CreateRoom", "action": "error"})
        client.post("/_twin/faults", json={"target": "DeleteRoom", "action": "delay"})

        resp = client.delete("/_twin/faults")
        assert resp.status_code == 204

        resp = client.get("/_twin/faults")
        assert len(resp.get_json()["faults"]) == 0

    def test_create_fault_invalid_action(self, client):
        resp = client.post("/_twin/faults", json={"target": "CreateRoom", "action": "invalid"})
        assert resp.status_code == 400

    def test_create_fault_missing_target(self, client):
        resp = client.post("/_twin/faults", json={"action": "error"})
        assert resp.status_code == 400


class TestLogs:
    def test_list_logs_empty(self, client):
        resp = client.get("/_twin/logs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["logs"] == []
        assert data["limit"] == 100
        assert data["offset"] == 0


class TestReset:
    def test_reset_clears_state(self, client, storage):
        storage.create_room({"name": "room-1"})
        storage.set_fault({"id": "FT_1", "target": "x", "action": "error"})

        resp = client.post("/_twin/reset")
        assert resp.status_code == 204

        # State should be cleared (logs has the reset entry)
        assert storage.list_rooms() == []
        assert storage.list_faults() == []


class TestSimulateWebhook:
    def test_simulate_webhook(self, client, storage):
        storage.create_room({"name": "sc-123"})
        resp = client.post("/_twin/simulate/webhook", json={
            "event": "participant_joined",
            "room_name": "sc-123",
            "participant_identity": "alice",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["webhook"]["event_type"] == "participant_joined"

        # Participant should be added to twin state
        participants = storage.list_participants("sc-123")
        assert len(participants) == 1
        assert participants[0]["identity"] == "alice"

    def test_simulate_webhook_missing_fields(self, client):
        resp = client.post("/_twin/simulate/webhook", json={"event": "room_finished"})
        assert resp.status_code == 400

    def test_simulate_room_finished_deletes_room(self, client, storage):
        storage.create_room({"name": "sc-456"})
        client.post("/_twin/simulate/webhook", json={
            "event": "room_finished",
            "room_name": "sc-456",
        })
        assert storage.get_room("sc-456") is None
