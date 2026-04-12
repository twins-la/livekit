"""Twin Plane management endpoints for the LiveKit proxy twin.

Provides: health, scenarios, settings, state inspection,
webhook inspection/simulation, fault injection, logs, reset,
and tenant bootstrap.
"""

import json

from flask import Blueprint, g, jsonify, request

from ..auth import require_admin_auth
from ..ids import generate_fault_id
from ..models import (
    egress_to_json,
    fault_to_json,
    log_to_json,
    now_iso,
    participant_to_json,
    room_to_json,
    webhook_to_json,
)
from ..webhooks import simulate_webhook
from .auth import require_tenant, require_tenant_or_admin, require_admin
from twins_local.tenants import (
    generate_tenant_id,
    generate_tenant_secret,
    hash_secret,
    reject_default_in_cloud,
)

twin_plane_bp = Blueprint("twin_plane", __name__, url_prefix="/_twin")


# -- Helpers --


def _scope_tenant_id() -> str:
    """Return the tenant_id to stamp on log entries.

    Admin requests log as "__operator_admin__"; tenant requests log as the
    authenticated tenant_id. Falls back to "" when auth was not required
    (e.g. proxy-level operations).
    """
    if getattr(g, "is_admin", False):
        from twins_local.tenants import OPERATOR_ADMIN_TENANT_ID
        return OPERATOR_ADMIN_TENANT_ID
    return getattr(g, "tenant_id", "") or ""


# -- Public (no auth) --


@twin_plane_bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    upstream_status = "healthy"
    process_mgr = g.get("process_manager")
    if process_mgr:
        upstream_status = "healthy" if process_mgr.is_healthy() else "unreachable"
    elif not g.get("upstream_url"):
        upstream_status = "not_started"

    return jsonify({
        "status": "ok",
        "twin": "livekit",
        "version": "0.2.0",
        "upstream": upstream_status,
    })


@twin_plane_bp.route("/scenarios", methods=["GET"])
def scenarios():
    """List supported scenarios."""
    return jsonify({
        "scenarios": [
            {
                "name": "rooms",
                "status": "supported",
                "capabilities": ["create", "delete", "list"],
            },
            {
                "name": "participants",
                "status": "supported",
                "capabilities": ["list"],
            },
            {
                "name": "egress",
                "status": "supported",
                "capabilities": ["start", "stop"],
            },
            {
                "name": "webhooks",
                "status": "supported",
                "capabilities": [
                    "room_finished",
                    "participant_joined",
                    "participant_left",
                ],
            },
            {
                "name": "fault_injection",
                "status": "supported",
                "capabilities": ["error", "delay", "drop"],
            },
        ]
    })


@twin_plane_bp.route("/settings", methods=["GET"])
def settings():
    """Return twin configuration."""
    return jsonify({
        "twin": "livekit",
        "version": "0.2.0",
        "base_url": g.base_url,
        "upstream_url": g.upstream_url,
        "api_key": g.livekit_api_key,
    })


@twin_plane_bp.route("/references", methods=["GET"])
def references():
    """Return the authoritative sources used to build this twin."""
    return jsonify({
        "references": [
            {
                "title": "LiveKit Server APIs (RoomService, Egress)",
                "url": "https://docs.livekit.io/home/server/api-reference/",
                "retrieved": "2026-04-07",
            },
            {
                "title": "LiveKit Webhooks",
                "url": "https://docs.livekit.io/home/server/webhooks/",
                "retrieved": "2026-04-07",
            },
            {
                "title": "LiveKit Server SDK (Go)",
                "url": "https://github.com/livekit/livekit",
                "retrieved": "2026-04-07",
            },
        ],
    })


# -- Tenant bootstrap (unauthenticated — secret shown once) --


@twin_plane_bp.route("/tenants", methods=["POST"])
def create_tenant():
    """Create a new tenant. Returns tenant_id and secret exactly once."""
    friendly_name = request.json.get("friendly_name", "") if request.is_json else ""

    tenant_id = generate_tenant_id()
    if g.get("is_cloud"):
        # UUIDv4 cannot collide with the reserved "default" id, but guard
        # defensively per PRINCIPLES.md §7.
        reject_default_in_cloud(tenant_id)
    tenant_secret = generate_tenant_secret()
    tenant = g.tenants.create_tenant(
        tenant_id=tenant_id,
        secret_hash=hash_secret(tenant_secret),
        friendly_name=friendly_name,
    )

    g.storage.append_log({
        "timestamp": now_iso(),
        "tenant_id": tenant_id,
        "operation": "twin.tenant.create",
        "target": tenant_id,
        "request_summary": f"friendly_name={friendly_name!r}",
        "response_status": 201,
        "fault_applied": None,
        "duration_ms": 0,
    })

    resp = jsonify({
        "tenant_id": tenant_id,
        "tenant_secret": tenant_secret,
        "friendly_name": tenant["friendly_name"],
        "created_at": tenant["created_at"],
    })
    resp.status_code = 201
    return resp


# -- Account management (contract compliance, single dev account) --


@twin_plane_bp.route("/accounts", methods=["POST"])
@require_tenant
def create_account():
    """Create account — returns the single dev account (LiveKit is single-tenant)."""
    return jsonify({
        "sid": "dev",
        "api_key": g.livekit_api_key,
        "friendly_name": "LiveKit Dev Account",
        "status": "active",
    }), 201


@twin_plane_bp.route("/accounts", methods=["GET"])
@require_tenant_or_admin
def list_accounts():
    """List accounts — returns the single dev account."""
    return jsonify({
        "accounts": [{
            "sid": "dev",
            "api_key": g.livekit_api_key,
            "friendly_name": "LiveKit Dev Account",
            "status": "active",
        }]
    })


