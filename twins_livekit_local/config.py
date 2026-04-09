"""Environment-based configuration for the local LiveKit twin host."""

import os

# Twin server
HOST = os.environ.get("TWIN_HOST", "0.0.0.0")
PORT = int(os.environ.get("TWIN_PORT", "7880"))
BASE_URL = os.environ.get("TWIN_BASE_URL", f"http://localhost:{PORT}")

# Storage
DB_PATH = os.environ.get("TWIN_DB_PATH", "data/livekit_twin.db")

# Upstream livekit-server
LIVEKIT_BIN = os.environ.get("LIVEKIT_BIN", "")
LIVEKIT_UPSTREAM_PORT = int(os.environ.get("LIVEKIT_UPSTREAM_PORT", "7881"))
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")

# Webhook forwarding
APP_WEBHOOK_URL = os.environ.get(
    "LIVEKIT_APP_WEBHOOK_URL", "http://localhost:8000/api/livekit/webhook"
)

# Admin — Bearer token for twin plane admin operations
# If unset, admin endpoints are unrestricted (local dev convenience)
ADMIN_TOKEN = os.environ.get("TWIN_ADMIN_TOKEN", "")
