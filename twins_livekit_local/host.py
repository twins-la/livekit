"""Local host entry point for the LiveKit proxy twin.

WSGI entry point for gunicorn:
    gunicorn 'twins_livekit_local.host:create_local_app()'
"""

import atexit
import logging
import os

from twins_livekit.app import create_app
from twins_local.tenants import SQLiteTenantStore, ensure_default_tenant

from .config import (
    ADMIN_TOKEN,
    APP_WEBHOOK_URL,
    BASE_URL,
    DB_PATH,
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_BIN,
    LIVEKIT_UPSTREAM_PORT,
)
from .process import LiveKitProcess
from .storage_sqlite import SQLiteStorage

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

_process_manager: LiveKitProcess | None = None


def create_local_app():
    """Create the locally-hosted LiveKit twin application."""
    global _process_manager

    # Ensure data directory exists
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    storage = SQLiteStorage(db_path=DB_PATH)

    tenants = SQLiteTenantStore()  # defaults to ~/.twins/tenants.sqlite3
    ensure_default_tenant(tenants)

    # Start livekit-server if binary path is set
    twin_port = int(os.environ.get("TWIN_PORT", "7880"))
    webhook_sink_url = f"http://127.0.0.1:{twin_port}/_twin/webhook-sink"

    if LIVEKIT_BIN:
        _process_manager = LiveKitProcess(
            binary_path=LIVEKIT_BIN,
            port=LIVEKIT_UPSTREAM_PORT,
            webhook_url=webhook_sink_url,
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        )
        _process_manager.start()
        atexit.register(_process_manager.stop)
    else:
        logger.warning(
            "LIVEKIT_BIN not set — proxy will forward to port %d but won't manage the process",
            LIVEKIT_UPSTREAM_PORT,
        )

    app = create_app(
        storage=storage,
        tenants=tenants,
        config={
            "base_url": BASE_URL,
            "upstream_url": f"http://127.0.0.1:{LIVEKIT_UPSTREAM_PORT}",
            "livekit_api_key": LIVEKIT_API_KEY,
            "livekit_api_secret": LIVEKIT_API_SECRET,
            "app_webhook_url": APP_WEBHOOK_URL,
            "admin_token": ADMIN_TOKEN,
            "process_manager": _process_manager,
            "is_cloud": False,
        },
    )

    logger.info(
        "LiveKit twin ready — db=%s upstream=:%d base_url=%s",
        DB_PATH,
        LIVEKIT_UPSTREAM_PORT,
        BASE_URL,
    )

    return app


def main():
    from .config import HOST, PORT

    app = create_local_app()
    logger.info("Starting LiveKit twin on %s:%d", HOST, PORT)
    app.run(host=HOST, port=PORT, debug=False)
