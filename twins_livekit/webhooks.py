"""Webhook sink, forwarding, and simulation.

Receives webhooks from the real livekit-server, logs them,
optionally applies fault rules, and forwards to the app.
"""

import json
import logging
import time

import jwt
import requests
from flask import Blueprint, Response, g, jsonify, request

from .ids import generate_webhook_id
from .models import now_iso, now_unix_nano

logger = logging.getLogger(__name__)

webhook_bp = Blueprint("webhooks", __name__)


def _verify_livekit_webhook(body: bytes, auth_header: str, api_secret: str) -> dict | None:
    """Verify and decode a LiveKit webhook payload.

    LiveKit webhooks use JWT in the Authorization header, signed with the API secret.
    Returns parsed event dict or None if verification fails.
    """
    try:
        # Try using livekit SDK's WebhookReceiver
        from livekit.api import WebhookReceiver

        receiver = WebhookReceiver(
            api_key=g.livekit_api_key,
            api_secret=api_secret,
        )
        event = receiver.receive(body.decode("utf-8"), auth_header)
        # Convert to dict
        return {
            "event": event.event if hasattr(event, "event") else str(event),
            "room": _room_to_dict(event.room) if hasattr(event, "room") and event.room else {},
            "participant": _participant_to_dict(event.participant)
            if hasattr(event, "participant") and event.participant
            else {},
        }
    except Exception as e:
        logger.warning("Webhook verification failed: %s", e)
        return None


def _room_to_dict(room) -> dict:
    """Convert a LiveKit Room proto to dict."""
    return {
        "name": getattr(room, "name", ""),
        "sid": getattr(room, "sid", ""),
    }


def _participant_to_dict(participant) -> dict:
    """Convert a LiveKit ParticipantInfo proto to dict."""
    return {
        "identity": getattr(participant, "identity", ""),
        "sid": getattr(participant, "sid", ""),
    }


def _check_webhook_fault(event_type: str):
    """Check for a fault rule targeting this webhook event type."""
    target = f"webhook:{event_type}"
    faults = g.storage.list_faults()
    for f in faults:
        if f["target"] == target:
            return f
    return None


def _forward_webhook(body: bytes, headers: dict, app_webhook_url: str) -> bool:
    """Forward a webhook to the app's webhook endpoint.

    Re-signs with the same credentials so the app can verify.
    Returns True if delivery succeeded.
    """
    if not app_webhook_url:
        return False

    try:
        resp = requests.post(
            app_webhook_url,
            data=body,
            headers={k: v for k, v in headers.items() if k.lower() != "host"},
            timeout=10,
        )
        return 200 <= resp.status_code < 300
    except Exception as e:
        logger.error("Failed to forward webhook: %s", e)
        return False


@webhook_bp.route("/_twin/webhook-sink", methods=["POST"])
def webhook_sink():
    """Receive webhooks from the real livekit-server."""
    body = request.get_data()
    auth_header = request.headers.get("Authorization", "")

    event_data = _verify_livekit_webhook(body, auth_header, g.livekit_api_secret)
    if event_data is None:
        return jsonify({"error": "invalid webhook signature"}), 403

    event_type = event_data.get("event", "unknown")
    room_info = event_data.get("room", {})
    participant_info = event_data.get("participant", {})

    room_name = room_info.get("name", "")
    participant_identity = participant_info.get("identity", "")

    # Record in storage
    webhook_record = g.storage.record_webhook({
        "id": generate_webhook_id(),
        "event_type": event_type,
        "room_name": room_name,
        "participant_identity": participant_identity,
        "timestamp": now_iso(),
        "payload": json.dumps(event_data),
        "forwarded": False,
    })

    # Update twin state
    _update_state_from_webhook(event_type, room_name, participant_identity, event_data)

    # Check fault rules
    fault = _check_webhook_fault(event_type)
    fault_applied = fault["id"] if fault else None

    if fault:
        if fault["action"] == "drop":
            g.storage.append_log({
                "timestamp": now_iso(),
                "operation": f"webhook:{event_type}",
                "target": "webhook-sink",
                "request_summary": f"room={room_name} participant={participant_identity}",
                "response_status": 200,
                "fault_applied": fault_applied,
                "duration_ms": 0,
            })
            return jsonify({"ok": True, "forwarded": False, "fault": "dropped"})

        if fault["action"] == "delay":
            delay_ms = min(fault.get("config", {}).get("delay_ms", 1000), 30000)
            time.sleep(delay_ms / 1000.0)

    # Forward to app
    app_webhook_url = g.app_webhook_url
    forwarded = _forward_webhook(
        body,
        dict(request.headers),
        app_webhook_url,
    )

    g.storage.append_log({
        "timestamp": now_iso(),
        "operation": f"webhook:{event_type}",
        "target": "webhook-sink",
        "request_summary": f"room={room_name} participant={participant_identity}",
        "response_status": 200,
        "fault_applied": fault_applied,
        "duration_ms": 0,
    })

    return jsonify({"ok": True, "forwarded": forwarded})


def _update_state_from_webhook(event_type: str, room_name: str, identity: str, event_data: dict):
    """Update twin state based on a webhook event."""
    if event_type == "participant_joined" and room_name and identity:
        participant = event_data.get("participant", {})
        g.storage.add_participant(room_name, {
            "identity": identity,
            "sid": participant.get("sid", ""),
            "joined_at": now_unix_nano(),
            "state": "ACTIVE",
        })

    elif event_type == "participant_left" and room_name and identity:
        g.storage.remove_participant(room_name, identity)

    elif event_type == "room_finished" and room_name:
        g.storage.delete_room(room_name)


def simulate_webhook(event_type: str, room_name: str, participant_identity: str = "") -> dict:
    """Construct and deliver a simulated webhook event.

    Returns dict with webhook record and delivery status.
    """
    event_data = {
        "event": event_type,
        "room": {"name": room_name, "sid": ""},
        "participant": {"identity": participant_identity, "sid": ""},
        "created_at": now_unix_nano(),
    }

    payload = json.dumps(event_data)

    # Record in storage
    webhook_record = g.storage.record_webhook({
        "id": generate_webhook_id(),
        "event_type": event_type,
        "room_name": room_name,
        "participant_identity": participant_identity,
        "timestamp": now_iso(),
        "payload": payload,
        "forwarded": False,
    })

    # Update twin state
    _update_state_from_webhook(event_type, room_name, participant_identity, event_data)

    # Deliver to app
    app_webhook_url = g.app_webhook_url
    delivered = False
    if app_webhook_url:
        try:
            # Sign the webhook using JWT (same format livekit-server uses)
            token = jwt.encode(
                {
                    "iss": g.livekit_api_key,
                    "sub": g.livekit_api_key,
                    "iat": int(time.time()),
                    "exp": int(time.time()) + 60,
                    "sha256": __import__("hashlib").sha256(payload.encode()).hexdigest(),
                },
                g.livekit_api_secret,
                algorithm="HS256",
            )

            resp = requests.post(
                app_webhook_url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                timeout=10,
            )
            delivered = 200 <= resp.status_code < 300
        except Exception as e:
            logger.error("Failed to deliver simulated webhook: %s", e)

    g.storage.append_log({
        "timestamp": now_iso(),
        "operation": f"simulate:webhook:{event_type}",
        "target": "simulate",
        "request_summary": f"room={room_name} participant={participant_identity}",
        "response_status": 200 if delivered else 502,
        "fault_applied": None,
        "duration_ms": 0,
    })

    return {
        "webhook": {
            "event_type": event_type,
            "room_name": room_name,
            "participant_identity": participant_identity,
        },
        "delivered": delivered,
    }