# -- State Inspection --


@twin_plane_bp.route("/rooms", methods=["GET"])
def list_rooms():
    """List rooms tracked by the twin."""
    rooms = g.storage.list_rooms()
    return jsonify({"rooms": [room_to_json(r) for r in rooms]})


@twin_plane_bp.route("/rooms/<name>", methods=["GET"])
def get_room(name):
    """Get a room by name, including participants."""
    room = g.storage.get_room(name)
    if not room:
        return jsonify({"error": f"room '{name}' not found"}), 404

    result = room_to_json(room)
    participants = g.storage.list_participants(name)
    result["participants"] = [participant_to_json(p) for p in participants]
    return jsonify(result)


@twin_plane_bp.route("/rooms/<name>/participants", methods=["GET"])
def list_room_participants(name):
    """List participants in a room."""
    participants = g.storage.list_participants(name)
    return jsonify({"participants": [participant_to_json(p) for p in participants]})


@twin_plane_bp.route("/egresses", methods=["GET"])
def list_egresses():
    """List egresses, optionally filtered by room."""
    room_name = request.args.get("room_name")
    egresses = g.storage.list_egresses(room_name=room_name)
    return jsonify({"egresses": [egress_to_json(e) for e in egresses]})


@twin_plane_bp.route("/egresses/<egress_id>", methods=["GET"])
def get_egress(egress_id):
    """Get an egress by ID."""
    egress = g.storage.get_egress(egress_id)
    if not egress:
        return jsonify({"error": f"egress '{egress_id}' not found"}), 404
    return jsonify(egress_to_json(egress))


# -- Webhook Inspection and Simulation --


@twin_plane_bp.route("/webhooks", methods=["GET"])
def list_webhooks():
    """List recorded webhook events."""
    room_name = request.args.get("room_name")
    event_type = request.args.get("event_type")
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)

    webhooks = g.storage.list_webhooks(
        room_name=room_name,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    return jsonify({"webhooks": [webhook_to_json(w) for w in webhooks]})


@twin_plane_bp.route("/simulate/webhook", methods=["POST"])
@require_tenant_or_admin
def simulate_webhook_endpoint():
    """Simulate a webhook event without waiting for the real server."""
    data = request.get_json(silent=True) or {}
    event_type = data.get("event", "")
    room_name = data.get("room_name", "")
    participant_identity = data.get("participant_identity", "")

    if not event_type or not room_name:
        return jsonify({"error": "event and room_name are required"}), 400

    result = simulate_webhook(event_type, room_name, participant_identity)
    return jsonify(result)


# -- Fault Injection --


@twin_plane_bp.route("/faults", methods=["POST"])
@require_tenant_or_admin
def create_fault():
    """Create a fault injection rule."""
    data = request.get_json(silent=True) or {}
    target = data.get("target", "")
    action = data.get("action", "")
    config = data.get("config", {})

    if not target or not action:
        return jsonify({"error": "target and action are required"}), 400

    valid_actions = {"error", "delay", "drop"}
    if action not in valid_actions:
        return jsonify({"error": f"action must be one of: {', '.join(valid_actions)}"}), 400

    fault_id = generate_fault_id()
    fault = g.storage.set_fault({
        "id": fault_id,
        "target": target,
        "action": action,
        "config": config,
    })

    g.storage.append_log({
        "timestamp": now_iso(),
        "tenant_id": _scope_tenant_id(),
        "operation": "twin.fault.create",
        "target": target,
        "request_summary": f"action={action}",
        "response_status": 201,
        "fault_applied": None,
        "duration_ms": 0,
    })

    return jsonify({"fault": fault_to_json(fault)}), 201


@twin_plane_bp.route("/faults", methods=["GET"])
def list_faults():
    """List all fault injection rules."""
    faults = g.storage.list_faults()
    return jsonify({"faults": [fault_to_json(f) for f in faults]})


@twin_plane_bp.route("/faults/<fault_id>", methods=["DELETE"])
@require_tenant_or_admin
def delete_fault(fault_id):
    """Delete a fault injection rule."""
    deleted = g.storage.delete_fault(fault_id)
    if not deleted:
        return jsonify({"error": f"fault '{fault_id}' not found"}), 404
    return "", 204


@twin_plane_bp.route("/faults", methods=["DELETE"])
@require_tenant_or_admin
def clear_faults():
    """Clear all fault injection rules (convenience for test teardown)."""
    g.storage.clear_faults()
    return "", 204


# -- Logs --


@twin_plane_bp.route("/logs", methods=["GET"])
@require_tenant_or_admin
def list_logs():
    """List operation logs. Admin sees all; tenant sees own."""
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)
    tenant_id = None if g.is_admin else g.tenant_id
    logs = g.storage.list_logs(limit=limit, offset=offset, tenant_id=tenant_id)
    return jsonify({"logs": [log_to_json(entry) for entry in logs], "limit": limit, "offset": offset})


# -- Reset --


@twin_plane_bp.route("/reset", methods=["POST"])
@require_tenant_or_admin
def reset():
    """Clear all twin state and restart livekit-server."""
    g.storage.clear_all()

    process_mgr = g.get("process_manager")
    if process_mgr:
        process_mgr.restart()

    g.storage.append_log({
        "timestamp": now_iso(),
        "tenant_id": _scope_tenant_id(),
        "operation": "twin.reset",
        "target": "all",
        "request_summary": "full reset",
        "response_status": 204,
        "fault_applied": None,
        "duration_ms": 0,
    })

    return "", 204
