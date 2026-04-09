"""Tests for SQLiteStorage — verifies the LiveKitStorage ABC contract."""

import pytest

from twins_livekit_local.storage_sqlite import SQLiteStorage


@pytest.fixture
def storage(tmp_path):
    db_path = str(tmp_path / "test.db")
    return SQLiteStorage(db_path=db_path)


class TestRooms:
    def test_create_and_get_room(self, storage):
        room = storage.create_room({
            "name": "test-room",
            "sid": "RM_abc123",
            "max_participants": 2,
            "empty_timeout": 300,
            "creation_time": 1000,
        })
        assert room["name"] == "test-room"

        fetched = storage.get_room("test-room")
        assert fetched is not None
        assert fetched["name"] == "test-room"
        assert fetched["sid"] == "RM_abc123"
        assert fetched["max_participants"] == 2
        assert fetched["participant_count"] == 0

    def test_get_nonexistent_room(self, storage):
        assert storage.get_room("nope") is None

    def test_list_rooms(self, storage):
        storage.create_room({"name": "room-a"})
        storage.create_room({"name": "room-b"})
        rooms = storage.list_rooms()
        assert len(rooms) == 2
        names = [r["name"] for r in rooms]
        assert "room-a" in names
        assert "room-b" in names

    def test_delete_room(self, storage):
        storage.create_room({"name": "to-delete"})
        assert storage.delete_room("to-delete") is True
        assert storage.get_room("to-delete") is None

    def test_delete_nonexistent(self, storage):
        assert storage.delete_room("nope") is False

    def test_delete_room_removes_participants(self, storage):
        storage.create_room({"name": "room-x"})
        storage.add_participant("room-x", {"identity": "user-1"})
        storage.delete_room("room-x")
        assert storage.list_participants("room-x") == []


class TestParticipants:
    def test_add_and_list_participants(self, storage):
        storage.create_room({"name": "room-1"})
        storage.add_participant("room-1", {"identity": "alice", "sid": "PA_1"})
        storage.add_participant("room-1", {"identity": "bob", "sid": "PA_2"})

        participants = storage.list_participants("room-1")
        assert len(participants) == 2
        identities = [p["identity"] for p in participants]
        assert "alice" in identities
        assert "bob" in identities

    def test_remove_participant(self, storage):
        storage.create_room({"name": "room-1"})
        storage.add_participant("room-1", {"identity": "alice"})
        assert storage.remove_participant("room-1", "alice") is True
        assert storage.list_participants("room-1") == []

    def test_remove_nonexistent_participant(self, storage):
        assert storage.remove_participant("room-1", "nobody") is False

    def test_participant_count_in_room(self, storage):
        storage.create_room({"name": "room-1"})
        storage.add_participant("room-1", {"identity": "alice"})
        room = storage.get_room("room-1")
        assert room["participant_count"] == 1


class TestEgress:
    def test_create_and_get_egress(self, storage):
        storage.create_egress({
            "egress_id": "EG_abc",
            "room_name": "room-1",
            "status": "EGRESS_STARTING",
            "started_at": 1000,
        })
        egress = storage.get_egress("EG_abc")
        assert egress is not None
        assert egress["egress_id"] == "EG_abc"
        assert egress["status"] == "EGRESS_STARTING"

    def test_update_egress(self, storage):
        storage.create_egress({"egress_id": "EG_abc", "room_name": "room-1"})
        updated = storage.update_egress("EG_abc", {"status": "EGRESS_COMPLETE", "stopped_at": 2000})
        assert updated is not None
        assert updated["status"] == "EGRESS_COMPLETE"
        assert updated["stopped_at"] == 2000

    def test_update_nonexistent_egress(self, storage):
        assert storage.update_egress("nope", {"status": "x"}) is None

    def test_list_egresses(self, storage):
        storage.create_egress({"egress_id": "EG_1", "room_name": "room-a"})
        storage.create_egress({"egress_id": "EG_2", "room_name": "room-b"})
        assert len(storage.list_egresses()) == 2
        assert len(storage.list_egresses(room_name="room-a")) == 1


