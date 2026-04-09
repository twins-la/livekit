"""JSON serialization helpers for LiveKit twin resources."""

from datetime import datetime, timezone


def now_iso() -> str:
    """Current time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def now_unix_nano() -> int:
    """Current time as Unix nanoseconds (LiveKit's timestamp format)."""
    return int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)


def room_to_json(room: dict) -> dict:
    """Convert a stored room to LiveKit Room JSON."""
    return {
        "name": room["name"],
        "sid": room.get("sid", ""),
        "max_participants": room.get("max_participants", 0),
        "empty_timeout": room.get("empty_timeout", 300),
        "creation_time": room.get("creation_time", 0),
        "num_participants": room.get("participant_count", 0),
    }


def participant_to_json(p: dict) -> dict:
    """Convert a stored participant to LiveKit ParticipantInfo JSON."""
    return {
        "identity": p["identity"],
        "sid": p.get("sid", ""),
        "name": p.get("name", ""),
        "state": p.get("state", "ACTIVE"),
        "joined_at": p.get("joined_at", 0),
    }


def egress_to_json(eg: dict) -> dict:
    """Convert a stored egress to LiveKit EgressInfo JSON."""
    result = {
        "egress_id": eg["egress_id"],
        "room_name": eg.get("room_name", ""),
        "status": eg.get("status", "EGRESS_STARTING"),
        "started_at": eg.get("started_at", 0),
    }
    if eg.get("stopped_at"):
        result["ended_at"] = eg["stopped_at"]
    return result


def webhook_to_json(wh: dict) -> dict:
    """Convert a stored webhook event to JSON."""
    return {
        "id": wh.get("id"),
        "event_type": wh["event_type"],
        "room_name": wh.get("room_name", ""),
        "participant_identity": wh.get("participant_identity", ""),
        "timestamp": wh.get("timestamp", ""),
        "payload": wh.get("payload", ""),
        "forwarded": wh.get("forwarded", False),
    }


def fault_to_json(f: dict) -> dict:
    """Convert a stored fault rule to JSON."""
    return {
        "id": f["id"],
        "target": f["target"],
        "action": f["action"],
        "config": f.get("config", {}),
    }


def log_to_json(entry: dict) -> dict:
    """Convert a stored log entry to JSON."""
    return {
        "id": entry.get("id"),
        "timestamp": entry.get("timestamp", ""),
        "operation": entry.get("operation", ""),
        "target": entry.get("target", ""),
        "request_summary": entry.get("request_summary", ""),
        "response_status": entry.get("response_status"),
        "fault_applied": entry.get("fault_applied"),
        "duration_ms": entry.get("duration_ms"),
    }
