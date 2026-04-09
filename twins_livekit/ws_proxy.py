"""WebSocket proxy for LiveKit signaling (/rtc).

Bidirectional passthrough with connection-level logging.
No protobuf message parsing — binary frames are relayed as-is.
"""

import logging
import threading
import time

import websocket as ws_client
from flask import g

from .models import now_iso

logger = logging.getLogger(__name__)


def _redact_url(url: str) -> str:
    """Redact access_token query parameter from URL."""
    import re
    return re.sub(r'access_token=[^&]+', 'access_token=REDACTED', url)


def proxy_websocket(ws, upstream_url: str, storage):
    """Proxy a WebSocket connection to the upstream livekit-server.

    Args:
        ws: The client-side flask-sock WebSocket.
        upstream_url: The upstream WebSocket URL (e.g., ws://localhost:7881/rtc?...).
        storage: LiveKitStorage instance for logging.
    """
    # Check fault rules for ws:connect
    faults = storage.list_faults()
    for f in faults:
        if f["target"] == "ws:connect" and f["action"] == "error":
            storage.append_log({
                "timestamp": now_iso(),
                "operation": "ws:connect",
                "target": "/rtc",
                "request_summary": "rejected by fault rule",
                "response_status": 503,
                "fault_applied": f["id"],
                "duration_ms": 0,
            })
            ws.close(1013, "Service unavailable (fault injected)")
            return

    connect_time = time.time()
    upstream = None
    upstream_closed = threading.Event()
    client_closed = threading.Event()

    storage.append_log({
        "timestamp": now_iso(),
        "operation": "ws:connect",
        "target": "/rtc",
        "request_summary": f"upstream={_redact_url(upstream_url)}",
        "response_status": 101,
        "fault_applied": None,
        "duration_ms": 0,
    })

    try:
        upstream = ws_client.WebSocket()
        upstream.connect(upstream_url, timeout=10)
    except Exception as e:
        logger.error("Failed to connect to upstream WebSocket: %s", e)
        storage.append_log({
            "timestamp": now_iso(),
            "operation": "ws:error",
            "target": "/rtc",
            "request_summary": f"upstream connect failed: {e}",
            "response_status": 502,
            "fault_applied": None,
            "duration_ms": int((time.time() - connect_time) * 1000),
        })
        ws.close(1014, "Upstream unavailable")
        return

    def relay_upstream_to_client():
        """Read from upstream, write to client."""
        try:
            while not client_closed.is_set():
                try:
                    opcode, data = upstream.recv_data(control_frame=True)
                except ws_client.WebSocketConnectionClosedException:
                    break
                except Exception:
                    break

                if opcode == 8:  # Close frame
                    break

                try:
                    ws.send(data)
                except Exception:
                    break
        finally:
            upstream_closed.set()

    # Start upstream-to-client relay in a thread
    relay_thread = threading.Thread(target=relay_upstream_to_client, daemon=True)
    relay_thread.start()

    # Main thread: client-to-upstream relay
    try:
        while not upstream_closed.is_set():
            try:
                data = ws.receive(timeout=1)
            except Exception:
                break

            if data is None:
                break

            try:
                if isinstance(data, str):
                    upstream.send(data)
                else:
                    upstream.send_binary(data)
            except Exception:
                break
    finally:
        client_closed.set()

    # Cleanup
    duration_ms = int((time.time() - connect_time) * 1000)
    try:
        upstream.close()
    except Exception:
        pass

    storage.append_log({
        "timestamp": now_iso(),
        "operation": "ws:disconnect",
        "target": "/rtc",
        "request_summary": f"duration={duration_ms}ms",
        "response_status": None,
        "fault_applied": None,
        "duration_ms": duration_ms,
    })

    logger.info("WebSocket proxy session ended after %dms", duration_ms)
