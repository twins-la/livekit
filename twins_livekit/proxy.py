"""HTTP/gRPC reverse proxy to real livekit-server.

Intercepts Twirp endpoints for logging and fault injection,
forwards everything else transparently.
"""

import json
import logging
import time

import requests
from flask import Blueprint, Response, g, request

from twins_local.logs import ANONYMOUS_TENANT_ID

from .errors import internal_error, twirp_error, unavailable
from .ids import generate_egress_id, generate_room_sid
from .logs import emit
from .models import now_iso, now_unix_nano

logger = logging.getLogger(__name__)

proxy_bp = Blueprint("proxy", __name__)

# Twirp endpoints the twin intercepts
INTERCEPTED_ROUTES = {
    "/twirp/livekit.RoomService/CreateRoom": "CreateRoom",
    "/twirp/livekit.RoomService/ListRooms": "ListRooms",
    "/twirp/livekit.RoomService/DeleteRoom": "DeleteRoom",
    "/twirp/livekit.RoomService/ListParticipants": "ListParticipants",
    "/twirp/livekit.Egress/StartRoomCompositeEgress": "StartRoomCompositeEgress",
    "/twirp/livekit.Egress/StopEgress": "StopEgress",
}


def _check_fault(target: str):
    """Check if a fault rule exists for the given target. Returns fault dict or None."""
    faults = g.storage.list_faults()
    for f in faults:
        if f["target"] == target:
            return f
    return None


def _apply_fault(fault: dict):
    """Apply a fault rule and return the error response, or None if delay-only."""
    action = fault["action"]
    config = fault.get("config", {})

    if action == "error":
        status_code = config.get("status_code", 500)
        message = config.get("message", "injected fault")
        # Map HTTP status to Twirp code
        code_map = {400: "invalid_argument", 404: "not_found", 500: "internal", 503: "unavailable"}
        twirp_code = code_map.get(status_code, "internal")
        return twirp_error(twirp_code, message, status_code)

    if action == "delay":
        delay_ms = min(config.get("delay_ms", 1000), 30000)  # Cap at 30s
        time.sleep(delay_ms / 1000.0)
        return None  # Continue after delay

    return None


def _forward_to_upstream(path: str):
    """Forward the current request to the upstream livekit-server."""
    upstream_url = g.upstream_url.rstrip("/") + path

    # Preserve query string
    if request.query_string:
        upstream_url += "?" + request.query_string.decode()

    # Forward headers, excluding Host
    headers = {k: v for k, v in request.headers if k.lower() != "host"}

    try:
        upstream_resp = requests.request(
            method=request.method,
            url=upstream_url,
            headers=headers,
            data=request.get_data(),
            timeout=30,
        )
    except requests.ConnectionError:
        return unavailable("upstream livekit-server is unreachable")
    except requests.Timeout:
        return unavailable("upstream livekit-server timed out")

    # Build response
    excluded_headers = {"transfer-encoding", "connection", "content-encoding"}
    resp_headers = {
        k: v
        for k, v in upstream_resp.headers.items()
        if k.lower() not in excluded_headers
    }

    return Response(
        upstream_resp.content,
        status=upstream_resp.status_code,
        headers=resp_headers,
    )


