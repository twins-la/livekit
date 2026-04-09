"""Explainer page for the LiveKit proxy twin.

Serves an HTML page at / and agent instructions at /_twin/agent-instructions.
Uses LiveKit teal (#12b5b0) for branding, following the same pattern as
the Twilio twin's red (#e11d48).
"""

from flask import Blueprint, Response

AGENT_INSTRUCTIONS = """\
# LiveKit Proxy Twin — livekit.twins.la

A proxy twin that wraps a real livekit-server, intercepting all HTTP/gRPC
and WebSocket traffic for observability, fault injection, and test control.
Code written against this twin works identically to a bare livekit-server
with only hostname changes.

## How It Works

The twin sits between your application and livekit-server:
- HTTP/gRPC (Twirp) requests are proxied with logging and optional fault injection
- WebSocket connections (/rtc) are proxied bidirectionally with connection-level logging
- Webhooks from livekit-server are intercepted, logged, and forwarded to your app

## Authentication

LiveKit API key and secret (dev mode defaults: devkey / secret).
Server-to-server calls use HTTP Basic Auth (key:secret).

## Twin Plane — /_twin/*

Management API for test control:

### Health & Info
- GET /_twin/health — status, upstream connectivity
- GET /_twin/scenarios — supported test scenarios
- GET /_twin/settings — current configuration

### State Inspection
- GET /_twin/rooms — list rooms tracked by the twin
- GET /_twin/rooms/{name} — room details with participants
- GET /_twin/egresses — list egress recordings
- GET /_twin/webhooks — list recorded webhook events

### Fault Injection
- POST /_twin/faults — inject errors, delays, or drops
- GET /_twin/faults — list active faults
- DELETE /_twin/faults/{id} — remove a fault
- DELETE /_twin/faults — clear all faults

### Simulation
- POST /_twin/simulate/webhook — fire a webhook without waiting for livekit-server

### Lifecycle
- POST /_twin/reset — clear all state, restart livekit-server

## Proxied LiveKit APIs

All standard LiveKit Twirp endpoints are proxied:
- POST /twirp/livekit.RoomService/CreateRoom
- POST /twirp/livekit.RoomService/ListRooms
- POST /twirp/livekit.RoomService/DeleteRoom
- POST /twirp/livekit.RoomService/ListParticipants
- POST /twirp/livekit.Egress/StartRoomCompositeEgress
- POST /twirp/livekit.Egress/StopEgress
- WebSocket /rtc (signaling — binary passthrough)

## Quick Start

```bash
# Set the livekit-server binary path
export LIVEKIT_BIN=/path/to/livekit-server

# Start the twin (starts livekit-server internally)
python -m twins_livekit_local

# Your app connects to port 7880 instead of livekit-server directly
# All requests are proxied with full observability
```
"""