class TestWebhooks:
    def test_record_and_list_webhooks(self, storage):
        storage.record_webhook({
            "id": "wh-1",
            "event_type": "room_finished",
            "room_name": "room-1",
            "participant_identity": "",
            "timestamp": "2024-01-01T00:00:00Z",
            "payload": "{}",
        })
        webhooks = storage.list_webhooks()
        assert len(webhooks) == 1
        assert webhooks[0]["event_type"] == "room_finished"

    def test_filter_webhooks(self, storage):
        storage.record_webhook({"id": "1", "event_type": "room_finished", "room_name": "r1", "timestamp": "t1"})
        storage.record_webhook({"id": "2", "event_type": "participant_joined", "room_name": "r1", "timestamp": "t2"})
        storage.record_webhook({"id": "3", "event_type": "room_finished", "room_name": "r2", "timestamp": "t3"})

        assert len(storage.list_webhooks(room_name="r1")) == 2
        assert len(storage.list_webhooks(event_type="room_finished")) == 2
        assert len(storage.list_webhooks(room_name="r1", event_type="room_finished")) == 1


class TestFaults:
    def test_set_and_get_fault(self, storage):
        fault = storage.set_fault({
            "id": "FT_1",
            "target": "CreateRoom",
            "action": "error",
            "config": {"status_code": 500},
        })
        assert fault["id"] == "FT_1"

        fetched = storage.get_fault("FT_1")
        assert fetched is not None
        assert fetched["config"]["status_code"] == 500

    def test_list_faults(self, storage):
        storage.set_fault({"id": "FT_1", "target": "CreateRoom", "action": "error"})
        storage.set_fault({"id": "FT_2", "target": "DeleteRoom", "action": "delay", "config": {"delay_ms": 1000}})
        assert len(storage.list_faults()) == 2

    def test_delete_fault(self, storage):
        storage.set_fault({"id": "FT_1", "target": "CreateRoom", "action": "error"})
        assert storage.delete_fault("FT_1") is True
        assert storage.get_fault("FT_1") is None

    def test_clear_faults(self, storage):
        storage.set_fault({"id": "FT_1", "target": "CreateRoom", "action": "error"})
        storage.set_fault({"id": "FT_2", "target": "DeleteRoom", "action": "error"})
        storage.clear_faults()
        assert storage.list_faults() == []


class TestLogs:
    def test_append_and_list_logs(self, storage):
        storage.append_log({
            "timestamp": "2024-01-01T00:00:00Z",
            "operation": "CreateRoom",
            "target": "/twirp/...",
            "request_summary": "name=test",
            "response_status": 200,
        })
        logs = storage.list_logs()
        assert len(logs) == 1
        assert logs[0]["operation"] == "CreateRoom"

    def test_log_ordering(self, storage):
        storage.append_log({"timestamp": "t1", "operation": "first"})
        storage.append_log({"timestamp": "t2", "operation": "second"})
        logs = storage.list_logs()
        # Most recent first
        assert logs[0]["operation"] == "second"

    def test_log_pagination(self, storage):
        for i in range(5):
            storage.append_log({"timestamp": f"t{i}", "operation": f"op-{i}"})
        assert len(storage.list_logs(limit=2)) == 2
        assert len(storage.list_logs(limit=2, offset=3)) == 2


class TestReset:
    def test_clear_all(self, storage):
        storage.create_room({"name": "room-1"})
        storage.add_participant("room-1", {"identity": "alice"})
        storage.create_egress({"egress_id": "EG_1", "room_name": "room-1"})
        storage.record_webhook({"id": "wh-1", "event_type": "test", "timestamp": "t"})
        storage.set_fault({"id": "FT_1", "target": "x", "action": "error"})
        storage.append_log({"timestamp": "t", "operation": "test"})

        storage.clear_all()

        assert storage.list_rooms() == []
        assert storage.list_participants("room-1") == []
        assert storage.list_egresses() == []
        assert storage.list_webhooks() == []
        assert storage.list_faults() == []
        assert storage.list_logs() == []