def _try_parse_json(data: bytes) -> dict | None:
    """Try to parse request/response body as JSON. Returns None if not JSON."""
    try:
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _handle_intercepted(path: str, operation: str):
    """Handle an intercepted Twirp endpoint."""
    start = time.time()

    # Check fault rules
    fault = _check_fault(operation)
    fault_applied = None
    if fault:
        fault_applied = fault["id"]
        error_resp = _apply_fault(fault)
        if error_resp is not None:
            duration_ms = int((time.time() - start) * 1000)
            emit(
                g.storage,
                tenant_id=ANONYMOUS_TENANT_ID,
                plane="data",
                operation=f"proxy.{operation}",
                outcome="failure",
                reason=f"fault-injected ({fault_applied})",
                details={
                    "target": path,
                    "request_summary": _summarize_request(),
                    "response_status": error_resp.status_code,
                    "fault_applied": fault_applied,
                    "duration_ms": duration_ms,
                },
            )
            return error_resp

    # Log the request
    req_body = _try_parse_json(request.get_data())
    req_summary = _summarize_request(req_body)

    # Forward to upstream
    resp = _forward_to_upstream(path)

    duration_ms = int((time.time() - start) * 1000)

    # Update twin state based on operation
    if isinstance(resp, Response) and 200 <= resp.status_code < 300:
        resp_body = _try_parse_json(resp.get_data())
        _update_state(operation, req_body, resp_body)

    status = resp.status_code if isinstance(resp, Response) else 500
    is_success = 200 <= status < 400
    emit(
        g.storage,
        tenant_id=ANONYMOUS_TENANT_ID,
        plane="data",
        operation=f"proxy.{operation}",
        outcome="success" if is_success else "failure",
        reason=None if is_success else f"upstream returned {status}",
        details={
            "target": path,
            "request_summary": req_summary,
            "response_status": status,
            "fault_applied": fault_applied,
            "duration_ms": duration_ms,
        },
    )

    return resp


def _summarize_request(body: dict | None = None) -> str:
    """Create a human-readable summary of the request."""
    if body is None:
        body = _try_parse_json(request.get_data())
    if body:
        # Extract key fields for summary
        parts = []
        for key in ("name", "room_name", "room", "egress_id", "identity"):
            if key in body:
                parts.append(f"{key}={body[key]}")
        return ", ".join(parts) if parts else json.dumps(body)[:200]
    return ""


def _update_state(operation: str, req_body: dict | None, resp_body: dict | None):
    """Update twin state based on a successful upstream response."""
    if not req_body:
        return

    if operation == "CreateRoom" and resp_body:
        g.storage.create_room({
            "name": resp_body.get("name", req_body.get("name", "")),
            "sid": resp_body.get("sid", generate_room_sid()),
            "max_participants": resp_body.get("max_participants", req_body.get("max_participants", 0)),
            "empty_timeout": resp_body.get("empty_timeout", req_body.get("empty_timeout", 300)),
            "creation_time": resp_body.get("creation_time", now_unix_nano()),
        })

    elif operation == "DeleteRoom":
        room_name = req_body.get("room", "")
        if room_name:
            g.storage.delete_room(room_name)

    elif operation == "StartRoomCompositeEgress" and resp_body:
        g.storage.create_egress({
            "egress_id": resp_body.get("egress_id", generate_egress_id()),
            "room_name": resp_body.get("room_name", req_body.get("room_name", "")),
            "status": resp_body.get("status", "EGRESS_STARTING"),
            "started_at": resp_body.get("started_at", now_unix_nano()),
        })

    elif operation == "StopEgress" and resp_body:
        egress_id = req_body.get("egress_id", "")
        if egress_id:
            g.storage.update_egress(egress_id, {
                "status": resp_body.get("status", "EGRESS_COMPLETE"),
                "stopped_at": now_unix_nano(),
            })


@proxy_bp.route("/twirp/<path:twirp_path>", methods=["POST"])
def handle_twirp(twirp_path):
    """Handle all Twirp RPC calls."""
    path = f"/twirp/{twirp_path}"
    operation = INTERCEPTED_ROUTES.get(path)

    if operation:
        return _handle_intercepted(path, operation)

    # Non-intercepted Twirp endpoint — forward transparently
    return _forward_to_upstream(path)


@proxy_bp.route("/<path:catch_all>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def handle_passthrough(catch_all):
    """Forward non-Twirp, non-twin-plane requests to upstream."""
    path = f"/{catch_all}"

    # Don't proxy twin plane or WebSocket paths
    if path.startswith("/_twin") or path == "/rtc":
        return Response("Not found", status=404)

    return _forward_to_upstream(path)
