# LiveKit Twin

A proxy twin that wraps [livekit-server](https://github.com/livekit/livekit) for [twins.la](https://twins.la).

## What This Is

A Python package that proxies LiveKit's HTTP/gRPC and WebSocket APIs through an instrumentation layer. This is a **proxy twin**: it runs a real `livekit-server --dev` process and intercepts all traffic to add observability, fault injection, and test control.

Existing LiveKit SDK code can be pointed at this twin with no changes. The twin forwards requests to the real server, logs everything, and lets you inject faults and simulate events through the Twin Plane.

## Why a Proxy?

LiveKit's WebRTC signaling protocol is proprietary protobuf over WebSocket — impractical to reimplement. But the control plane APIs (rooms, participants, egress) are small and well-defined. Proxying gives you full API fidelity (it's the real server) with the observability and test control of a twin.

```
Client (app / E2E test)
  |
  v
Twin (port 7880)
  |-- HTTP/gRPC  ->  intercept, log, optionally fault  ->  livekit-server (port 7881)
  |-- WebSocket  ->  passthrough with logging            ->  livekit-server (port 7881)
  |-- /_twin/*   ->  management plane (not proxied)
```

## Supported Scenarios

- **Rooms** — Create, list, and delete rooms via the RoomService Twirp API
- **Participants** — List participants in a room
- **Egress** — Start and stop room composite egress
- **WebSocket signaling** — Transparent passthrough with connection-level logging
- **Webhooks** — Intercept, log, and forward server webhooks; simulate webhook events
- **Fault injection** — Inject errors, delays, and drops on any proxied API or webhook

## Usage

This package is not run directly. It is loaded by a host:

- **Local**: `twins-livekit-local` (sibling package under `twins_livekit_local/`) — run locally via gunicorn or `python -m twins_livekit_local`
- **Cloud**: not deployed yet

The twin requires a `livekit-server` binary on the host. In dev mode it manages the server process automatically.

### Quick Start

```bash
pip install -e . ./twins_livekit_local/
python -m twins_livekit_local
```

Then use the LiveKit SDK as normal:

```python
from livekit.api import LiveKitAPI

api = LiveKitAPI(
    url="http://localhost:7880",
    api_key="devkey",
    api_secret="secret",
)

# Create a room
room = api.room.create_room(name="my-room")

# Check twin logs
import requests
logs = requests.get("http://localhost:7880/_twin/logs").json()
```

## Twin Plane

Every twin exposes a management API at `/_twin/`. In addition to the standard endpoints (health, scenarios, settings, logs), the LiveKit twin adds:

- **State inspection** — `GET /_twin/rooms`, `/_twin/egresses`
- **Webhook simulation** — `POST /_twin/simulate/webhook` to trigger events without waiting for timeouts
- **Fault injection** — `POST /_twin/faults` to inject errors, delays, or drops on any API
- **Reset** — `POST /_twin/reset` to clear all state and restart livekit-server

## Configuration

```
TWIN_PORT=7880                  # Twin listens here
TWIN_BASE_URL=http://localhost:7880
TWIN_DB_PATH=data/livekit_twin.db

LIVEKIT_BIN=livekit-server      # Path to binary
LIVEKIT_UPSTREAM_PORT=7881      # Port for the real server
LIVEKIT_API_KEY=devkey          # Dev mode credentials
LIVEKIT_API_SECRET=secret

LIVEKIT_APP_WEBHOOK_URL=http://localhost:8000/api/livekit/webhook
```