EXPLAINER_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>livekit.twins.la — LiveKit Proxy Twin</title>
    <link rel="icon" type="image/png" href="/twins.png">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #374151;
            background: #f8f8f8;
        }
        main {
            max-width: 700px;
            margin: 0 auto;
            padding: 3rem 1.5rem;
        }
        .hero {
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 0.5rem;
        }
        .hero img {
            width: 72px;
            height: 72px;
            border-radius: 14px;
        }
        h1 {
            font-size: 2rem;
            font-weight: 700;
            color: #1a2e4a;
        }
        h1 .livekit { color: #12b5b0; }
        .tagline {
            color: #6b7280;
            font-size: 1.1rem;
            margin-bottom: 2rem;
        }
        h2 {
            font-size: 1.25rem;
            font-weight: 600;
            color: #1a2e4a;
            margin-top: 2rem;
            margin-bottom: 0.75rem;
        }
        p { margin-bottom: 1rem; }
        ul {
            margin-bottom: 1rem;
            padding-left: 0;
            list-style: none;
        }
        ul li {
            padding-left: 1.25rem;
            position: relative;
            margin-bottom: 0.4rem;
        }
        ul li::before {
            content: "\\2192";
            position: absolute;
            left: 0;
            color: #12b5b0;
            font-weight: bold;
        }
        a { color: #12b5b0; text-decoration: none; }
        a:hover { color: #0e948f; }
        code {
            background: #f3f4f6;
            padding: 0.15rem 0.4rem;
            border-radius: 3px;
            font-size: 0.9rem;
        }
        pre {
            background: #1a2e4a;
            color: #e5e7eb;
            padding: 1rem;
            border-radius: 6px;
            overflow-x: auto;
            font-size: 0.85rem;
            line-height: 1.5;
            margin-bottom: 1rem;
        }
        .snippet-box {
            position: relative;
            margin-top: 2rem;
        }
        .snippet-box pre {
            max-height: 400px;
            overflow-y: auto;
        }
        .copy-btn {
            position: absolute;
            top: 0.5rem;
            right: 0.5rem;
            background: #12b5b0;
            color: white;
            border: none;
            padding: 0.3rem 0.8rem;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.8rem;
        }
        .copy-btn:hover { background: #0e948f; }
        .diagram {
            background: #1a2e4a;
            color: #e5e7eb;
            padding: 1rem;
            border-radius: 6px;
            font-family: monospace;
            font-size: 0.8rem;
            line-height: 1.4;
            margin-bottom: 1rem;
            overflow-x: auto;
            white-space: pre;
        }
        footer {
            margin-top: 3rem;
            padding-top: 1.5rem;
            border-top: 1px solid #e5e7eb;
            color: #9ca3af;
            font-size: 0.85rem;
        }
        footer a { color: #12b5b0; }
    </style>
</head>
<body>
    <main>
        <div class="hero">
            <img src="/twins.png" alt="twins.la logo">
            <h1><span class="livekit">livekit</span>.twins.la</h1>
        </div>
        <p class="tagline">A proxy twin of the LiveKit real-time communication server.</p>

        <h2>What is this?</h2>
        <p>This twin sits between your application and a real
        <code>livekit-server</code>, proxying all traffic while adding
        observability, fault injection, and test control. Your app connects
        here instead of directly to LiveKit.</p>

        <div class="diagram">Client (app / E2E test)
  |
  v
Twin Proxy (this server)
  |-- HTTP/gRPC  --> intercept, log, fault --> livekit-server
  |-- WebSocket  --> passthrough + logging  --> livekit-server
  \\-- /_twin/*   --> management plane (not proxied)</div>

        <h2>What can it do?</h2>
        <ul>
            <li>Proxy all LiveKit Twirp RPC calls with full request/response logging</li>
            <li>Relay WebSocket signaling with connection-level event tracking</li>
            <li>Intercept and forward webhooks with optional delay or drop</li>
            <li>Inject faults: return errors, add latency, drop webhooks</li>
            <li>Simulate webhook events without waiting for the real server</li>
            <li>Inspect twin state: rooms, participants, egresses, webhook history</li>
            <li>Reset everything between test runs with a single API call</li>
        </ul>

        <h2>Quick start</h2>
<pre>
# Start the twin (manages livekit-server internally)
export LIVEKIT_BIN=/path/to/livekit-server
python -m twins_livekit_local

# Your app uses port 7880 — all calls are proxied
# Inject a fault:
curl -X POST http://localhost:7880/_twin/faults \\
  -H "Content-Type: application/json" \\
  -d '{"target":"CreateRoom","action":"error","config":{"status_code":500}}'

# Simulate a webhook:
curl -X POST http://localhost:7880/_twin/simulate/webhook \\
  -H "Content-Type: application/json" \\
  -d '{"event":"room_finished","room_name":"test-room"}'

# Check the logs:
curl http://localhost:7880/_twin/logs
</pre>

        <h2>Agent instructions</h2>
        <p>Copy the block below into your AI agent's context to teach it how to
        interact with this twin.</p>

        <div class="snippet-box">
            <button class="copy-btn" onclick="navigator.clipboard.writeText(document.getElementById('agent-snippet').textContent)">Copy</button>
            <pre id="agent-snippet">""" + AGENT_INSTRUCTIONS + """</pre>
        </div>

        <footer>
            <p>Part of <a href="https://twins.la">twins.la</a> <span style="color: #12b5b0;">&#8226;</span> Open source under MIT</p>
        </footer>
    </main>
</body>
</html>
"""

explainer_bp = Blueprint("explainer", __name__)


@explainer_bp.route("/", methods=["GET"])
def explainer_page():
    """Serve the HTML explainer page."""
    return EXPLAINER_HTML


@explainer_bp.route("/_twin/agent-instructions", methods=["GET"])
def agent_instructions():
    """Serve agent instructions as plain text."""
    return Response(AGENT_INSTRUCTIONS, mimetype="text/plain")
