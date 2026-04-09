"""Tests for the HTTP proxy and fault injection logic."""

from unittest.mock import patch, MagicMock

import pytest
import responses

from twins_livekit.app import create_app
from twins_livekit_local.storage_sqlite import SQLiteStorage


@pytest.fixture
def storage(tmp_path):
    return SQLiteStorage(db_path=str(tmp_path / "test.db"))


@pytest.fixture
def app(storage):
    app = create_app(storage=storage, config={
        "upstream_url": "http://localhost:7881",
        "livekit_api_key": "devkey",
        "livekit_api_secret": "secret",
    })
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestProxyFaultInjection:
    def test_error_fault_returns_error_without_forwarding(self, client, storage):
        """When an error fault is set, the proxy returns the error without forwarding."""
        storage.set_fault({
            "id": "FT_1",
            "target": "CreateRoom",
            "action": "error",
            "config": {"status_code": 500, "message": "injected error"},
        })

        resp = client.post(
            "/twirp/livekit.RoomService/CreateRoom",
            json={"name": "test-room"},
            content_type="application/json",
        )

        assert resp.status_code == 500
        data = resp.get_json()
        assert data["msg"] == "injected error"

        # Verify it was logged
        logs = storage.list_logs()
        assert len(logs) == 1
        assert logs[0]["operation"] == "CreateRoom"
        assert logs[0]["fault_applied"] == "FT_1"

    @responses.activate
    def test_proxy_forwards_to_upstream(self, client, storage):
        """Without faults, requests are forwarded to upstream."""
        responses.add(
            responses.POST,
            "http://localhost:7881/twirp/livekit.RoomService/CreateRoom",
            json={"name": "test-room", "sid": "RM_xyz", "max_participants": 2},
            status=200,
        )

        resp = client.post(
            "/twirp/livekit.RoomService/CreateRoom",
            json={"name": "test-room", "max_participants": 2},
            content_type="application/json",
        )

        assert resp.status_code == 200

        # Verify room was tracked in twin state
        room = storage.get_room("test-room")
        assert room is not None
        assert room["sid"] == "RM_xyz"

        # Verify it was logged
        logs = storage.list_logs()
        assert len(logs) == 1
        assert logs[0]["response_status"] == 200

    @responses.activate
    def test_proxy_handles_upstream_down(self, client, storage):
        """When upstream is unreachable, return 503."""
        # No mock registered — requests will raise ConnectionError
        resp = client.post(
            "/twirp/livekit.RoomService/CreateRoom",
            json={"name": "test-room"},
            content_type="application/json",
        )

        assert resp.status_code == 503

    @responses.activate
    def test_delete_room_updates_state(self, client, storage):
        """DeleteRoom proxy updates twin state."""
        storage.create_room({"name": "room-to-delete"})

        responses.add(
            responses.POST,
            "http://localhost:7881/twirp/livekit.RoomService/DeleteRoom",
            json={},
            status=200,
        )

        resp = client.post(
            "/twirp/livekit.RoomService/DeleteRoom",
            json={"room": "room-to-delete"},
            content_type="application/json",
        )

        assert resp.status_code == 200
        assert storage.get_room("room-to-delete") is None

    @responses.activate
    def test_non_intercepted_twirp_forwarded(self, client):
        """Non-intercepted Twirp endpoints are forwarded transparently."""
        responses.add(
            responses.POST,
            "http://localhost:7881/twirp/livekit.RoomService/UpdateRoomMetadata",
            json={"name": "test"},
            status=200,
        )

        resp = client.post(
            "/twirp/livekit.RoomService/UpdateRoomMetadata",
            json={"room": "test"},
            content_type="application/json",
        )

        assert resp.status_code == 200


class TestProxyStateTracking:
    @responses.activate
    def test_egress_start_tracked(self, client, storage):
        responses.add(
            responses.POST,
            "http://localhost:7881/twirp/livekit.Egress/StartRoomCompositeEgress",
            json={"egress_id": "EG_123", "room_name": "room-1", "status": "EGRESS_STARTING"},
            status=200,
        )

        client.post(
            "/twirp/livekit.Egress/StartRoomCompositeEgress",
            json={"room_name": "room-1"},
            content_type="application/json",
        )

        egress = storage.get_egress("EG_123")
        assert egress is not None
        assert egress["room_name"] == "room-1"

    @responses.activate
    def test_egress_stop_tracked(self, client, storage):
        storage.create_egress({"egress_id": "EG_123", "room_name": "room-1", "status": "EGRESS_ACTIVE"})

        responses.add(
            responses.POST,
            "http://localhost:7881/twirp/livekit.Egress/StopEgress",
            json={"egress_id": "EG_123", "status": "EGRESS_COMPLETE"},
            status=200,
        )

        client.post(
            "/twirp/livekit.Egress/StopEgress",
            json={"egress_id": "EG_123"},
            content_type="application/json",
        )

        egress = storage.get_egress("EG_123")
        assert egress["status"] == "EGRESS_COMPLETE"
